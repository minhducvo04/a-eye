# the team's slow-turn fix, measured 2026-10-23 about 21:00 to 21:15 PDT

Conditions like the team's run: camera frames at 1 fps (each different), cooking pack, typed final text standing in for
the browser speech final, server TTS (Kokoro on the GPU box), vision on the box. Same 5 questions each run.
The browser's own speech-final delay is not in these numbers (no real mic); the page now sends the interim text
after 700 ms of no new words instead of waiting for the browser's final.

| Run | Ack (`turn received`) | First spoken text, median | First audio, median | Worst first audio |
|---|---|---|---|---|
| Before (main at b9fcdd2), local brain qwen3.5:9b | none | 1692 ms | 2353 ms | 4767 ms |
| After, local brain qwen3.5:9b | 1 to 3 ms | 1366 ms | 1630 ms | 2248 ms |
| After, Claude brain (claude-sonnet-5-5, key in .env) | 1 to 3 ms | 3017 ms | 3290 ms | 3671 ms |

What changed: an immediate ack and stage messages; scene refresh only on a new frame and never during a brain
stream; voice only when the camera is off; reply text streamed into captions; brain first-token timeout with a
backup provider. Also found live: the box TTS hung after a dropped (barged-in) stream and every later turn failed
with ReadTimeout; fixed in `boxsvc` and redeployed.

Claude first token for a one-sentence reply was 0.78 to 0.91 s from this Mac (effort default or low); the turn is
slower because the brain writes a JSON drawing header before the spoken text.
