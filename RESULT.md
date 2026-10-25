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

## Acceptance fixes — 2026-10-25

Branch: `pkg/accept-fix`; no push. Full analysis: [acceptance-fixes.md](docs/results/acceptance-fixes.md).

Changed:

- `server/agent.py`: reuse recent local captions for private scene questions; first-speech timeout for private/local streams.
- `server/recent_memory.py`: opening-call selection and shared closed current-view question matching.
- `server/live_memory.py`: avoid holding/restarting the ordinary current-view Live answer.
- `scripts/live_acceptance.py`: require a grounded private answer within 4 s; timeout filler fails.
- `server/test_agent.py`, `server/test_recent_memory.py`, `server/test_live_memory.py`, `server/test_pipeline.py`,
  `scripts/test_live_acceptance.py`: 12 added regression cases, all passed in the final full run.
- `docs/results/acceptance-fixes.md`, `docs/results/acceptance-fixes-tests.txt`, `RESULT.md`: evidence and handoff.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` - FAIL
(1007 passed, 17 failed, 2 warnings, 51.02 s; 16 sandbox socket-related failures, one unchanged stale ready-test assertion).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_pipeline.py::test_private_audio_turn_answers_from_local_caption_without_talker server/test_recent_memory.py::test_generic_opening_caption_does_not_inherit_live_mug_claim` - PASS
(2 passed in 0.85 s; synthetic in-process protocol/voice and caption-provenance checks).

Test: `git diff --check` - PASS (no whitespace errors).

Limits: no network or real-model timing; no proof of the original local mug caption. The 2 s ask target remains;
the private 4 s check measures grounded reply text, not audio playback. The private general-model deadline is an
availability bound, not a successful-answer guarantee. No `.env` read; protected builder files untouched.
Owner/integrator must rerun live acceptance and the full suite where loopback sockets are permitted.
