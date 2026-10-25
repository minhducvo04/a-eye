# Background context and Gemini Live streaming

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

## Original build evidence

Original build notes (checkpointed as `67ac9eb`): Live remains the real-time talker.
Claude builds background summaries; an allowed local model is the fallback when
Claude is unavailable or disallowed. No blocking context collection remains in
Live setup, microphone input, question handling, or input transcription.

## Behavior

- One cancellable context worker coalesces scene/turn triggers, starts at most
  every four seconds, and times out a build after ten seconds. It gathers local
  evidence off the event loop, checks hazards before publishing, and retains the
  last successful summary on failure. Background messages use
  `clientContent.turnComplete=false`, with a 250 ms transport deadline.
- The prompt no longer requires `gather_context` before answering. That tool
  remains an optional lookup for a missing personal detail.
- Live PCM is released after a 250 ms initial wall-clock guard, in 150 ms chunks
  at the existing client contract's 16 kHz rate. The final chunk can be shorter.
  Turn completion flushes the remainder instead of releasing the whole answer.
- Input and accumulated output transcripts are checked incrementally before
  audio is forwarded. A hazard clears buffered audio, latches the stop, sends
  the existing listening/cancellation signal and a new fixed-line utterance.
  The new caption cancels desktop playback; the listening state also cancels
  paired-phone playback. The existing fixed-line TTS path supplies stop audio.
- Late audio, turn completion, and interruption acknowledgements cannot reopen
  a safety-stopped reply. New user input can start a fresh reply. Ordinary
  barge-in still allows the following spoken reply.
- Captions stream through existing `reply_delta` and `say` messages. One
  utterance ID is retained for PCM throughout a reply. No contract changes.

## Measured latency

Three loopback trials per version, using the same synthetic provider schedule.
The probe timestamps the first nonempty PCM message **received by a WebSocket
client**, through the actual `LiveBridge`. This is text question to client PCM,
not microphone-to-speaker or physical-device latency. Camera and background
assessment are disabled to isolate the audio-buffer change.

| p50, milliseconds | Before | After |
| --- | ---: | ---: |
| First provider audio | 52.4 | 52.6 |
| First client audio | 1767.6 | 315.1 |
| Provider turn complete | 1762.6 | 1761.6 |

Client first audio improved by 1452.5 ms (82%). The deterministic provider
schedule is not a claim about Gemini's real-world latency. A separate integration
test verifies that a stalled context model does not block microphone/text input
or first client audio, and that closing the bridge cancels its context worker.

Commands:

```sh
/Users/minhducvo/Projects/a-eye/.venv/bin/python -m server.live_latency_probe --bridge-source /private/tmp/aeye-bg-context-live-before.py
/Users/minhducvo/Projects/a-eye/.venv/bin/python -m server.live_latency_probe
make -C /Users/minhducvo/Projects/a-eye -f /private/tmp/aeye-bg-context-probe.mk -k bg-context-real-before bg-context-real-after PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python
```

Before source: a copy of this worktree's original uncommitted `gemini_live.py`,
SHA-256 `a307eabf20f23cf2d4155d80bb25c8111a71135d78ca82b4fb3efb1986e4018b`.
Evidence: `/private/tmp/aeye-live-before.json`, `/private/tmp/aeye-live-after.json`.
Only timing metadata is retained; no media is written.

The worktree's make environment has no Gemini key. Using the main checkout's
make-loaded key, both real before/after probes were **blocked by the existing
daily cloud budget before any provider call**. The cap was not changed.
Evidence: `/private/tmp/aeye-live-real-main.log`.

## Verification and limits

Fake Live socket tests cover first PCM before completion, the initial guard,
150 ms chunk sizes, split mid-reply hazards, suppression of stopped tails,
question refusal before provider forwarding, and normal barge recovery. An
actual `/ws2` integration verifies the fixed stop caption and synthetic TTS PCM.
Background tests cover context publication during speech, a stalled worker,
coalescing, freshness, cancellation, privacy, model routing, and coded hazards.

Test: affected Live/context/WebSocket suite - PASS (59 passed in 5.13s).
Test: `make -k test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - FAIL
(1 failed, 1257 passed, 2 warnings in 68.89s; web: 169 passed, 0 failed).
Test: `node --test client-web/` - PASS (169 passed, 0 failed, 0 skipped).
Test: `git diff --check` - PASS.

Logs: `/private/tmp/aeye-bg-context-targeted.log`,
`/private/tmp/aeye-bg-context-verified-full.log`,
`/private/tmp/aeye-bg-context-node.log`.
An earlier overlapping run also missed the unrelated status test's three-second
deadline (3.39 seconds); the final run without overlapping tests passed it.

The full Python suite has an unrelated missing fixture:
`vision/fixtures/gemini_payment_required.json`. The unchanged vision test expects
it, but it is not tracked in this checkout. That package was not edited.

The 250 ms guard gives transcription an initial lead; it cannot retract audio
already played if a hazard's transcript arrives later. No physical playback,
real Gemini latency, or real Claude-context quality is claimed. The full-frame
Claude consent/normalization hook belongs to the separate `claude-sees` package;
without that hook this builder sends text evidence only.
