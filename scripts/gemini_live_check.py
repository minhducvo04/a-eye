#!/usr/bin/env python3
"""One real Live session with a synthetic blue frame; no media is written to disk."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def check():
    from PIL import Image
    from websockets.asyncio.client import connect
    from server import privacy
    from server.gemini_live import discover_model, ENDPOINT, WIRE_LOGGER

    if privacy.local_only():
        print('Private: Google blocked')
        return 2
    privacy.set_call({'google': True})
    try:
        model = await discover_model()
        buffer = io.BytesIO()
        Image.new('RGB', (320, 240), 'blue').save(buffer, 'JPEG')
        async with connect(ENDPOINT + '?key=' + quote(os.environ['GEMINI_API_KEY'], safe=''),
                           open_timeout=10, close_timeout=2, logger=WIRE_LOGGER) as ws:
            await ws.send(json.dumps({'setup': {'model': model,
                'generationConfig': {'responseModalities': ['AUDIO']}, 'outputAudioTranscription': {}}}))
            ready = json.loads(await asyncio.wait_for(ws.recv(), 15))
            if 'setupComplete' not in ready:
                raise ValueError('setup failed')
            started = perf_counter()
            await ws.send(json.dumps({'realtimeInput': {'video': {'mimeType': 'image/jpeg',
                'data': base64.b64encode(buffer.getvalue()).decode()}}}))
            await ws.send(json.dumps({'clientContent': {'turns': [{'role': 'user',
                'parts': [{'text': 'what do you see?'}]}], 'turnComplete': True}}))
            first_audio, reply = None, []
            async with asyncio.timeout(40):
                while True:
                    response = json.loads(await ws.recv())
                    if 'error' in response:
                        raise ValueError('provider error')
                    content = response.get('serverContent', {})
                    if first_audio is None and any('inlineData' in p for p in content.get('modelTurn', {}).get('parts', [])):
                        first_audio = round((perf_counter() - started) * 1000)
                    text = content.get('outputTranscription', {}).get('text')
                    if text:
                        reply.append(text)
                    if content.get('turnComplete'):
                        break
            print('model: ' + model)
            print('first-audio ms: ' + (str(first_audio) if first_audio is not None else 'none'))
            print('reply text: ' + ''.join(reply))
            return 0 if first_audio is not None and reply else 1
    except Exception:
        # Provider exceptions may include the key in their request URL. Never print them.
        print('Live check failed (discovery, connection or reply unavailable)')
        return 1


def main():
    if not os.environ.get('GEMINI_API_KEY'):
        print('not configured')
        return 2
    return asyncio.run(check())


if __name__ == '__main__':
    raise SystemExit(main())
