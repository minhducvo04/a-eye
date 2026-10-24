# Trigger door — lead-review handoff

Implemented in the working tree; **not committed**. Software checks pass. Arduino compilation/upload and physical-device acceptance remain pending: the installed AVR compiler fails on this Mac with `bad CPU type in executable`.

## Scope and files

- `server/trigger.py`: authenticated owner mailbox, POST `/api/trigger`, owner-wide five-second trigger cooldown (429 + Retry-After), status, client polling/acknowledgement, and presence lease renewal. Existing `/api/` token/Access middleware handles auth; trigger routes additionally reject the unauthenticated local/open identity.
- `server/app.py`: exactly one added router-registration line. Dynamic import keeps registration inside the requested one-line integration boundary. **No `server/ws2.py` or contract changes.**
- `client-web/trigger.js`, `client-web/agent.js`: poll only while an agent call is connected; deduplicate wakes; start the existing microphone route and feed one reminder into the existing speech path. No camera callback, camera message, or pairing action. Stop polling on socket close/end.
- `device/arduino/aeye_wake/aeye_wake.ino`: D2 PIR, D9/D10/D11 RGB, 115200 baud P1/P0 transitions plus one-second state heartbeats; L OFF/ARMED/EVENT/SESSION; shared-leg polarity constant; only one color at a time; five-second command-loss watchdog.
- `scripts/wake_bridge.py`: pyserial discovery or explicit port, five-second minimum cooldown, configurable quiet window (30 s default), high-state/short-pulse retention, server LED state, one-second LED keepalives, `--fake` serial mode. Added `pyserial` to `requirements.txt` because USB serial access needs it.
- `server/test_trigger.py`, `scripts/test_wake_bridge.py`, `client-web/trigger.test.mjs`: auth and valid control, owner isolation, rate limit, real ws2-backed wake mailbox delivery, camera-off preservation, acknowledgement/expiry/disconnect state, no invented memory fact, short arm-motion pulses, and network failure.
- `scripts/wake_smoke.py`: temporary localhost server with mock dependencies, real HTTP/ws2, actual `wake_bridge.py --fake` subprocess, synthetic client acknowledgement, temporary local memory. No cloud/media traffic.
- `docs/wiring.md`: beginner wiring/ASCII diagram, both LED types, H-mode/range/delay calibration, upload instructions, bridge setup, local reminder setup, Shortcut steps and placeholders.

## Interface and state

```text
PIR / Shortcut → authenticated trigger → owner's live client mailbox
                                         ↓ starts existing mic / speaks local line
                          client ACK → server state → bridge → LED
```

POST body: `{"source":"arduino-pir","kind":"presence","zone":"entryway"}`. Kinds also include door, schedule, shortcut. A token-based caller sends both `Authorization: Bearer …` and the existing `X-Aeye-Owner` call capability. Access uses the verified same-person identity. Token alone cannot select another private call. Latest polling call wins if the same Access owner opens several calls.

Local zone text uses an existing memory **place tag**: its name matches the zone, and its label supplies the short reminder. Missing tag gives “I’m here. How can I help?” No model inference or cloud TTS request is made by the trigger door; the page uses its existing browser speech/fallback path. This is an explicit reminder, not proof of a fresh object sighting.

- OFF: no client heartbeat within five seconds, or bridge HTTP failure.
- ARMED: connected client, no current presence lease.
- EVENT: wake pending/listening not acknowledged.
- SESSION: client acknowledged its listening route and the presence lease remains active.

The server's default wake lease is 30 seconds. Bridge positive PIR reports renew it with `--quiet`; P0 never immediately ends it. Continuous high holds it awake, and subsequent short P1 pulses renew it. Quiet expiry rearms the indicator; it does not turn off a manually chosen microphone or camera. `POST /api/trigger/presence` renews only an already-active same-zone lease and does not generate speech. Changing `source` or `zone` cannot evade the trigger cooldown.

## Verification on this working tree

Python executable: `/Users/minhducvo/Projects/a-eye/.venv/bin/python` (shared existing environment).

Test: `<python> -m pytest server/test_trigger.py scripts/test_wake_bridge.py server/test_access.py server/test_identity.py -q` - PASS (**35 passed, 2 warnings in 1.13s**). Warnings come from existing short synthetic JWT keys in identity tests.

Test: `node --test client-web/` - PASS (**139 tests, 139 pass, 0 fail**, 1172.75 ms).

Test: `<python> scripts/wake_smoke.py` - PASS. It runs the bridge with `--fake --quiet 1 --duration 4` against a real temporary localhost server. Summary:

```text
LED ARMED
LED EVENT
LED SESSION
LED ARMED
LED OFF
Bridge finished (fake serial; real HTTP)
Wake smoke PASS: real HTTP + ws2; one local reminder; client ACK; camera off; quiet rearmed
```

Test: `node --check client-web/agent.js` - PASS.

Test: `git diff --check` - PASS.

Test: `arduino-cli compile --fqbn arduino:avr:uno --build-path /private/tmp/aeye-trigger-uno-build device/arduino/aeye_wake` - FAIL (environment/toolchain: AVR GCC 7.3.0 `avr-g++: bad CPU type in executable`; installed core `arduino:avr 1.8.8`). No successful firmware build or upload is claimed.

During development, the first client-suite run retained a polling timer; polling was moved to the connected-call lifecycle and that old test process was stopped. The expanded auth suite caught its extracted close-handler harness depending on new closure state; cleanup now uses a separate close listener and the complete targeted selection passes. No existing assertions were weakened. Tests were added alongside the implementation, so no fail-before feature-test claim is made.

## Remaining acceptance / limits

1. Compile/upload using a compatible AVR toolchain; identify the actual LED pinout and polarity; confirm colors/current and serial operation on the arriving board.
2. Calibrate PIR range and approximately 30 s delay physically. A stationary body is not detectable by PIR; an arm pulse must cross its sensing pattern. Hardware delay plus software quiet time is additive.
3. Verify actual browser microphone permission, audible first line, phone pairing and camera-off behavior on the intended Mac/phone. The smoke's client is synthetic, not a browser or a microphone. Paired-phone SESSION reflects the existing configured phone mic route; it is not proof that the phone physically captured sound. A paired phone must have its mic enabled through the existing flow.
4. Single server worker/process only, matching the existing in-memory call registry. Mailboxes are bounded (256), old entries expire, and nothing survives a restart. Refresh the owner capability after a new token-based call.
5. Browser sleep/background throttling can make the LED go OFF. Serial disconnect exits the bridge; restart after reconnecting. HTTP failure turns the LED OFF; credential values are never printed by the bridge.
6. Full app suite and `make smoke` were not run; the task-specific integration test and required client suite were run. No commit, push, deployment, system-toolchain install or actual hardware verification.

Reviewer entry points: inspect auth/owner matching and the camera-free client callback first, then pulse lease timing and the physical wiring. Hardware/audio acceptance remains separate from this software PASS.
