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

## Fix-back round 4 on pkg/planner-live4 — 2026-10-25

Base: `a5b3cb4` (main with planner-live3 merged). Work stays in this worktree;
no push, `.env` read, network permission change, or real provider request.

### Reproduction and change

The new synthetic packet regression starts with the first 21 characters of the
reported headphone sentence, interleaves model PCM and output transcription,
waits for `rejected/no_intent/chars:21`, then delivers more input transcription.
One variant puts model `turnComplete` before the final input chunk; the other
keeps model output open. Before production changes: 1 failed, 1 passed
(91 deselected in 2.09s). The completion-before-tail variant never started a plan.
The variant with late input before completion already worked on the base.

The remaining bug was transcript lifetime: `turnComplete` cleared `question`,
and the next input packet reset planner observation state. Retrying only that
tail lost the earlier problem statement. The bridge now keeps a separate,
bounded planner transcript in call RAM across model-output resets. Every input
growth schedules a 300 ms debounce, independent of model output or `finished`.
Unchanged rejections stay deduplicated; a positive decision latches observation.
Model completion still flushes the latest text, but a rejection remains eligible
for retries on trailing input. New mic utterances, typed input, interruptions,
and reconnects reset the retained planner input; close cancels deferred work.
No contract, safety checker, planner budget, or guide wait limit changed.

Both interleaved cases now request exactly one two-call plan using the full
sentence and install step 1. The literal supplied sentence has 67 characters
(68 with a trailing space); the regression asserts the actual full-text length
alongside the 21-character rejection. Diagnostics contain lengths, not text.

The same regression delays planner completion, starts a fresh mic turn with
`Okay, what is the next step?`, verifies the free-form Live reply is held, then
releases the plan and asserts the spoken prompt contains **step 1 of 2**, without
advancement or a second build. Existing tests still exercise the real three-second
pending-plan timeout, invalid plan, safety stop, and completion during debounce.

### Verification

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py --tb=short` - PASS
(100 passed in 11.08s; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1238 passed, 16 failed, 2 warnings in 60.13s; exit 1; summary and failure evidence
read). Fifteen failures are denied local socket operations. The sixteenth is
`server/test_live_streaming.py::test_ws2_hazard_sends_stop_caption_and_fixed_audio`,
which raises `KeyError: 'state'` after `live_start_failed` / `PermissionError`.
The failed node IDs match the sixteen documented in the earlier rounds. No
planner/checker test failed. Warnings concern short synthetic JWT keys.
Full local output: `.pytest_cache/planner-live4-full.log` (gitignored).

Test: `git diff --check` - PASS.

Changed files: `server/gemini_live.py`, `server/live_guide.py`,
`server/test_planner.py`, this report, and `RESULT.md`.

Limits: synthetic packets and fake providers only; no real Live call, device
playback, merge, or deployment verification. No packet capture establishes the
real provider's exact sequence. A transcription-only stream without a fresh
mic/typed/interruption signal cannot distinguish an unaccepted turn's late tail
from a new utterance; retained rejected input intentionally remains retryable.


## Fix-back round 5 on pkg/planner-live5 — 2026-10-25

Base: `9469744` (main with planner-live4 merged). Local worktree only; no push,
`.env` read, network permission change, or real provider request.

### Reproduction and change

New regressions failed before production changes: 7 failed, 9 passed,
126 deselected in 1.39s. They reproduced the Sonnet default, missing rejection
gate id, rejection of the eight-step headphone repair, and four safe hot-tip
warning variants. The reported real provider output was not supplied; `good13`
is a saved, hand-written realistic regression fixture, not a captured model reply.

The planner now defaults to `claude-haiku-5-5`, retaining `PLANNER_MODEL` overrides,
zero SDK retries, and the existing **12-second total timeout** across both calls.
The researcher/planner flow remains two sequential calls: the supplied Haiku
observation finished quickly, so there is no current evidence that Haiku requires
a one-call redesign. Tests verify default/override selection and that the second
call cannot extend the total deadline. Real Haiku latency remains unmeasured here.

`hot_tool` is now a `Gate` with an affirmative-action output pattern. Direct
negated warnings (don't, do not, never, avoid) pass, while instructions or intent
to touch/grab the hot tip still stop. Matching does not cross sentence/clause
punctuation into another action. The electronics pack uses the same hot-tool
output pattern; its old independent any-mention check also rejected precautions.
Planner output skips only the hot-tool **input** trigger, then runs the output
check. User speech still runs the input gate, including `I will touch the hot tip`.
Other conservative input gates remain active for plans: a bare instruction to
cut a live wire still drops, even without an explicit claim that it is safe.

The saved eight-step repair covers unplugging headphones, ventilation and eye
protection, cutting and stripping wire, tinning, soldering, hot-tip warnings,
returning the iron to its stand, cooling, heat-shrink insulation, and checking
before reconnecting. `Unplug the headphones` now satisfies spoken power-off
preparation. Typical unplugging and heat-shrink/cooling steps do not trigger
`live_power` or `burning_device`; actual live-wire approval and continued use of
a burning cable still reject. Runtime tests install this plan from synthetic
Live input, reload it from cache, and advance through all eight steps.

Unsafe plans continue to be rejected as a whole; no partial-plan continuation was
introduced. Rejections now include only the coded `reason.gate` identifier (for
example `hot_tool`, `power_off`, or `ventilation`), never rejected plan text.
A regression checks the hot-tool event and absence of transcript/step text.

The checker bank adds one good case (13 total); all 15 bad cases and the allowed
maximum of one false drop are unchanged. The first full run found the new case's
long task label duplicated the existing server repair regression. The saved
fixture now has a distinct short task label; runtime tests derive the requested
label through `task_request`. The held-out leakage guard is unchanged and passes.

### Verification

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py eval/swap/test_checker_regressions.py server/test_home_safety.py server/test_ee_guide.py eval/swap/test_components.py eval/swap/test_heldout.py --tb=short` - PASS
(185 passed in 12.00s; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(final run: 1253 passed, 16 failed, 2 warnings in 60.76s; exit 1; summary and
failure evidence read). Fifteen failures are sandbox-denied socket operations.
The sixteenth, `test_ws2_hazard_sends_stop_caption_and_fixed_audio`, is a downstream
`KeyError: 'state'` after `live_start_failed` / `PermissionError`. These are the
same sixteen socket-dependent nodes documented in earlier rounds. No planner,
checker, or held-out-data test failed. Warnings concern short synthetic JWT keys.
No network permissions were requested. Full local output:
`.pytest_cache/planner-live5-full.log`. The initial run (1252 passed, 17 failed)
is retained in `.pytest_cache/planner-live5-full-initial.log`; its additional
fixture-label failure was fixed before the final run.

Test: `~/Projects/a-eye/.venv/bin/python eval/swap/run.py checker --model current --out .pytest_cache/planner-live5-checker` - PASS
(production checker, offline socket guard): **15/15 bad plans caught; 1/13 good
plans false-dropped; 0 checker errors**. New `good13` is accepted by all checks.
The remaining false drop is existing `good01`, whose first step strips wires
without spoken power-off preparation (`power_off`); it also lacks initial
ventilation. Its fixture and preparation requirements were not weakened.
Detailed report: `.pytest_cache/planner-live5-checker/swap-checker-current.json`.

Test: `git diff --check` - PASS.

Changed files: `server/planner.py`, `server/safety.py`,
`server/packs/electronics.py`, `server/test_planner.py`,
`eval/cases/checker_good_plans.jsonl`, `eval/swap/checker.py`,
`eval/swap/test_checker_regressions.py`, `eval/swap/test_components.py`,
`docs/results/planner-live.md`, and `RESULT.md`.

Limits: real local Python execution with synthetic packets and fake providers;
no live Claude/Gemini latency, physical playback, merge, or deployment proof.
The fix covers the recorded regression and the existing gate bank; regex gates
remain conservative text backstops, not general semantic safety verification.

## Round 6 — forced plan submission and first-reply protection — 2026-10-25

Branch `pkg/planner-live6`, base `111aaa8` (main's planner-live5 merge).
The reported real Haiku rejection (`schema`, 67 input characters) did not include
its output, so the exact rejected payload cannot be diagnosed offline. These
changes address the strict text-output path and the reproduced timing failures.

- The research call remains text-only. The second Anthropic call declares only
  `submit_plan`, with the plan JSON Schema, and forces that tool using
  `tool_choice={"type":"tool","name":"submit_plan"}`. Its parsed `input` goes
  through the same local validator as cached and text plans. There is no tool
  execution or additional request; the two-call budget, no retries, and shared
  12-second deadline remain.
- Text fallback strips code fences and decodes the first JSON object, accepting
  surrounding prose but never substituting a later object after validation fails.
  Missing `target` and `check` become empty strings; surrounding whitespace is
  trimmed, and a single step object becomes a one-element list. Unknown fields,
  missing required fields, unsafe/private content, more than eight steps and
  overlong speech still reject the whole plan. The prompt/tool description asks
  for at most 22 words; code retains the 24-word ceiling.
- Rejections log allowlisted codes: `not_json`, `missing_steps`,
  `too_many_steps`, `too_long`, or `schema`, alongside the existing safety/privacy
  outcomes. Neither response content nor provider exception text enters logs.
- A trailing “Next step?” in the same triggering utterance cannot claim Live's
  initial reply, whether planning is pending or installed. Subsequent next-step
  requests retain their bounded wait. The three-second deadline now includes
  guide debounce, planning, and provider-idle waiting; it no longer adds a second
  three-second idle wait. Provider generation/transport time is not an audio SLA.

### Verification

The selected pre-fix regressions failed **10/10**: fenced/prose JSON, four short
rejection codes, tool-only SDK outputs (two model settings), suppressed initial
PCM, and a follow-up exceeding the shared wait budget.

Recorded synthetic Haiku-like examples live in `server/test_planner_output.py`:
fenced JSON with whitespace/omitted fields/single step, prose plus two JSON
objects, a nine-step plan, and an exactly 30-word step. They are realistic test
records, **not captured provider responses**. Existing SDK text-response tests
continue exercising the fallback; the SDK boundary test now supplies parsed
`tool_use` input and checks the forced tool/schema. Existing adversarial safety,
cache, privacy and coded-guide tests remain in the focused set.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_output.py server/test_planner.py server/test_live_guide.py eval/swap/test_checker_regressions.py --tb=short` - PASS
(157 passed in 14.71s; exit 0; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1260 passed, 16 failed, 2 warnings in 64.37s; exit 1; summary and failure traces read).
Fifteen failures raise `PermissionError` for denied loopback sockets. The hazard
case instead raises `KeyError: 'state'` after `live_start_failed` records the same
`PermissionError`. Warnings concern short synthetic JWT keys. No network or
socket permission escalation was requested.

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
Logs: `/private/tmp/planner-live6-targeted.log`, `/private/tmp/planner-live6-full.log`.

Changed files: `server/planner.py`, `server/live_guide.py`, `server/gemini_live.py`,
`server/test_planner.py`, `server/test_planner_output.py`, this report, `RESULT.md`.
Limits: no `.env` access, external network, real API call, raw media, push, merge,
or deployment. Real Haiku tool acceptance and actual first-audio latency still
need an authorized live call; offline packet timing does not establish either.


## Planner Live fix-back round 7 — 2026-10-25

Base: `b45000c` (`Merge pkg/planner-live6`), branch `pkg/planner-live7`.
The reported main-call headphone plan hit the USB-only LED pack's `mains` rule
when it instructed normal use of a soldering iron's wall plug.

### Changes

- The plan checker applies the electronics pack's mains, USB and series-resistor
  refusals only to LED-build tasks. The pack's spoken-input behavior is unchanged.
  Every plan still receives the general safety gates, including live power,
  water/electricity, burning devices, hot-tool intent, chemicals and gas.
- Unsafe individual steps become that gate's fixed safety line. The checker clears
  all other model instructions from the replaced step and retains the step count
  and unaffected steps. Missing power-off/ventilation preparation stops affected
  actions with fixed lines too. Exact code-owned replacement objects survive
  cache validation, including fixed lines longer than the model speech ceiling.
  Malformed or private plans still reject.
- Unsafe task requests and post-model task validation reject with
  `cause: unsafe_task` and a gate id. Added general checks for opening a microwave
  and mains wiring; ordinary wall-outlet use does not match the mains-wiring check.
- The eval now counts only the production checker's rejection/replacement as a
  catch. Standalone electronics/safety hits remain diagnostic; they cannot mask
  an absent, crashing or permissive planner. All 15 existing bad fixtures are
  unchanged. Added `good14`, an eight-step synthetic headphone-repair plan with
  unplugging, ventilation and “Plug the soldering iron into the wall outlet and
  set it in its stand.” This is a hand-written regression, not a captured response.

### Verification

Four new regressions failed before the fix: the headphone control, unsafe charger
and microwave task causes, and one-step replacement/cache persistence. They pass
now. Updated existing whole-plan-drop assertions to require the fixed replacement,
cleared dangerous metadata, retained step count and stable revalidation. Synthetic
Live integration verifies replacement before installation/cache; task rejection
logs are verified both before model calls and at the post-model validation boundary.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_planner_output.py server/test_home_safety.py eval/swap/test_checker_regressions.py eval/swap/test_components.py eval/swap/test_heldout.py --tb=short` - PASS
(189 passed in 14.82s; summary read; before the final task-cause logging tests).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py eval/swap/test_checker_regressions.py eval/swap/test_heldout.py --tb=short` - PASS
(156 passed in 11.38s on final source; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1271 passed, 16 failed, 2 warnings in 65.15s on final source; exit 1;
summary and failure evidence read). Fifteen failures are denied loopback sockets;
one hazard-state `KeyError` follows Live startup `PermissionError`. These are the
same failed node IDs documented in round 6. No planner/checker test failed.
Warnings concern short synthetic JWT keys. No socket/network permission was requested.

Test: `~/Projects/a-eye/.venv/bin/python eval/swap/run.py checker --model current --out .pytest_cache/planner-live7-checker` - PASS
**15/15 bad plans caught; 1/14 good plans counted as false drops; 0 checker errors.**
`good14` passes unchanged despite its diagnostic electronics-pack hit. The only
false drop is existing `good01`, the loose-wire soldering plan without spoken
power-off and ventilation preparation. It now retains six steps with affected
instructions replaced, rather than dropping the whole plan; the eval counts
replacements as false drops too. All accepted/repaired bank plans were also checked
for stable revalidation.

Test: `git diff --check` - PASS.

Logs: `/private/tmp/planner-live7-targeted.log`,
`/private/tmp/planner-live7-final-targeted.log`,
`/private/tmp/planner-live7-full-final.log`.
Checker summary/rows: `.pytest_cache/planner-live7-checker/swap-checker-current.json`.

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

Changed files: `server/planner.py`, `server/safety.py`, `server/test_planner.py`,
`eval/cases/checker_good_plans.jsonl`, `eval/swap/checker.py`,
`eval/swap/test_checker_regressions.py`, `eval/swap/test_components.py`,
`docs/results/planner-live.md`, `RESULT.md`.
Limits: offline synthetic providers/fixtures only; no `.env` read, external network,
real API call, raw media, push, merge or deployment. The next real Haiku call is
not verified by this offline work. Local commit only.


## Planner Live round 8 — 2026-10-25

Merged background research and planning into one text-only forced `submit_plan`
call. The prompt considers task facts, tools, parts, mistakes and safety directly;
no separate research response or second call remains. Haiku remains the default,
SDK retries remain disabled, `max_tokens=700`, and `temperature=0.1`.
`PLANNER_TIMEOUT_S` now configures the whole build deadline and SDK timeout;
the default is 20 seconds. The final planner event retains total `ms` and adds
numeric `reason.call_ms` for the single completion attempt, including timeout or
cancellation; cache hits have no call timing. No model text or evidence is logged.

Live speech/guide production code is unchanged. A regression exercises synthetic
Live audio before and after the plan lands during an active reply, then verifies
GUIDE publication and the next guided turn. The existing bounded wait for an
explicit pending-plan “next” request remains unchanged.

Verification: the new single-call SDK regression failed twice on the original
implementation (two calls instead of one), then passed after the fix. Real-duration
slow fakes verify an eight-step plan at 15 seconds completes before 20 seconds,
and a 25-second completion is cancelled at the 20-second deadline without cache
or guide installation. Configured timeout, forced tool, token limit, temperature,
zero retries, and numeric call timing are asserted.

Initial targeted run: 102 passed, 1 failed in 50.01s. The sole failure was an old
exact log-shape assertion missing the new `call_ms` metadata; updated its metadata
filter. Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_planner_output.py -k 'sdk_one_call or diagnostics_without_client or lands_during' --tb=short` - PASS
(5 passed, 99 deselected in 0.98s; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1273 passed, 16 failed, 2 warnings in 100.67s; exit 1; summary and failures read).
All planner tests pass, including both real-duration slow fakes and the handoff
regression. The same 16 failed node IDs as round 7 remain: 15 denied loopback
socket operations and one hazard-state KeyError after Live startup PermissionError.
Warnings concern short synthetic JWT keys. No network permission was requested.
Test: `git diff --check` - PASS.

Logs: `/private/tmp/planner-live8-targeted.log` (initial assertion mismatch),
`/private/tmp/planner-live8-full.log` (final source and complete suite).

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

Changed files: `server/planner.py`, `server/test_planner.py`,
`server/test_planner_output.py`, `docs/results/planner-live.md`, `RESULT.md`.
Limits: offline synthetic provider/Live packets only; no `.env` read, external
network, real Haiku call, push, merge, deployment, or physical-device proof.
Actual Haiku latency and eight-step output within 700 tokens remain unverified.
Local commit only on `pkg/planner-live8`.


## Planner Live round 9 — 2026-10-25

Base: `a0d257d`, branch `pkg/planner-live9`. Reproduced the instant failure
against the installed `anthropic 2.3.0`: `AsyncMessages.create` does not accept
`temperature`. Both the default-model and override regressions raised TypeError
before reaching the mock transport. Removed that argument rather than bypassing
the SDK signature through extra_body. Single forced submit_plan, 700 tokens,
zero retries and the configured deadline remain unchanged.

Offline cause audit:

- `tools` and `tool_choice` are valid parameters in the installed sync and async
  messages.create signatures. The production request serializes both correctly.
- `_shared_anthropic` creates AsyncAnthropic per event loop; awaiting create is
  correct. No sync client or thread wrapper is involved in this request.
- `with_options(max_retries=0, timeout=float)` is supported and returns an async
  client. The real transport sees the configured read timeout and retry count 0.
- The failure is an unsupported temperature keyword, before any server-side
  temperature/tool-choice compatibility check could occur.
- `claude-haiku-5-5` appears in the installed ModelParam literals. This establishes
  SDK recognition only; live availability/account access is unverified.

Unexpected planner failures now add only `reason.error_type` (exception class
name), never the exception message/arguments. Tests cover TypeError and uncoded
ValueError, no plan installation/cache on failure, and absence of synthetic
private evidence in captured logs. Existing coded validation failures retain
their reason codes.

The new regression runs production planner.claude, _shared_anthropic,
with_options, SDK argument binding, serialization and typed response parsing.
Only construction supplies a fake HTTP transport and synthetic credential.
Anthropic 2.3.0 uses `httpx2` and explicitly rejects original `httpx` client types,
so this test uses `httpx2.MockTransport` (imported as httpx). It checks the actual
POST body, forced tool/schema, text-only message, model override, 700-token limit,
no temperature, configured timeout and first-request retry count. No sockets are
used by this regression. The former **kwargs-only SDK fake missed this defect.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py -k 'installed_sdk_request or error_logs_class' --tb=short` - FAIL before fix
(4 failed, 95 deselected in 0.82s; two unsupported-keyword failures and two missing
error_type failures). Proof: `/private/tmp/planner-live9-before.log`.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py -k 'installed_sdk_request or error_logs_class or sdk_one_call' --tb=short` - PASS
(6 passed, 93 deselected in 0.81s; summary read).
Proof: `/private/tmp/planner-live9-targeted.log`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1276 passed, 17 failed, 2 warnings in 102.70s; exit 1; summary and failure traces
read). Fifteen failures are denied local socket operations; one is the existing
hazard-state KeyError after Live startup PermissionError. The additional failure
is test_triggering_turn_audio_flows_while_planner_stalls waiting 0.5 seconds for
its fake planner to start. That test does not invoke the SDK. Its whole file
passes on isolated recheck without edits; suite-level timing/order cause remains
unresolved, and the full run is not claimed green. All server/test_planner.py
cases, including the four new regression cases, passed in the full run.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_output.py --tb=short` - PASS
(9 passed in 4.54s; summary read; no source changes after full run).
Test: `git diff --check` - PASS.
Logs: `/private/tmp/planner-live9-full.log`,
`/private/tmp/planner-live9-output-recheck.log`.

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
- `server/test_planner_output.py::test_triggering_turn_audio_flows_while_planner_stalls`
- `server/test_step_check.py::test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero`
- `scripts/test_ready.py::test_live_pair_request_on_fake_socket`

Files changed: `server/planner.py`, `server/test_planner.py`,
`docs/results/planner-live.md`, `RESULT.md`.
Limits: no .env read, network access, real provider call, push, merge or deployment.
The offline SDK failure is reproduced and fixed; the original live exception was
not captured, so attribution of that specific call remains a strong inference.
Live model acceptance and latency still need an authorized real call. Local
commit only in this worktree.


## Planner Live round 10 — 2026-10-25

Base: `8efa591`, branch `pkg/planner-live10`. The reported real call returned in
5668 ms but was rejected as `missing_steps`; that timing and rejection are user
supplied, not remeasured here. No provider response from that call was available.

Inspected the actual POST `/v1/messages` body built by installed anthropic 2.3.0
through production `planner.claude`, the shared async client and an in-process
`httpx2.MockTransport`. Before this change, `task` and `steps` were already
required at the top level and the parser already scanned all content blocks for
`submit_plan`. Neither missing schema nesting nor reading only content[0] was
reproduced. JSON-string steps did reproduce a local rejection (`schema`, not
`missing_steps`); truncation remains a hypothesis.

The serialized tool schema now requires top-level `task` and `steps`, with
`steps` an array of 2–8 simple objects containing `say`, `show`, `target`, `check`
and `safety`; `say` is required, and existing required `show` and `safety` remain
aligned with the local validator. Existing length, privacy,
spoken-preparation and unsafe-action checks still run over normalized values.
The schema and prompt request at least two generated steps; the local checker
retains compatibility with existing single-step plans and legacy object steps.

`validate()` decodes JSON-string steps before the existing checks. Malformed
strings still reject, and unsafe decoded actions still receive the code-owned
safety replacement. The request and prompt use 1200 output tokens. One forced
tool, zero retries, timeout, model override and text-only evidence are unchanged.
When a tool input has no top-level `steps`, `planner_tool_input` logs only its
sorted top-level key names plus the fixed cause code; it does not log values or
nested content. Unexpected nesting remains rejected, with keys available to
diagnose it on the next authorized live run.

Saved `server/fixtures/planner_tool_use.json` is a realistic synthetic recording,
not a captured provider response. It contains a text block followed by a
`submit_plan` tool_use block. The real SDK regression replays list steps,
JSON-string steps and missing/nested steps for default and overridden model/
timeout settings. It checks the serialized request and typed response parsing,
including names-only diagnostics. Separate checks cover schema bounds, missing
show rejection, malformed strings and safety enforcement after decoding.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py -k 'installed_sdk_request or submit_plan_schema or json_string_steps' --tb=short` - FAIL before fix
(8 failed, 5 passed, 97 deselected in 1.05s; summary read).
Proof: `/private/tmp/planner-live10-before.log`.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py -k 'installed_sdk_request or submit_plan_schema or json_string_steps or sdk_one_call' --tb=short` - PASS
(15 passed, 95 deselected in 0.67s; summary read).
Proof: `/private/tmp/planner-live10-targeted.log`.

The first full run caught an over-broad omission normalization: defaulting missing
`show` to `say` accepted existing bad case `bad11`. Removed that normalization
and retained required `show`/`safety` in both schema and validator. The challenge
bank and its thresholds were not changed.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL, intermediate state
(17 failed, 1287 passed, 2 warnings in 100.94s; summary and failure traces read).
Sixteen failures are the existing denied-loopback/downstream startup failures;
the additional checker failure is corrected in the final source.
Proof: `/private/tmp/planner-live10-full.log`.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py eval/swap/test_checker_regressions.py -k 'installed_sdk_request or submit_plan_schema or json_string_steps or sdk_one_call or production_checker_challenge_bank' --tb=short` - PASS, final source
(16 passed, 153 deselected in 0.77s; summary read).
Proof: `/private/tmp/planner-live10-final-targeted.log`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL, final source
(16 failed, 1288 passed, 2 warnings in 101.33s; exit 1; summary and failure traces
read). All planner and checker tests pass. Fifteen failures are denied local
socket binds (PermissionError); the remaining hazard-state KeyError follows
Live startup PermissionError. These match the previously documented 16 failures.
No network permissions were changed or retried outside the sandbox.
Proof: `/private/tmp/planner-live10-final-full.log`.
Test: `git diff --check` - PASS.

Final failed node IDs:

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

Files changed: `server/planner.py`, `server/test_planner.py`,
`server/fixtures/planner_tool_use.json`, `docs/results/planner-live.md`, `RESULT.md`.
Limits: no .env read, network access, real provider call, push, merge or deployment.
The fixture is synthetic. The live failure cause, provider acceptance and latency
with the larger token budget remain unverified. Local commit in this worktree.
