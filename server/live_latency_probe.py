"""Synthetic question -> LiveBridge -> loopback client first-PCM timings.

No media or transcripts are saved. --real uses the consented Gemini key inherited
from make; --bridge-source permits comparison with a saved pre-change module.
"""
import argparse
import asyncio
import base64
from contextlib import AsyncExitStack
import importlib.util
import json
import os
import tempfile
from statistics import median
from time import monotonic

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from server import cloud_meter, gemini_live, privacy
from server.agent import Session


async def trial(bridge_class, real=False):
    times = {}
    ready = asyncio.Event()
    bridge = None
    async def fake(ws):
        await ws.recv()
        await ws.send('{"setupComplete": {}}')
        async for raw in ws:
            if 'text' not in json.loads(raw).get('realtimeInput', {}):
                continue
            await asyncio.sleep(.05)
            for i in range(8):
                content = {'modelTurn': {'parts': [{'inlineData': {
                    'mimeType': 'audio/pcm;rate=24000',
                    'data': base64.b64encode(b'\x01\x00' * 3600).decode()}}]}}
                if i == 1:
                    content['outputTranscription'] = {'text': 'A blue cup is on the table.'}
                await ws.send(json.dumps({'serverContent': content}))
                await asyncio.sleep(.15)
            await asyncio.sleep(.5)
            await ws.send('{"serverContent": {"turnComplete": true}}')

    async def relay(ws):
        nonlocal bridge
        privacy.set_call({'google': True})
        async def emit(msg):
            await ws.send(json.dumps(msg))
        async def fixed(line):
            raise RuntimeError('unexpected fixed response')
        options = {}
        if not real:
            async def discover():
                return 'models/synthetic-live'
            options = dict(discover=discover, endpoint=provider)
        bridge = bridge_class(Session('latency-probe', camera=False), None, None, emit, fixed, **options)
        original = bridge.handle
        async def handle(response):
            content = response.get('serverContent', {})
            if any('inlineData' in p for p in content.get('modelTurn', {}).get('parts', [])):
                times.setdefault('provider_audio', monotonic())
            if content.get('turnComplete'):
                times['provider_complete'] = monotonic()
            await original(response)
        bridge.handle = handle
        try:
            if not await bridge.start():
                ready.set()
                await ws.close()
                return
            ready.set()
            await ws.recv()
            times['started'] = monotonic()
            await bridge.text('In two short sentences, describe what a blue cup can be used for.')
            await ws.wait_closed()
        finally:
            await bridge.close()

    async with AsyncExitStack() as stack:
        if not real:
            server = await stack.enter_async_context(serve(fake, '127.0.0.1', 0, logger=gemini_live.WIRE_LOGGER))
            provider = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
        server = await stack.enter_async_context(serve(relay, '127.0.0.1', 0, logger=gemini_live.WIRE_LOGGER))
        client = await stack.enter_async_context(connect(f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}',
                                                         logger=gemini_live.WIRE_LOGGER))
        async with asyncio.timeout(45):
            await ready.wait()
            await client.send('start')
            while True:
                msg = json.loads(await client.recv())
                if msg['type'] == 'audio' and msg['pcm16_b64']:
                    times.setdefault('client_audio', monotonic())
                if msg.get('stage') == 'done':
                    break
        await client.close()
    if 'client_audio' not in times:
        raise RuntimeError('no client PCM')
    return {name + '_ms': round((times[name] - times['started']) * 1000, 1)
            for name in ('provider_audio', 'client_audio', 'provider_complete')}


async def run(args):
    privacy.set_call({'google': True})
    os.environ['LIVE_CONTEXT_ENABLED'] = '0'  # isolate the playback bottleneck
    if not args.real:
        os.environ['GEMINI_API_KEY'] = 'synthetic'
    bridge_class = gemini_live.LiveBridge
    if args.bridge_source:
        spec = importlib.util.spec_from_file_location('live_before', args.bridge_source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        bridge_class = module.LiveBridge
    rows = []
    for _ in range(args.trials):
        rows.append(await trial(bridge_class, args.real))
    result = dict(mode='real' if args.real else 'fake', trials=rows,
                  p50={k: round(median(row[k] for row in rows), 1) for k in rows[0]})
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--bridge-source')
    args = parser.parse_args()
    if args.real and not os.getenv('GEMINI_API_KEY'):
        print('Live latency probe: not configured (GEMINI_API_KEY absent)')
        return 2
    if args.real and cloud_meter.BUDGET.exhausted():
        print('Live latency probe: blocked by existing daily cloud budget; no provider call made')
        return 2
    if args.real and os.getenv('LOCAL_ONLY') == '1':
        print('Live latency probe: blocked by LOCAL_ONLY; no provider call made')
        return 2
    try:
        if args.real:
            asyncio.run(run(args))
        else:
            # Fake transport must neither consume the real daily cap nor depend
            # on its current balance. Real runs always retain the owner's cap.
            with tempfile.TemporaryDirectory(prefix='aeye-live-probe-') as directory:
                os.environ['CLOUD_BUDGET_PATH'] = directory + '/synthetic-budget.sqlite3'
                asyncio.run(run(args))
    except Exception:
        # Provider exceptions can contain the key-bearing URL. Never print them.
        print('Live latency probe: unavailable (connection, consent, budget or reply)')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
