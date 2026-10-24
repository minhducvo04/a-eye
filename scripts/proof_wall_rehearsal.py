"""Five real loopback WS/HTTP trials with temporary text-only yesterday memory.

Uses the production server and configured LAN services, never a user's memory. No media is saved.
Missing Kokoro produces SKIP, not fabricated first-audio timing. Internet stays connected; assert zero cloud AI calls and payload bytes.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import uvicorn
from websockets.asyncio.client import connect

from scripts.offline_check import seed


async def main():
    os.environ.update(LOCAL_ONLY='1', A_EYE_TOKEN=secrets.token_urlsafe(32), ROUTER='off', A_EYE_MOCK='0')
    from server.app import create_app
    from server.auth import mint_owner
    from server.memory import Memories
    from server import safety
    app = create_app()
    owner = mint_owner()
    headers = {'Authorization': 'Bearer ' + os.environ['A_EYE_TOKEN'], 'X-Aeye-Owner': owner}
    with tempfile.TemporaryDirectory(prefix='proof-rehearsal-') as folder:
        app.state.memories = Memories(base=folder)
        store = app.state.memories.for_owner('token:' + hashlib.sha256(owner.encode()).hexdigest())
        store.save_settings(dict(consent=dict(person=True, caregiver=True), remembering=True,
                                 items=[dict(item='keys', home='blue tray')], rooms=['kitchen'], kept_days=7))
        seed(store)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        passed = skipped = 0
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    await asyncio.sleep(.05)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', headers=headers) as http:
                for trial in range(1, 6):
                    sid = f'proof-{trial}'
                    async with connect(f'ws://127.0.0.1:{port}/ws2', additional_headers=headers) as ws:
                        await ws.send(json.dumps(dict(v=2, type='hello', session_id=sid, private=True,
                                                      pack='general', camera=False, rewind=False)))
                        async with asyncio.timeout(15):
                            while json.loads(await ws.recv()).get('type') != 'agent_state':
                                pass
                        ok, audible = True, True
                        for name, question in [('yesterday', 'Where did I leave my keys yesterday?'),
                                               ('safety', 'My power strip is smoking. Is it safe?')]:
                            began, first, answer, messages = monotonic(), None, None, []
                            await ws.send(json.dumps(dict(v=2, type='user_text', session_id=sid,
                                                          text=question, final=True)))
                            async with asyncio.timeout(45):
                                while True:
                                    msg = json.loads(await ws.recv())
                                    messages.append(msg)
                                    if msg['type'] == 'audio' and msg.get('pcm16_b64') and first is None:
                                        first = (monotonic() - began) * 1000
                                    if msg['type'] == 'say' and msg.get('final'):
                                        answer = (monotonic() - began) * 1000
                                    if msg['type'] == 'turn' and msg['stage'] in ('done', 'failed'):
                                        break
                            said = ' '.join(m['text'] for m in messages if m['type'] == 'say')
                            valid = (any(m['type'] == 'find_item' and m.get('found') for m in messages)
                                     and 'yesterday' in said.lower()) if name == 'yesterday' else (
                                     any(m.get('detail') == 'Stopped by code' for m in messages)
                                     and any(line in said for line in safety.LINES))
                            ok &= valid
                            audible &= first is not None
                            timing = f'{first:.0f}ms' if first is not None else 'SKIP (Kokoro audio unavailable)'
                            print(f'trial {trial} {name}: {"PASS" if valid else "FAIL"}; '
                                  f'first_audio={timing}; answer={answer:.0f}ms' if answer is not None else
                                  f'trial {trial} {name}: FAIL no final answer', flush=True)
                        response = await http.get('/api/proof', params={'session_id': sid})
                        response.raise_for_status()
                        proof = response.json()
                        cloud_ok = proof.get('cloud_ai_calls') == 0 and proof.get('bytes_to_cloud') == 0
                        ok &= cloud_ok
                        print(f'trial {trial} Cloud AI calls: {proof.get("cloud_ai_calls")}; '
                              f'Bytes to cloud: {proof.get("bytes_to_cloud")}; '
                              f'{"PASS" if cloud_ok else "FAIL"}', flush=True)
                        count = proof['pictures_saved']
                        ok &= isinstance(count, int)
                        print(f'trial {trial} pictures: {count}; '
                              f'{"PASS" if ok and audible else "SKIP audio" if ok else "FAIL"}', flush=True)
                        passed += int(ok and audible)
                        skipped += int(ok and not audible)
        finally:
            server.should_exit = True
            await task
            sock.close()
        print(f'REHEARSAL: {passed}/5 PASS, {skipped}/5 SKIP (missing local audio), '
              f'{5 - passed - skipped}/5 FAIL; text fixture removed')
        return 0 if passed == 5 else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
