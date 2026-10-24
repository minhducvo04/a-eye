# Rewind result

Rewind is a memory of the call built on TwelveLabs video search. It is off by default. When the switch is on, A-eye
keeps short clips around change-triggered keyframes (`server/keyframes.py`) and uploads them to a dedicated
TwelveLabs index. You can then ask "when did I ...?" and get the call time, plus the frame with the object boxed.

## Setup

- **Index:** `a-eye-rewind`, id `6adc47d7b9bcb0b6b0467378`. Model `marengo3.0`, option `visual`, addon `thumbnail`. The account's default index is untouched.
- **API:** plain HTTP to v1.3 (`GET/POST /indexes`, `POST /tasks`, `GET /tasks/{id}`, `POST /search`) in `server/rewind.py`. The key stays on the server as `TWELVELABS_API_KEY` and is never logged or printed.
- **Clips:**
  - Frames are sampled at 4 fps from the session frame, which covers paired phone cameras too.
  - A first or change keyframe cuts a clip from 2 s before to 3 s after, extended up to 12 s on a busy stretch. TwelveLabs needs at least 4 s.
  - Each clip is encoded to an ffmpeg H.264 MP4 with no audio, and the temp file is deleted right after upload.
  - Upload runs every `REWIND_FLUSH_S` (default 60 s), when a question arrives, and at the end of the call.
- **Test content:** synthetic frames only. Two drawn scenes (a red ball on a desk, a blue coffee mug) went through the real keyframe gate. No faces and no person tagging.
- **Hosts:** server on 127.0.0.1:8437. Real local vision on :8001 (`qwen3.5:9b` on the PC GPU) for the hit check.

## Real TwelveLabs numbers

Probe, `scripts/rewind_probe.py`, 2026-10-23:

| Step | Result |
|---|---|
| Upload, per clip (encode + POST /tasks) | 0.3 to 0.9 s (2 clips: 2.9 s total) |
| Indexing until `ready` | 6.8 s for 1 clip; 14.5 s for 2 clips |
| Search latency | about 0.3 to 1.1 s per call |

Tasks: `6adc47d8c63e9d23a635e9e1` (trial clip, empty desk), `6adc480bd2c9c9e5051db15a` (red ball),
`6adc480c3a2b1d8fd82be3c3` (blue mug).

| Query | Rank 1 | Rank 2 |
|---|---|---|
| "a red ball" | ball clip, 0 to 4.0 s | mug clip, 0 to 5.3 s (it has 2 s of ball pre-roll) |
| "a blue coffee mug" | mug clip, 0 to 5.3 s, call time 6 s | none |

Key lines from the probe log:

```
keyframe t=0.00s reason=first
keyframe t=8.00s reason=change
index: 6adc47d7b9bcb0b6b0467378; uploads: [('6adc480bd2c9c9e5051db15a', 315), ('6adc480c3a2b1d8fd82be3c3', 899)]; upload total 2.9s
indexed: [('6adc480bd2c9c9e5051db15a', 'ready'), ('6adc480c3a2b1d8fd82be3c3', 'ready')]; indexing wait 14.5s
search 'a blue coffee mug': raw rows: [('6adc480c3a2b1d8fd82be3c3', 0, 5.265999794006348, 1, None)]
```

/ws2 voice-path check, `scripts/rewind_ws_check.py`. It sends the typed question "When did I put down the red ball?" with Rewind on, using 1 clip per run:

| Run | Flush (upload) | Indexed | Answer after question |
|---|---|---|---|
| Before rebase | 1303 ms | 13.3 s | `rewind_hit` and spoken line at 2.29 s |
| After rebase on main | 820 ms | 8.8 s | `rewind_hit` and spoken line at 2.26 s |

```
rewind_state: {'on': True, ..., 'notice': 'Rewind on: short video clips of this call are uploaded to TwelveLabs so you can ask about them later.'}
flush: {'on': True, 'clips': 1, 'indexing': 1, 'uploaded': 1} in 820 ms
indexed: {'on': True, 'clips': 1, 'ready': 1} after 8.8 s
rewind_hit after 2258 ms: {'query': 'put down the red ball', 't_s': 0.0, 'start_s': 0.0, 'end_s': 4.0, 'sure': True, 'objects': [{'label': 'red ball', 'bbox': [0.163, 0.059, 0.654, 0.881], 'conf': 0.7}]}
say after 2259 ms: "That was right at the start of the call. Here's the clip."
```

## Credits used

There were 5 uploads in total: 3 probe clips (4.0 + 4.0 + 5.3 s) and 2 /ws2 check clips (about 4 to 5 s each). That is
about 22 s of Marengo indexing, plus about 8 searches. The API used here exposes no credit counter.

## Limits

- **No score.** TwelveLabs v1.3 search returns `rank` only, so a query with no true match can still return a weak rank-1 clip. This was seen once on the empty-desk trial clip.
- **Local VLM guard.** Before the talker claims a hit, our own vision host checks the rank-1 frame with `/scene` and the target object (no extra cloud call). That check also gives the box. If it does not confirm the object, the talker says "I'm not sure I saw it. Maybe ... or ..." and gives the top 2 times.
- **Deprecated endpoint.** `POST /tasks` is marked deprecated in v1.3 but still served.
- **Memory.** Rewind state lives in memory per server process, for the last 5 calls.
- **Routing.** Questions are routed by a regex ("when did I", "where did I put", "rewind") and only while Rewind is on or has clips.
- **Not tested here:** synthetic frames only, with no real camera, iPhone or Vision Pro run.

## Rerun

```sh
# Real probe: at most 2 clips into a-eye-rewind (reads the key from .env, prints length and prefix only)
.venv/bin/python scripts/rewind_probe.py --env ~/Projects/a-eye/.env --query "a red ball" --query "a blue coffee mug"
# Real /ws2 check against a running server with TWELVELABS_API_KEY set (1 clip); sends A_EYE_TOKEN when set
.venv/bin/python scripts/rewind_ws_check.py --url http://127.0.0.1:8437
```

Test: .venv/bin/python -m pytest -q - PASS (427 passed; the timing test test_backbone status timeout flaked twice under load and passes alone)
Test: node --test client-web/ - PASS (93 passed)
Test: make browser-smoke URL=http://127.0.0.1:8438 - PASS (server with A_EYE_TOKEN unset; the smoke script sends no token)
