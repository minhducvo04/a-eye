# Private capture — lead review handoff

Implemented in the working tree; not committed. `server/ws2.py` and contracts are unchanged.

## Changes

- `device/capture.py`: separate Off / Armed / Event path; five-second bounded grey RAM pre-roll, five-second
  Event burst, fail-closed person filtering, at most three stills, cleanup on success/failure/stop. Armed opens
  no application socket or microphone. Explicit startup arming expires after 12 hours by default.
- `device/trigger.py`, `config.py`, `device.example.toml`: watched zone and configurable Armed cap.
- `device/client.py`, `__main__.py`, `hw.py`: existing Session path retained; terminal commands and optional
  GPIO22 Remember button; low-resolution camera requests; distinct terminal and PWM LED states.
- `server/memory_capture.py`, `memory_api.py`: bounded `/api/memory/event`, existing authentication/owner and
  memory consent gates, local Ollama only, one question, zero or one short text note, no crop writer. Existing
  Find searches these notes. Request/inference errors clear the frame list; no frame contents are logged.
- `scripts/capture_power.py`: 20 fake or manually observed trials, battery/temperature/USB readings and SKIPs.
- Tests: `device/test_capture.py`, `server/test_memory_capture.py`; shared server fixture in `test_client.py`.
  Removed the obsolete regression that required motion to start an audio Session; replaced with motion-to-Event.
- `docs/device.md`: state signals, controls, deployment limits and measurement commands.

## Verification

Tests use synthetic frames, a real loopback HTTP/WebSocket server and a scripted vision answer. They do not
contact a model host. Logs are local under `/tmp/private-capture-*.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest device server -q` — PASS
`340 passed, 2 warnings in 57.90s`. Warnings are existing short JWT fixture keys. This run preceded final device
stop-handling and additional failure-path tests; the final affected-module result is recorded below.

Test: final `python -m pytest device server/test_memory_capture.py -q` — PASS
`27 passed in 18.22s` (includes final client lifecycle, real HTTP Find, motion-to-Event, fake GPIO and failure cleanup).

Test: `git diff --check` — PASS.

Test: real Chromium `scripts/browser_smoke.py` against temporary mock server — PASS
`frames_sent: 2`, `problems: []`, `BROWSER SMOKE PASS`. Invoked with the documented `uv --with playwright`
environment because the repository Python has no Playwright installed. Synthetic camera and microphone only.

Test: `PYTHONPATH=. python scripts/capture_power.py --fake` — PASS
`SUMMARY trials=20 events=20 misses=0; SKIP physical capture/power proof`.
Mac battery sensor returned 80%; Pi temperature and USB meter returned `SKIP`. This is not a battery-drain result.

Privacy checks inspect every file in isolated device/server output roots for image suffixes, JPEG/PNG magic
and JPEG base64. A negative control deliberately saves an image as `cache.bin` and proves the checker rejects
it. Tests assert the Event RAM list is empty, real HTTP notes are findable, person-marked frames are absent
from transmitted JPEGs, and Armed cannot connect a socket. Failure, unavailable detector and consent refusal
paths have cleanup checks. No pre-implementation failing-test run was recorded; the mutation control validates
the disk assertion, rather than claiming fail-before evidence.

Initial sandbox execution could not bind localhost. Authorized expanded test execution supplied the real
HTTP/WebSocket proof. No permissions or persistent services were changed.

## Limits for review

- The design combines “nothing stored in Armed” with five seconds of pre-roll. Here “stored” means persisted:
  Armed retains five tiny grey thumbnails in process memory. No high-resolution Armed capture is requested.
- Those 64×48 pre-roll thumbnails are too small for HOG and are dropped before sending. Thus the server sees
  safe post-trigger stills, not five seconds of useful visual pre-roll. Higher-resolution pre-roll would require
  a different power/privacy tradeoff or a validated tiny-frame detector.
- HOG can miss people. The transport gate is tested; universal recognition is not. Detector unavailable or
  inspection failure never sends an Event. This is not proof that all real-world person frames are excluded.
- Python releases image references; it does not guarantee secure memory erasure or prevent swap/core dumps.
  The application creates no image files. Physical-disk claims require deployment OS controls and measurement.
- Pi camera, GPIO, LED brightness, USB driver output and physical battery/temperature are unverified. GPIO
  patterns were exercised with a fake PWM driver; a single LED uses brightness rather than Session color.
- No wake phrase / always-open mic. Remember works through the second GPIO button or terminal command;
  existing Session audio is unchanged. No new browser UI was needed for the terminal strip.
- Local model quality/latency was not measured. `OLLAMA_URL` must point to the user's home box; the Event path
  does not use cloud fallback. Server inference timeout is bounded; stop cancels device transport, but cannot
  recall an already-received request. The server still performs its own bounded cleanup.
- Armed's no-traffic assertion covers this application, not OS Wi-Fi background traffic. No physical-radio
  disablement or camera standby driver work was attempted.

Lead review should retain the hardware/person-recognition/pre-roll limitations before making demo claims.
