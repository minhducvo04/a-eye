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

## Fix-back on pkg/planner-live2 — 2026-10-25

Base: `3749491` (the local merge of `pkg/planner-live`). Work and commit stay
on `pkg/planner-live2`; no push, network permission change, or `.env` access.

### Reproduction and intent

The exact reported transcript is now exercised through `LiveBridge.handle`:

> dad The wire on my headphones broke near the plug. How do I fix it?

The packet regression also covers lowercase `dad` with lowercase `the`, `Dad,`,
trailing spaces, and chunks beginning with a standalone `dad` delta. Each runs
with `inputTranscription.finished` and with only `turnComplete`. It constructs
the real app/default planner and replaces only the Anthropic SDK transport.
It asserts two calls, normalized task, step 1 installation, and later step 2.

Important evidence limit: all eight repair variants already passed against this
checkout before the production edits. The reported exact-string `no_intent`
failure was **not reproduced** here; the deployed process and its packet sequence
were not inspected. It would be incorrect to attribute that failure to lowercase
`dad` alone. Address normalization is now shared across repair, direct-task and
learning intent, so punctuation and case do not select different intent paths.

Additional Live packet cases cover `help me fix`, `can you teach me`, `how do I
solder`, and `what does a capacitor do`. The last form now produces the reusable
learning task `what a capacitor does`. Table observation, wrench recall and small
talk request no plan. Existing scope, safety, privacy and personal-data gates stay
in force.

### Pending-plan next step

An early `Okay, what is the next step?` now claims the existing guide hold and
drops Gemini's free-form reply while waiting for the first plan. The wait runs
outside the socket reader with a three-second deadline including guide debounce.
If the plan arrives, the speaking prompt contains **step 1**, without advancing;
the next ordinary next-step request advances to step 2.

The pending plan is captured before the asynchronous hold and debounce, so a
completion during either still starts at step 1. A coded-guide start can replace
the wait. A safety stop prevents the held plan from speaking. On timeout or an
invalid plan, the held question returns to Live; timeout does not cancel the
background build or cause an unsolicited second answer when it later completes.
Live's existing provider-idle wait can add up to three seconds before a new
speaking prompt; the plan wait itself is bounded at three seconds.

Changed files: `server/planner.py`, `server/live_guide.py`,
`server/gemini_live.py`, `server/test_planner.py`, this report and `RESULT.md`.

### Verification

Before production edits, the new selected regressions reported 6 failed,
15 passed: two learning-intent rejections and four missing pending-plan holds.
The exact repair transcript and variants were among the passing cases.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py --tb=short` - PASS
(88 passed in 4.38s; summary read). Includes the real three-second timeout,
completion during hold/debounce, invalid plan, safety stop and coded replacement.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1188 passed, 16 failed, 2 warnings in 54.62s; exit 1; summary and failure evidence
read). The failed node IDs are the same sixteen listed in the original report
above: fifteen denied loopback socket operations and the hazard test's downstream
`KeyError: 'state'` after `live_start_failed` / `PermissionError`. The two warnings
concern short synthetic JWT keys. No socket permissions were lifted.
Final output: `.pytest_cache/planner-live2-full.log` (local, gitignored).

Test: `git diff --check` - PASS.

Limits: synthetic packets, fake provider transport and local execution only.
No real provider call, physical-device playback, deployment or merge was tested.

## Merged-main repair on pkg/planner-live3 — 2026-10-25

Base: `c83d4a1`, containing both `pkg/checker` and `pkg/planner-live2`.
Work stays in this worktree; no push, `.env` access, or network permission change.

### A. Soldering failure attribution

Reproduced both reported `test_live_intent_packets` failures: 2 failed, 7 passed
(72 deselected). Both requests produced `started`, then `rejected/unsafe` after
the fake provider's two calls. `task_decision` accepted the requests; neither
the task itself nor Live's input safety gate refused soldering.

Checker commit `4d606db` added the requirement for spoken ventilation preparation
in the first step whenever the plan/task mentions soldering. Planner-live2 commit
`96ebe58` added soldering packet cases using the generic fake headphone-inspection
plan, which has no ventilation. That fixture was invalid under the merged checker.
The fix supplies an actual three-step soldering fixture: disconnect device power
and arrange ventilation, prepare the iron stand, then solder the disconnected
wire joint with cooling and hot-tip precautions. Both packet tests assert that
this plan installs, and that the old unprepared plan still fails validation.
No checker or intent safety rule was relaxed.

### B. Live timing reproduction and fix

`LiveGuide.observe` forwarded text unchanged. The bridge's `observe_guide` set
`guide_observed = True` before knowing whether the decision was positive. An early
`inputTranscription.finished` on `dad` therefore emitted one `no_intent` event and
prevented the later full utterance from being judged, including at `turnComplete`.
The former bridge also waited until `turnComplete` if `finished` was absent,
even when model output had already begun.

The new regression sends these deltas as separate `serverContent` messages with
event-loop delays: `dad`, ` The wire on my`, ` headphones broke near`,
` the plug. How do I fix it?`. Before production changes, the early-finished
variants reproduced the lone rejection and no plan; the first-output variant
failed to start planning before the reply ended. The completed-input variant
already planned, but failed the new missing-`chars` assertion (4 failures total).
This demonstrates the early-finished hypothesis in executable code; without
provider packet capture it does not prove that the reported real call sent that
exact boundary sequence. Plain chunks followed only by `turnComplete` already
worked on the base and remain covered by the existing app/client regression.

The bridge now starts a 150 ms debounce on `finished` or first model output
(audio, output transcription, or tool call). Later input resets that debounce;
continued model output does not postpone it. The decision reads the current
assembled question. `turnComplete` flushes it before clearing the question, and
typed input remains immediate. Only an accepted request latches the turn;
unchanged rejected text is deduplicated, but longer input can retry. Existing
per-task request and spending limits remain in place. Turn reset, interruption,
and close cancel deferred observations; safety is rechecked before observation.

Every planner diagnostic now includes `reason.chars`, the input text length only.
For the timed repair regression, `started` and `valid` have `chars: 67`; a deliberately
late delta can first produce `rejected/no_intent` with `chars: 3`, followed by the
successful full-text decision. Neither event contains the transcript.

Seven timed cases cover final/early `finished`, no `finished`, audio-only output,
output before the last input delta, continued output, and input after an initial
rejection. Each installs step 1 before `turnComplete`, then the exact follow-up
`Okay, what is the next step?` advances to step 2 without another provider build.
Three cancellation cases cover stop, interruption/new input, and close.

Changed files: `server/gemini_live.py`, `server/live_guide.py`, `server/planner.py`,
`server/test_planner.py`, this report, and `RESULT.md`.

### Verification

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py eval/swap/test_checker_regressions.py --tb=short` - PASS
(133 passed in 7.45s; summary read). Includes the unchanged checker challenge bank
and all existing planner privacy, safety, budget, cache, and pending-plan checks.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1236 passed, 16 failed, 2 warnings in 57.25s; exit 1; summary and each failure
trace read). Fifteen failures are denied loopback socket operations. The sixteenth,
`server/test_live_streaming.py::test_ws2_hazard_sends_stop_caption_and_fixed_audio`,
is a downstream `KeyError: 'state'` after `live_start_failed` with `PermissionError`.
The node IDs match the sixteen socket-dependent failures listed earlier in this
report. No planner/checker regression failed. The warnings concern short synthetic
JWT keys. Network permissions were not lifted or retried.
Full local output: `.pytest_cache/planner-live3-full.log` (gitignored).

Test: `git diff --check` - PASS.

Limits: local execution with synthetic packets and fake provider transport.
No real Gemini/Claude call, device playback, merge, or deployment was tested.
