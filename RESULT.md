## Whole-index past-call search — pkg/whole-index

Saved clip search now uses up to six concurrent batches of 60 IDs, newest first,
merges by rank/score and enforces the total result limit. One four-second deadline
includes index lookup and shared-index fallback; completed hits survive slow or
failed batches. HTTP failures log status only. Owner/demo rules are unchanged.

Files changed: `server/rewind.py`, `server/test_past_calls.py`,
`docs/results/whole-index-search.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_rewind.py server/test_past_calls.py server/test_clip_play.py` - FAIL (39 passed, 7 failed in 6.18s; summary read).
All seven new cases passed. All seven failures reproduce with unchanged HEAD
Rewind source (32 passed, 7 failed, 6 deselected); no existing assertions changed.
Test: `git diff --check` - PASS.

Limits: six batches cover at most 360 saved IDs per index. Offline audit hook
blocked network and `.env` access; no real provider proof or push.
Details, baseline method and local logs: [whole-index report](docs/results/whole-index-search.md).

---

## Found-memory clip playback — pkg/clip-play

The existing found card plays bounded this-call JPEG flipbooks and optional native
HLS windows for saved calls. Boxes and layout are retained; routing is unchanged.
Server media stays out of model tool results; retrieval has a two-second timeout.
Playback stops on sheet close/replacement. Optional v2 schema/type/examples updated
for the explicitly requested wire fields. No new dependency.

Changed files and limits: [docs/results/clip-play.md](docs/results/clip-play.md).

Python commands ran with `PYTHONPATH=.pytest_cache/clip-play/offline:.` to block
network and `.env` access. The Makefile was not invoked because it includes `.env`.

Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q server - FAIL (1146 passed, 22 failed, 2 warnings; final source; summary read).
Test: node --test client-web/*.test.mjs - PASS (175 passed).
Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_clip_play.py server/test_live_prefetch.py::test_rewind_consent_revocation_blocks_lookup_and_cached_evidence - PASS (8 passed).
Test: targeted contracts/Rewind/past-call/Live-memory/review checks - FAIL (136 passed, 5 baseline failures; contract examples passed).
Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q - FAIL (1750 passed, 25 failed, 4 errors; before final text-only-hit fix, subsequently verified by the final server run).
Test: git diff --check - PASS.

Final server failures: 15 network-dependent checks blocked, 7 non-network failures
reproduced against original f5bbfc5. The repository-wide run additionally hit
blocked device sockets and a denied synthetic `.env` read. No tests weakened.
No real provider/browser/device proof, network access, `.env` reads, or push.

---

## Past-call recall — pkg/past-calls, 2026-10-25

Saved calls now retain bounded local text; past-call questions search saved
videos with consent or read the newest saved summary before the old fallback.
WebSocket teardown snapshots text before clearing RAM. No UI changes.

Files: `server/recent_memory.py`, `server/rewind.py`, `server/ws2.py`,
`server/test_past_calls.py`, `docs/results/past-calls.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_past_calls.py` - PASS (10 passed; original 8 failed before fix).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_past_calls.py server/test_recent_memory.py server/test_recall_review.py server/test_recall_pipeline.py` - PASS (40 passed before two additional acceptance checks).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server` - FAIL (1144 passed, 15 failed, 2 warnings, 95.81s; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server --lf --tb=line` - FAIL (14 denied loopback binds; one downstream Live startup assertion; 15 failed in 1.04s).
Test: `git diff --check` - PASS.

Limits: old saved calls cannot gain summaries offline; save a new call for generic
recall. No `.env` reads, network access granted, real provider/device proof, push
or deployment. Detailed behavior, evidence and failed nodes:
[past-calls report](docs/results/past-calls.md).

---

## Final product README rewrite

Changed files: README.md and this RESULT.md entry. The README now describes the
Dad call, electronics and tie guides, coded stops, object boxes, time-scoped
memory, background planning, parts shelf, local mode, system map and model evals.
Claims were checked against current source, the Makefile and existing evidence.
Only the requested performance and cost figures are included.

Limits: guest sign-in does not itself enable Private mode; the README makes that
distinction. Independent decision accuracy and demo timings are attributed to
recorded team evidence, not remeasured. No network, credential-file access,
application run, push or deployment was performed. The live map URL was not fetched.

Test: README reference, Makefile target, section-shape and wording checks - PASS.
Test: git diff --check - PASS.
Test: project Python scripts/check_public.py, before edits - PASS.
check_public: PASS (775 files, 0 hits, 154 binary files without visual inspection)
Test: project Python scripts/check_public.py, rewritten README - FAIL.
check_public: FAIL (775 files, 2 hits, 154 binary files without visual inspection)

The final scan flags only the explicitly requested public map URL and team
credit in README.md (known identity rule). Both are retained as requested.
The checker was not weakened or changed. A final publication PASS is not claimed.

---

## Planner Live fix-back round 5 — pkg/planner-live5, 2026-10-25

Base: `9469744`. Default planner model is now `claude-haiku-5-5`; env overrides,
two sequential calls, zero retries, and the 12-second total deadline remain.
Safe hot-tip warnings pass both the planner and electronics check; spoken intent
to touch the hot tip and unsafe plan actions still stop. Rejections log only a
coded gate id. Spoken headphone unplugging now satisfies power-off preparation.

Added a saved eight-step headphone-repair fixture with soldering precautions.
It is hand-written, not captured provider output. It passes the checker, installs
from synthetic Live input, reloads from cache, and advances through all eight
steps. The 15 existing bad cases and false-drop threshold are unchanged.

Changed files: `server/planner.py`, `server/safety.py`,
`server/packs/electronics.py`, `server/test_planner.py`,
`eval/cases/checker_good_plans.jsonl`, `eval/swap/checker.py`,
`eval/swap/test_checker_regressions.py`, `eval/swap/test_components.py`,
`docs/results/planner-live.md`, and `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py eval/swap/test_checker_regressions.py server/test_home_safety.py server/test_ee_guide.py eval/swap/test_components.py eval/swap/test_heldout.py --tb=short` - PASS
(185 passed in 12.00s; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1253 passed, 16 failed, 2 warnings in 60.76s; summary and failure evidence read).
Fifteen failures are denied local sockets; one hazard assertion fails downstream
of Live startup `PermissionError`. No planner/checker/held-out failure remains.
Log: `.pytest_cache/planner-live5-full.log`.
Test: `~/Projects/a-eye/.venv/bin/python eval/swap/run.py checker --model current --out .pytest_cache/planner-live5-checker` - PASS
(15/15 bad caught, 1/13 false-dropped, 0 errors). The new repair fixture passes;
existing `good01` lacks the required spoken preparation and still drops.
Test: `git diff --check` - PASS.

Limits: no `.env` read, network permission change, real provider request, push,
merge, deployment, or device proof. Real Haiku latency is unverified.
Full report: [planner-live](docs/results/planner-live.md).

---

## Planner Live fix-back round 4 — pkg/planner-live4, 2026-10-25

Base: `a5b3cb4`. Model `turnComplete` no longer discards rejected planner input.
A separate bounded transcript survives model-output resets, retries whenever
input grows after a 300 ms debounce, and resets on fresh mic/typed input,
interruption, or reconnect. Positive decisions latch; unchanged rejections are
deduplicated. The existing three-second pending-plan hold remains unchanged.

The interleaved PCM/output/input regression reproduced loss of the final repair
request when `turnComplete` preceded the last input chunk (1 failed, 1 passed
before production changes). Both orderings now plan from the full text after the
21-character rejection. The exact second-turn next-step question waits for the
pending plan and speaks step 1, without advancement or another build.

Changed files: `server/gemini_live.py`, `server/live_guide.py`,
`server/test_planner.py`, `docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py --tb=short` - PASS
(100 passed in 11.08s; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1238 passed, 16 failed, 2 warnings in 60.13s; summary and failure evidence read).
Fifteen failures are denied local sockets; the hazard assertion fails downstream
of Live startup `PermissionError`. These match the earlier sixteen failed node
IDs; no planner/checker test failed. Log: `.pytest_cache/planner-live4-full.log`.
Test: `git diff --check` - PASS.

Limits: synthetic packets/fake providers only; no `.env` read, network permission
change, real provider call, push, merge, deployment, or device proof. Retained
rejected transcription requires a fresh mic/typed/interruption signal to identify
a new utterance. Details: [planner-live](docs/results/planner-live.md).

---

## Planner Live merged-main fix — pkg/planner-live3, 2026-10-25

Base: `c83d4a1` with checker and planner-live2 merged. The two soldering failures
were invalid fake plans missing the checker's newly required ventilation step;
requests were accepted by `task_decision`. Tests now supply a safe soldering
lesson and still reject unprepared plans. No safety checker was weakened.

Reproduced the early-finished transcription latch: judging only `dad` rejected
once and suppressed the final repair request. Live now debounces finished/first
model output for 150 ms, refreshes on trailing input, and latches only positive
decisions. `turnComplete` flushes before reset. Planner diagnostics include text
length as `reason.chars`; full repair text yields 67. Seven timed packet cases
verify step 1 installation and the exact next-step follow-up; three cases verify
deferred work cannot survive stop, interruption, or close.

Changed files: `server/gemini_live.py`, `server/live_guide.py`, `server/planner.py`,
`server/test_planner.py`, `docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py eval/swap/test_checker_regressions.py --tb=short` - PASS
(133 passed in 7.45s; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1236 passed, 16 failed, 2 warnings in 57.25s; summary and failure traces read).
Fifteen failures are sandbox-denied loopback sockets; one hazard assertion fails
after fake Live startup reports `PermissionError`. Full output is retained at
`.pytest_cache/planner-live3-full.log`. No planner/checker regression failed.
Test: `git diff --check` - PASS.

Limits: no `.env` read, network access granted, real provider call, push, merge,
deployment, or physical-device proof. The real call's exact packet sequence is
unknown; the early-finished failure is reproduced with synthetic timed packets.
Details: [planner-live](docs/results/planner-live.md).

---

## Planner Live regression fix — 2026-10-25

Fixed the problem-first headphone repair trigger and the exact follow-up
“Okay, what is the next step?”. Completed Live input is observed once, with
planner start/outcome diagnostics and an explicit missing-client result.
The packet regression uses the real app/default planner and a fake SDK transport.

Changed files: `server/gemini_live.py`, `server/planner.py`, `server/packs/home.py`,
`server/test_planner.py`, `docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_live_guide.py --tb=short` - PASS
(66 passed in 1.27s).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1166 passed, 16 failed, 2 warnings in 51.61s; summary and failure traces read).
Fifteen failures are sandbox-denied loopback sockets; one is a downstream hazard
assertion after fake Live startup fails with `PermissionError`.
Test: `git diff --check` - PASS.

Limits: no `.env` read, external network, real provider call, push or deployment.
The full suite is not green; network permissions were not lifted.
Details and retained proof: [planner-live](docs/results/planner-live.md).

---

## Planner merge of local main — 2026-10-25

Merged local `main` at `8ec3ae3` into `pkg/planner` from `e307a60`.
Resolved `server/gemini_live.py` by preserving main's user-input-only scope
redirect, separate from the safety latch, before typed planner observation.
Planner observation at finished-transcription and turn-complete boundaries also
respects the scope hold. Main's acceptance fixes and all planner wiring remain.
`RESULT.md` retains both branches' report sections below.

Resolution files: `server/gemini_live.py`, `RESULT.md`. Other merge changes are
inherited unchanged from local main; planner implementation/tests remain intact.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` - FAIL
(1081 passed, 16 failed, 2 warnings in 51.73s; summary read, exit 1).
Only the authorized sandbox socket exceptions remain: fifteen tests fail directly
on denied `127.0.0.1` binds. The hazard test raises `KeyError: 'state'` after its
fake Live server fails to bind; captured output records
`live_start_failed` with `error: PermissionError` before that assertion.
Warnings concern short synthetic JWT keys. Full output:
`/private/tmp/aeye-planner-merge-pytest.log`.

Sandbox socket failures, by pytest node ID:

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
- `server/test_live_streaming.py::test_ws2_hazard_sends_stop_caption_and_fixed_audio` (secondary failure)
- `server/test_step_check.py::test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero`
- `scripts/test_ready.py::test_live_pair_request_on_fake_socket`

Test: `git diff --check` - PASS.
Limits: no `.env` read, external network, push, real provider or device verification.
Socket restrictions were not lifted for tests. Reports below describe prior work;
their historical checks and permissions do not describe this merge run.

---

# RESULT: Background task planner — 2026-10-25

Implemented the two-call background planner on `pkg/planner`; Gemini remains the planned
guide's only talker. Coded guides win, rejected/timed-out plans fall back to free-form, and
validated plans cache locally with user-reported completion marked good.

Files changed: `server/planner.py`, `server/live_guide.py`, `server/gemini_live.py`,
`server/test_planner.py`, `docs/results/planner.md`, `RESULT.md`.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` -
FAIL (1064 passed, 17 failed, 2 warnings in 51.38s). All 51 planner tests passed. Fifteen failures
are denied localhost fake-server binds; the other two also reproduce with the unchanged Live
modules (one home-guide timeout, one hazard test affected by a denied Live start).

Test: `git diff --check` - PASS.

Limits: no real provider/device call, no `.env` read, no UI/contract changes, no push. The
coordinator owns real-call acceptance before 05:00 PDT. Full design, failure attribution and
acceptance instructions: [docs/results/planner.md](docs/results/planner.md).

The inherited report follows unchanged.

---

# RESULT: Background context and Live streaming — 2026-10-24

Continued the inherited uncommitted background-context work in `pkg/bg-context`.
All changes remain uncommitted.

Live now sends 150 ms PCM chunks after a 250 ms initial guard, rather than holding
the whole answer until turn completion. Accumulated output and input transcripts
run through the coded safety checks. A hazard cancels playback, discards buffered
audio, and uses the existing fixed-line caption/TTS path. Late provider packets
cannot reopen a safety stop; ordinary barge-in remains usable. Captions stream
using the existing contract and one PCM utterance ID per reply.

Context builds and publication run in a separate cancellable worker, with
coalesced triggers, bounded summaries, consent checks, coded hazard stops and
timeouts. Removed blocking Live context collection and the mandatory
`gather_context` prompt instruction. The optional lookup remains available.

### Files changed

- `server/gemini_live.py`: streaming PCM, incremental captions/safety, latched
  stops, normal-barge recovery, background publication and worker lifecycle.
- `server/context_agent.py`: background context assessment/worker (inherited
  uncommitted implementation retained and verified).
- `server/agent.py`: session's background worker reference.
- `server/ws2.py`: scene triggers and removal of the redundant Live-startup gather.
- `server/test_bg_context.py`, `server/test_context_agent.py`: nonblocking context,
  publication, cancellation, routing/privacy, hazards and optional lookup tests.
- `server/test_live_streaming.py`, `server/test_gemini_live.py`: fake Live socket
  streaming/safety tests, normal barge recovery, and actual `/ws2` fixed-line PCM.
- `server/live_latency_probe.py`: fake/real provider to loopback-client benchmark;
  only timing metadata is printed, never media or credentials.
- `docs/results/bg-context.md`: implementation, benchmark method, proof and limits.
- `RESULT.md`: this handoff, appended to the prior report.

### Measurement

Three fake-provider trials per version: client first-audio p50 **1767.6 -> 315.1
ms** (82% lower). Provider turn-complete p50 stayed **1762.6 -> 1761.6 ms**.
This timestamps PCM received by a WebSocket client, not audible device playback.
Background assessment and camera are disabled for this bottleneck measurement;
a separate test verifies audio flows while a background assessment is stalled.
Proof: `/private/tmp/aeye-live-before.json`, `/private/tmp/aeye-live-after.json`.

Both real before/after probes through the main checkout's make-loaded credentials
were blocked by the existing daily cloud budget before any provider call. The
cap was not changed. Proof: `/private/tmp/aeye-live-real-main.log`.

### Tests

Test: .venv/bin/python -m pytest -q server/test_live_streaming.py server/test_bg_context.py server/test_gemini_live.py server/test_context_agent.py server/test_ws2.py --tb=short - PASS (59 passed in 5.13s).

Test: make -k test PY=.venv/bin/python - FAIL (Python: 1 failed, 1257 passed, 2 warnings in 68.89s; Node: 169 passed, 0 failed).

Test: node --test client-web/ - PASS (169 passed, 0 failed, 0 skipped).

Test: git diff --check - PASS.

Final logs: `/private/tmp/aeye-bg-context-targeted.log`,
`/private/tmp/aeye-bg-context-verified-full.log`,
`/private/tmp/aeye-bg-context-node.log`.

The sole final failure is the unchanged
`vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`:
`vision/fixtures/gemini_payment_required.json` is absent and not tracked in this
checkout. No vision-package files were changed. An intermediate overlapping run
also missed an unrelated status-test deadline; it passed in the final run.

### Limits and next checks

No physical-client audio playback, real Gemini latency, or real Claude context
quality was verified. The small initial guard cannot retract audio already
played when transcription trails audio. Full-frame Claude input remains gated
on the separate package's consent/normalization hook; absent that hook, this
builder sends text only. Restore the missing vision fixture through its owner,
and repeat real before/after measurements when the existing cloud budget permits.

## Main hotfix merge verification — 2026-10-24

Checkpoint: `67ac9eb`. Merged local `main` at `fad5a5e` into `pkg/bg-context`.
No push. The merge retains the cancellable background context builder,
incremental transcript safety checks, 250 ms initial guard, and 150 ms PCM chunks.
Captions precede PCM and retain one utterance ID throughout the streamed reply.
The client cuts queued playback on Live `listening` interruptions. The lead's
fallback auto-pointer runs when Live did not call `point_at`; its per-turn flag
resets with the reply. Pointer budget remains 3 seconds and confidence 0.6.
Cross-call Rewind remains identical to main, including owner-scoped kept calls.

Resolution files: `server/gemini_live.py`, `server/test_live_streaming.py`.
Main also supplies `client-web/agent.html`, `client-web/agent.js`,
`server/pointer.py`, `server/rewind.py`, `server/test_ee_guide.py`,
`server/test_gemini_live.py`, and `server/test_pointer.py`.
Restored `vision/fixtures/gemini_payment_required.json` byte-for-byte from the
main checkout's untracked fixture; it contains only a generic provider error.
This fixes the previously recorded missing-fixture failure without changing the test.
Updated receipts: `RESULT.md` and `docs/results/bg-context.md`.

Test: affected Live/context/pointer tests - PASS (78 passed in 4.14s).
Test: `make -k test PY=.venv/bin/python` - PASS
(1260 passed, 2 warnings in 67.17s; web: 169 passed, 0 failed).
Test: `node --test client-web/` - PASS (169 passed, 0 failed, 0 skipped).
Test: `make smoke PY=.venv/bin/python` - PASS
(`steps=['SAFETY', 'IDENTIFY', 'LOCATE', 'GUIDE', 'AWAIT'] target_overlays=1`, `SMOKE PASS`).
Test: `/private/tmp/aeye-bg-merge-rewind-check.py` with the project Python and
worktree PYTHONPATH - PASS (saved-call retrieval after empty/current-call misses;
other-owner isolation; fake TwelveLabs, metadata only).
Test: `git diff --cached --check` - PASS.

Real checks used `make -f Makefile -f /private/tmp/aeye-bg-merge-probe.mk`, with
`PY=.venv/bin/python`. The supplemental makefile
loads the main checkout's `.env` without printing it and invokes this worktree's
`server.live_latency_probe --real --trials 5` and `scripts/gemini_live_check.py`.
The existing daily cap is $5; the ledger reports $5.03 and a latched stop.
No cap, ledger, cost rate, key, or app privacy setting was changed.

Real latency: BLOCKED — `Live latency probe: blocked by existing daily cloud budget; no provider call made`.
Real camera: BLOCKED — `Private: Google blocked` (the budget forces local-only mode).
Real first client-audio samples: 0/5; p50 unavailable. No real provider latency or
physical-device playback claim. A separate temporary $1 probe budget was proposed
for user approval; it has not been used.

Evidence under `/private/tmp/`: `aeye-bg-merge-targeted.log`,
`aeye-bg-merge-full.log`, `aeye-bg-merge-node.log`, `aeye-bg-merge-smoke.log`,
`aeye-bg-merge-rewind.log`, `aeye-bg-merge-real-latency.log`, and
`aeye-bg-merge-real-camera.log`. The initial sandboxed targeted attempt could
not bind loopback sockets; the reported test pass used permitted socket access.

## Live resilience — 2026-10-25

Branch: `pkg/live-resilience`; committed locally, no push.
Full handoff: [docs/results/live-resilience.md](docs/results/live-resilience.md).

Setup now requests session resumption and sliding-window compression. The latest
resumable handle is reused on disconnect/goAway, and a healthy minute renews the
single retry allowance. A stopped session keeps its audio latch and drops the
handle. First audio releases after 250 ms of PCM is buffered and safety checks
pass, including the initial partial chunk. The setup text limits catchphrases
and asks for a choice with a reason.

Files changed: `server/gemini_live.py`, `server/test_gemini_live.py`,
`server/test_live_streaming.py`, `server/test_live_prefetch.py`,
`docs/results/live-resilience.md`, `RESULT.md`. Production edits stay in setup,
the reconnect path, and `flush_audio()`; memory-turn implementation is unchanged.
Two prefetch fixtures now send enough synthetic PCM for the duration-based hold.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_gemini_live.py server/test_live_streaming.py --tb=short` - PASS (43 passed in 3.26s).
Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_prefetch.py --tb=short` - PASS (12 passed in 1.22s).
Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server` - PASS (818 passed, 2 warnings in 45.07s; summary read, exit 0).
Test: `git diff --check` - PASS.

Proof: `/private/tmp/aeye-live-resilience-server-final.log`.
Limits: no `.env` read and no real Gemini calls. Real provider acceptance of the
new setup fields, real 2–3 minute continuity, latency and physical playback are
not verified. All test media and provider responses were synthetic.

## System map (pkg/system-map)

See docs/results/system-map.md and docs/results/system-map-review.md.

## fix-memory

See its docs/results report.

## fix-recall

See its docs/results report.

## fix-guide

See its docs/results report.

## fix-bridge — 2026-10-25

Mic chunks preserve guide/memory holds and the safety latch. The inherited
`prompt_turn()` post-wait safety/closed checks already cover the second finding;
two new regression functions cover both findings (eight cases).

Changed files: `server/gemini_live.py`, `server/test_gemini_live.py`,
`docs/results/fix-bridge.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router` - PASS
(908 passed, 2 warnings in 50.90s; summary read, exit 0).
Test: targeted bridge regressions - PASS (8 passed, 36 deselected in 0.76s).
Test: `git diff --check` - PASS.

Limits: fake providers and synthetic media only; no `.env` read, real Gemini
call, push, deployment or physical-device proof. Initial full run needed a rerun
with local socket access. Full evidence: [fix-bridge](docs/results/fix-bridge.md).

## acceptance

See its docs/results report.

## refocus

See docs/results/refocus-electronics-tie.md.

## scope-fix — 2026-10-25

Scope replies now inspect only user input, suppress only the rejected Live turn,
and allow the next question to receive audio. Cabinet/valve scene captions and
Live speech no longer trigger scope stops. Classic home requests receive the
electronics/tie scope line with existing safety gates preserved.

Changed files: `server/packs/__init__.py`, `server/gemini_live.py`, `server/agent.py`,
`server/test_refocus.py`, `server/test_gemini_live.py`, `docs/results/scope-fix.md`,
`RESULT.md`. Completed the coordinator's inherited partial changes.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` - PASS
(1034 passed, 2 warnings in 51.45s; summary read, exit 0).
Test: focused refocus and mic-hold regressions - PASS (26 passed in 0.91s).
Test: `git diff --check` - PASS.

Limits: synthetic media and fake providers only; no `.env` read, real Gemini call,
push, deployment or physical-device proof. Local branch: `pkg/scope-fix`.
Full evidence: [scope-fix](docs/results/scope-fix.md).

## accept-fix

See its docs/results report.

## evals

See its docs/results report.

## checker

See its docs/results report.

## planner-live2

See its docs/results report.

## planner-live6 — 2026-10-25

Forced Anthropic `submit_plan` tool output, normalized harmless schema omissions,
and retained strict safety/size checks. Schema failures emit short content-free
codes. The triggering utterance cannot hold Live's first reply; a pending-plan
follow-up shares one three-second deadline with the provider-idle wait.

Files changed: `server/planner.py`, `server/live_guide.py`, `server/gemini_live.py`,
`server/test_planner.py`, `server/test_planner_output.py`,
`docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_output.py server/test_planner.py server/test_live_guide.py eval/swap/test_checker_regressions.py --tb=short` - PASS
(157 passed in 14.71s; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1260 passed, 16 failed, 2 warnings in 64.37s; summary/traces read; all failures
trace to denied local sockets, including one downstream hazard-state KeyError).
Test: `git diff --check` - PASS.

Pre-fix proof: 10 selected regressions failed. Final logs and all failed node IDs
are linked/listed in [the round 6 report](docs/results/planner-live.md).
Limits: fixtures are synthetic Haiku-like records; no real provider acceptance
or physical audio timing claim. No `.env` read, network escalation, push, merge,
or deployment. Local commit only on `pkg/planner-live6`.


## planner-live7 — 2026-10-25

LED-only mains/USB/series refusals now apply only to LED-build plans. General
safety gates remain universal. Unsafe steps become fixed safety lines with their
metadata cleared and count preserved; unsafe tasks reject with `unsafe_task`.
Replacements survive cache reload. Added the realistic headphone wall-outlet
control, plus microwave/mains-wiring general guards and production-only eval scoring.

Files changed: `server/planner.py`, `server/safety.py`, `server/test_planner.py`,
`eval/cases/checker_good_plans.jsonl`, `eval/swap/checker.py`,
`eval/swap/test_checker_regressions.py`, `eval/swap/test_components.py`,
`docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py eval/swap/test_checker_regressions.py eval/swap/test_heldout.py --tb=short` - PASS
(156 passed in 11.38s; final source; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1271 passed, 16 failed, 2 warnings in 65.15s; final source; summary read).
The same 16 socket-related failures as round 6: 15 PermissionErrors plus a
hazard-state KeyError after Live startup PermissionError. No planner/checker failures.
Test: `~/Projects/a-eye/.venv/bin/python eval/swap/run.py checker --model current --out .pytest_cache/planner-live7-checker` - PASS
(15/15 bad caught, 1/14 false drops, 0 errors). Headphone `good14` passes unchanged;
existing `good01` lacks required preparation and is repaired, counted as a false drop.
Test: `git diff --check` - PASS.

Four new regressions failed before the fix. Broader focused checks passed 189 tests
before the final task-cause logging additions. Logs, failed node IDs and behavior
are recorded in [the round 7 report](docs/results/planner-live.md).
Limits: no `.env` read, external network, real provider call, raw media, push,
merge or deployment. Local commit on `pkg/planner-live7` only.


## planner-live8 — 2026-10-25

One forced `submit_plan` call merges research and planning, with 700 output tokens,
temperature 0.1, no retries, and `PLANNER_TIMEOUT_S` defaulting to 20 seconds.
Planner result metadata includes numeric `reason.call_ms`. Existing speech and
guide handoff code remains unchanged; synthetic audio verifies the current reply
continues when the plan lands and the next guide turn uses it.

Files changed: `server/planner.py`, `server/test_planner.py`,
`server/test_planner_output.py`, `docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py server/test_planner_output.py -k 'sdk_one_call or diagnostics_without_client or lands_during' --tb=short` - PASS
(5 passed, 99 deselected in 0.98s; summary read).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1273 passed, 16 failed, 2 warnings in 100.67s; summary and failure evidence read).
All planner tests pass. The 15-second fake installs eight steps before 20 seconds;
the 25-second fake times out at 20 seconds without installation or caching.
All 16 failures match round 7's denied sockets/downstream hazard-state failure.
Test: `git diff --check` - PASS.

Full log: `/private/tmp/planner-live8-full.log`. Details and failed node IDs:
[planner-live report](docs/results/planner-live.md).
Limits: no `.env` read, external network, real provider call, push or deployment.
Real Haiku latency/output fit remains unverified. Local commit only.


## planner-live9 — 2026-10-25

Reproduced instant TypeError with installed anthropic 2.3.0: messages.create no
longer accepts temperature. Removed it from the planner; forced tool output,
async shared client, timeout, zero retries and token limit remain unchanged.
Unexpected errors log exception class only. Added real SDK request/response
regressions with httpx2.MockTransport (the installed SDK rejects httpx clients),
plus privacy checks for TypeError and uncoded ValueError.

Files changed: `server/planner.py`, `server/test_planner.py`,
`docs/results/planner-live.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner.py -k 'installed_sdk_request or error_logs_class or sdk_one_call' --tb=short` - PASS
(6 passed, 93 deselected in 0.81s; four new cases failed before fix).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1276 passed, 17 failed, 2 warnings in 102.70s; summary and failure traces read).
Sixteen failures match prior denied-socket/downstream hazard failures. One
additional planner-audio test hit its 0.5s startup deadline; its full file passed
unchanged in isolation. Suite-level timing/order cause is unresolved.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_output.py --tb=short` - PASS
(9 passed in 4.54s; summary read).
Test: `git diff --check` - PASS.

Proof: `/private/tmp/planner-live9-before.log`,
`/private/tmp/planner-live9-targeted.log`, `/private/tmp/planner-live9-full.log`,
`/private/tmp/planner-live9-output-recheck.log`.
Limits: no .env read, network access, real provider call, push or deployment.
SDK accepts the request offline; live provider acceptance remains unverified.
Details: [round 9 report](docs/results/planner-live.md).


## fix-false-stop — 2026-10-25

Reproduced live_power false positives in streamed soldering speech and a Live
context summary, plus a hot-tip warning false stop and a latched next voice turn.
The supplied reply prefix alone passes; the original triggering packet remains
unconfirmed. Narrowed electrical-state matching, retained real hazard stops,
and let new user transcripts recover from rejected model speech while stale
provider output remains blocked.

Files changed: `server/safety.py`, `server/gemini_live.py`,
`server/test_false_stop.py`, `docs/results/fix-false-stop.md`, `RESULT.md`.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_false_stop.py server/test_recall_review.py server/test_home_safety.py eval/swap/test_checker_regressions.py --tb=short` - PASS
(103 passed in 1.62s).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1291 passed, 16 failed, 2 warnings in 100.95s; summary and failure traces read).
Fifteen denied socket binds; one downstream missing state after Live startup
PermissionError. Matches the existing socket-related failures. Local log:
`.pytest-false-stop.log`. No production changes after this run.
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_false_stop.py --tb=short` - PASS
(15 passed; final regression matrix adds recovery without a provider boundary).
Test: `git diff --check` - PASS.

Limits: no `.env` read, network access, provider call, push, merge, deployment,
or physical-device proof. Full report: [fix-false-stop](docs/results/fix-false-stop.md).

## live-polish

See its docs/results report.

## planner-live10

See its docs/results report.

## planner-live11 — 2026-10-25

Fixed the emergency-line-as-plan-step path: calm, gate-specific precautions,
legacy cache migration, and per-step gate-ID logging. Water/electric matching
requires an explicit water word and an electrical word within one sentence;
no pairing across plan fields/task context. Both eight-step headphone fixtures
now replay their spoken output without stop latches. Real hazard input still stops.
A bounded normal soldering-iron plug-in instruction no longer hits the general
outlet-repair refusal; repair/mains/hazard checks remain.

Fixed main failure
`server/test_gemini_live.py::test_fake_live_wire_audio_tools_captions_and_revocation`:
its assertion now expects the complete intentional `live=True` persona block.
Other wire/audio/consent assertions remain unchanged.

Changed: `server/planner.py`, `server/safety.py`, `server/gates.py`,
`server/test_planner_safety_steps.py`, `server/test_planner.py`,
`server/test_gates.py`, `server/test_gemini_live.py`,
`eval/swap/test_checker_regressions.py`, `docs/results/planner-live.md`, `RESULT.md`.

Test: `PYTHONPATH=.pytest_cache/offline:. ~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1370 passed, 1 failed, 2 warnings in 103.28s). Only
`scripts/test_public.py::test_tracked_scan_and_git_free_export` failed: our audit
guard blocked its attempt to read its temporary fake `.env`. The user's no-read
restriction remains in force. The named main regression and all planner/safety
checks passed. Full log: `.pytest_cache/planner-live11-pytest-final.log`.
Test: `~/Projects/a-eye/.venv/bin/python eval/swap/run.py checker --model current --out .pytest_cache/planner-live11-checker` - PASS
(15/15 bad caught, 1/14 false drops, 0 errors; unchanged case bank/threshold).
Test: `git diff --check` - PASS.

Limits: the real six-step text was not available in this worktree; exact live
trigger remains unverified. Existing fixtures are synthetic. No `.env` reads,
external network, cloud calls, push, merge or deployment. Synthetic localhost
servers only. Detailed cause, baseline failures and evidence:
[round 11 report](docs/results/planner-live.md).


## Planner Live round 12 — pkg/planner-live12

Fixed generated precaution matching for headphone disconnection and cooling
before handling a hot tool. Live stops now record an allowlisted source and
gate ID without text. Real user hazards, negations and later unsafe clauses
still stop. Six-step synthetic LiveBridge/context replay advances without fixed
emergency speech. See docs/results/planner-live.md for cause, evidence and limits.

Files changed: server/safety.py, server/gemini_live.py, server/live_guide.py,
server/planner.py, server/test_planner_safety_steps.py,
docs/results/planner-live.md, RESULT.md.

All Python commands below ran with `PYTHONPATH=.pytest_cache/offline:.`;
the audit hook blocks sockets/DNS and `.env` reads.

Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_safety_steps.py -k round12 --tb=short - FAIL before fix (3 failed, 1 passed).
Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_safety_steps.py server/test_false_stop.py server/test_planner.py eval/swap/test_checker_regressions.py --tb=short - PASS (227 passed; primary fix).
Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_planner_safety_steps.py --tb=short - PASS (54 passed; final source).
Test: ~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval - FAIL (1370 passed, 17 failed, 2 warnings in 102.01s; final source).
Test: ~/Projects/a-eye/.venv/bin/python eval/swap/run.py checker --model current --out .pytest_cache/planner-live12-checker - PASS (15/15 bad plans caught; existing 1/14 good false drop; zero checker errors).
Test: git diff --check - PASS.

Full-suite failures: 15 blocked network operations, one downstream Live-start
failure, one blocked read of the publication test's synthetic `.env`.
Log: .pytest_cache/planner-live12-final-full.log.
Limits: no network, `.env` read, real provider/physical call, push, merge or
outside-worktree source changes. Original live-call phrase unverified; synthetic
reproduction verified. Local commit only, no push.


## Planner Live round 13 — summary advice false stop

Split full hazard-field checks from clause-local, present-danger summary checks.
Reproduced the headphone turn-2 water/cord precaution false stop before the fix;
kept the existing smoking-charger-after-word-limit regression passing.

Files changed: `server/context_agent.py`, `server/test_bg_context.py`,
`docs/results/planner-live.md`, `RESULT.md`.

Test: `PYTHONPATH=.pytest_cache/offline:. ~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_bg_context.py -k 'summary_facts or hazards_are_fixed'` - PASS (17 passed, 6 deselected; before fix: 9 failed, 8 passed).
Test: `PYTHONPATH=.pytest_cache/offline:. ~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL (1386 passed, 17 failed, 2 warnings, 101.95s).
Test: `git diff --check` - PASS.

Full-suite failures are 15 blocked network operations, one downstream Live-start
assertion and one blocked synthetic `.env` read; summary read, no full PASS claimed.
Proof and failed node IDs: `docs/results/planner-live.md`, round 13;
local logs: `.pytest_cache/planner-live13-{before,targeted,full}.log`.
Limits: lexical summary guard; no provider/physical-call verification, network,
`.env` reads, push, merge or deployment. Only comments changed after suite launch.

---

# No recap result

Removed automatic web recap and its sheet trigger; added kept-call indexing status on web and iPhone. Server waits for final and already-indexing clips without Pegasus. Explicit recap callers remain supported.

Files changed, exact commands, test evidence and limits: [docs/results/no-recap.md](docs/results/no-recap.md).

Test: $HOME/Projects/a-eye/.venv/bin/python -m pytest -q server - FAIL (1135 passed; 15 sandbox/network-related failures; 2 warnings).
Test: $HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_no_recap.py - PASS (3 passed).
Test: node --test client-web/*.test.mjs - PASS (172 passed).
Test: swift build --package-path ios/AEyeCore --scratch-path /private/tmp/a-eye-no-recap-swift --disable-sandbox - PASS.
Test: swiftc -frontend -parse ios/AEye/App/Call/CallController.swift ios/AEye/App/RootView.swift ios/AEye/App/Views/StartScreen.swift - PASS (syntax only).
Test: xcodebuild (full command in report) - BLOCKED (sandbox cache permissions and unavailable simulator service).
Test: git diff --check - PASS.

No iPhone recap view/trigger was present to remove. App-target compilation and physical-device behavior remain unverified. No push, .env reads, or external service calls.
