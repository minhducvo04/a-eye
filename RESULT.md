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
