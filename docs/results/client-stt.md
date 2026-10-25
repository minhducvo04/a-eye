# client-stt

Server STT is in the web client. `?stt=server` sets `hello.stt` to `"server"`, opens the mic, and sends `v2_audio_in` (16 kHz mono PCM16). The default stays browser speech recognition. The label beside the mic button reads Whisper or Browser.

## Files

- `client-web/voice.js`
- `client-web/voice.test.mjs`
- `client-web/agent.js`
- `RESULT.md`

## Limits

No real mic or Safari was tested. AudioWorklet and ScriptProcessorNode were not run in a browser. Tests use a fake clock, a fake AudioContext, and a fake getUserMedia. The first captured frame sets the noise floor and is not sent. Speaker audio can still trip barge-in if echo cancellation does not remove it. Nothing is recorded or stored.

Test: node --test client-web/ - PASS (54 pass, 0 fail)

Commit: not created. This session cannot write `$HOME/Projects/a-eye/.git/worktrees/client-stt` (`index.lock`, operation not permitted). The four files above are saved in the worktree and are not staged.
