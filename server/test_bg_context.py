"""Background Live context: speech independence, consent, stops and freshness."""
import asyncio
import json
from time import monotonic
from types import SimpleNamespace

import anthropic
from anthropic import _base_client
import httpx
import pytest

from server import cloud_meter, context_agent, llm, privacy
from server.agent import Session
from server.context_agent import ContextAgent
from server.gemini_live import LiveBridge


def test_live_input_and_reply_never_collect_context():
    async def trial():
        privacy.set_call({'google': True})
        session = Session('nonblocking', camera=False)
        session.context_agent = ContextAgent(session)
        async def slow(*args, **kwargs):
            await asyncio.Event().wait()
        session.context_agent.collect = slow
        wire, emitted = [], []
        async def send(raw):
            wire.append(json.loads(raw))
        async def emit(msg):
            emitted.append(msg)
        bridge = LiveBridge(session, None, None, emit, emit)
        bridge.ws = SimpleNamespace(send=send)
        bridge.active, bridge.model = True, 'fixture'
        await asyncio.wait_for(bridge.audio('AAA=', True), .1)
        await asyncio.wait_for(bridge.text('What next?'), .1)
        await asyncio.wait_for(bridge.handle({'serverContent': {
            'inputTranscription': {'text': 'What next?'},
            'outputTranscription': {'text': 'Use the blue cup.'},
            'turnComplete': True}}), .1)
        assert any(m['type'] == 'audio' for m in emitted)
        assert wire[0] == {'realtimeInput': {'audio': {'mimeType': 'audio/pcm;rate=16000', 'data': 'AAA='}}}
    asyncio.run(trial())


def test_builder_coalesces_triggers_keeps_last_block_and_cancels(monkeypatch):
    async def trial():
        privacy.set_call({'google': True, 'claude': False})
        session = Session('coalesced', camera=False)
        session.context_agent = ContextAgent(session)
        started, release = asyncio.Event(), asyncio.Event()
        calls, published, stops = [], [], []
        async def assess(session, evidence):
            calls.append(monotonic())
            if len(calls) == 2:
                started.set()
                await release.wait()
            return {'context': 'Blue cup on table. User is choosing a cup.', 'hazard': ''}
        async def publish(block):
            published.append(block)
            return True
        async def stop(line):
            stops.append(line)
        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        builder = context_agent.LiveContextBuilder(session, publish, stop, lambda text: None, interval=.05)
        builder.start()
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert len(published) == 1
            for _ in range(100):
                builder.request()
            await asyncio.sleep(.08)
            assert len(calls) == 2 and builder.block == published[0]
            release.set()
            await asyncio.sleep(.02)
            assert len(published) >= 2
            assert all(b - a >= .045 for a, b in zip(calls, calls[1:]))
            assert builder.updated_at >= builder.observed_at
            assert len(builder.block.split()) < 120
        finally:
            await builder.close()
        assert builder.task.done() and session.live_context is None and not stops
    asyncio.run(trial())


@pytest.mark.parametrize('private,claude', [(False, True), (False, False), (True, True)])
def test_assessment_routes_and_counts_real_http_boundary(monkeypatch, private, claude):
    async def trial():
        privacy.set_call({'google': True, 'claude': claude}, private=private)
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic')
        monkeypatch.setenv('ANTHROPIC_CONTEXT_MODEL', 'claude-haiku-5-5-test')
        session = Session('providers', private=private)
        session.frame = {'seq': 1, 'jpeg_b64': 'NEVER-SEND-RAW-FRAME'}
        requests = []
        def handler(request):
            payload = json.loads(request.content)
            requests.append((request.url.host, payload))
            answer = json.dumps({'context': 'Blue cup on table.', 'hazard': ''})
            if request.url.host == 'api.anthropic.com':
                return sdk_http.Response(200, json=dict(id='test', type='message', role='assistant',
                    model=payload['model'], content=[{'type': 'text', 'text': answer}],
                    stop_reason='end_turn', usage=dict(input_tokens=10, output_tokens=20)))
            return httpx.Response(200, json={'message': {'content': answer}})
        sdk_http = getattr(_base_client, 'httpx2', None) or _base_client.httpx
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http, \
                sdk_http.AsyncClient(transport=sdk_http.MockTransport(handler)) as sdk_transport:
            client = anthropic.AsyncAnthropic(api_key='synthetic', http_client=sdk_transport)
            monkeypatch.setattr(llm, '_shared_anthropic', lambda: client)
            monkeypatch.setattr(llm, '_shared_async_client', lambda: http)
            meter = cloud_meter.start()
            result = await context_agent.assess_live_context(session, 'Scene: blue cup; step: choosing.')
            assert result['context'] == 'Blue cup on table.'
            cloud = claude and not private
            assert requests[0][0] == ('api.anthropic.com' if cloud else '127.0.0.1')
            assert requests[0][1]['model'] == ('claude-haiku-5-5-test' if cloud else llm.local_model())
            assert meter.calls == int(cloud)
            assert 'NEVER-SEND-RAW-FRAME' not in json.dumps(requests)
    asyncio.run(trial())


def test_builder_hazards_are_fixed_stops_even_after_word_limit(monkeypatch):
    async def trial():
        from server.safety import before
        privacy.set_call({'google': True})
        session = Session('hazard', camera=False)
        session.context_agent = ContextAgent(session)
        emitted, fixed, wire = [], [], []
        async def emit(msg):
            emitted.append(msg)
        async def speak(line):
            fixed.append(line)
        async def send(raw):
            wire.append(json.loads(raw))
        bridge = LiveBridge(session, None, None, emit, speak)
        bridge.ws, bridge.active = SimpleNamespace(send=send), True
        async def assess(session, evidence):
            return {'context': 'cup ' * 130, 'hazard': 'smoking charger'}
        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        builder = context_agent.LiveContextBuilder(session, bridge.publish_context, bridge.stop,
                                                   lambda text: bridge.stop_line(text, True))
        await builder.build()
        assert fixed == [before('smoking charger')]
        assert bridge.blocked and not builder.block
        assert not any(m['clientContent']['turns'] for m in wire if 'clientContent' in m)
    asyncio.run(trial())


@pytest.mark.parametrize('summary,hazard,gate', [
    ('The user is repairing headphones and asks, "Okay, what is the next step?" '
     'The headphones, cord and plug are on a clear desk. Next, inspect the cable. '
     'Keep hands dry and keep water away from cords and plugs.', '', None),
    ('Make sure there is no water near the cord.', '', None),
    ('There is no water near the cord.', '', None),
    ('The charger is not smoking.', '', None),
    ("Never touch a wet plug; don't touch the outlet.", '', None),
    ('Avoid water near the cord.', '', None),
    ('Keep the plug dry.', '', None),
    ('Check whether the charger is smoking.', '', None),
    ('The plan mentions opening a power supply.', '', None),
    ('The charger is smoking.', '', None),
    ('Water is pooling around the plug.', '', None),
    ('There is no water near the cord, but the charger is smoking.', '', None),
    ('Keep hands dry; the charger is smoking.', '', None),
    ('The charger is smoking; do not touch it.', '', None),
    ('The headphone wire is plugged into a phone during cable repair.', '', None),
    ('The wire is still live.', '', None),
    ('Repairing headphones.', 'The wire is plugged in.', None),
    ('Repairing a USB cable.', 'Water near the cord.', None),
    ('Wiring an Arduino.', 'The wire is still live.', None),
    ('Repairing a 9 V battery circuit.', 'The wire is still live.', None),
    ('Repairing a battery powered circuit at 11.1 volts.', 'The wire is still live.', None),
    ('Repairing a 12 V battery circuit.', 'The wire is still live.', 'live_power'),
    ('The desk is clear.', 'The wire is not live.', None),
    ('The desk is clear.', 'Check whether the wire is live.', None),
    ('The desk is clear.', 'The wire is still live.', 'live_power'),
    ('The desk is clear.', 'No water near the cord; the charger is smoking.', 'burning_device'),
    ('The desk is clear.', 'water near the cord', 'water_electric'),
    ('The desk is clear.', 'opening a power supply', 'open_power_supply'),
])
def test_builder_only_explicit_present_hazards_outside_low_voltage(monkeypatch, summary, hazard, gate):
    async def trial():
        from server import safety
        privacy.set_call({'google': True})
        session = Session('headphone-next-step', camera=False)
        session.context_agent = ContextAgent(session)
        published, fixed = [], []
        async def publish(block):
            published.append(block)
            return True
        async def stop(line):
            fixed.append(line)
        async def assess(session, evidence):
            return {'context': summary, 'hazard': hazard}
        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        bridge = LiveBridge(session, None, None, stop, stop)
        builder = context_agent.LiveContextBuilder(
            session, publish, stop, lambda text: bridge.stop_line(text, True))
        await builder.build()
        if gate:
            assert fixed == [next(g.line for g in safety.GATES if g.id == gate)]
            assert not published and not builder.block
        else:
            assert not fixed
            assert published and builder.block == published[0]
    asyncio.run(trial())


def test_live_publishes_context_while_next_build_waits_and_cancels_on_close(monkeypatch):
    from websockets.asyncio.server import serve
    from server.test_live_streaming import audio_content

    async def trial():
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic')
        monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '1')
        privacy.set_call({'google': True})
        wire, emitted = [], []
        published, waiting, cancelled, heard = [asyncio.Event() for _ in range(4)]
        calls = 0
        async def assess(session, evidence):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {'context': 'A blue cup. Next: choose a cup.', 'hazard': ''}
            waiting.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        async def fake(ws):
            wire.append(json.loads(await ws.recv()))
            await ws.send('{"setupComplete": {}}')
            async for raw in ws:
                msg = json.loads(raw)
                wire.append(msg)
                if msg.get('clientContent', {}).get('turns'):
                    published.set()
                if 'text' in msg.get('realtimeInput', {}):
                    await ws.send(json.dumps(audio_content('Use the blue cup.')))
                    await ws.send(json.dumps(audio_content()))
        async def emit(msg):
            emitted.append(msg)
            if msg['type'] == 'audio' and msg['pcm16_b64']:
                heard.set()
        async def discover():
            return 'models/fake'
        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(Session('context-wire', camera=False), None, None, emit, emit,
                discover=discover, endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            assert await bridge.start()
            builder = bridge.context_builder
            builder.interval = .05
            try:
                await asyncio.wait_for(published.wait(), 1)
                await asyncio.wait_for(waiting.wait(), 1)
                assert builder.block.endswith('A blue cup. Next: choose a cup.')
                started = monotonic()
                await bridge.audio('AAA=', final=True)
                await bridge.text('What next?')
                await asyncio.wait_for(heard.wait(), .7)
                assert monotonic() - started < .7 and not cancelled.is_set()
                context = next(m['clientContent'] for m in wire if 'clientContent' in m)
                assert context['turnComplete'] is False
                assert len(context['turns'][0]['parts'][0]['text']) < 1200
                privacy.update('google', False)
                assert not await bridge.publish_context('must stay local')
            finally:
                await bridge.close()
            assert cancelled.is_set() and builder.task.done()
            assert bridge.session.live_context is None
    asyncio.run(trial())


def test_scene_prose_cannot_stop_without_explicit_hazard(monkeypatch):
    async def trial():
        from server.safety import before
        session = Session('scene-prose', camera=True)
        session.scene = {'caption': 'The wire is still live.'}
        published, fixed = [], []
        async def assess(*args):
            return {'context': 'Inspecting the wire.', 'hazard': ''}
        async def publish(block):
            published.append(block)
            return True
        async def stop(line):
            fixed.append(line)
        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        builder = context_agent.LiveContextBuilder(session, publish, stop, before)
        await builder.build()
        assert published and not fixed
    asyncio.run(trial())
