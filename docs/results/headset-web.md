# Headset web — ready for lead review

Implemented, uncommitted. No server or contract changes.

- `client-web/headset.js`: visionOS / Vision Pro UA detection plus reliable `?device=headset` override; video capture boundary rejects headset video requests.
- `client-web/agent.js`, `agent.html`, `agent.css`: waiting panel, one-tap pairing/QR sheet, connected dark canvas with existing drawings, explicit Safari sound unlock, larger controls/text, reduced motion, Settings “Works with” lines. Headset URLs cannot enter phone-camera boot. Camera start/retry/swap and Settings permissions cannot acquire video. Phone pairing stops local mic and Settings preview; disconnect restores a previously active mic.
- `client-web/headset.test.mjs`, `turn.test.mjs`: detection, capture boundary and actual call-page handler regression coverage, with desktop camera behavior retained.
- `client-web/headset_smoke.py`: reproducible Chromium integration using a visionOS Safari UA and a second real phone page with synthetic media.
- Demo instructions: [headset-demo.md](../headset-demo.md). Screenshots: [waiting](headset-web/waiting.png), [connected with drawings](headset-web/connected.png).

Test: `node --test client-web/*.test.mjs` - PASS (135 tests). After final sound-button addition: `node --test client-web/turn.test.mjs client-web/headset.test.mjs` - PASS (11 tests).

Test: `uv run --no-project --with playwright python scripts/browser_smoke.py http://127.0.0.1:18741` - PASS (2 camera frames; no problems; longest task after find card 0 ms).

Test: `uv run --no-project --with playwright python client-web/headset_smoke.py http://127.0.0.1:18741` - PASS (UA-only detection and explicit override, QR, phone joins and sends frames, no headset video requests, mic handoff, no Settings mic while paired, kick and second-call reset, sound button, no page errors).

Browser setup: existing Python environment from `/Users/minhducvo/Projects/a-eye/.venv`; local server on 18741 with `A_EYE_MOCK=1`, `LOCAL_ONLY=1`, `A_EYE_MEMORY_DIR=/private/tmp/aeye-headset-memory`, fake vision service on 18742. No real media or cloud model used. Screenshots contain synthetic/mock content only.

Limits: the existing protocol sends phone frames to the server, not back to the call page, so this uses the requested dark-canvas fallback. The integration used code pairing against an unauthenticated local mock server; remembered-phone same-identity behavior was inspected in `server/test_phone_remember.py`, not exercised through live Access sign-in. A paired phone is treated as the mic source because the protocol does not report mic availability separately. Physical Vision Pro Safari, gaze/pinch, and audible playback still need device verification; Chromium UA emulation is not device proof. Safari may present a Mac UA, so use the documented URL flag.
