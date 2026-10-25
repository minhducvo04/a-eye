# RESULT: headset dad-guide demo

Fastest path: existing headset web mode (`client-web` in Safari on Vision Pro) with the phone as camera. The visionOS app still cannot see the main camera without Apple’s enterprise entitlement.

## Files

- `client-web/headset.js`: `headsetStep()` for the Sink / General instruction card.
- `client-web/headset.test.mjs`: step-card copy.
- `client-web/agent.html`: `#step-card` and a headset-only typed field (`#composer` / `#typed`).
- `client-web/agent.css`: large captions, visible wait/step cards, always-on 88 px end-call, thicker overlay shadow.
- `client-web/agent.js`: render the step card; do not auto-hide the call bar on a headset.
- `client-web/turn.test.mjs`: Sink + General headset captions, draw ops, end-call.
- `docs/headset-demo.md`: exact run steps and the demo gap list.

## Limits

- Phone frames are not sent back to Safari; boxes and arrows draw on a dark canvas.
- No physical Vision Pro Safari run in this worktree.
- Valve “Show me again” stays until a real checker or the laptop presenter mode.
- Native AEyeVision remains photo-or-pair, not live headset camera.

## Test

`node --test client-web/headset.test.mjs client-web/turn.test.mjs` - PASS (19 tests, 0 failures, exit 0)

## Merge main UI redesign

Merged main at `7551d8d` (the main tip when `git merge main` began).
Phone and desktop retain the one-Call start screen and redesigned call controls.
Headset-only UI retains Sink guide, large captions, the step card, overlay styling,
typed questions and phone QR pairing. The headset caption stack scrolls while End
call stays fixed; pairing remains reachable. Desktop Rewind prompts send directly.

Merge resolution files: `client-web/agent.html`, `client-web/agent.js`,
`client-web/turn.test.mjs`. Supporting changes: `client-web/agent.css`,
`client-web/headset_smoke.py`, `client-web/call-ui-smoke.py`,
`scripts/browser_smoke.py`, `docs/headset-demo.md`, this report.
The pre-existing uncommitted headset report above was retained.

Test: node --test client-web/ - PASS (169 passed, 0 failed, 0 skipped).
Proof: `/private/tmp/aeye-headset-node.log`.
Browser tests use real Chromium, synthetic media, a loopback mock backend and a
throwaway token. No physical Vision Pro, live cloud provider or native app proof.

Test: uv run --no-project --with playwright python scripts/browser_smoke.py http://127.0.0.1:18742 - PASS (BROWSER SMOKE PASS; frames_sent: 2; problems: []; longest task: 0 ms).
Test: uv run --no-project --with playwright python client-web/headset_smoke.py http://127.0.0.1:18742 - PASS (HEADSET SMOKE PASS; UA + flag, no local video, QR, fake-phone join/frames, mic handoff, settings, kick, second Sink call; no page errors).
Test: A_EYE_UI_PROOF_DIR=/private/tmp/aeye-headset-merge-ui uv run --no-project --with playwright python client-web/call-ui-smoke.py <server-python> - PASS (1280x844, 390x844, 768x1024, 844x390; CALL UI BROWSER: PASS; 12 screenshots).
Test: git diff --check - PASS.
Proof logs: `/private/tmp/browser_smoke-merge.log`, `/private/tmp/headset_smoke-merge.log`.
Proof images: `/private/tmp/aeye-headset-merge-proof/` and `/private/tmp/aeye-headset-merge-ui/`.
Main advanced concurrently after the merge began; later context-agent and start-copy commits are outside this tested merge snapshot.

## Background context and Live streaming — 2026-10-24

Continued the inherited uncommitted background-context work in `pkg/bg-context`.
All changes remain uncommitted. The earlier headset report above is retained.

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

Test: /Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_streaming.py server/test_bg_context.py server/test_gemini_live.py server/test_context_agent.py server/test_ws2.py --tb=short - PASS (59 passed in 5.13s).

Test: make -k test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python - FAIL (Python: 1 failed, 1257 passed, 2 warnings in 68.89s; Node: 169 passed, 0 failed).

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
Test: `make -k test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - PASS
(1260 passed, 2 warnings in 67.17s; web: 169 passed, 0 failed).
Test: `node --test client-web/` - PASS (169 passed, 0 failed, 0 skipped).
Test: `make smoke PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - PASS
(`steps=['SAFETY', 'IDENTIFY', 'LOCATE', 'GUIDE', 'AWAIT'] target_overlays=1`, `SMOKE PASS`).
Test: `/private/tmp/aeye-bg-merge-rewind-check.py` with the project Python and
worktree PYTHONPATH - PASS (saved-call retrieval after empty/current-call misses;
other-owner isolation; fake TwelveLabs, metadata only).
Test: `git diff --cached --check` - PASS.

Real checks used `make -f Makefile -f /private/tmp/aeye-bg-merge-probe.mk`, with
`PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python`. The supplemental makefile
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
