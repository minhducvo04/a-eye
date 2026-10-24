"""Independent v2 socket lifecycle, latest-turn cancellation and streaming speech."""
import asyncio
import base64
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx
from jsonschema import ValidationError

from contracts import validate
from server import packs
from server.agent import Session, message, run_turn, say, state
from server.llm import LLMClient
from voice import adapter
from voice.fake import FakeAdapter

router = APIRouter()


class SceneClient:
    def __init__(self, url=None, transport=None):
        self.url = url or os.environ.get('VISION_URL', 'http://127.0.0.1:8001')
        self.transport = transport

    async def call(self, operation, payload):
        validate('scene_request', payload)
        async with httpx.AsyncClient(base_url=self.url, timeout=25, transport=self.transport) as client:
            response = await client.post('/scene', json=payload)
            response.raise_for_status()
            scene = response.json()
        validate('scene_response', scene)
        return scene


@router.websocket('/ws2')
async def websocket(ws: WebSocket):
    await ws.accept()
    session = None
    turn_task = None
    audio_tasks = {}
    voice = None
    vision = getattr(ws.app.state, 'vision_v2', None) or SceneClient()
    llm = getattr(ws.app.state, 'llm_v2', None) or LLMClient()
    send_lock = asyncio.Lock()

    async def send(msg):
        validate('server_message_v2', msg)
        async with send_lock:
            await ws.send_json(msg)

    async def audio(msg):
        try:
            # One-chunk lookahead marks the last PCM chunk without buffering the utterance.
            pending = None
            async for chunk in voice.say(msg['utterance_id'], msg['text']):
                if pending is not None:
                    await send(message('audio', agent=msg['agent'], utterance_id=msg['utterance_id'],
                                       sample_rate=16000, pcm16_b64=base64.b64encode(pending).decode(), final=False))
                pending = chunk
            await send(message('audio', agent=msg['agent'], utterance_id=msg['utterance_id'],
                               sample_rate=16000, pcm16_b64=base64.b64encode(pending or b'').decode(), final=True))
        except Exception:
            await send(message('error', code='internal', message='Speech audio is unavailable.'))
        finally:
            audio_tasks.pop(msg['utterance_id'], None)

    async def emit(msg):
        await send(msg)
        if msg['type'] == 'say' and session.tts == 'server' and voice is not None:
            audio_tasks[msg['utterance_id']] = asyncio.create_task(audio(msg))

    async def cancel_turn():
        nonlocal turn_task
        if turn_task is not None:
            turn_task.cancel()
            await asyncio.gather(turn_task, return_exceptions=True)
            turn_task = None

    async def cancel_audio(utterance=None):
        selected = [(key, task) for key, task in list(audio_tasks.items())
                    if utterance is None or utterance == key]
        for key, task in selected:
            task.cancel()
            if voice is not None:
                voice.stop(key)
        await asyncio.gather(*(task for _, task in selected), return_exceptions=True)

    async def turn(text):
        try:
            await run_turn(session, text, vision=vision, llm=llm)
        except Exception:
            await send(message('error', code='internal', message='The turn could not finish.'))

    try:
        while True:
            try:
                incoming = await ws.receive_json()
                validate('client_message_v2', incoming)
            except (json.JSONDecodeError, ValidationError, KeyError):
                await send(message('error', code='bad_message', message='Invalid client message.'))
                continue
            kind = incoming['type']
            if kind == 'hello':
                try:
                    new_session = Session(incoming['session_id'], packs.get(incoming['pack']),
                                          incoming.get('board_id', 'demo-b650'), incoming.get('tts', 'browser'))
                except (OSError, ValueError, ValidationError, KeyError):
                    await send(message('error', code='bad_message', message='Unknown or invalid board or pack.'))
                    continue
                await cancel_turn()
                await cancel_audio()
                session = new_session
                session.emit = emit
                voice = None
                if session.tts == 'server':
                    factory = getattr(ws.app.state, 'voice_factory_v2', adapter.make_adapter)
                    candidate = factory()
                    if not isinstance(candidate, FakeAdapter):
                        voice = candidate
                await send(state('listening'))
                continue
            if session is None or incoming['session_id'] != session.session_id:
                await send(message('error', code='bad_message', message='Send hello with the matching session first.'))
                continue
            if kind == 'frame':
                if session.frame is None or incoming['seq'] > session.frame['seq']:
                    session.frame = incoming
            elif kind == 'user_text' and incoming['final']:
                await cancel_turn()
                await cancel_audio()
                turn_task = asyncio.create_task(turn(incoming['text']))
            elif kind == 'confirm' and incoming['what'] == 'power_off':
                await cancel_turn()
                session.power_off = incoming['value']
                if session.power_off:
                    await emit(say('Thanks. What are we working on?'))
            elif kind == 'barge_in':
                await cancel_turn()
                await cancel_audio(incoming['utterance_id'])
                await send(state('listening'))
    except WebSocketDisconnect:
        pass
    finally:
        await cancel_turn()
        await cancel_audio()
        if session:
            session.frame = None
            session.history.clear()
