# Memory review fixes — 2026-10-25

All five requested fixes are implemented on `pkg/fix-memory`, based on `29ac1aa`.
Review source: `/Users/minhducvo/kyra-grok/aeye-review-memory/RESULT.md`.
No push, `.env` read, or real Gemini call. `server/recent_memory.py` is unchanged;
its two medium findings remain with the other builder.

| Finding | Change | Reproduction in `server/test_live_memory.py` |
|---|---|---|
| Safety arrives after a memory hold | Every detected safety line calls `stop()`, even when blocked. `stop()` invalidates the memory version and cancels its task and lookup. | `test_streaming_safety_stop_cancels_an_already_held_lookup` |
| Barge-in/new input leaves old work alive | `reset()` cancels and increments the version. Scheduled runs capture a version; router completion, filler, lookup delivery and post-idle prompt delivery check ownership. The hold remains until the prompt is delivered. | `test_new_input_cancels_old_memory_turn_and_invalidates_delivery` (lookup and idle-wait phases, interruption and new-input paths) |
| Idle-wait prompt clears a safety stop | `prompt_turn()` re-checks the safety latch after the idle wait, then resets output fields separately from the latch. Fresh user input retains its existing full-reset path. | `test_prompt_turn_preserves_a_safety_stop_during_idle_wait` |
| Router-only questions leak an early guess | Hold before scheduling the router decision. A `now` verdict releases the question as one fresh Live prompt. | `test_router_only_question_holds_audio_until_scope_is_known` (past and now controls) |
| Code-owned memory sends transcript/crop cards | Suppress cards on this path; keep spoken evidence. `agent.js` handles both card types at lines 791–793 and `showFind()` opens the sheet. Rewind consent does not prove that sheet is already visible. | `test_code_owned_memory_does_not_send_query_or_crop_cards` (Rewind and long-term cards) |

The five new test functions cover ten parameterized cases. All ten failed against
the original implementation before production edits. Existing tests still check
ordinary current questions, safe input after a stop, guide priority, honest misses,
timeouts, consent and ordinary tool cards.

Files changed: `server/gemini_live.py`, `server/live_memory.py`,
`server/test_live_memory.py`, this receipt and the appended `RESULT.md` handoff.
No contracts, router, client or recent-memory source edits.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_memory.py -k 'streaming_safety_stop or new_input_cancels or prompt_turn_preserves or router_only_question or code_owned_memory' --tb=short` - FAIL as intended before fixes (10 failed, 11 deselected in 1.68s).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_memory.py --tb=short` - PASS (21 passed in 2.43s).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router` - sandbox attempt FAIL (15 failed, 860 passed, 2 warnings in 50.62s). The failures were local socket-bind permission errors, including the downstream fixed-audio test whose fake provider could not start. Re-run with loopback permission recorded below.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router` - PASS with loopback permission (875 passed, 2 warnings in 52.32s; summary read, exit 0). Warnings are the existing short synthetic JWT keys in two identity tests. Output retained locally in `.pytest_cache/fix-memory-review-tests.log` (ignored).

Test: `git diff --check` - PASS.

Limits: executable tests use synthetic media, fake providers, and local sockets.
No claim of real Gemini behavior, browser playback or physical-device verification.
Card suppression applies only to code-owned memory turns; ordinary user/tool
memory cards retain their existing behavior. The integrator owns landing and smoke.
