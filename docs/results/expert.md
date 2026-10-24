# Expert package result

Implemented the expert backend and pipeline status. The separate wait-card render hook is pending scope approval: its renderer is in `client-web/agent.js`, which the package's explicit owned-file list excludes. No edits were made there, to client voice code, or to contracts. This is not a claim that all acceptance criteria are complete.

## Files changed

- `server/expert_rules.md`: stable escalation rules included in the talker system prompt.
- `server/expert.py`: process-wide admission, session task, explicit phrase and repeated-failure backstops, model selection, cooldown, timeout, cancellation, same-voice sentence delivery, planner reuse, prices and private metrics.
- `server/agent.py`: split-stream tag handling, failure reports, expert handoff, and extracted shared planner call.
- `server/llm.py`: cached stable system blocks for streaming talker/planner; expert cloud/local adapters, bounded Fable retries, effort, web search, refusal handling and usage accounting.
- `server/ws2.py`: small start/cancel hooks and cache reads in `turn_end` logging.
- `server/logs.py`: expert metadata allowlist.
- `client-web/turn.js`, `client-web/turn.test.mjs`: independent EXPERT timer in pipeline status, survives newer turns, clears on matching completion or disconnect.
- `server/test_expert.py`: fake provider/clock tests, synthetic crop and planner checks, real in-process WebSocket lifecycle tests.
- `scripts/expert_run.py`: six-question live /ws2 probe with camera off; joins expert metadata by hashed session and turn ID.
- `RESULT.md`: this handoff.

## Verification

Final full-suite state:

Test: .venv/bin/python -m pytest -q - FAIL (2 failed, 477 passed in 15.34s; both failures also reproduce on untouched HEAD 7c9c25d)
Test: node --test client-web/ - PASS (113 passed, 0 failed)
Test: .venv/bin/python -m pytest -q server/test_expert.py server/test_stream.py server/test_pipeline.py server/test_crops.py server/test_llm.py - PASS (78 passed in 2.30s; before adding the final crop/planner integration test, which passed in the full suite)
Test: .venv/bin/python scripts/expert_run.py --help - PASS (CLI loads and describes live run)
Test: git diff --check - PASS (no whitespace errors)

Existing failures, independently reproduced using a temporary archive of untouched HEAD:

- `server/test_access.py::test_4401_stops_retries_and_offers_reload`: extracted JS handler references `wait`, absent from the test harness.
- `server/test_rewind.py::test_voice_path_through_ws2`: clip exists but its frame list is empty when the test immediately reads it.

Those files are outside this package's ownership and were not changed.

## Remaining limits and integration

- Wait-card rendering is pending the requested ownership exception. The pipeline status already shows EXPERT with elapsed seconds. Proposed render-only change in `agent.js:renderWait`: use `{agent: 'helper', stage: 'expert', startedAtMs: turn.expertAt, typicalMs: 45000}` when `turn.expertAt != null`, ahead of the ordinary `visibleWait`; for that state use `{eyebrow: 'EXPERT', line: statusLine(turn, now)}` instead of `waitCopy`. This keeps the state in `turn.js` and requires no voice-code changes.
- Run the live six-question probe on the integrator's running server: `.venv/bin/python scripts/expert_run.py --log /tmp/a-eye-server.log`. Point `--log` at the server's actual JSON stdout capture. Default 21-second spacing after expert calls avoids the 20-second cooldown; adjust `--cooldown` when the server override is longer. No live provider call was made here, as requested.
- Failure marking uses explicit user reports (`failed`, `didn't work`, `still not working`) against the preceding helper instruction. `mark_failed(session, step)` also accepts an explicit stable step ID; v2 currently has no structured step-failure input. Different conversational wording is not a verified failure report.
- The timeout bounds the expert model request. Speech delivery and the follow-up planner are separate cancellable work. An expert task survives normal new turns and is cancelled on explicit barge-in, stop, session replacement or disconnect.
- Search cost is excluded and marked UNVERIFIED. Missing usage on timeout/cancellation is null, not zero. Unknown model prices are null. Haiku's cache-read rate was not supplied, so that cell is unknown rather than guessed.
- Cache-control enables caching but does not guarantee a hit: short prefixes may be below provider thresholds. Reported cache reads come from provider usage.
- Files remain unstaged. No git add was attempted, no commit was made, and nothing was pushed or published.
