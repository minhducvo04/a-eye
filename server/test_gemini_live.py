"""Synthetic Live wire frames; privacy is checked before any network work."""
import asyncio
import base64
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from websockets.asyncio.server import serve

from server import cloud_meter, privacy
from server.agent import Session
from server.gemini_live import LiveBridge, discover_model, DOCUMENTED_MODEL


@pytest.mark.parametrize('evidence', ['none', 'fresh', 'stale', 'other_question'])
def test_memory_claim_guard_cuts_reply_and_runs_code_lookup(monkeypatch, capsys, evidence):
    from server import live_memory
    from server.test_live_memory import bridge_for, played
    monkeypatch.setattr(live_memory, 'DEBOUNCE', 0)

    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        question = 'Was I holding a neck pillow in our last call?'
        bridge.question = bridge.guide_question = question
        lookups = []

        async def lookup(text, scope=None):
            lookups.append((text, scope))
            return dict(source='unavailable', found=False, say='No matching saved moment was found.'), []

        bridge._lookup_memory = lookup
        if evidence != 'none':
            # Produce evidence through the real code-owned turn, including its delivery.
            async def found(text, scope=None):
                return dict(source='recent', found=True, say='A pillow was visible.'), []
            bridge._lookup_memory = found
            await bridge.memory.hold()
            bridge.memory.schedule(question)
            await bridge.memory.task
            bridge._lookup_memory = lookup
            if evidence == 'stale':
                bridge.memory.evidence_at -= 11
            elif evidence == 'other_question':
                bridge.new_input_turn()
                bridge.question = bridge.guide_question = 'Was there a blue pillow in our last call?'
            emitted.clear()
        claim = "I've reviewed our records and there's no clip"
        await bridge.handle({'serverContent': {'outputTranscription': {'text': claim},
                                               'turnComplete': True}})
        if bridge.memory.task:
            await bridge.memory.task
        assert not bridge.safety_stopped and bridge.safety_line is None
        if evidence == 'fresh':
            assert not lookups and any(m.get('text') == claim for m in played(emitted))
        else:
            assert lookups == [(bridge.guide_question, 'long-term')]
            assert bridge.blocked and not played(emitted)
            assert fixed == ['No matching saved moment was found.']
            assert await bridge.text('Describe the blue board')
            assert not bridge.blocked and not bridge.safety_stopped
        await bridge.memory.close()
        await bridge.prefetch.close()
    asyncio.run(trial())
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"event":"claim_guard"' in line]
    assert len(rows) == (0 if evidence == 'fresh' else 1)
    if rows:
        assert rows[0]['reason'] == 'records_check'
        assert 'pillow' not in json.dumps(rows) and 'reviewed' not in json.dumps(rows)


@pytest.mark.parametrize('phrase', ["checked my memory", "checked the clips", "no clip of",
                                    "I don't have any clips", "can't find that in our calls",
                                    "found a clip"])
def test_memory_claim_guard_streaming_cut(monkeypatch, phrase):
    from server.test_live_memory import bridge_for

    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        bridge.question = bridge.guide_question = 'What about the neck pillow?'
        calls = []
        async def lookup(question, scope=None):
            calls.append((question, scope))
            return dict(source='unavailable', found=False, say='No saved match.'), []
        bridge._lookup_memory = lookup
        first, last = phrase.rsplit(' ', 1)
        await bridge.handle({'serverContent': {'outputTranscription': {'text': first + ' '}}})
        emitted.clear()
        blob = dict(mimeType='audio/pcm;rate=24000',
                    data=base64.b64encode(b'\x01\x00' * 9600).decode())
        await bridge.handle({'serverContent': {'outputTranscription': {'text': last},
                                               'modelTurn': {'parts': [{'inlineData': blob}]}}})
        await bridge.handle({'serverContent': {'outputTranscription': {'text': ' invented tail'},
                                               'modelTurn': {'parts': [{'inlineData': blob}]},
                                               'turnComplete': True}})
        await bridge.memory.task
        assert calls == [('What about the neck pillow?', 'long-term')]
        assert not any(m['type'] in ('audio', 'reply_delta', 'say') for m in emitted)
        assert fixed == ['No saved match.'] and not bridge.safety_stopped
        await bridge.memory.close()
    asyncio.run(trial())


def jpeg():
    out = io.BytesIO()
    Image.new('RGB', (900, 600), 'blue').save(out, 'JPEG')
    return base64.b64encode(out.getvalue()).decode()


def test_fake_live_recent_step_transcripts_and_scene_stay_local(monkeypatch):
    # The tool and prefetch path, as with LIVE_MEMORY_GATE=0 (the gate has its own tests in test_live_memory.py).
    monkeypatch.setenv('LIVE_MEMORY_GATE', '0')
    async def trial():
        from server.ws2 import scene_loop
        from server.test_ws2 import Vision
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        privacy.set_call({'google': True})
        wire, emitted = [], []
        done = asyncio.Event()
        question = 'what step was I just on?'
        instruction = 'Step 3: place the resistor on row 12.'
        async def fake(ws):
            wire.append(json.loads(await ws.recv()))
            await ws.send(json.dumps({'setupComplete': {}}))
            await ws.send(json.dumps({'serverContent': {
                'inputTranscription': {'text': 'Help with the resistor.'},
                'outputTranscription': {'text': 'Step 3: place the '}}}))
            await ws.send(json.dumps({'serverContent': {
                'outputTranscription': {'text': 'resistor on row 12.'}, 'turnComplete': True}}))
            async for raw in ws:
                msg = json.loads(raw)
                wire.append(msg)
                if msg.get('realtimeInput', {}).get('text') == question:
                    await ws.send(json.dumps({'toolCall': {'functionCalls': [
                        dict(id='recent', name='recent_memory', args={'question': question})]}}))
                if 'toolResponse' in msg:
                    result = msg['toolResponse']['functionResponses'][0]['response']['result']
                    await ws.send(json.dumps({'serverContent': {
                        'outputTranscription': {'text': result}, 'turnComplete': True}}))
        async def emit(msg):
            emitted.append(msg)
            if msg.get('type') == 'say' and 'the guide said' in msg['text']:
                done.set()
        async def discover():
            return 'models/' + DOCUMENTED_MODEL
        session = Session('recent-live')
        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(session, Vision(), None, emit, emit, discover=discover,
                                endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            # Memory settings must not attach a persistent backend to this Live log.
            session.recent_memory.bind(SimpleNamespace(remembering=lambda: True), session.session_id)
            assert session.recent_memory.store is None
            assert await bridge.start()
            scan = None
            try:
                for _ in range(100):
                    if any(m.get('text') == instruction for m in emitted):
                        break
                    await asyncio.sleep(.01)
                session.frame = dict(seq=1, jpeg_b64=jpeg())
                scan = asyncio.create_task(scene_loop(session, bridge.vision, emit))
                for _ in range(100):
                    if any(e['kind'] == 'scene' for e in session.recent_memory.entries):
                        break
                    await asyncio.sleep(.01)
                entries = list(session.recent_memory.entries)
                assert any(e['kind'] == 'scene' and e['note'] for e in entries)
                assert any(e['kind'] == 'user' and e['note'] == 'Help with the resistor.' for e in entries)
                assert any(e['kind'] == 'helper' and e['note'] == instruction for e in entries)
                await bridge.text(question)
                await asyncio.wait_for(done.wait(), 2)
                response = next(m['toolResponse']['functionResponses'][0]['response']
                                for m in wire if 'toolResponse' in m)
                assert set(response) == {'result', 'scheduling'}
                assert response['scheduling'] == 'WHEN_IDLE'
                assert 'the guide said' in response['result'] and instruction in response['result']
                setup = json.dumps(wire[0])
                assert all(key not in setup for key in ('additionalProperties', 'minLength', 'maxLength'))
                assert 'observed_at' not in json.dumps(wire) and 'wall_t' not in json.dumps(wire)
            finally:
                if scan:
                    scan.cancel()
                    await asyncio.gather(scan, return_exceptions=True)
                await bridge.close()
    asyncio.run(trial())


@pytest.mark.parametrize('args', [{}, {'question': ''}, {'question': 'x' * 301},
                                 {'question': 3}, {'question': 'step', 'extra': 'no'}])
def test_recent_tool_strict_arguments(args):
    async def trial():
        privacy.set_call({'google': True})
        async def emit(msg):
            pass
        bridge = LiveBridge(Session('s'), None, None, emit, emit)
        assert await bridge.tool(dict(name='recent_memory', args=args)) == 'Invalid tool arguments.'
    asyncio.run(trial())


def test_recent_tool_temporal_routes_and_local_result_cards(tmp_path):
    async def trial():
        from scripts.recent_memory_bench import fixture
        privacy.set_call({'google': True, 'twelvelabs': True})
        evidence = fixture(tmp_path)
        session = Session('s', recent_memory=evidence.recent_memory)
        session.rewind = evidence.rewind
        emitted = []
        async def emit(msg):
            emitted.append(msg)
        bridge = LiveBridge(session, None, None, emit, emit)
        async def recall(question):
            return await bridge.tool(dict(name='recent_memory', args={'question': question}))
        assert 'row 12' in await recall('Where was the red wire a minute ago?')
        assert session.rewind.calls == 0
        assert '0:30' in await recall('Where was the resistor earlier in this call?')
        assert session.rewind.calls == 1
        assert 'parts bin' in await recall('Where was the resistor yesterday?')
        assert any(m['type'] == 'find_item' for m in emitted)
        session.rewind.on = False
        # Over 5 minutes with Rewind off: this call's notes only, never another call relabelled as then.
        assert "can't confirm" in await recall('Where was the resistor 6 minutes ago?')
        assert session.rewind.calls == 1
        assert "can't confirm" in await recall('Where was the blue wire just now?')
        privacy.update('google', False)
        with pytest.raises(PermissionError):
            await recall('What was step 3?')
    asyncio.run(trial())


def test_camera_precedes_realtime_question():
    async def trial():
        from time import monotonic
        privacy.set_call({'google': True})
        wire = []
        async def send(raw):
            wire.append((monotonic(), json.loads(raw)))
        async def emit(msg):
            pass
        session = Session('s', frame=dict(seq=1, jpeg_b64=jpeg()))
        bridge = LiveBridge(session, None, None, emit, emit)
        bridge.active = True
        bridge.ws = SimpleNamespace(send=send)
        assert await bridge.text('what do you see?')
        assert len(wire) == 2
        assert wire[0][1]['realtimeInput']['video']['mimeType'] == 'image/jpeg'
        assert wire[1][1] == {'realtimeInput': {'text': 'what do you see?'}}
        assert wire[1][0] - wire[0][0] >= .25
    asyncio.run(trial())


@pytest.mark.parametrize('reply,expected', [
    ('I see a solid blue image.', True),
    ("I don't have eyes, so I can't see anything.", False),
    ('I cannot see a blue image.', False),
    ('A red image.', False),
])
def test_probe_requires_blue_visual_reply(reply, expected):
    from scripts.gemini_live_check import sees_blue
    assert bool(sees_blue(reply)) is expected


@pytest.mark.parametrize('private,google,local', [(True, True, False), (False, False, False), (False, True, True)])
def test_privacy_before_discovery_and_connection(monkeypatch, private, google, local):
    async def trial():
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        monkeypatch.setenv('LOCAL_ONLY', '1' if local else '0')
        privacy.set_call({'google': google}, private=private)
        calls = []
        async def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError('network attempted')
        bridge = LiveBridge(Session('s'), None, None, forbidden, forbidden, discover=forbidden)
        assert not await bridge.start()
        assert calls == []
    asyncio.run(trial())


def test_discovery_filters_methods_paginates_and_validates_override(monkeypatch):
    async def trial():
        privacy.set_call({'google': True})
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        monkeypatch.delenv('GEMINI_LIVE_MODEL', raising=False)
        def handle(request):
            assert request.headers['x-goog-api-key'] == 'synthetic-key'
            assert 'key=' not in str(request.url)
            if not request.url.params.get('pageToken'):
                return httpx.Response(200, json={'models': [{'name': 'models/text-only', 'supportedGenerationMethods': ['generateContent']}], 'nextPageToken': 'next'})
            return httpx.Response(200, json={'models': [{'name': 'models/' + DOCUMENTED_MODEL, 'supportedGenerationMethods': ['bidiGenerateContent']}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            assert await discover_model(client) == 'models/' + DOCUMENTED_MODEL
            monkeypatch.setenv('GEMINI_LIVE_MODEL', 'text-only')
            with pytest.raises(ValueError):
                await discover_model(client)
    asyncio.run(trial())


def test_fake_live_wire_audio_tools_captions_and_revocation(monkeypatch):
    async def trial():
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        privacy.set_call({'google': True})
        meter = cloud_meter.start()
        received, emitted, fixed = [], [], []
        sent = asyncio.Event()
        async def fake(ws):
            received.append(json.loads(await ws.recv()))
            await ws.send(json.dumps({'setupComplete': {}}))
            async for raw in ws:
                msg = json.loads(raw)
                received.append(msg)
                if 'text' in msg.get('realtimeInput', {}):
                    await ws.send(json.dumps({'serverContent': {'inputTranscription': {'text': 'What is here?'}}}))
                    await ws.send(json.dumps({'toolCall': {'functionCalls': [{'id': 't1', 'name': 'find_item', 'args': {'name': 'keys'}}]}}))
                if 'toolResponse' in msg:
                    # Audio arrives before its transcript: do not play until checked.
                    await ws.send(json.dumps({'serverContent': {'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': base64.b64encode(b'\x00\x00' * 240).decode()}}]}}}))
                    await ws.send(json.dumps({'serverContent': {'outputTranscription': {'text': 'A blue board.'}, 'turnComplete': True}}))
                    sent.set()
        async def emit(msg):
            emitted.append(msg)
        async def fixed_say(text):
            fixed.append(text)
        async def discover():
            return 'models/' + DOCUMENTED_MODEL
        async with serve(fake, '127.0.0.1', 0) as server:
            endpoint = 'ws://127.0.0.1:' + str(server.sockets[0].getsockname()[1])
            # Count the synthetic remote transport, not a real cloud request.
            monkeypatch.setattr(cloud_meter, 'is_local', lambda url: False)
            session = Session('s')
            session.frame = dict(seq=1, jpeg_b64=jpeg())
            bridge = LiveBridge(session, None, SimpleNamespace(state=SimpleNamespace()), emit, fixed_say,
                                discover=discover, endpoint=endpoint)
            assert await bridge.start()
            setup = received[0]['setup']
            assert setup['generationConfig']['responseModalities'] == ['AUDIO']
            assert setup['realtimeInputConfig']['turnCoverage'] == 'TURN_INCLUDES_ALL_INPUT'
            assert setup['sessionResumption'] == {}
            assert setup['contextWindowCompression'] == {'slidingWindow': {}}
            assert 'live camera' in setup['systemInstruction']['parts'][0]['text']
            from server import personas
            assert personas.style_block(session.persona, live=True) in setup['systemInstruction']['parts'][0]['text']
            assert setup['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == session.persona['gemini_live_voice']
            await bridge.audio(base64.b64encode(b'\x00\x00' * 160).decode(), True)
            await bridge.video()
            await bridge.video()  # at most one picture per second
            await bridge.text('What is here?')
            await asyncio.wait_for(sent.wait(), 2)
            for _ in range(100):
                if any(m['type'] == 'audio' for m in emitted):
                    break
                await asyncio.sleep(.01)
            assert any(m['type'] == 'say' and m['text'] == 'A blue board.' for m in emitted)
            audio = next(m for m in emitted if m['type'] == 'audio')
            assert audio['sample_rate'] == 16000 and len(base64.b64decode(audio['pcm16_b64'])) == 320
            assert not any(m.get('state') == 'listening' for m in emitted[emitted.index(audio):])
            assert meter.pictures_sent == 1 and meter.calls >= 1 and meter.bytes > 0
            wire = json.dumps(received)
            assert 'audio/pcm;rate=16000' in wire and 'Memory is off' in wire
            image = next(m['realtimeInput']['video']['data'] for m in received if 'video' in m.get('realtimeInput', {}))
            assert max(Image.open(io.BytesIO(base64.b64decode(image))).size) <= 320
            privacy.update('google', False)
            count = len(received)
            assert not await bridge.text('must stay local')
            await bridge.close()
            assert len(received) == count
    asyncio.run(trial())


def test_reconnect_once_then_fallback_and_close(monkeypatch):
    async def trial():
        from server.gemini_live import FALLBACK_LINE
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        privacy.set_call({'google': True})
        connections, fixed = [], []
        async def fake(ws):
            connections.append(json.loads(await ws.recv()))
            await ws.send('{"setupComplete": {}}')
            await asyncio.sleep(.02)
            await ws.close()
        async def emit(msg):
            pass
        async def fixed_say(text):
            fixed.append(text)
        async def discover():
            return 'models/' + DOCUMENTED_MODEL
        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(Session('s'), None, None, emit, fixed_say, discover=discover,
                                endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            assert await bridge.start()
            await asyncio.wait_for(bridge.task, 2)
            assert len(connections) == 2 and not bridge.active
            assert fixed == [FALLBACK_LINE]
            await bridge.close()
            assert bridge.task.done()
    asyncio.run(trial())


@pytest.mark.parametrize('go_away,stopped', [(False, False), (True, False), (True, True)])
def test_reconnect_reuses_latest_resumable_handle(monkeypatch, go_away, stopped):
    async def trial():
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '0')
        privacy.set_call({'google': True})
        setups, fixed, emitted = [], [], []
        resumed = asyncio.Event()
        async def fake(ws):
            setups.append(json.loads(await ws.recv())['setup'])
            await ws.send('{"setupComplete": {}}')
            if len(setups) == 1:
                for update in [dict(resumable=True, newHandle='older'),
                               dict(resumable=True, newHandle='latest'),
                               dict(resumable=False, newHandle='')]:
                    await ws.send(json.dumps({'sessionResumptionUpdate': update}))
                if stopped:
                    await ws.send(json.dumps({'serverContent': {'outputTranscription': {
                        'text': 'Open the electrical panel.'}}}))
                if go_away:
                    await ws.send('{"goAway": {"timeLeft": "30s"}}')
                    # The bridge must reconnect without waiting for server closure.
                    await ws.wait_closed()
                else:
                    await ws.close()
            else:
                resumed.set()
                await ws.wait_closed()
        async def emit(msg):
            emitted.append(msg)
        async def speak(text):
            fixed.append(text)
        async def discover():
            return 'models/fake'
        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(Session('resume', camera=False), None, None, emit, speak,
                discover=discover, endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            assert await bridge.start()
            try:
                await asyncio.wait_for(resumed.wait(), 2)
                assert setups[0]['sessionResumption'] == {}
                assert setups[1]['sessionResumption'] == ({} if stopped else {'handle': 'latest'})
                assert bridge.active and bool(fixed) == stopped
                if stopped:
                    assert bridge.blocked and bridge.safety_stopped
                    from server.test_live_streaming import audio_content
                    await bridge.handle(audio_content('Stale reply.', turnComplete=True))
                    assert not any(m['type'] == 'audio' for m in emitted)
            finally:
                await bridge.close()
    asyncio.run(trial())


@pytest.mark.parametrize('healthy_seconds,expected_connections', [(59.9, 2), (60, 3), (121, 3)])
def test_reconnect_budget_resets_after_healthy_minute(monkeypatch, healthy_seconds, expected_connections):
    async def trial():
        from server import gemini_live
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '0')
        privacy.set_call({'google': True})
        clock, setups, fixed = [0.0], [], []
        monkeypatch.setattr(gemini_live, 'monotonic', lambda: clock[0])
        class Socket:
            def __init__(self, index):
                self.index, self.reads = index, 0
            async def send(self, raw):
                setups.append(json.loads(raw)['setup'])
            async def recv(self):
                self.reads += 1
                if self.reads == 1:
                    return '{"setupComplete": {}}'
                if self.index == 1 and self.reads == 2:
                    clock[0] += healthy_seconds
                    return '{"sessionResumptionUpdate": {"resumable": true, "newHandle": "healthy"}}'
                raise ConnectionError('synthetic disconnect')
            async def close(self):
                pass
        async def connect(*args, **kwargs):
            return Socket(len(setups))
        async def emit(msg):
            pass
        async def speak(text):
            fixed.append(text)
        async def discover():
            return 'models/fake'
        monkeypatch.setattr(gemini_live, 'connect', connect)
        bridge = LiveBridge(Session('reset', camera=False), None, None, emit, speak, discover=discover)
        assert await bridge.start()
        try:
            await asyncio.wait_for(bridge.task, 2)
            assert len(setups) == expected_connections
            assert fixed == [gemini_live.FALLBACK_LINE]
            if expected_connections == 3:
                assert setups[-1]['sessionResumption'] == {'handle': 'healthy'}
        finally:
            await bridge.close()
    asyncio.run(trial())


@pytest.mark.parametrize('rate', [16000, 24000])
def test_first_audio_releases_at_buffered_250ms_and_stop_cuts_tail(monkeypatch, rate):
    async def trial():
        from server import gemini_live
        privacy.set_call({'google': True})
        # Audio can arrive faster than real time: no wall-clock delay is needed.
        monkeypatch.setattr(gemini_live, 'monotonic', lambda: 0.0)
        emitted, fixed = [], []
        async def emit(msg):
            emitted.append(msg)
        async def speak(text):
            fixed.append(text)
        bridge = LiveBridge(Session('early', camera=False), None, None, emit, speak)
        bridge.model = 'models/fake'
        def audio(samples, text=None):
            content = {'modelTurn': {'parts': [{'inlineData': {
                'mimeType': f'audio/pcm;rate={rate}',
                'data': base64.b64encode(b'\x01\x00' * samples).decode()}}]}}
            if text:
                content['outputTranscription'] = {'text': text}
            return {'serverContent': content}
        await bridge.handle(audio(rate // 4 - 1, 'A blue cup. '))
        assert not any(m['type'] == 'audio' for m in emitted)
        await bridge.handle(audio(1))
        chunks = [m for m in emitted if m['type'] == 'audio']
        assert chunks and sum(len(base64.b64decode(m['pcm16_b64'])) for m in chunks) == 8000
        assert not bridge.audio_buffer
        assert emitted.index(next(m for m in emitted if m['type'] == 'say')) < emitted.index(chunks[0])
        await bridge.handle(audio(rate // 10, 'Open the electrical '))
        await bridge.handle(audio(rate // 10, 'panel.'))
        stopped_at = len(emitted)
        assert fixed and bridge.blocked and not bridge.audio_buffer
        await bridge.handle({'serverContent': {'interrupted': True}})
        await bridge.handle(audio(rate))
        await bridge.handle({'serverContent': {'turnComplete': True}})
        assert not any(m['type'] == 'audio' for m in emitted[stopped_at:])
        await bridge.close()
    asyncio.run(trial())


def test_split_safety_transcript_suppresses_early_audio_and_tools():
    async def trial():
        from server.safety import before
        privacy.set_call({'google': True})
        emitted, fixed = [], []
        async def emit(msg):
            emitted.append(msg)
        async def speak(text):
            fixed.append(text)
        bridge = LiveBridge(Session('s'), None, None, emit, speak)
        blob = dict(mimeType='audio/pcm;rate=24000', data=base64.b64encode(b'\x00\x00' * 240).decode())
        await bridge.handle({'serverContent': {'modelTurn': {'parts': [{'inlineData': blob}]}}})
        assert not emitted
        await bridge.handle({'serverContent': {'inputTranscription': {'text': 'open the electrical '}}})
        await bridge.handle({'serverContent': {'inputTranscription': {'text': 'panel'}}})
        assert fixed == [before('open the electrical panel')]
        assert await bridge.tool(dict(name='tag_item', args={'name': 'keys', 'place': 'bowl'})) == 'Stopped by code.'
        await bridge.handle({'serverContent': {'outputTranscription': {'text': 'Here is a step.'}, 'turnComplete': True}})
        assert not any(m['type'] == 'audio' for m in emitted)
        assert not bridge.audio_buffer
    asyncio.run(trial())


def test_tools_local_memory_and_no_media_result(tmp_path, monkeypatch):
    async def trial():
        from server import memory
        from server.test_memory import Words, Person, FRAME, KEYS
        privacy.set_call({'google': True})
        store = memory.Store('live-test', base=tmp_path, cipher=memory.Cipher(''))
        registry = SimpleNamespace(for_call=lambda call: (store, None), embedder=Words(), vision=None)
        monkeypatch.setattr(memory, 'memories', lambda app: registry)
        emitted = []
        async def emit(msg):
            emitted.append(msg)
        bridge = LiveBridge(Session('s'), None, None, emit, emit)
        tag = await bridge.tool(dict(name='tag_item', args={'name': 'keys', 'place': 'blue bowl'}))
        assert 'remember your keys' in tag and store.tags()['keys']['home'] == 'blue bowl'
        writer = memory.Writer(store, 's', embedder=Words(), person_check=Person())
        await writer.observe(dict(caption='keys on the table', objects=[KEYS]), FRAME)
        result = await bridge.tool(dict(name='find_item', args={'name': 'keys'}))
        assert 'keys' in result and 'base64' not in result and FRAME not in result
        assert any(m['type'] == 'find_item' and m.get('frame_b64') for m in emitted)
        result = await bridge.tool(dict(name='forget_memory', args={'name': 'keys'}))
        assert 'Forgotten' in result and store.count('keys') == 0 and 'keys' not in store.tags()
        assert await bridge.tool(dict(name='rewind_search', args={'query': 'keys'})) == 'Tool unavailable.'
    asyncio.run(trial())


@pytest.mark.parametrize('source,cloud,conf,expected', [('ollama', False, .8, True),
    (None, True, .7, True), ('fake', True, .9, False), (None, True, .2, False)])
def test_point_uses_configured_backend_and_abstains(monkeypatch, source, cloud, conf, expected):
    async def trial():
        from server.test_pointer import Vision, LABEL
        if cloud:
            monkeypatch.setenv('VISION_BACKEND', 'gemini')
        privacy.set_call({'google': True})
        session = Session('s', frame=dict(seq=1, jpeg_b64=jpeg()))
        vision = Vision(source=source, conf=conf)
        if source is None:
            vision.result.pop('source')
        emitted = []
        async def emit(msg):
            emitted.append(msg)
        bridge = LiveBridge(session, vision, None, emit, emit)
        # point_at is no longer offered to Live; the server boxes what Live names.
        assert await bridge.tool(dict(name='point_at', args={'label': LABEL})) == 'Tool unavailable.'
        session.scene = dict(caption='', objects=[dict(label=LABEL)])
        await bridge._auto_point(f'Use the {LABEL} there.')
        assert bool(emitted) == expected
        if expected:
            assert [o['kind'] for o in emitted[0]['ops']] == ['clear', 'box', 'arrow']
        session.frame_time -= 4  # pointer budget is 3 s (owner: boxes must show on the demo link)
        emitted.clear()
        await bridge.tool(dict(name='point_at', args={'label': LABEL}))
        assert not emitted
    asyncio.run(trial())


def test_tool_hazard_and_pc_power_gate():
    async def trial():
        from server import packs
        from server.agent import POWER_LINE
        privacy.set_call({'google': True})
        lines = []
        async def emit(msg):
            pass
        async def fixed(line):
            lines.append(line)
        bridge = LiveBridge(Session('s', pack=packs.get('pc_build')), None, None, emit, fixed)
        await bridge.tool(dict(name='find_item', args={'name': 'CPU fan'}))
        assert lines == [POWER_LINE]
        bridge = LiveBridge(Session('s'), None, None, emit, fixed)
        await bridge.tool(dict(name='tag_item', args={'name': 'gas line', 'place': 'wall'}))
        assert 'gas line' in lines[-1]
    asyncio.run(trial())


@pytest.mark.parametrize('owner', ['guide', 'memory', 'safety', 'barge'])
def test_mic_chunk_preserves_code_owned_hold(monkeypatch, owner):
    async def trial():
        from server import agent, live_guide, live_memory
        from server.packs.home import HomeGuide
        from server.step_check import Verdict

        monkeypatch.setenv('LIVE_GUIDE', '1')
        monkeypatch.setenv('LIVE_MEMORY_GATE', '1')
        monkeypatch.setenv('ROUTER', 'off')
        monkeypatch.setattr(live_guide, 'DEBOUNCE', 0)
        monkeypatch.setattr(live_memory, 'DEBOUNCE', 0)
        privacy.set_call({'google': True})
        emitted, fixed, wire = [], [], []
        entered, release = asyncio.Event(), asyncio.Event()

        async def emit(msg):
            emitted.append(msg)

        async def speak(line):
            fixed.append(line)

        async def send(raw):
            wire.append(json.loads(raw))

        async def check(*args):
            entered.set()
            await release.wait()
            return Verdict('closed', 1)

        async def lookup(*args):
            entered.set()
            await release.wait()
            return dict(source='recent', found=True, say='The mug was on the shelf.'), []

        bridge = LiveBridge(Session('mic-hold', camera=False), None, None, emit, speak)
        bridge.ws, bridge.active, bridge.model = SimpleNamespace(send=send), True, 'fake'
        # VAD ends the input stream while code is still checking the user's turn.
        await bridge.audio('AAA=', final=True)
        if owner == 'guide':
            monkeypatch.setenv('HOME_TASKS', '1')
            monkeypatch.setattr(agent, 'check_water_off', check)
            bridge.session.home_guide = HomeGuide(task='sink', index=2, introduced=True)
            bridge.guide.kind = 'home'
            question = "it's off"
        elif owner == 'memory':
            bridge._lookup_memory = lookup
            question = 'Where was the mug a minute ago?'
        else:
            question = None
        if question:
            await bridge.handle({'serverContent': {'inputTranscription': {'text': question}}})
            await asyncio.wait_for(entered.wait(), 1)
        elif owner == 'safety':
            await bridge.stop(bridge.stop_line('open the electrical panel'))
        else:
            await bridge.interrupt()
        task = (bridge.guide.task if owner == 'guide' else
                bridge.memory.task if owner == 'memory' else None)
        version = bridge.memory.version
        safety_line = bridge.safety_line
        emitted.clear()
        try:
            await bridge.audio('AAA=')
            await bridge.handle({'serverContent': {
                'outputTranscription': {'text': 'Unverified provider reply.'},
                'modelTurn': {'parts': [{'inlineData': {
                    'mimeType': 'audio/pcm;rate=24000',
                    'data': base64.b64encode(b'\x00\x00' * 6000).decode()}}]}}})
            played = [m for m in emitted if m['type'] in ('audio', 'say', 'reply_delta')]
            assert bool(played) == (owner == 'barge')
            assert bridge.blocked == (owner != 'barge')
            assert bridge.safety_stopped == (owner == 'safety')
            assert bridge.safety_line == safety_line
            assert bridge.memory.version == version
            assert wire[-1]['realtimeInput']['audio']['data'] == 'AAA='
            if task:
                assert not task.done()
                if owner == 'memory':
                    assert bridge.memory.current(version)
                else:
                    assert not bridge.session.home_guide.water_off_passed
                # Only the owner's completed check may release the held output.
                await bridge.handle({'serverContent': {'turnComplete': True}})
                release.set()
                await asyncio.wait_for(task, 1)
                assert not bridge.blocked
                prompts = [m['clientContent'] for m in wire if 'clientContent' in m]
                assert len(prompts) == 1 and prompts[0]['turnComplete']
                prompt = prompts[0]['turns'][0]['parts'][0]['text']
                assert ('step 4 of 7' if owner == 'guide' else 'The mug was on the shelf.') in prompt
        finally:
            release.set()
            await bridge.guide.close()
            await bridge.memory.close()
            await bridge.prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('stop', ['safety', 'closed'])
@pytest.mark.parametrize('idle_result', ['idle', 'timeout'])
def test_prompt_turn_rechecks_stop_after_provider_idle_wait(stop, idle_result):
    async def trial():
        privacy.set_call({'google': True})
        wire, fixed = [], []
        entered, release = asyncio.Event(), asyncio.Event()

        async def emit(msg):
            pass

        async def speak(line):
            fixed.append(line)

        async def send(raw):
            wire.append(json.loads(raw))

        async def wait_idle():
            entered.set()
            await release.wait()
            if idle_result == 'timeout':
                raise asyncio.TimeoutError
            return True

        bridge = LiveBridge(Session('prompt-stop', camera=False), None, None, emit, speak)
        bridge.ws, bridge.active = SimpleNamespace(send=send), True
        await bridge.hold()
        bridge.provider_idle.wait = wait_idle
        task = asyncio.create_task(bridge.prompt_turn('Say the checked step.'))
        await asyncio.wait_for(entered.wait(), 1)
        line = bridge.stop_line('open the electrical panel')
        if stop == 'safety':
            await bridge.stop(line)
        else:
            bridge.closed = True
        release.set()
        assert await asyncio.wait_for(task, 1) is False
        assert bridge.blocked and not wire
        if stop == 'safety':
            assert bridge.safety_stopped and bridge.safety_line == line and fixed == [line]
        else:
            assert bridge.closed and not fixed
    asyncio.run(trial())


def test_output_safety_and_next_safe_question():
    async def trial():
        privacy.set_call({'google': True})
        emitted, fixed, wire = [], [], []
        async def emit(msg):
            emitted.append(msg)
        async def speak(text):
            fixed.append(text)
        async def send(raw):
            wire.append(json.loads(raw))
        bridge = LiveBridge(Session('s'), None, None, emit, speak)
        bridge.active = True
        bridge.model = DOCUMENTED_MODEL
        bridge.ws = SimpleNamespace(send=send)
        await bridge.handle({'serverContent': {'outputTranscription': {'text': 'Open the electrical '}}})
        await bridge.handle({'serverContent': {'outputTranscription': {'text': 'panel.'}}})
        assert fixed and bridge.blocked
        assert not any(m['type'] == 'say' for m in emitted)
        # Local refusals need not produce a provider turnComplete. The next safe turn works.
        assert await bridge.text('Describe the blue board')
        await bridge.handle({'serverContent': {'outputTranscription': {'text': 'A blue board.'}, 'turnComplete': True}})
        assert any(m['type'] == 'say' and m['text'] == 'A blue board.' for m in emitted)
        assert wire == [{'realtimeInput': {'text': 'Describe the blue board'}}]
    asyncio.run(trial())


def test_rewind_tool_requires_live_consent_and_only_returns_text(monkeypatch):
    async def trial():
        from server.gemini_live import declarations
        from server import rewind_tools
        privacy.set_call({'google': True, 'twelvelabs': True})
        session = Session('s')
        session.rewind = SimpleNamespace(on=True)
        calls, emitted = [], []
        async def run(name, args, current, **kwargs):
            calls.append((name, args, current))
            return {'say': 'Keys were on the table.', 'frame_b64': 'private-crop'}, []
        async def emit(msg):
            emitted.append(msg)
        monkeypatch.setattr(rewind_tools, 'run_tool', run)
        bridge = LiveBridge(session, None, None, emit, emit)
        assert 'rewind_search' in [d['name'] for d in declarations(bridge.rewind_on())]
        call = dict(name='rewind_search', args={'query': 'keys'})
        assert await bridge.tool(call) == 'Keys were on the table.'
        assert calls == [('search_past', {'query': 'keys'}, session)]
        session.rewind.on = False
        assert await bridge.tool(call) == 'Tool unavailable.'
        session.rewind.on = True
        privacy.update('twelvelabs', False)
        assert await bridge.tool(call) == 'Tool unavailable.'
        assert len(calls) == 1
    asyncio.run(trial())


def test_ws2_live_selection_routing_and_default_fallback(monkeypatch):
    from fastapi.testclient import TestClient
    from server.test_ws2 import app, send, receive
    from server.gemini_live import FALLBACK_LINE
    bridges = []
    class FakeBridge:
        def __init__(self, session, vision, app, send, fixed):
            self.active = False
            self.calls = []
            self.closed = False
            self.fixed = fixed
            bridges.append(self)
        async def start(self):
            self.active = privacy.google_allowed()
            return self.active
        async def text(self, text):
            self.calls.append(('text', text))
        async def audio(self, data, final):
            self.calls.append(('audio', data, final))
        async def interrupt(self):
            self.calls.append(('interrupt',))
        async def close(self):
            self.active = False
            self.closed = True
    application = app()
    application.state.live_factory_v2 = FakeBridge
    with TestClient(application) as client:
        with client.websocket_connect('/ws2') as ws:
            send(ws, 'hello', pack='general', camera=False)
            assert receive(ws)['state'] == 'listening'
            assert bridges == []
        with client.websocket_connect('/ws2?mode=gemini-live&google=1') as ws:
            send(ws, 'hello', pack='general', camera=False, stt='server')
            assert receive(ws)['state'] == 'listening'
            send(ws, 'user_text', text='What is here?', final=True)
            send(ws, 'audio_in', seq=1, pcm16_b64='AAA=', final=True)
            ws.send_json({})
            assert receive(ws)['code'] == 'bad_message'  # processing barrier
            assert bridges[-1].calls == [('text', 'What is here?'), ('audio', 'AAA=', True)]
            send(ws, 'hello', pack='general', camera=False, private=True)
            assert receive(ws)['text'] == FALLBACK_LINE
            assert receive(ws)['state'] == 'listening'
            assert bridges[-2].closed and not bridges[-1].active
        assert bridges[-1].closed
    # Actual unconfigured Live falls through to the untouched normal text pipeline.
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with TestClient(app()) as client, client.websocket_connect('/ws2?mode=gemini-live&google=1') as ws:
        send(ws, 'hello', pack='general', camera=False)
        assert receive(ws)['text'] == FALLBACK_LINE
        assert receive(ws)['state'] == 'listening'
        send(ws, 'user_text', text='Hello there', final=True)
        assert receive(ws)['state'] == 'thinking'
        for _ in range(10):
            if receive(ws).get('type') == 'say':
                break
        else:
            pytest.fail('normal fallback did not answer')
