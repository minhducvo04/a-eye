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
