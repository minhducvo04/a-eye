# Private capture — lead review handoff

Implemented in the working tree; not committed. `server/ws2.py` and contracts are unchanged.

## Independent privacy review fixes (2026-10-24)

All five findings from `$HOME/kyra-grok/aeye-review-capture/RESULT.md` are addressed:

1. **Fail-closed device person gate:** `device/hw.py` refuses unavailable detectors, errors and unknown
   results. Both Event and Session use the shared gate; only an explicit negative check permits a frame.
   Safe synthetic frames still send. Session audio is unchanged.
2. **Camera indicator:** GPIO only calls `off()` for Off. Armed pulses at 3–15% duty, never zero; Event is
   signalled before full-resolution open. Session camera opening is inside cleanup so a partially failed open
   closes before Off. The fake GPIO probe records camera state and LED values through transitions.
3. **Server Event gate:** every validated still passes the existing local `PersonCheck` before the judge.
   Person, unknown and failed checks refuse the whole burst without inference or a note. The shared check now
   rejects malformed detector responses; an empty detection list remains a valid negative result.
4. **Armed cap:** one deadline includes the Event burst and upload. Expiry cancels pending transport, clears
   buffers, closes the camera and signals Off. Slow reads and person checks run off the event loop; late read
   results are closed, and detector workers own copies so cancellation can release the Event buffer safely.
5. **Disabled filtering:** `drop_person_frames = false` means no detector, so neither Event nor Session sends
   images. The example config and `docs/device.md` state this explicitly; no server-only fallback is promised.

Changed files for this fix: `device/{capture,client,hw}.py`, `device/device.example.toml`,
`device/test_capture.py`, `device/test_client.py`, new `device/test_capture_privacy.py`,
`server/{memory,memory_capture}.py`, `server/test_memory.py`, `server/test_memory_capture.py`,
`docs/device.md`, this handoff and the appended task receipt in root `RESULT.md`.

### Fail-before evidence

All following runs preceded the corresponding production changes. The Python executable was
`$HOME/Projects/a-eye/.venv/bin/python` (this worktree has no `.venv`).

- `-m pytest device/test_capture_privacy.py server/test_memory_capture.py -q`:
  **16 failed, 6 passed in 1.40s**. Reproduced absent/unavailable/disabled/unknown Session gating, detector
  errors, GPIO ordering/darkness, partial camera-open cleanup, Event cap overrun and missing server gating.
- `-m pytest device/test_capture_privacy.py -q -k event_requires --tb=short`:
  **2 failed, 2 passed, 15 deselected in 0.08s**. Event unknown-result and exception paths; safe/disabled controls.
- A fresh read-only patch reviewer identified malformed server responses and synchronous work delaying expiry.
  The malformed-result check with legitimate controls in `server/test_memory.py` produced
  **5 failed, 3 passed, 19 deselected in 0.18s** (the `None` case already refused, but raised a different error).
- `-m pytest device/test_capture_privacy.py server/test_memory_capture.py -q
  -k 'blocking_event or real_person_checker' --tb=short`:
  **5 failed, 1 passed, 26 deselected in 0.78s**. Reproduced both slow-work cap failures and three malformed
  responses reaching inference through the real `PersonCheck`; empty-list control passed.

### Current verification

Test: focused device privacy/server capture/shared memory checks — PASS:
`59 passed in 2.55s`.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest device server -q --tb=short` — PASS:
`383 passed, 2 warnings in 62.05s (0:01:02)`.

Test: real Chromium, `uv run --offline --no-project --with playwright python scripts/browser_smoke.py
http://127.0.0.1:18439` — PASS: `frames_sent: 2`, `problems: []`,
`longest task after the find card: 0 ms`, `BROWSER SMOKE PASS`.
The temporary loopback server used `A_EYE_MOCK=1`, `LOCAL_ONLY=1`, an isolated memory directory and synthetic
camera/microphone input; it was stopped afterwards. No real camera, model host or GPIO hardware was contacted.

Test: `git diff --check` — PASS.

An initial sandbox suite had `365 passed, 2 warnings, 4 errors in 37.93s`: all four errors were denied loopback
binds. The authorized loopback run then passed `369 passed, 2 warnings in 59.88s`, before the two review
follow-ups. The final run supersedes it. Warnings concern existing short JWT test keys.

The independent review was source-only; its two follow-up findings were reproduced and fixed by the builder,
with passing regressions. This is not a second independent approval of the final patch.

### Remaining proof limits

- HOG and the server detector can miss real people. Tests prove control flow, not universal recognition.
- The server gate prevents judge inference and note storage; it cannot undo receipt of a device false negative.
- Thread cancellation cannot securely erase pixels or terminate a stuck native driver. Late worker-owned
  images are released when that worker completes. Physical camera close latency and GPIO brightness still need
  a Pi/device test; the cap tests prove prompt application cleanup with synthetic blocking reads/checks.
- No physical LED, sensor power or battery measurement was performed. No new deployment claim is made.

## Original implementation handoff (historical)

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

## Original verification

Tests use synthetic frames, a real loopback HTTP/WebSocket server and a scripted vision answer. They do not
contact a model host. Logs are local under `/tmp/private-capture-*.log`.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest device server -q` — PASS
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
  inspection failure now refuses both Event and Session frames, as covered by the fixes above. This is not
  proof that all real-world person frames are excluded.
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
