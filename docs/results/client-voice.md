# client-voice package

Browser talk-back module for the call page: mic speech-to-text, `speechSynthesis`, gapless 16 kHz PCM16 playback, and barge-in. The page imports `client-web/voice.js`. Contracts were not changed.

## Changed files

- `client-web/voice.js`
- `client-web/voice.test.mjs`
- `client-web/README.md` (Voice section)
- `RESULT.md`

## Limits

No real microphone was tested. Safari was not tested. iOS audio unlock is covered only by a fake suspended `AudioContext`. Web Speech auto-restart is the synchronous `onend` path with a fake recognizer. Echo rejection is a word-containment check, not acoustic echo cancellation. Use headphones so speaker playback does not look like the user talking. Whisper on the PC is not in this package.

Commit did not happen. `git add` cannot create `index.lock` in `$HOME/Projects/a-eye/.git/worktrees/client-voice` from this session (operation not permitted). The four files above are saved and unstaged.

## Test

Test: node --test client-web/ - PASS (26 passed, 0 failed)
