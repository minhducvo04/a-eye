# Background context and Gemini Live streaming

Changes are uncommitted in `pkg/bg-context`. Live remains the real-time talker.
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
