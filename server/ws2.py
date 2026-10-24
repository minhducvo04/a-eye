"""Independent v2 socket lifecycle, latest-turn cancellation and streaming speech."""
import asyncio
import base64
import json
import os
from time import monotonic

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


async def scene_loop(session, vision, send):
    """Serial refreshes use only the newest frame; requests never overlap."""
    interval = max(0.001, float(os.environ.get('SCENE_INTERVAL_MS', '1000')) / 1000)
    previous_seq = None
    while True:
        frame = session.frame
        if frame is None or frame['seq'] == previous_seq:
            await asyncio.sleep(0.01)
            continue
        previous_seq = frame['seq']
        started = monotonic()

        async def refresh():
            try:
                scene = await vision.call('scene', dict(image_b64=frame['jpeg_b64'],
                                                       queries=list(session.pack.default_queries)))
                validate('scene_response', scene)
                session.scene = scene
                session.scene_seq = frame['seq']
                session.scene_time = monotonic()
                await send(message('track', seq=frame['seq'], objects=scene['objects']))
                await send(message('metrics', seq=frame['seq'], vlm_ms=(monotonic() - started) * 1000))
            except Exception:
                if not session.vision_error_sent:
                    await send(message('error', code='vision_unavailable', message='Vision is unavailable.'))
                    session.vision_error_sent = True

        session.scene_task = asyncio.create_task(refresh())
        try:
            await session.scene_task
        finally:
            session.scene_task = None
        frame = None
        await asyncio.sleep(max(0, interval - (monotonic() - started)))


@router.websocket('/ws2')
async def websocket(ws: WebSocket):
    await ws.accept()
    session = None
    turn_task = None
    audio_tasks = {}
    scene_loop_task = None
    voice = None
    vision = getattr(ws.app.state, 'vision_v2', None) or SceneClient()
    llm = getattr(ws.app.state, 'llm_v2', None) or LLMClient()
    send_lock = asyncio.Lock()

    async def send(msg):
        validate('server_message_v2', msg)
        async with send_lock:
            await ws.send_json(msg)

    async def speech_audio(msg):
        try:
            pending = None
            async for chunk in voice.say(msg['utterance_id'], msg['text']):
                if pending is not None:
                    yield message('audio', agent=msg['agent'], utterance_id=msg['utterance_id'],
                                  sample_rate=16000, pcm16_b64=base64.b64encode(pending).decode(), final=False)
                pending = chunk
            yield message('audio', agent=msg['agent'], utterance_id=msg['utterance_id'],
                          sample_rate=16000, pcm16_b64=base64.b64encode(pending or b'').decode(), final=True)
        finally:
            voice.stop(msg['utterance_id'])

    async def audio(msg):
        try:
            async for chunk in speech_audio(msg):
                await send(chunk)
        finally:
            audio_tasks.pop(msg['utterance_id'], None)

    async def emit(msg):
        await send(msg)
        if msg['type'] == 'say' and 'turn_id' not in msg and session.speak:
            audio_tasks[msg['utterance_id']] = asyncio.create_task(audio(msg))

    async def cancel_scene():
        nonlocal scene_loop_task
        if scene_loop_task:
            scene_loop_task.cancel()
            await asyncio.gather(scene_loop_task, return_exceptions=True)
            scene_loop_task = None

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
                await cancel_scene()
                session = new_session
                session.emit = emit
                voice = None
                if session.tts == 'server':
                    factory = getattr(ws.app.state, 'voice_factory_v2', adapter.make_adapter)
                    candidate = factory()
                    if not isinstance(candidate, FakeAdapter):
                        voice = candidate
                session.speak = speech_audio if voice else None
                scene_loop_task = asyncio.create_task(scene_loop(session, vision, send))
                await send(state('listening'))
                continue
            if session is None or incoming['session_id'] != session.session_id:
                await send(message('error', code='bad_message', message='Send hello with the matching session first.'))
                continue
            if kind == 'frame':
                if session.frame is None or incoming['seq'] > session.frame['seq']:
                    session.frame = incoming
                    await asyncio.sleep(0)
            elif kind == 'user_text' and incoming['final']:
                await cancel_turn()
                await cancel_audio()
                turn_task = asyncio.create_task(turn(incoming['text']))
            elif kind == 'confirm' and incoming['what'] == 'power_off':
                await cancel_turn()
                await cancel_audio()
                session.power_off = incoming['value']
                if session.power_off:
                    await emit(say('Thanks. What are we working on?'))
            elif kind == 'barge_in':
                await cancel_turn()
                await cancel_audio()
                await send(state('listening'))
    except WebSocketDisconnect:
        pass
    finally:
        await cancel_turn()
        await cancel_audio()
        await cancel_scene()
        if session:
            session.scene = None
            session.frame = None
            session.history.clear()
