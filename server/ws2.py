"""Independent v2 socket lifecycle, latest-turn cancellation and streaming speech."""
import asyncio
import base64
import json
import os
import io
import re
from contextlib import asynccontextmanager

from PIL import Image
from time import monotonic

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx
from jsonschema import ValidationError

from contracts import validate
from server.box_client import BoxClient
from server import packs
from server.agent import Session, message, run_turn, say, state
from server.llm import LLMClient
from voice import adapter
from voice.fake import FakeAdapter

router = APIRouter()


class GPUGate:
    """One active GPU job; waiting brains precede new scene refreshes."""
    def __init__(self):
        self.condition = asyncio.Condition()
        self.active = False
        self.brains = 0

    @asynccontextmanager
    async def hold(self, brain=False):
        async with self.condition:
            self.brains += int(brain)
            try:
                await self.condition.wait_for(lambda: not self.active and (brain or not self.brains))
                self.active = True
            finally:
                self.brains -= int(brain)
                self.condition.notify_all()
        try:
            yield
        finally:
            async with self.condition:
                self.active = False
                self.condition.notify_all()


def gpu_gate(app):
    if not hasattr(app.state, 'gpu_gate'):
        app.state.gpu_gate = GPUGate()
    return app.state.gpu_gate


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


async def scene_loop(session, vision, send, gate=None):
    """Serial refreshes use only the newest frame; requests never overlap."""
    gate = gate or GPUGate()
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
                                                       queries=list(session.pack.default_queries)[:2]))
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

        async with gate.hold():
            # No scene_task exists while queued: a turn must not await its own gate.
            frame = session.frame
            previous_seq = frame['seq']
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
    active_audio = set()
    stt_mode = 'browser'
    stt_failed = False
    audio_buffer = bytearray()
    stt_task = None
    yolo_task = None
    box = getattr(ws.app.state, 'box_v2', None) or BoxClient()
    gate = gpu_gate(ws.app)
    vision = getattr(ws.app.state, 'vision_v2', None) or SceneClient()
    llm = getattr(ws.app.state, 'llm_v2', None) or LLMClient()
    send_lock = asyncio.Lock()

    async def send(msg):
        validate('server_message_v2', msg)
        async with send_lock:
            await ws.send_json(msg)

    async def speech_audio(msg):
        active_audio.add(msg['utterance_id'])
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
            active_audio.discard(msg['utterance_id'])
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
            async with gate.hold(brain=True):
                await run_turn(session, text, vision=vision, llm=llm)
        except Exception:
            await send(message('error', code='internal', message='The turn could not finish.'))

    async def cancel_stt():
        nonlocal stt_task
        if stt_task:
            stt_task.cancel()
            await asyncio.gather(stt_task, return_exceptions=True)
            stt_task = None

    async def start_text(text):
        nonlocal turn_task
        await cancel_turn()
        await cancel_audio()
        turn_task = asyncio.create_task(turn(text))

    async def transcribe(pcm):
        nonlocal stt_failed, stt_mode
        try:
            text = await box.stt(pcm)
            if text.strip():
                await start_text(text)
        except Exception:
            stt_mode = 'browser'
            if not stt_failed:
                stt_failed = True
                await send(message('error', code='internal',
                                   message='Server speech is unavailable; using the browser.'))

    async def close_voice():
        if voice is not None and hasattr(voice, 'aclose'):
            await voice.aclose()

    async def cancel_yolo():
        nonlocal yolo_task
        if yolo_task:
            yolo_task.cancel()
            await asyncio.gather(yolo_task, return_exceptions=True)
            yolo_task = None

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
                await cancel_stt()
                await cancel_turn()
                await cancel_audio()
                await cancel_scene()
                await cancel_yolo()
                await close_voice()
                audio_buffer.clear()
                stt_mode = incoming.get('stt', 'browser')
                stt_failed = False
                session = new_session
                session.emit = emit
                voice = None
                if session.tts == 'server':
                    factory = getattr(ws.app.state, 'voice_factory_v2', adapter.make_adapter)
                    candidate = await asyncio.to_thread(factory)
                    if not isinstance(candidate, FakeAdapter):
                        voice = candidate
                session.speak = speech_audio if voice else None
                scene_loop_task = asyncio.create_task(scene_loop(session, vision, send, gate))
                if os.environ.get('YOLO_REFRESH') == '1':
                    yolo_task = asyncio.create_task(yolo_loop(session, box, send))
                await send(state('listening'))
                continue
            if session is None or incoming['session_id'] != session.session_id:
                await send(message('error', code='bad_message', message='Send hello with the matching session first.'))
                continue
            if kind == 'frame':
                if session.frame is None or incoming['seq'] > session.frame['seq']:
                    session.frame = incoming
                    await asyncio.sleep(0)
            elif kind == 'audio_in' and stt_mode == 'server':
                if not incoming.get('final', False) and active_audio:
                    await cancel_stt()
                    await cancel_turn()
                    await cancel_audio()
                    await send(state('listening'))
                try:
                    chunk = base64.b64decode(incoming['pcm16_b64'], validate=True)
                    if len(chunk) % 2 or len(audio_buffer) + len(chunk) > 16000 * 2 * 60:
                        raise ValueError('Invalid audio size')
                    audio_buffer.extend(chunk)
                except ValueError:
                    audio_buffer.clear()
                    await send(message('error', code='bad_message', message='Invalid audio.'))
                    continue
                if incoming.get('final', False):
                    await cancel_stt()
                    await cancel_turn()
                    await cancel_audio()
                    pcm = bytes(audio_buffer)
                    audio_buffer.clear()
                    stt_task = asyncio.create_task(transcribe(pcm))
            elif kind == 'user_text' and incoming['final']:
                await cancel_stt()
                audio_buffer.clear()
                await start_text(incoming['text'])
            elif kind == 'confirm' and incoming['what'] == 'power_off':
                await cancel_stt()
                audio_buffer.clear()
                await cancel_turn()
                await cancel_audio()
                session.power_off = incoming['value']
                if session.power_off:
                    await emit(say('Thanks. What are we working on?'))
            elif kind == 'barge_in':
                await cancel_stt()
                audio_buffer.clear()
                await cancel_turn()
                await cancel_audio()
                await send(state('listening'))
    except WebSocketDisconnect:
        pass
    finally:
        await cancel_stt()
        audio_buffer.clear()
        await cancel_yolo()
        await cancel_turn()
        await cancel_audio()
        await cancel_scene()
        await close_voice()
        await box.aclose()
        if session:
            session.scene = None
            session.frame = None
            session.history.clear()


def small_jpeg(encoded):
    with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as image:
        image.thumbnail((320, 320))
        output = io.BytesIO()
        image.convert('RGB').save(output, format='JPEG')
        return base64.b64encode(output.getvalue()).decode()


def match_detections(scene, detections):
    remaining = list(scene['objects'])
    matched = []
    for detection in detections:
        words = set(re.findall(r'\w+', detection['label'].lower()))
        candidates = [obj for obj in remaining
                      if words.intersection(re.findall(r'\w+', obj['label'].lower()))]
        if not candidates:
            continue
        def distance(obj):
            a, b = obj['bbox'], detection['bbox']
            return sum((a[i] + a[i + 2] / 2 - b[i] - b[i + 2] / 2) ** 2 for i in (0, 1))
        obj = min(candidates, key=distance)
        remaining.remove(obj)
        matched.append(dict(obj, bbox=detection['bbox'], conf=detection['conf']))
    return matched


async def yolo_loop(session, box, send):
    pending = set()
    previous = None
    sent_seq = -1

    async def refresh(frame):
        nonlocal sent_seq
        try:
            jpeg = await asyncio.to_thread(small_jpeg, frame['jpeg_b64'])
            detections = await box.detect(jpeg)
            if session.scene is None or frame['seq'] <= sent_seq or frame['seq'] < session.scene_seq:
                return
            objects = match_detections(session.scene, detections)
            if objects:
                await send(message('track', seq=frame['seq'], objects=objects))
                sent_seq = frame['seq']
        except Exception:
            pass  # Optional re-anchoring must not interrupt the browser tracker.

    try:
        while True:
            frame = session.frame
            if frame and frame['seq'] != previous and session.scene and len(pending) < 3:
                previous = frame['seq']
                task = asyncio.create_task(refresh(frame))
                pending.add(task)
                task.add_done_callback(pending.discard)
            await asyncio.sleep(0.01)
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def warm_brain(app):
    """Warm only the local model, using the same GPU gate as socket turns."""
    from server.llm import LOCAL_DEFAULT
    try:
        async with gpu_gate(app).hold(brain=True):
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    os.environ.get('OLLAMA_URL', 'http://100.93.176.7:11434').rstrip('/') + '/api/chat',
                    json=dict(model=os.environ.get('LOCAL_LLM_MODEL', LOCAL_DEFAULT), stream=False,
                              think=False, options=dict(num_predict=1, num_ctx=4096), keep_alive='30m',
                              messages=[dict(role='user', content='Hi')]))
                response.raise_for_status()
    except Exception:
        pass
