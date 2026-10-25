# Live resilience — 2026-10-25

Branch: `pkg/live-resilience`. Local changes only; no push.

## Changes

- `server/gemini_live.py`: setup enables `sessionResumption: {}` and
  `contextWindowCompression: {slidingWindow: {}}`. The reader keeps the latest
  nonempty `newHandle` with `resumable: true` in RAM and supplies it as
  `sessionResumption.handle` on reconnect. A temporarily non-resumable update
  does not erase the last usable handle. `goAway` initiates reconnect immediately,
  without waiting for the provider to close the socket.
- The retry counter resets after 60 seconds on a successfully established
  connection. Consecutive short-lived failures still fall back after one retry.
  Reconnect preserves a latched safety stop and discards its resumption handle;
  this also prevents the explicit context-deletion stop from restoring old context.
- `flush_audio()` measures its initial hold as 250 ms of buffered PCM, independent
  of packet arrival time. After the existing incremental question/output safety
  checks, it releases the initial buffer, including a partial 150 ms chunk.
  Subsequent chunks remain 150 ms. Stops still clear buffered audio and cancel
  queued playback; late provider packets cannot re-arm a stopped reply.
- Live setup text limits the persona catchphrase to once per call and directs
  the model to pick one option and explain why when asked which one.
- `server/test_gemini_live.py`: setup, latest-handle reuse, proactive `goAway`,
  stopped reconnects, the 59.9/60/121-second retry boundary, and immediate release
  at exactly 250 ms for both 16 kHz and 24 kHz PCM, followed by a split safety stop.
- `server/test_live_streaming.py`: replaces the old wall-time minimum with the
  synthetic transcript/second-packet timing. Existing caption/chunk/stop checks remain.
- `server/test_live_prefetch.py`: each of two tool/audio fixtures now sends two
  150 ms packets to reach the new buffer threshold. Assertions are unchanged.
- `RESULT.md`: appended this package's handoff. Memory-turn implementation unchanged.

Field names checked against Google's [Live WebSocket API reference](https://ai.google.dev/api/live)
and [session-management guide](https://ai.google.dev/gemini-api/docs/live-session).

## Verification

All media is synthetic. Transport tests use real local WebSockets; model discovery
is fake. Counter tests advance a fake clock, and the buffer-boundary test holds
the clock fixed to prove release needs no wall-time wait. No `.env` was read and
no real Gemini calls were made. Loopback tests required sandbox escalation.

Fail-before check: the focused new selection produced **7 failed, 1 passed,
27 deselected in 0.84s** before implementation (missing setup fields, retry
allowance, and early audio); the 59.9-second control passed.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_gemini_live.py server/test_live_streaming.py --tb=short` - PASS (43 passed in 3.26s).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_prefetch.py --tb=short` - PASS (12 passed in 1.22s).

First server-suite run: **2 failed, 816 passed, 2 warnings in 48.73s**.
Both failures were the 150 ms-only prefetch fixtures described above.
Log: `/private/tmp/aeye-live-resilience-server.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server` - PASS (**818 passed, 2 warnings in 45.07s**).
Summary line read from `/private/tmp/aeye-live-resilience-server-final.log`;
process exit status 0. Both warnings are short test JWT key warnings in
`server/test_identity.py`.

Test: `git diff --check` - PASS.

## Limits

**Not verified: real provider acceptance of the new setup fields.** No real
2–3 minute Gemini session, provider resumption fidelity, real latency improvement,
or physical-device playback was tested. Persona behavior is a prompt instruction,
not a deterministic guarantee. An older handle can omit newer in-flight content;
reconnect does not replay client packets. Incremental checks cannot retract audio
already heard before a later transcript reveals a hazard.
