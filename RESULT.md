# Rewind result

Rewind is a memory of the call built on TwelveLabs video search. It is off by default.

## Files
- `server/rewind.py`: clip ring and keyframe clips, ffmpeg MP4 encoding (temp file deleted after upload), plain-HTTP TwelveLabs v1.3 client (indexes, tasks, search), `Registry` of recent calls, `rewind_turn` (spoken answer plus `rewind_hit`), and a local-vision check of the rank-1 frame.
- `server/rewind_api.py`: `GET /api/rewind/status`, `POST /api/rewind/search`, `POST /api/rewind/flush`, all behind the `/api` token check.
- `server/ws2.py`: small hooks for `hello.rewind`, the `rewind` message, frames into the ring, keyframes cutting clips, Rewind questions routed to `rewind_turn`, and the rest uploaded at the end of the call. `server/app.py` includes the router.
- `contracts/*`: v2.5 (v2.4 is phone pairing), additive: `v2_hello.rewind`, `v2_rewind`, `v2_rewind_state`, `v2_rewind_hit`.
- `client-web/rewind.js` (+ test), `agent.html/js/css`: the Rewind switch in Settings with the TwelveLabs notice, a "Rewind on" badge, and an answer sheet that shows the frame with the object boxed and the call time.
- `scripts/rewind_probe.py`, `scripts/rewind_ws_check.py`: the real-run scripts. `conftest.py` clears `TWELVELABS_API_KEY`; `.env.example` lists the name.

## Limits
- TwelveLabs v1.3 search returns a rank but no score. Our own vision host checks the rank-1 frame. If it does not confirm the object, the talker says it is not sure and gives the top 2 times.
- The tasks upload endpoint is marked deprecated (still served).
- Clips come from camera frames only, with no audio and no face or person tagging. Rewind state lives in memory per server process, for the last 5 calls.

Test: .venv/bin/python -m pytest -q - PASS (420 passed; test_backbone timing test flaked once under load, passes alone)
Test: node --test client-web/ - PASS (90 passed)
Test: make browser-smoke URL=http://127.0.0.1:8438 - PASS (server with A_EYE_TOKEN unset; the smoke script sends no token)
