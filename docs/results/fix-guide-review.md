# Sink guide review fixes — 2026-10-25

Fixed all eight requested guide findings in `pkg/fix-guide`. Local commit only;
no push, `.env` read, real Gemini call, or edit to another builder's files.
Starting revision: `2b42c150fe830d296ae5eaa6ccb8aae5b7b15e67`.

## Changes and reproductions

All reproductions live in `server/test_guide_review.py` (eight test functions,
14 cases including OFF phrases, pass/fail hazard results, and completed guides).

| Bug | Fix | Reproduction test |
| --- | --- | --- |
| Later transcription cancels a valve check | Only the pending debounce is replaceable. Once a run starts, it finishes without a second check or advancement. Consume the presenter fixture after the check returns; reject a result after a hazard, guide replacement, or growth-epoch change. | `test_later_transcription_does_not_cancel_valve_check` |
| Too little frame-age budget remains | Wait up to 1.5 seconds for a frame at most 100 ms old; snapshot that frame and its own `session.frame_time` together. Pass that timestamp to the checker. Both admission and completion retain the original 1.5-second image-age limit. No timestamp is refreshed artificially. | `test_valve_check_waits_for_fresh_frame_and_preserves_capture_time` |
| NEXT matches narration or negation | Home and Live share a completion/request-clause matcher. Accept explicit requests, including `next step`, `I'm done`, `done`, `ok next`, `what's next`, and existing comma-separated confirmations. Reject `next to` and `not done`. Re-read a growing transcript after debounce. | `test_next_requires_completion_intent_in_home_and_live` |
| OFF misses common confirmations | Recognize `I closed it`, `it's closed`, `turned it off`, `shut it`, and `I shut the valve`. These request a check and cannot grant its pass. | `test_off_phrases_request_check_but_cannot_pass` |
| Ordinary prompt loses GUIDE | Route the ordinary-question fallback through `_prompt`, including the current GUIDE. A speaking prompt marks the background GUIDE unpublished so the existing idle hook sends it with `turnComplete: false`. | `test_question_prompt_keeps_and_republishes_guide` |
| Hazard during check still prompts | Re-check closed/safety state after the check await, before consuming a pass or issuing retry speech; guard later prompt entry as well. | `test_hazard_during_check_prevents_prompt_or_retry` |
| Dialogue warms future-step parts | Require the current `task:step` in each matched card's `step_keys`; unrestricted lookup remains available outside a task. | `test_dialogue_cannot_warm_future_step_parts` |
| Forget leaves an old guide active | Recreate the current Home/Electronics guide, clear the presenter verdict, acknowledge forgetting, and publish/speak step 1 with an updated session note. Completed guides also accept forget. | `test_forget_recreates_and_republishes_first_step` |

The existing parts-shelf regression now excludes the multimeter at
`ee_resistor:1`: its card belongs to step 2. Its unrestricted dialogue lookup
remains covered. No existing NEXT test expectation was weakened.

## Verification

- Before fixes: the initial reproduction run reported **11 failed, 3 passed**.
  The initial parts reproduction was accidentally hidden by the note-length cap;
  isolating its card then reproduced the missing step filter (**1 failed**).
  Every requested bug had a failing reproduction before its production fix.
- Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_guide_review.py server/test_live_guide.py server/test_home_pack.py server/test_step_check.py server/test_parts_shelf.py --tb=short` - PASS (**60 passed in 2.93s**).
- Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server` - PASS (**867 passed, 2 warnings in 48.47s**, exit 0; final summary read).
- Test: `git diff --check` - PASS.

The two full-suite warnings concern short synthetic JWT signing keys in existing
identity tests. The first targeted attempt could not bind a loopback socket under
the filesystem sandbox; the successful targeted and full runs had socket access.
The real loopback HTTP test exercised the app and local Qwen protocol with a
synthetic model response and synthetic image, asserting zero saved pictures.
Live tests used a fake socket; no real provider or physical-device proof is claimed.

## Integration hooks and limits

- No new bridge API is required. Keep the existing idle/turn-complete
  `publish_guide()` hook: `_prompt` now leaves its publication pending.
- The separately owned `gemini_live.py` fixes remain required: `prompt_turn`
  must re-check `safety_stopped`/`closed` after its internal provider-idle wait,
  and mic input/reset must not release an active guide/memory hold. This patch's
  pre-prompt guard cannot protect a race inside the bridge's await. `guide.task`
  remains active for the entire check for the hold-owner guard.
- Real checker activation still requires a validated, non-synthetic evaluation
  configuration. Missing configuration stays locked. Inference taking longer
  than the remaining 1.5-second image-age budget still cannot pass. This patch
  does not claim real Qwen speed or accuracy and does not bypass that safety gate.
- The timestamp is the camera frame's existing monotonic `session.frame_time`,
  assigned by the receiver; it is not replaced with inference start time.
- Once a debounced guide run starts, additional transcription packets are
  coalesced into that run rather than queued as another step. A new step request
  should follow completion of the current check.
- Untouched: `server/gemini_live.py`, `server/live_memory.py`,
  `server/recent_memory.py`, `server/rewind.py`, `server/ws2.py`, and `server/safety.py`.

Changed files: `server/live_guide.py`, `server/packs/home.py`, `server/agent.py`,
`server/step_check.py`, `server/parts_shelf.py`, `server/test_guide_review.py`,
`server/test_parts_shelf.py`, this report, and the appended root `RESULT.md` receipt.

Finished
