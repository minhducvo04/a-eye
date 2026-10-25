"""Real loopback Live socket: early playback, split hazards, and stopped tails."""
import asyncio
import base64
import json
from time import monotonic

import pytest
from websockets.asyncio.server import serve

from server import privacy
from server.agent import Session
from server.gemini_live import LiveBridge
from server.safety import before


def audio_content(text=None, **fields):
    content = {'modelTurn': {'parts': [{'inlineData': {
        'mimeType': 'audio/pcm;rate=24000',
        'data': base64.b64encode(b'\x01\x00' * 3600).decode()}}]}, **fields}
    if text is not None:
        content['outputTranscription'] = {'text': text}
    return {'serverContent': content}


@pytest.mark.parametrize('hazard', [False, True])
def test_fake_live_streams_before_complete_and_stops_mid_reply(monkeypatch, hazard):
    async def trial():
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic')
        monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '0')
        privacy.set_call({'google': True})
        emitted, fixed = [], []
        early, finished = asyncio.Event(), asyncio.Event()
        times = {}
        async def fake(ws):
            await ws.recv()
            await ws.send('{"setupComplete": {}}')
            await ws.recv()
            times['provider_audio'] = monotonic()
            await ws.send(json.dumps(audio_content()))
            await asyncio.sleep(.08)
            await ws.send(json.dumps({'serverContent': {'outputTranscription': {'text': 'A blue cup. '}}}))
            await ws.send(json.dumps(audio_content()))
            await asyncio.wait_for(early.wait(), 1)
            assert 'complete' not in times
            if hazard:
                await ws.send(json.dumps(audio_content('Open the electrical ')))
                await ws.send(json.dumps(audio_content('panel.')))
            else:
                await ws.send(json.dumps(audio_content('Use it for water.')))
            times['complete'] = monotonic()
            await ws.send(json.dumps({'serverContent': {'turnComplete': True}}))
            if hazard:
                # Provider interruption/late data must not re-arm a stopped reply.
                await ws.send(json.dumps({'serverContent': {'interrupted': True}}))
                await ws.send(json.dumps(audio_content('More stale output.', turnComplete=True)))
            finished.set()
            await ws.wait_closed()
        async def emit(msg):
            emitted.append(msg)
            if msg['type'] == 'audio' and msg['pcm16_b64']:
                times.setdefault('client_audio', monotonic())
                early.set()
        async def speak(line):
            fixed.append((line, len(emitted)))
        async def discover():
            return 'models/fake'
        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(Session('stream', camera=False), None, None, emit, speak,
                discover=discover, endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            assert await bridge.start()
            try:
                await bridge.text('Describe the cup.')
                await asyncio.wait_for(finished.wait(), 2)
                await asyncio.sleep(.1)
                assert .24 <= times['client_audio'] - times['provider_audio'] < .65
                chunks = [m for m in emitted if m['type'] == 'audio' and m['pcm16_b64']]
                assert all(3200 <= len(base64.b64decode(m['pcm16_b64'])) <= 6400 for m in chunks)
                assert len({m['utterance_id'] for m in chunks}) == 1
                if hazard:
                    assert len(fixed) == 1 and fixed[0][0] == before('open the electrical panel')
                    assert any(m.get('state') == 'listening' for m in emitted[:fixed[0][1]])
                    assert not any(m['type'] == 'audio' for m in emitted[fixed[0][1]:])
                    assert bridge.blocked
                else:
                    assert not fixed
                    assert [m for m in emitted if m['type'] == 'audio'][-1]['final']
            finally:
                await bridge.close()
    asyncio.run(trial())


def test_hazard_question_never_reaches_live():
    async def trial():
        from types import SimpleNamespace
        privacy.set_call({'google': True})
        wire, fixed = [], []
        async def send(raw):
            wire.append(json.loads(raw))
        async def emit(msg):
            pass
        async def speak(line):
            fixed.append(line)
        bridge = LiveBridge(Session('question', camera=False), None, None, emit, speak)
        bridge.ws, bridge.active = SimpleNamespace(send=send), True
        await bridge.text('Open the electrical panel')
        assert fixed == [before('Open the electrical panel')]
        assert not any('realtimeInput' in m for m in wire)
        await bridge.handle(audio_content('Stale reply.', turnComplete=True))
        assert bridge.blocked
    asyncio.run(trial())


def test_normal_barge_ack_does_not_block_next_spoken_reply():
    async def trial():
        from types import SimpleNamespace
        privacy.set_call({'google': True})
        emitted = []
        async def emit(msg):
            emitted.append(msg)
        async def send(raw):
            pass
        bridge = LiveBridge(Session('barge', camera=False), None, None, emit, emit)
        bridge.ws, bridge.active, bridge.model = SimpleNamespace(send=send), True, 'fake'
        await bridge.interrupt()
        await bridge.audio('AAA=')
        await bridge.handle({'serverContent': {'interrupted': True}})
        await bridge.audio('AAA=', final=True)
        await bridge.handle(audio_content('A blue cup.', turnComplete=True))
        assert any(m['type'] == 'audio' and m['pcm16_b64'] for m in emitted)
    asyncio.run(trial())


def test_ws2_hazard_sends_stop_caption_and_fixed_audio(monkeypatch):
    """Exercise the actual fixed_say callback and client wire, with fake TTS."""
    from fastapi.testclient import TestClient
    from contracts import validate
    from server.test_ws2 import app, send
    from voice.fake import FakeAdapter
    from voice.adapter import VoiceAdapter

    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic')
    monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '0')
    bridges, stopped = [], []

    class LocalLive(LiveBridge):
        async def _open(self):
            self.fake_server = await serve(self.provider, '127.0.0.1', 0)
            self.endpoint = f'ws://127.0.0.1:{self.fake_server.sockets[0].getsockname()[1]}'
            await super()._open()

        async def provider(self, ws):
            await ws.recv()
            await ws.send('{"setupComplete": {}}')
            async for raw in ws:
                if 'text' not in json.loads(raw).get('realtimeInput', {}):
                    continue
                await ws.send(json.dumps(audio_content('A blue cup.')))
                await ws.send(json.dumps(audio_content()))
                await asyncio.sleep(.35)
                await ws.send(json.dumps(audio_content(' Open the electrical ')))
                await ws.send(json.dumps(audio_content('panel.')))
                await ws.send(json.dumps(audio_content('Late audio.', turnComplete=True)))

        async def close(self):
            await super().close()
            if hasattr(self, 'fake_server'):
                self.fake_server.close()
                await self.fake_server.wait_closed()

    class FixedVoice(VoiceAdapter):
        async def say(self, utterance_id, text):
            stopped.append(text)
            async for chunk in FakeAdapter.say(self, utterance_id, text):
                yield chunk

    async def discover():
        return 'models/fake'
    def factory(*args):
        bridge = LocalLive(*args, discover=discover)
        bridges.append(bridge)
        return bridge
    application = app(voice=FixedVoice())
    application.state.live_factory_v2 = factory
    emitted = []
    with TestClient(application) as client, client.websocket_connect('/ws2?mode=gemini-live&google=1') as ws:
        send(ws, 'hello', pack='general', camera=False, tts='server', stt='server')
        assert ws.receive_json()['state'] == 'listening'
        send(ws, 'user_text', text='Describe the cup', final=True)
        stop_id = None
        for _ in range(100):
            msg = ws.receive_json()
            validate('server_message_v2', msg)
            emitted.append(msg)
            if msg['type'] == 'say' and msg['text'] == before('open the electrical panel'):
                stop_id = msg['utterance_id']
            if msg['type'] == 'audio' and msg['utterance_id'] == stop_id and msg['final']:
                break
        else:
            pytest.fail('fixed stop audio did not complete')
        assert stop_id and stopped == [before('open the electrical panel')]
        first_pcm = next(m for m in emitted if m['type'] == 'audio' and m['pcm16_b64'])
        assert first_pcm['utterance_id'] != stop_id
        stop_at = next(i for i, m in enumerate(emitted) if m.get('utterance_id') == stop_id)
        assert any(m.get('state') == 'listening' for m in emitted[:stop_at])
        assert all(m['utterance_id'] == stop_id for m in emitted[stop_at:] if m['type'] == 'audio')
        assert bridges[0].blocked
