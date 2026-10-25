# Live polish — 2026-10-25

Branch: `pkg/live-polish`. Base: `a0d257dff16dd748c22f603528cdabc94ed1330f`.
Local server changes only; no push, UI edits, persona JSON edits, `.env` reads,
network permission changes, or real provider calls.

## Changes

- `server/personas.py`: Live style omits catchphrases and their instructions;
  classic style and the persona registry retain them.
- `server/gemini_live.py`: setup asks to see an item at most once, then gives
  a concrete step from the son's words within the safety/guide rules. It limits
  object names to clear visual evidence, requires two different frames before
  claiming placement/movement, and rules out object small talk. Ordinary visual
  questions remain allowed with task scope enabled.
- Punctuation-only output cannot emit a caption/delta or start an empty audio
  turn. Leading punctuation is discarded. A real caption precedes initial PCM
  so the existing client does not cancel playback on a late caption. If a
  transcript arrives late, initial audio waits for it or provider completion;
  audio-only completed replies still play. The existing PCM safety hold remains.
- `server/context_agent.py`: background coded stops are queued while microphone
  input is open, then released at input `final`. Provider `turnComplete` is not
  treated as microphone final. The input `stop_line` path remains immediate,
  including a hot-tip question while a background stop is queued.
- `server/task_scope.py`: scope redirection requires a home topic plus repair
  intent/problem wording. Table, valve-identification and sink-visibility
  questions pass; repair instructions remain refused with home tasks disabled.
- `server/test_live_polish.py`: setup, silent filler, caption-before-PCM,
  background-stop timing, direct hot-tip and scope regressions.

## Verification

Initial regressions reproduced the defects: 10 failed, 1 passed in 0.80s.
Focused checks after the fixes and scope repair:

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_polish.py server/test_refocus.py server/test_personas.py eval/swap/test_checker_regressions.py` - PASS (97 passed in 1.68s; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_polish.py eval/swap/test_checker_regressions.py eval/swap/test_heldout.py` - PASS (73 passed in 1.26s; summary read).

The first full run caught a scope regression in the planner challenge bank:
`bad09` (turn the sink valve and remove the drain trap) escaped the narrowed
scope check. Repair verbs and an explicit regression were added; the challenge
bank passes again. No evaluation assertion or threshold was weakened.
The next run caught a held-out sentence copied into the regression test. It was
replaced with independent short repair examples; the held-out isolation guard
then passed unchanged.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL (1284 passed, 16 failed, 2 warnings in 100.83s; final summary read).

All 16 remaining failures are socket-environment failures: 15 denied loopback
binds (`PermissionError`) and the hazard test's downstream `KeyError` after Live
startup failed with that same permission error. The failing modules are
`test_bg_context`, `test_cloud_meter`, `test_gemini_live`, `test_limits`,
`test_live_prefetch`, `test_live_streaming`, `test_step_check`, and
`scripts/test_ready`. No scope/checker or held-out isolation failures remain.
The full local output is retained at `.pytest_cache/live-polish-full.log`.

Test: `git diff --check` - PASS.

## Limits

Prompt tests verify the supplied setup, not Gemini's spoken compliance.
All new runtime tests use synthetic in-process inputs. The sandbox denies
loopback socket binding, so socket integration tests cannot establish transport
proof here. No camera, microphone, browser, native audio model, or device run
was performed. The new caption wait's real-call latency is unmeasured.
