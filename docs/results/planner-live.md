# Planner in the real Live packet path

2026-10-25 · branch `pkg/planner-live` · base `e1d1ba6`

The reported request failed at intent detection, before any planner model call.
The regression now drives the default planner through `LiveBridge.handle`, using
the real app factory and a fake Anthropic transport. It reaches `Guide: plan 1/2`
and advances to `Guide: plan 2/2` for the reported follow-up. No real provider call
or physical call was made; socket-based checks remain blocked in this sandbox.

## Findings from the full path

1. `server/app.py:create_app` sets `state.llm` / `state.llm_v2` through
   `make_llm()`. `server/ws2.py:open_live` creates `LiveBridge` with that app.
2. `server/gemini_live.py:LiveBridge.handle` appends `inputTranscription.text`
   deltas into `question`. The old code already observed the guide on either
   `inputTranscription.finished` or `turnComplete`, before clearing the reply.
   Missing `finished` alone was **not** the root cause in this checkout.
3. `LiveGuide.claims` owns coded starts and active-guide controls. Generic requests
   reach `LiveGuide.observe` and then `BackgroundPlanner.observe` only at the
   completed-input boundary; they do not block Gemini's immediate speech.
4. `planner.task_request` required a leading intent such as “help me fix…”.
   “Dad, the wire on my headphones broke near the plug. How do I fix it?” starts
   with a problem description and failed that anchored match. The return was
   silent, so it produced zero planner events.
5. `planner.claude` uses `llm._shared_anthropic()`, which lazily creates an
   `anthropic.AsyncAnthropic` client per event loop from the process environment.
   It does **not** require an app-state client or a test injection. No missing
   `app.py` assignment was found. Missing credentials previously appeared only as
   `disabled`; they now produce `no_client`. The real deployment's credentials
   and provider/model availability were not inspected.
6. A second defect affected the exact follow-up: the shared `NEXT` expression
   accepted “what is next”, but not “what is the next step?”. Even an installed
   plan would have left that follow-up to free-form Live speech.

## Changes

- `server/planner.py`: accept a bounded breakage description followed by an
  explicit same-utterance repair question. The reported request normalizes to
  `fix the wire on the headphones near the plug`. Existing safety, personal-data,
  memory, scope, coded-guide and length gates remain. This is conservative text
  matching, not an unrestricted conversational intent classifier.
- `server/gemini_live.py`: centralize completed-input observation and observe once
  per input turn, including typed input. Streaming chunks never spend planner
  calls; `finished` followed by `turnComplete` does not repeat the decision.
- `server/packs/home.py`: extend the shared next-step control to recognize the
  reported follow-up. LiveGuide and PlannedGuide already share this expression.
- `server/test_planner.py`: exercise both packet variants (with and without
  `finished`), actual app construction, lazy shared-client construction, two
  model calls, installed step detail, published guide context and advancement.
  Only the Anthropic SDK transport is replaced in that regression, not the
  planner, trigger, app LLM assignment or guide. Additional checks cover safe
  rejection diagnostics and the missing-client path without constructing a client.

## Diagnostics

All diagnostics use `event="planner"` and allowlisted `reason` metadata:

```json
{"reason":{"task_hash":"8d9c39c04929b287","result":"started"}}
{"reason":{"task_hash":"8d9c39c04929b287","result":"valid"},"ms":5}
{"reason":{"result":"rejected","cause":"no_intent"}}
```

The first two lines are retained metadata from the synthetic regression run;
timing varies. An accepted build emits `started`, then one terminal result:
`valid`, `timeout`, `no_client`, `rejected` with an allowlisted `cause`,
`cancelled`, or `error`. An input rejected before building emits one rejection
event. Validation failures include causes such as `schema`, `unsafe` and
`personal`. No transcript, scene, task text, key or provider exception is logged.
An active guide's next-step control does not request another plan, so its planner
decision can report `rejected/no_intent` while the guide emits `Guide: plan 2/2`.

## Verification

Fail-before proof:

- The new two-variant packet regression failed twice with
  `finished Live utterance must request a plan` on the original implementation.
- With the repair trigger fixed, both variants reached plan installation but
  failed at the follow-up because no guide-control task was scheduled. Extending
  `NEXT` fixed that second failure.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py --tb=short` - PASS
(66 passed in 1.27s; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1166 passed, 16 failed, 2 warnings in 51.61s; exit 1; summary and failure traces read).
Output retained locally at `.pytest_cache/planner-live-full.log` (gitignored).
Fifteen failures are denied loopback socket operations. The hazard test below
instead raises `KeyError: 'state'` after its fake Live server fails with
`live_start_failed` / `PermissionError`. Warnings concern short synthetic JWT keys.
No socket permission was requested or lifted.

Failed node IDs:

- `server/test_bg_context.py::test_live_publishes_context_while_next_build_waits_and_cancels_on_close`
- `server/test_cloud_meter.py::test_real_websocket_send_boundary`
- `server/test_gemini_live.py::test_fake_live_recent_step_transcripts_and_scene_stay_local`
- `server/test_gemini_live.py::test_fake_live_wire_audio_tools_captions_and_revocation`
- `server/test_gemini_live.py::test_reconnect_once_then_fallback_and_close`
- `server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[False-False]`
- `server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[True-False]`
- `server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[True-True]`
- `server/test_limits.py::test_live_minutes_stop_idle_connection`
- `server/test_live_prefetch.py::test_slow_tool_does_not_delay_audio`
- `server/test_live_prefetch.py::test_streaming_prefetch_card_cache_and_idle_publication`
- `server/test_live_streaming.py::test_fake_live_streams_before_complete_and_stops_mid_reply[False]`
- `server/test_live_streaming.py::test_fake_live_streams_before_complete_and_stops_mid_reply[True]`
- `server/test_live_streaming.py::test_ws2_hazard_sends_stop_caption_and_fixed_audio`
- `server/test_step_check.py::test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero`
- `scripts/test_ready.py::test_live_pair_request_on_fake_socket`

Test: `git diff --check` - PASS.

Limits: worktree-only edits; no `.env` read, external network, real LLM call,
raw media, push, merge or deployment. Actual Live/provider acceptance remains
unverified. The immediate Gemini response still plays while planning runs in the
background, and a next-step request before a plan finishes cannot advance it.
