# pipe-client result

Implemented camera on/off (track and frame-loop shutdown/restart, camera messages, and hello.camera), explicit mic mute/unmute, browser speech submission after 700 ms without an interim update, and suppression of late finals/corrections for the same recognition result.

Added a persistent pipeline strip with 100 ms elapsed updates, server stage/detail/typical timing, one retry after a two-second missing ack, connection failure feedback, reconnect backoff with hello replay, and an eight-second no-speech message. Transcript entries retain local sent, received, first-text, and first-sound timestamps. Reply deltas appear immediately; completed sentences retain audio highlighting.

## Files changed

- client-web/agent.html
- client-web/agent.css
- client-web/agent.js
- client-web/ui.js
- client-web/ui.test.mjs
- client-web/voice.js
- client-web/voice.test.mjs
- client-web/turn.js
- client-web/turn.test.mjs
- RESULT.md

## Verification

Test: node --test client-web/ - PASS (69 tests, 69 passed, 0 failed, 0 cancelled, 0 skipped, 0 todo)

The executable page harness exercises the actual agent module with simulated DOM, media devices, sockets, and timers: camera on/off/on, interval removal, voice-only hello, text retry, failure status, streamed captions, reconnect backoff, and updated camera state in hello. Pure reducer and fake-clock tests cover pipeline stages, timing, silence, and early-final suppression. Existing client tests pass. git diff --check passes.

## Limits

- No real mic or Safari tested. No real browser/device or live-server integration run; page integration uses simulated browser APIs.
- Browser first-sound timestamps use speech synthesis start events. PCM timestamps mark successful immediate playback scheduling on a running AudioContext, not acoustic output measured at the speaker.
- Retries replay the same user_text once; the additive contract has no client turn/idempotency key. Server-side deduplication is needed to prevent duplicate work if an ack is lost after processing.
- Server STT audio is not retained for replay. The text resend path applies to browser-recognized and typed input; server STT timeout feedback remains visible without storing audio.
- Late browser corrections keep the early text, including corrections of more than one word, to avoid a second turn.

No contracts or other packages changed. No push or publication.

## Commit status

Commit blocked by filesystem permissions: git add could not create the parent repository's .git/worktrees/pipe-client/index.lock (Operation not permitted). The required escalation attempt returned `Rejected("approval request failed")`. Files remain uncommitted on pkg/pipe-client; nothing was pushed.
