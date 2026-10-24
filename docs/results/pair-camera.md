# Pair camera

Implemented phone camera pairing within the owned files. No contracts or device-picker code changed. Nothing pushed or published; changes are unstaged.

## Files changed

- `server/pairing.py`: process-wide random four-digit codes, 300-second expiry, single-use redemption, replacement, restricted camera socket, status notifications and hashed-session event logs. Retired codes cannot be reissued during their original lifetime.
- `server/ws2.py`: pairing hooks, shared session frame routing, source changes and disconnect cleanup. Call speech remains on the call socket; local camera state is restored when the phone leaves.
- `server/test_pairing.py`: real TestClient WebSocket pairs with synthetic frames and fake dependencies; scene-loop routing, sequence/data checks, speech isolation, camera toggles, fallback, reused/unknown/expired/replaced codes, call closure, authentication and log-field checks. Fake clock; no network.
- `client-web/pair.js`: call pairing controls and isolated phone-only entry, token-preserving links, tap-to-start camera, shared JPEG frame encoder, camera toggle and disconnect handling.
- `client-web/qr.js`: self-contained byte-mode QR encoder, ECC L, versions 1–5, quiet zone and local canvas rendering; no network/CDN.
- `client-web/pair.test.mjs`: URL/mode/status checks, QR dimensions/finder patterns/capacity, and executable phone-entry lifecycle test with mocked camera/WebSocket.
- `client-web/agent.html`, `client-web/agent.js`: small settings controls and module hooks.
- `RESULT.md`: this handoff.

## Verification

Test: node --test client-web/ - PASS (84 tests, 84 passed, 0 failed, 0 skipped)
Test: .venv/bin/python -m pytest -q - PASS (410 passed in 15.00s)

Earlier focused pairing run: 3 passed in 1.10s. First full Python run: 410 passed in 14.51s. Final diff whitespace check passed. TestClient exercised the real socket/session/scene-loop boundary; a disconnect test exposed cancellation interrupting the left notification, now protected during cleanup.

## Limits

- Registry is process-local: both devices must reach the same server worker. One active phone camera per call; reconnecting needs a fresh code.
- QR supports at most 106 UTF-8 bytes. Longer links (including long tokens) remain visible and copyable with an explanatory message instead of a QR.
- Real iOS camera permissions and optical QR scanning were not tested on hardware. QR tests check structure, not decoding. Phone capture requires HTTPS outside localhost.
- Pairing sends phone frames to the call's server-side session; it does not relay a phone video preview back to the call page.
