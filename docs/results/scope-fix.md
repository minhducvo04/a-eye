# Scope replies without muting Live — 2026-10-25

Branch: `pkg/scope-fix`, based on `446fe77`. Completed the coordinator's inherited
changes in this worktree. Local commit only; no push.

The electronics/tie scope reply now answers only typed user text or Live's input
transcription. It is absent from pack refusal/speech guards and from
`LiveBridge.stop_line()`, which also checks scene summaries and model tool arguments.
Cabinet/valve observations and Live's own speech therefore cannot trigger that
scope reply as a safety stop.

Live suppresses the rejected turn with a separate scope flag, without setting
`safety_stopped` or `safety_line`. It cancels pending code-owned work, discards late
provider output and mic-chunk reopening, and releases the scope hold on the next
typed question or new input-transcription turn. Real safety checks still run first;
their latch and late-packet protection remain intact.

Classic `run_turn()` returns the same scope line for user home requests, including
while an electronics or tie guide exists. Existing safety refusals, observed
electronics hazards and the PC power-off gate retain precedence. Home guides still
require `HOME_TASKS=1`.

## Changed files

- `server/packs/__init__.py`: retained the coordinator's removal of scope from safety.
- `server/gemini_live.py`: separated scope handling from safety stops and added next-input recovery.
- `server/agent.py`: scope replies at the classic user-input boundary.
- `server/test_refocus.py`: corrected the speech-guard expectation while retaining hazard checks;
  added typed/spoken continuation and cabinet/valve context-builder/audio regressions.
- `server/test_gemini_live.py`: enabled `HOME_TASKS=1` explicitly in the guide-hold fixture;
  kept all hold, checker, safety and playback assertions.
- `docs/results/scope-fix.md`, `RESULT.md`: handoff and verification.

## Verification

Baseline with the inherited partial fix: the reported six failures reproduced
(`6 failed, 16 passed in 2.45s`). Both new continuation cases then failed because
the partial fix set `safety_stopped`; the scene cases already passed thanks to the
coordinator's pack-chain removal.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_refocus.py server/test_gemini_live.py::test_mic_chunk_preserves_code_owned_hold --tb=short` - PASS
(`26 passed in 0.91s`). The four original classic home cases remain intact.

The initial wider targeted run could not bind loopback servers in the sandbox.
The final full run uses permitted loopback socket access for fake provider servers.
Full-suite output: `/private/tmp/aeye-scope-fix-pytest.log`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` - PASS
(`1034 passed, 2 warnings in 51.45s`; summary read, exit 0). The warnings are
`InsecureKeyLengthWarning` from short synthetic JWT keys in two identity tests.
This covers the final runtime/test changes on base `446fe77`, including existing
loopback Live transport, safety, privacy, guide and memory tests.

Test: `git diff --check` - PASS.

## Limits

Synthetic media and fake/mocked providers only. No `.env` read, real Gemini call,
deployment, push or physical-device playback verification. The regression proves
context publication and emitted Live audio/captions, not real provider behavior.
