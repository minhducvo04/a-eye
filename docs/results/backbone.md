# Backbone result

Implemented shared-token authentication for both WebSockets and all `/api/*` paths, contract-checked scene and market REST endpoints, parallel cached dependency status, offline mock vision/brain/voice/STT, structured metadata logs, browser token forwarding, and mock/tunnel Make targets. Contracts remain unchanged at v2.2.

## Files changed

- `server/app.py`: auth middleware, router registration, mock wiring and startup warning.
- `server/ws2.py`: connection auth and event logging only.
- `server/api.py`: scene/market validation and proxying; status checks (2-second per-dependency timeout, parallel execution, 10-second cache).
- `server/auth.py`: constant-time shared-secret comparison.
- `server/logs.py`: JSON metadata events, session hashes, Uvicorn query-token redaction.
- `server/mock.py`: in-process FakeBackend, deterministic drawing/speech, generated PCM tones, fixed STT; first-frame barrier for immediate phone turns.
- `server/test_backbone.py`: 19 offline boundary/regression checks.
- `client-web/agent.js`, `client-web/call.js`: one token-forwarding line each.
- `.env.example`, `Makefile`: environment names, `make mock`, quick-tunnel instructions.
- `RESULT.md`: this handoff.

## Phone use

Run `make mock`, then open `/agent.html?token=...` using the value configured as `A_EYE_TOKEN`. Native clients can use the same query or an Authorization Bearer header. `/health` is public; `/api/status` reports mock/live mode and dependency readiness. Mock audio requires hello `tts: "server"`; mock microphone input requires `stt: "server"`. Use the general pack for the unconstrained demo; PC power confirmation and refusal gates still apply.

## Limits

- Internal provider fallbacks swallowed by unowned `server/llm.py` are not observable from the permitted socket log hooks. Observable TTS/STT fallbacks and status-check brain fallback are logged. Turns that return at the existing safety gate do not emit v2 metrics, so they have no metrics-based turn-end event. Completing internal provider telemetry needs an integrator change to that owner’s files.
- Live status uses cheap health/model-list checks; it does not prove inference or synthesis succeeds. External services and physical iPhone playback were not tested. Market uses its existing configured provider (fixture by default).
- A real localhost Uvicorn smoke attempt was blocked by sandbox port-binding restrictions. The escalation was rejected by the approval system. In-process TestClient HTTP/WebSocket integration runs passed, including complete mock audio turns.
- Files are unstaged. No commit, push, publication, global settings, or trust-store changes.

## Verification

Test: .venv/bin/python -m pytest -q - PASS (340 passed in 8.72s)
Test: node --test client-web/ - PASS (60 passed, 0 failed)
Test: git diff --check - PASS (no whitespace errors)

The first focused run found a missing required v1 hello field in the test fixture; corrected before the full run. A subsequent immediate-frame regression exposed missing initial grounding; the mock first-scene barrier fixes it, and the final full suite includes that regression. The status timeout test exercises all five stalled dependencies together and verifies the cached failure report.
