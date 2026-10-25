#!/usr/bin/env python3
"""Live prefetch timing probe; synthetic media only, never saved.

Default: real loopback WebSocket, fake Live and delayed Rewind.
--live: real gemini-3.8-live, synthetic Rewind (requires exported GEMINI_API_KEY).
--live --rewind --vision URL: also upload/index/delete one synthetic mug clip with
TwelveLabs and confirm it on our vision host (requires TWELVELABS_API_KEY).
No .env is read. Fact timing means a matching output transcript, not speaker playback.
"""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import privacy  # noqa: E402
from server.agent import Session  # noqa: E402
from server.gemini_live import LiveBridge  # noqa: E402


def audio(text):
    return {'serverContent': {'outputTranscription': {'text': text}, 'modelTurn': {'parts': [
        {'inlineData': {'mimeType': 'audio/pcm;rate=24000',
                        'data': base64.b64encode(b'\x01\x00' * 3600).decode()}}]}}}


async def probe(args):
    from websockets.asyncio.server import serve
    from server.rewind import Rewind
    from server.ws2 import SceneClient
    from scripts.rewind_probe import scene

    if args.live and not os.getenv('GEMINI_API_KEY'):
        print('SKIP: GEMINI_API_KEY is not exported; no cloud call made.')
        return 2
    if args.rewind and not os.getenv('TWELVELABS_API_KEY'):
        print('SKIP: TWELVELABS_API_KEY is not exported; no cloud call made.')
        return 2
    if privacy.local_only():
        print('SKIP: Private mode or cloud budget blocks Live.')
        return 2
    os.environ['LIVE_CONTEXT_ENABLED'] = '0'
    if not args.live:
        os.environ['GEMINI_API_KEY'] = 'synthetic'
        os.environ['ROUTER'] = 'off'
    privacy.set_call({'google': True, 'twelvelabs': True, 'claude': False, 'cartesia': False})
    session = Session('live-prefetch-probe', camera=False)
    question = ('Where was the blue mug earlier in this call?' if args.rewind
                else 'Where was the resistor earlier in this call?')
    fact = re.compile(args.fact_text or (r'\b(seconds|minute|start of the call)\b' if args.rewind
                                       else r'\brow\s*(12|twelve)\b'), re.I)
    timings, counts = {}, {'searches': 0, 'tools': 0, 'mid_reply_context': 0}
    card, done = asyncio.Event(), asyncio.Event()
    began = None
    output = ''
    fake_server = bridge = real_rewind = None
    vision = SceneClient(args.vision) if args.rewind else None

    def mark(name):
        if began is not None:
            timings.setdefault(name, round((monotonic() - began) * 1000, 2))

    async def emit(msg):
        nonlocal output
        if msg['type'] == 'rewind_hit':
            mark('card_ms')
            card.set()
        if msg['type'] == 'audio' and msg['pcm16_b64']:
            mark('first_audio_ms')
        if msg['type'] == 'reply_delta':
            output += msg['text']
            if fact.search(output):
                mark('fact_transcript_ms')
        if msg['type'] == 'turn' and msg['stage'] == 'done' and 'fact_transcript_ms' in timings:
            done.set()

    async def fixed(line):
        raise RuntimeError('Live fallback or code stop')

    async def answer(text, vision=None, before_s=None):
        counts['searches'] += 1
        mark('search_start_ms')
        await asyncio.sleep(args.delay)
        return 'At 0:30 in this call, the resistor was on row 12.', dict(
            sure=True, t_s=30, start_s=28, end_s=32, alternatives=[], objects=[])

    async def fake(ws):
        setup = json.loads(await ws.recv())['setup']
        assert all(d['behavior'] == 'NON_BLOCKING' for d in setup['tools'][0]['functionDeclarations'])
        await ws.send('{"setupComplete": {}}')
        await ws.recv()
        await ws.send(json.dumps({'serverContent': {'inputTranscription': {'text': 'Where was the '}}}))
        await asyncio.sleep(.05)
        await ws.send(json.dumps({'serverContent': {'inputTranscription': {
            'text': 'resistor earlier in this call?'}}}))
        await ws.send(json.dumps(audio('Let me check. ')))
        await asyncio.wait_for(card.wait(), 5)
        await ws.send(json.dumps({'toolCall': {'functionCalls': [dict(
            id='recall', name='recent_memory', args={'question': question})]}}))
        started = monotonic()
        response = json.loads(await ws.recv())
        assert 'toolResponse' in response
        timings['cache_tool_ms'] = round((monotonic() - started) * 1000, 2)
        result = response['toolResponse']['functionResponses'][0]['response']
        assert result['scheduling'] == 'WHEN_IDLE'
        await ws.send(json.dumps(audio(result['result'])))
        await ws.send('{"serverContent": {"turnComplete": true}}')
        evidence = json.loads(await ws.recv())
        assert evidence['clientContent']['turnComplete'] is False
        await ws.wait_closed()

    try:
        if args.rewind:
            clock = [0.0]
            real_rewind = Rewind(session.session_id, clock=lambda: clock[0])
            session.rewind = real_rewind
            real_rewind.set_on(True)
            for i in range(24):
                clock[0] = i / 4
                real_rewind.add_frame(scene('mug', clock[0]))
                if i == 8:
                    real_rewind.keyframe('probe')
            real_rewind.close()
            await real_rewind.flush(wait=True, timeout=60)
            if not any(c.status == 'ready' for c in real_rewind.clips):
                raise RuntimeError('Synthetic clip not ready')
            clock[0] = 40  # eligible for the recent-memory 20-second indexing guard
            original = real_rewind.answer

            async def measured(*a, **kw):
                counts['searches'] += 1
                mark('search_start_ms')
                return await original(*a, **kw)

            real_rewind.answer = measured
        else:
            session.rewind = SimpleNamespace(on=True, now_s=lambda: 240, answer=answer)

        kwargs = {}
        if not args.live:
            fake_server = await serve(fake, '127.0.0.1', 0)

            async def discover():
                return 'models/gemini-3.8-live'

            kwargs = dict(discover=discover,
                          endpoint=f'ws://127.0.0.1:{fake_server.sockets[0].getsockname()[1]}')
        else:
            os.environ['GEMINI_LIVE_MODEL'] = 'gemini-3.8-live'
        bridge = LiveBridge(session, vision, None, emit, fixed, **kwargs)
        original_tool, original_publish = bridge.tool, bridge.publish_context

        async def tool(call):
            counts['tools'] += 1
            mark('tool_call_ms')
            return await original_tool(call)

        async def publish(block):
            generating = bridge.generating
            sent = await original_publish(block)
            if sent and generating:
                counts['mid_reply_context'] += 1
            if sent:
                mark('context_ms')
            return sent

        bridge.tool, bridge.publish_context = tool, publish
        if not await bridge.start():
            raise RuntimeError('Live setup unavailable')
        began = monotonic()
        if args.live:
            await bridge.text(question)
        else:
            await bridge._input({'realtimeInput': {'text': 'start synthetic transcript'}})
        await asyncio.wait_for(done.wait(), 40)
        await asyncio.sleep(.05)
        passed = (counts['mid_reply_context'] == 0 and all(
            k in timings for k in ('card_ms', 'first_audio_ms', 'fact_transcript_ms')))
        if not args.live:
            passed = passed and counts['searches'] == 1 and timings.get('cache_tool_ms', 1000) < 100
        print(json.dumps(dict(mode='real-live' if args.live else 'loopback',
            rewind='real-synthetic-clip' if args.rewind else 'synthetic-adapter',
            status='PASS' if passed else 'FAIL', timings=timings, **counts), sort_keys=True))
        return 0 if passed else 1
    except Exception as error:
        print(json.dumps(dict(status='FAIL', error=type(error).__name__, timings=timings, **counts)))
        return 1
    finally:
        if bridge:
            await bridge.close()
        if fake_server:
            fake_server.close()
            await fake_server.wait_closed()
        if real_rewind:
            await real_rewind.forget()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--rewind', action='store_true')
    parser.add_argument('--vision', default='http://127.0.0.1:8001')
    parser.add_argument('--delay', type=float, default=.6)
    parser.add_argument('--fact-text', help='Regex identifying evidence in the synthetic answer transcript')
    args = parser.parse_args()
    if args.rewind and not args.live:
        parser.error('--rewind requires --live')
    if not args.live:
        # Fake transport has no billable calls; keep its accounting off the real daily ledger.
        with TemporaryDirectory(prefix='aeye-prefetch-') as directory:
            os.environ['CLOUD_BUDGET_PATH'] = str(Path(directory) / 'fake-budget.sqlite3')
            return asyncio.run(probe(args))
    return asyncio.run(probe(args))


if __name__ == '__main__':
    raise SystemExit(main())
