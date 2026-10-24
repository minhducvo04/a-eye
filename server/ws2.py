"""Independent v2 socket lifecycle, latest-turn cancellation and streaming speech."""
import asyncio
import base64
import json
import hashlib
import os
import io
import re
from contextlib import aclosing, asynccontextmanager
from datetime import datetime, timezone

from PIL import Image
from time import monotonic

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx
from jsonschema import ValidationError

from contracts import validate
from server.box_client import BoxClient
from server.auth import accept_socket
from server.logs import event
from server.keyframes import signature
from server import packs
from server.agent import Session, Turn, message, run_turn, say, state
from server.llm import LLMClient
from voice import adapter
from voice.fake import FakeAdapter

router = APIRouter()

PARTIAL_EVERY_BYTES = int(16000 * 2 * 0.3)  # a partial transcript per 300 ms of new speech
PARTIAL_MIN_BYTES = int(16000 * 2 * 0.5)
PARTIAL_WAIT_S = 0.6          # at the final, wait this long for an in-flight partial
TAIL_MAX_BYTES = int(16000 * 2 * 0.9)


def quiet_tail(pcm, upto, ratio=0.3):
    """True when the audio after the last partial is short and much quieter than the speech before it."""
    if upto <= 0 or len(pcm) - upto > TAIL_MAX_BYTES:
        return False
    from array import array
    def rms(data):
        samples = array('h', data[:len(data) - len(data) % 2])
        return (sum(x * x for x in samples) / len(samples)) ** 0.5 if samples else 0.0
    tail = pcm[upto:]
    if not tail:
        return True
    return rms(tail) <= max(200.0, rms(pcm[:upto]) * ratio)


class GPUGate:
    """Brains bypass an existing scene; new scenes wait for all reserved turns."""
    def __init__(self):
        self.condition = asyncio.Condition()
        self.active = False
        self.brain_active = False
        self.brains = 0

    @asynccontextmanager
    async def hold(self, brain=False):
        async with self.condition:
            self.brains += int(brain)
            try:
                await self.condition.wait_for(
                    lambda: not self.brain_active if brain else not self.active and not self.brains)
                if brain:
                    self.brain_active = True
                else:
                    self.active = True
            except BaseException:
                self.brains -= int(brain)
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            async with self.condition:
                if brain:
                    self.brain_active = False
                    self.brains -= 1
                else:
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
    """Select changed frames and heartbeats; serialize scans behind reserved turns."""
    gate = gate or GPUGate()
    keyframes = session.keyframe_gate
    previous_seq = None
    while True:
        frame = session.frame
        requested = session.refresh_requested.is_set()
        if (not session.camera or session.voice_pending or frame is None
                or (frame['seq'] == previous_seq and not requested)):
            await asyncio.sleep(0.01)
            continue
        async with gate.hold():
            if not session.camera or session.voice_pending or session.frame is None:
                continue
            frame = session.frame
            observed_at = session.frame_time
            requested = session.refresh_requested.is_set()
            session.refresh_requested.clear()
            if frame['seq'] == previous_seq and not (
                    requested and monotonic() - session.scene_time >= keyframes.heartbeat_s):
                continue
            previous_seq = frame['seq']
            try:
                # Decode/resize off the event loop, including larger camera frames.
                sig = await asyncio.to_thread(signature, frame['jpeg_b64'])
            except (ValueError, OSError):
                session.scene_skips += 1
                continue
            # A turn or camera change can arrive during the Pillow worker.
            if not session.camera or session.voice_pending or gate.brains:
                previous_seq = None
                continue
            scan, reason = keyframes.should_scan(sig, monotonic())
            if not scan:
                session.scene_skips += 1
                continue
            started = monotonic()
            session.scene_scans += 1

            async def refresh():
                try:
                    scene = await vision.call('scene', dict(image_b64=frame['jpeg_b64'],
                                                           queries=list(session.pack.default_queries)[:2]))
                    validate('scene_response', scene)
                    if not session.camera:
                        return
                    session.scene = scene
                    session.scene_seq = frame['seq']
                    session.scene_time = monotonic()
                    session.scene_memory.add(scene, observed_at)
                    await send(message('track', seq=frame['seq'], objects=scene['objects']))
                except Exception:
                    event('dependency_error', session.session_id, dependency='vision', level='error')
                    if not session.vision_error_sent:
                        await send(message('error', code='vision_unavailable', message='Vision is unavailable.'))
                        session.vision_error_sent = True
                finally:
                    elapsed = (monotonic() - started) * 1000
                    # Fixed metadata only: the shared logger does not allow these scene fields.
                    print(json.dumps(dict(ts=datetime.now(timezone.utc).isoformat(),
                        level='info', event='scene_scan',
                        session=hashlib.sha256(session.session_id.encode()).hexdigest()[:12],
                        seq=frame['seq'], reason=reason, scans=session.scene_scans,
                        skips=session.scene_skips, vlm_ms=elapsed)), flush=True)
                await send(message('metrics', seq=frame['seq'], vlm_ms=elapsed))

            session.scene_task = asyncio.create_task(refresh())
            try:
                await session.scene_task
            finally:
                session.scene_task = None
        frame = None


@router.websocket('/ws2')
async def websocket(ws: WebSocket):
    if not await accept_socket(ws):
        return
    session = None
    turn_task = None
    current_turn = None
    audio_tasks = {}
    scene_loop_task = None
    voice = None
    active_audio = set()
    stt_mode = 'browser'
    stt_failed = False
    audio_buffer = bytearray()
    stt_task = None
    # Incremental STT: partial transcripts of the growing utterance while the user talks, so the final
    # can reuse the last partial when everything after it is quiet (the VAD hang or a release pause).
    partial = dict(gen=0, task=None, upto=0, text='')
    yolo_task = None
    box = getattr(ws.app.state, 'box_v2', None) or BoxClient()
    gate = gpu_gate(ws.app)
    vision = getattr(ws.app.state, 'vision_v2', None) or SceneClient()
    llm = getattr(ws.app.state, 'llm_v2', None) or LLMClient()
    send_lock = asyncio.Lock()

    async def send(msg):
        validate('server_message_v2', msg)
        if msg['type'] == 'metrics' and 'turn_id' in msg:
            event('turn_end', session.session_id if session else None, **{k: v for k, v in msg.items() if k.endswith('_ms')})
        async with send_lock:
            await ws.send_json(msg)

    async def speech_audio(msg):
        active_audio.add(msg['utterance_id'])
        try:
            voice.turn = msg.get('turn_id')  # Cartesia keeps one context (prosody) per turn
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
        if msg['type'] == 'say' and current_turn and not current_turn.terminal:
            msg.setdefault('turn_id', current_turn.id)
            await current_turn.stage('speaking')
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
        if current_turn:
            await current_turn.stage('cancelled')

    async def cancel_audio(utterance=None):
        selected = [(key, task) for key, task in list(audio_tasks.items())
                    if utterance is None or utterance == key]
        for key, task in selected:
            task.cancel()
            if voice is not None:
                voice.stop(key)
        await asyncio.gather(*(task for _, task in selected), return_exceptions=True)

    class TurnBrain:
        async def stream(self, *args, **kwargs):
            try:
                async with gate.hold(brain=True):
                    options = {}
                    if isinstance(llm, LLMClient):
                        async def backup():
                            await current_turn.stage('backup', detail='brain slow, trying backup')
                        options['on_backup'] = backup
                    async with aclosing(llm.stream(*args, **options, **kwargs)) as stream:
                        async for delta in stream:
                            yield delta
            finally:
                if not asyncio.current_task().cancelling():
                    session.voice_pending = False

    async def turn(text, lifecycle):
        event('turn_start', session.session_id)
        try:
            await lifecycle.stage('thinking', text=text)
            # Talker + thinker: a Haiku-class talker speaks while the planner (no GPU gate) draws in parallel.
            duo = (isinstance(llm, LLMClient) and os.environ.get('BRAIN_MODE', 'duo') == 'duo'
                   and bool(os.environ.get('ANTHROPIC_API_KEY')) and os.environ.get('LOCAL_ONLY') != '1')
            await run_turn(session, text, vision=vision, llm=TurnBrain(),
                           started_at=lifecycle.started, turn_id=lifecycle.id, planner=llm if duo else None)
            await lifecycle.stage('done')
        except asyncio.CancelledError:
            await lifecycle.stage('cancelled')
            raise
        except Exception as exc:
            # Class name and the innermost frame only: never message text, which could hold user words.
            tb = exc.__traceback__
            while tb and tb.tb_next:
                tb = tb.tb_next
            where = f'{tb.tb_frame.f_code.co_filename.rsplit("/", 1)[-1]}:{tb.tb_lineno}' if tb else ''
            event('dependency_error', session.session_id, dependency='turn', level='error',
                  error=type(exc).__name__, where=where)
            await lifecycle.stage('failed', detail='Brain failed')
        finally:
            if not asyncio.current_task().cancelling():
                session.voice_pending = False

    async def cancel_stt():
        nonlocal stt_task
        if stt_task:
            stt_task.cancel()
            await asyncio.gather(stt_task, return_exceptions=True)
            stt_task = None

    async def start_text(text, lifecycle):
        nonlocal turn_task
        session.voice_pending = True
        turn_task = asyncio.create_task(turn(text, lifecycle))

    def reset_audio():
        audio_buffer.clear()
        partial['gen'] += 1
        task = partial['task']
        if task is not None and not task.done():
            task.cancel()
        partial.update(task=None, upto=0, text='')

    async def run_partial(snapshot, gen):
        try:
            text = await box.stt(snapshot)
        except Exception:
            return
        if gen == partial['gen'] and len(snapshot) > partial['upto']:
            partial.update(upto=len(snapshot), text=text)

    def maybe_partial():
        if partial['task'] is not None and not partial['task'].done():
            return
        if len(audio_buffer) < PARTIAL_MIN_BYTES or len(audio_buffer) - partial['upto'] < PARTIAL_EVERY_BYTES:
            return
        partial['task'] = asyncio.create_task(run_partial(bytes(audio_buffer), partial['gen']))

    async def transcribe(pcm, lifecycle, guess=None):
        nonlocal stt_failed, stt_mode
        try:
            await lifecycle.stage('transcribing')
            text = None
            if guess is not None:
                task, gen = guess
                if task is not None and not task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(task), PARTIAL_WAIT_S)
                    except Exception:
                        pass
                if gen == partial['gen'] and partial['text'].strip() and quiet_tail(pcm, partial['upto']):
                    text = partial['text']
                    event('stt_partial_used', session.session_id, ms=(len(pcm) - partial['upto']) / 32)
                # The next utterance starts its own partials.
                partial['gen'] += 1
                partial.update(task=None, upto=0, text='')
            if text is None:
                text = await box.stt(pcm)
            if text.strip():
                await start_text(text, lifecycle)
            else:
                session.voice_pending = False
                await lifecycle.stage('failed', detail="Didn't catch that")
        except asyncio.CancelledError:
            await lifecycle.stage('cancelled')
            raise
        except Exception:
            session.voice_pending = False
            await lifecycle.stage('failed', detail="Didn't catch that")
            stt_mode = 'browser'
            event('fallback_used', session.session_id, dependency='stt', to='browser')
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
            received_at = monotonic()
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
                reset_audio()
                stt_mode = incoming.get('stt', 'browser')
                stt_failed = False
                session = new_session
                session.camera = incoming.get('camera', True)
                current_turn = None
                event('hello', session.session_id, pack=session.pack.id, tts=session.tts, stt=stt_mode)
                session.emit = emit
                voice = None
                if session.tts == 'server':
                    factory = getattr(ws.app.state, 'voice_factory_v2', adapter.make_adapter)
                    picked = incoming.get('voice')
                    candidate = await asyncio.to_thread(
                        factory, **({'voice': picked} if factory is adapter.make_adapter else {}))
                    if not isinstance(candidate, FakeAdapter):
                        voice = candidate
                        voice.voice = picked  # schema-checked id; the adapter checks its own kind
                        if hasattr(voice, 'warm'):
                            await voice.warm()
                    else:
                        event('fallback_used', session.session_id, dependency='tts', to='browser')
                session.speak = speech_audio if voice else None
                scene_loop_task = asyncio.create_task(scene_loop(session, vision, send, gate))
                if os.environ.get('YOLO_REFRESH') == '1':
                    yolo_task = asyncio.create_task(yolo_loop(session, box, send))
                await send(state('listening'))
                continue
            if session is None or incoming['session_id'] != session.session_id:
                await send(message('error', code='bad_message', message='Send hello with the matching session first.'))
                continue
            final_input = (kind == 'user_text' or (kind == 'audio_in' and stt_mode == 'server')) and incoming.get('final', False)
            if final_input:
                lifecycle = Turn(session, send, received_at)
                await lifecycle.stage('received', **({'text': incoming['text']} if kind == 'user_text' else {}))
                await cancel_stt()
                await cancel_turn()
                await cancel_audio()
                current_turn = lifecycle
            speech_start = ((kind == 'audio_in' and not incoming.get('final', False)) or
                            (kind == 'user_text' and not incoming['final']))
            if speech_start and not session.user_speaking:
                was_speaking = bool(active_audio)
                await cancel_stt()
                await cancel_turn()
                await cancel_audio()
                if was_speaking:
                    await send(state('listening'))
                session.voice_pending = False
                session.user_speaking = True
                if monotonic() - session.scene_time > .5 and session.scene_task is None:
                    session.refresh_requested.set()
            if (kind == 'user_text' or (kind == 'audio_in' and stt_mode == 'server')) and incoming.get('final', False):
                session.user_speaking = False
                session.voice_pending = True
            if kind == 'camera':
                session.camera = incoming['on']
                if not session.camera:
                    session.frame = session.scene = None
                    await cancel_scene()
                    await cancel_yolo()
                else:
                    if scene_loop_task is None:
                        scene_loop_task = asyncio.create_task(scene_loop(session, vision, send, gate))
                    if yolo_task is None and os.environ.get('YOLO_REFRESH') == '1':
                        yolo_task = asyncio.create_task(yolo_loop(session, box, send))
            elif kind == 'frame':
                if not session.camera:
                    continue
                if session.frame is None or incoming['seq'] > session.frame['seq']:
                    session.frame = incoming
                    session.frame_time = monotonic()
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
                    reset_audio()
                    session.voice_pending = False
                    session.user_speaking = False
                    if final_input:
                        await current_turn.stage('failed', detail="Didn't catch that")
                    await send(message('error', code='bad_message', message='Invalid audio.'))
                    continue
                if incoming.get('final', False):
                    pcm = bytes(audio_buffer)
                    guess = (partial['task'], partial['gen'])
                    audio_buffer.clear()  # the partial state stays until transcribe has read it
                    session.voice_pending = True
                    stt_task = asyncio.create_task(transcribe(pcm, current_turn, guess))
                else:
                    maybe_partial()
            elif kind == 'user_text' and incoming['final']:
                await cancel_stt()
                reset_audio()
                await start_text(incoming['text'], current_turn)
            elif kind == 'confirm' and incoming['what'] == 'power_off':
                await cancel_stt()
                reset_audio()
                await cancel_turn()
                await cancel_audio()
                session.voice_pending = False
                session.user_speaking = False
                session.power_off = incoming['value']
                if session.power_off:
                    await emit(say('Thanks. What are we working on?'))
            elif kind == 'barge_in':
                await cancel_stt()
                reset_audio()
                await cancel_turn()
                await cancel_audio()
                session.voice_pending = False
                session.user_speaking = False
                await send(state('listening'))
    except WebSocketDisconnect:
        pass
    finally:
        await cancel_stt()
        reset_audio()
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
