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
