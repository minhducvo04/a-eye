"""Synthetic Live transport regressions: tools must not hold the audio reader."""
import asyncio
import json
from time import monotonic
from types import SimpleNamespace

import pytest

from websockets.asyncio.server import serve

from server import privacy
from server.agent import Session
from server.gemini_live import LiveBridge
from server.test_live_streaming import audio_content
from server.live_prefetch import Prefetch


def test_slow_tool_does_not_delay_audio(monkeypatch):
    async def trial():
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic')
        monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '0')
        privacy.set_call({'google': True})
        started, audio, release, replied = (asyncio.Event() for _ in range(4))
        wire = []

        async def slow(call):
            started.set()
            await release.wait()
            return 'The resistor was on row 12.'

        async def fake(ws):
            wire.append(json.loads(await ws.recv()))
            await ws.send('{"setupComplete": {}}')
            await ws.send(json.dumps({'toolCall': {'functionCalls': [
                dict(id='slow', name='recent_memory', args={'question': 'Where was the resistor earlier?'})]}}))
            await started.wait()
            await ws.send(json.dumps(audio_content('Let me check.')))
            await ws.send(json.dumps(audio_content()))  # 300 ms PCM clears the 250 ms initial hold.
            async for raw in ws:
                wire.append(json.loads(raw))
                if 'toolResponse' in wire[-1]:
                    replied.set()

        async def emit(msg):
            if msg['type'] == 'audio' and msg['pcm16_b64']:
                audio.set()

        async def discover():
            return 'models/gemini-3.8-live'

        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(Session('slow', camera=False), None, None, emit, emit,
                discover=discover, endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            monkeypatch.setattr(bridge, 'tool', slow)
            assert await bridge.start()
            try:
                await asyncio.wait_for(started.wait(), 1)
                began = monotonic()
                await asyncio.wait_for(audio.wait(), .8)
                assert monotonic() - began < .8 and not release.is_set()
                release.set()
                await asyncio.wait_for(replied.wait(), 1)
                declarations = wire[0]['setup']['tools'][0]['functionDeclarations']
                assert all(d['behavior'] == 'NON_BLOCKING' for d in declarations)
                response = wire[-1]['toolResponse']['functionResponses'][0]
                assert response == dict(id='slow', name='recent_memory', response={
                    'result': 'The resistor was on row 12.', 'scheduling': 'WHEN_IDLE'})
            finally:
                release.set()
                await bridge.close()
    asyncio.run(trial())


def test_streaming_prefetch_card_cache_and_idle_publication(monkeypatch):
    async def trial():
        from contracts import validate
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic')
        monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '0')
        monkeypatch.setenv('ROUTER', 'off')
        privacy.set_call({'google': True, 'twelvelabs': True})
        started, release, card, audio, done = (asyncio.Event() for _ in range(5))
        wire, emitted, searches, timings = [], [], [], {}
        question = 'Where was the resistor earlier?'

        async def answer(text, vision=None, before_s=None):
            searches.append((text, before_s))
            started.set()
            await release.wait()
            return 'At 0:30, on row 12.', dict(sure=True, t_s=30,
                objects=[dict(id='resistor', label='resistor', bbox=[.1, .1, .2, .2], conf=.9)])

        async def fake(ws):
            await ws.recv()
            await ws.send('{"setupComplete": {}}')
            await ws.send(json.dumps({'serverContent': {'inputTranscription': {'text': 'Where was the '}}}))
            await asyncio.sleep(.2)
            assert not searches
            await ws.send(json.dumps({'serverContent': {'inputTranscription': {'text': 'resistor earlier?'}}}))
            await asyncio.wait_for(started.wait(), 1)
            # Lookup began on a partial transcript, before Live output / end of speech.
            assert searches == [(question, 220)]
            await ws.send(json.dumps(audio_content('Let me check.')))
            await ws.send(json.dumps(audio_content()))  # 300 ms PCM clears the 250 ms initial hold.
            await asyncio.wait_for(audio.wait(), 1)
            release.set()
            await asyncio.wait_for(card.wait(), 1)
            # Both tools should consume the same already-delivered evidence with no new search.
            for name, argument in [('recent_memory', 'question'), ('rewind_search', 'query')]:
                began = monotonic()
                await ws.send(json.dumps({'toolCall': {'functionCalls': [
                    dict(id=name, name=name, args={argument: question})]}}))
                response = json.loads(await asyncio.wait_for(ws.recv(), .2))
                timings[name] = monotonic() - began
                wire.append(response)
                assert 'toolResponse' in response  # A mid-reply clientContent would fail here.
                assert response['toolResponse']['functionResponses'][0]['response'] == {
                    'result': 'At 0:30, on row 12.', 'scheduling': 'WHEN_IDLE'}
            await ws.send(json.dumps({'serverContent': {'turnComplete': True}}))
            response = json.loads(await asyncio.wait_for(ws.recv(), 1))
            wire.append(response)
            assert response['clientContent']['turnComplete'] is False
            text = response['clientContent']['turns'][0]['parts'][0]['text']
            assert 'MEMORY v1' in text and 'row 12' in text and 'retrieved' in text
            done.set()
            await ws.wait_closed()

        async def emit(msg):
            validate('server_message_v2', msg)
            emitted.append(msg)
            if msg['type'] == 'rewind_hit':
                card.set()
            if msg['type'] == 'audio' and msg['pcm16_b64']:
                audio.set()

        async def discover():
            return 'models/gemini-3.8-live'

        session = Session('cache', camera=False)
        session.rewind = SimpleNamespace(on=True, now_s=lambda: 240, answer=answer)
        async with serve(fake, '127.0.0.1', 0) as server:
            bridge = LiveBridge(session, None, None, emit, emit, discover=discover,
                endpoint=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            assert await bridge.start()
            try:
                await asyncio.wait_for(done.wait(), 3)
                assert len(searches) == 1
                assert len([m for m in emitted if m['type'] == 'rewind_hit']) == 1
                assert all(t < .1 for t in timings.values())
            finally:
                await bridge.close()
    asyncio.run(trial())


def test_debounce_now_route_and_changed_question(monkeypatch):
    async def trial():
        from server import routing
        privacy.set_call({'google': True})
        routed, looked, ready = [], [], []

        async def route(session, text):
            routed.append(text)
            return 'now' if 'now' in text else 'past'

        async def lookup(text):
            looked.append(text)
            return {'say': text}, []

        async def resolved(*args):
            ready.append(args)

        monkeypatch.setattr(routing, 'route_turn', route)
        prefetch = Prefetch(Session('debounce'), lookup, resolved, debounce=.02)
        try:
            prefetch.feed('Where is it')
            await asyncio.sleep(.03)
            assert not routed
            prefetch.feed('Where is the resistor now?')
            await prefetch.task
            assert not looked
            prefetch.feed('Where was the resistor earlier?')
            prefetch.feed('Where was the blue wire earlier?')
            await prefetch.task
            assert looked == ['Where was the blue wire earlier?']
            prefetch.feed('Where was the blue wire earlier?')
            assert len(ready) == 1
            assert await prefetch.get('where WAS the blue wire earlier') == {'say': looked[0]}
            assert await prefetch.get('Where was the blue wire yesterday?') is None
        finally:
            await prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('action', ['new_turn', 'close', 'privacy'])
def test_late_prefetch_never_publishes_after_cancel_or_revocation(monkeypatch, action):
    async def trial():
        monkeypatch.setenv('ROUTER', 'off')
        privacy.set_call({'google': True})
        started, release = asyncio.Event(), asyncio.Event()
        ready = []

        async def lookup(text):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                pass  # Even a dependency that finishes after cancellation must be discarded.
            return {'say': 'stale'}, []

        async def resolved(*args):
            ready.append(args)

        prefetch = Prefetch(Session('cancel'), lookup, resolved, debounce=0)
        prefetch.feed('Where was the resistor earlier?')
        await asyncio.wait_for(started.wait(), 1)
        task = prefetch.task
        if action == 'new_turn':
            prefetch.new_turn()
        elif action == 'close':
            await prefetch.close()
        else:
            privacy.update('google', False)
            release.set()
        await task
        assert not ready and prefetch.result is None
        await prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('action', ['new_turn', 'barge_in', 'provider_cancel', 'close'])
def test_tool_tasks_cancel_without_late_responses(action):
    async def trial():
        privacy.set_call({'google': True})
        started, cancelled = asyncio.Event(), asyncio.Event()
        wire = []

        async def send(raw):
            wire.append(json.loads(raw))

        async def noop(*args):
            pass

        async def slow(call):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        bridge = LiveBridge(Session('cancel'), None, None, noop, noop)
        bridge.ws = SimpleNamespace(send=send, close=noop)
        bridge.active = True
        bridge.tool = slow
        await bridge.handle({'toolCall': {'functionCalls': [dict(id='pending', name='recent_memory')]}})
        await started.wait()
        if action == 'new_turn':
            await bridge.handle({'serverContent': {'inputTranscription': {'text': 'A new question'}}})
        elif action == 'barge_in':
            await bridge.interrupt()
        elif action == 'provider_cancel':
            await bridge.handle({'toolCallCancellation': {'ids': ['pending']}})
        else:
            await bridge.close()
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not wire
        await bridge.close()
    asyncio.run(trial())


def test_rewind_consent_revocation_blocks_lookup_and_cached_evidence(monkeypatch):
    async def trial():
        monkeypatch.setenv('ROUTER', 'off')
        privacy.set_call({'google': True, 'twelvelabs': True})
        calls, emitted = [], []

        async def answer(*args, **kwargs):
            calls.append(args)
            return 'At 0:30, row 12.', dict(sure=True, t_s=30)

        async def emit(msg):
            emitted.append(msg)

        session = Session('privacy')
        session.rewind = SimpleNamespace(on=True, now_s=lambda: 240, answer=answer)
        bridge = LiveBridge(session, None, None, emit, emit)
        bridge.prefetch.debounce = 0
        question = 'Where was the resistor earlier?'
        bridge.prefetch.feed(question)
        await bridge.prefetch.task
        assert len(calls) == 1 and bridge.prefetch.result['source'] == 'rewind'
        privacy.update('twelvelabs', False)
        emitted.clear()
        result = await bridge.tool(dict(name='recent_memory', args={'question': question}))
        assert 'row 12' not in result and len(calls) == 1 and not emitted
        assert await bridge.tool(dict(name='rewind_search', args={'query': question})) == 'Tool unavailable.'
        await bridge.publish_memory()
        assert bridge.pending_memory is None
        await bridge.prefetch.close()
    asyncio.run(trial())


def test_safety_tool_response_interrupts():
    async def trial():
        privacy.set_call({'google': True})
        wire, fixed = [], []

        async def send(raw):
            wire.append(json.loads(raw))

        async def emit(msg):
            pass

        async def stop(line):
            fixed.append(line)

        bridge = LiveBridge(Session('safety'), None, None, emit, stop)
        bridge.ws = SimpleNamespace(send=send)
        original = bridge.tool
        cancelled = asyncio.Event()

        async def tool(call):
            if call['id'] == 'slow':
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return await original(call)

        bridge.tool = tool
        await bridge.handle({'toolCall': {'functionCalls': [dict(id='slow', name='recent_memory')]}})
        await asyncio.sleep(0)
        await bridge.handle({'toolCall': {'functionCalls': [dict(id='stop', name='find_item',
            args={'name': 'open the electrical panel'})]}})
        await asyncio.gather(*bridge.tool_tasks.values(), return_exceptions=True)
        assert cancelled.is_set() and len(wire) == 1
        response = wire[0]['toolResponse']['functionResponses'][0]['response']
        assert response['scheduling'] == 'INTERRUPT'
        assert fixed == [response['result']] and bridge.blocked
    asyncio.run(trial())
