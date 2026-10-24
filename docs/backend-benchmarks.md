# AI backend benchmarks (2026-10-23, 20:40 to 21:45 PDT)

Question: which ways of reaching a model (cloud API, coding CLIs, local models on the GPU box) understand "what we
are talking about" in a camera frame plus a short conversation, how fast, at what cost, and how to handle live video
when the models only take still images. Harness: `eval/backends/` (`run.py`, `video.py`, `cases.json`,
`fetch_images.py`, `test_backends.py`).

**Read first, what is not verified**

- **The Anthropic API rows sent full 1280 px frames** (public Commons photos) to measure the model. AGENTS.md says
  the app's cloud brain gets the scene as text, with only small crops through `server/llm.py`'s size check; a
  production escalation must follow that, so its image cost will be lower than measured here and its box accuracy
  on a crop is not measured. The key was added after a Mac restart at about 21:30 and read only through `make`'s
  `.env` loading (108 chars; never printed). The Claude Code session's own `ANTHROPIC_BASE_URL` was unset for the
  run so the calls went to the public API.
- **Gemini CLI skipped**: installed but not signed in (it opened a browser login; we did not sign in). No
  OpenAI-compatible, xAI or other model key exists in `.env` besides `ANTHROPIC_API_KEY`.
- The Mac restarted at about 21:30 during the grok run; its last 5 of 48 calls were resumed afterwards.
- **The CLI rows (`claude -p`, `codex exec`, `grok -p`) are dev-time only.** They run on personal subscriptions;
  routing a public app's users through them is against those products' terms and is not a production backend.
  Their latency includes a full coding-agent start-up.
- 16 cases is a small set: keyword topic accuracy is saturated (most rows 16/16), so the judge score and the box
  score are the ones that separate backends. Gold boxes were drawn by eye on a 10% grid (rough).
- The judge is a local model (gemma4:31b, think off, fixed rubric, n = 1 per answer). It shares a family with the
  two gemma4 rows. It saw only text (reference answer, model answer), not the image.
- The qwen rows ran while the box also served the live app's models (other sessions were using it); the gemma
  rows ran with the box to themselves (the app's models were unloaded, then reloaded and warmed afterwards). The
  qwen tails (p90) are therefore pessimistic. Costs for local hardware are estimates.

## Test set

16 cases across four packs (6 PC parts, 5 cooking, 2 desk/general, 3 assembly), each with 1 to 3 prior turns, a
current frame, the question, and gold topic, topic keywords, target object, target keywords, a rough gold box and a
reference answer (`eval/backends/cases.json`). Frames are public Wikimedia Commons photos resized to 1280 px long
edge (`eval/backends/data/`, licences and pages in `data/sources.json`: CC0, CC BY, CC BY-SA). No personal content.
One case is a safety case (PSU fuse: the right answer refuses to open the PSU).

Every backend gets the same system line and asks for one JSON object `{topic, target, bbox, answer}`. Box format:
pixels for qwen2.5vl and the CLIs; 0 to 1000 normalized for qwen3.5 and gemma4 (their native style). Ollama:
`think: false`, temperature 0, `num_ctx` 4096, a unique first line per call (defeats prompt caching), one warm-up
per model, rep-major order (all 16 cases, then repeat), 3 reps, so n = 48 calls per backend. Latency from the
Mac is wall time over Tailscale with the image upload; "box-side" is Ollama's own `total_duration`.

Metrics: topic (judge) = judge says the stated topic and reply match the reference topic; topic (keyword) = a gold
keyword appears in topic or answer; target named = a target keyword in the stated target; box = IoU >= 0.3 with the
gold box; quality = judge 1 to 5 with the rubric in `run.py`; bad JSON and errors are counted, never dropped.
Accuracy columns use rep 1 (n = 16); latency uses all reps.

## Results

| Backend | Topic (judge) | Topic (keyword) | Target named | Box IoU>=0.3 | Quality 1-5 | TTFT p50/p90 s (Mac) | Total p50/p90 s (Mac) | Box-side total p50/p90 s | Bad JSON | Errors |
|---|---|---|---|---|---|---|---|---|---|---|
| cli:claude (`claude -p --model sonnet`) | 15/16 | 16/16 | 15/16 | 15/16 | 4.50 | 7.83/10.61 | 11.44/13.88 | n/a | 0/16 | 0/48 |
| cli:codex (`codex exec -i`) | 16/16 | 16/16 | 16/16 | **16/16** | 4.38 | n/a (no stream) | 12.24/16.58 | n/a | 0/16 | 0/48 |
| cli:grok (`grok -p`) | 16/16 | 16/16 | 15/16 | 14/16 | 4.56 | n/a (no stream) | 44.5/81.8 | n/a | 0/16 | 0/48 |
| ollama gemma4:12b (alone on GPU) | 16/16 | 16/16 | 15/16 | 14/16 | 3.81 | 1.25/1.51 | 1.67/1.94 | 1.46/1.74 | 0/16 | 0/48 |
| ollama gemma4:26b-a4b (alone on GPU) | 16/16 | 16/16 | 15/16 | 6/16 (14/16 read as y,x) | 4.25 | 1.33/1.77 | 1.81/2.18 | 1.58/1.95 | 0/16 | 0/48 |
| ollama qwen3.5:9b (image in) | 16/16 | 16/16 | 15/16 | 15/16 | 3.75 | 1.76/3.58 | 2.37/4.05 | 1.91/3.52 | 0/16 | 0/48 |
| ollama qwen2.5vl:7b (the app's VLM today) | 15/16 | 16/16 | 12/16 | 12/16 | 2.56 | 1.92/3.87 | 2.38/4.83 | 2.01/3.54 | 0/16 | 0/48 |
| pipe: qwen2.5vl caption -> qwen3.5:9b text (the app's privacy pattern) | 15/16 | 14/16 | 14/16 | n/a (text only) | 3.75 | **0.32/0.92** | **0.76/1.58** | 0.47/0.53 | 0/16 | 0/48 |
| boxsvc YOLO11n 640 px (boxes only) | n/a | n/a | n/a | 4/5 COCO-class targets | n/a | n/a | 2.23/3.63 | about 0.01 to 0.02 (`ms`) | n/a | 0/48 |
| **api: Claude Sonnet 5.5** (effort low, streamed) | 16/16 | 16/16 | 16/16 | **16/16** | **4.88** | 1.44/2.50 | 2.45/4.09 | n/a | 0/16 | 0/48 |
| **api: Claude Haiku 5.5** (effort low, streamed) | 16/16 | 16/16 | 16/16 | 15/16 | 4.81 | 1.60/2.42 | 2.14/2.85 | n/a | 0/16 | 0/48 |

Notes on the table:

- **gemma4:26b-a4b returns boxes as [y1, x1, y2, x2]** (Gemma's native order) even when asked for x first; read
  that way it lands 14/16. gemma4:12b followed the asked order (14/16). Parse per model, do not trust the prompt.
- **qwen2.5vl gave the one unsafe answer**: on the PSU case it said to unplug "before opening the box"
  (quality 1). The PC pack's code-level `refuse()` gate exists for exactly this; keep it ahead of any model.
- **The caption pipeline is fast because the caption is not on the turn's path** (captions were made once per frame
  in the background, median 2.2 s per caption from the Mac with a 120-token limit). It loses grounding (no box) and
  some detail (14/16 keyword topic).
- Box-side time for image calls includes 0.5 to 0.9 s that Ollama reports as `load_duration` even with a warm model
  and no other client (gemma alone: 0.53 to 0.61 s); it is image preprocessing, not a model reload. The prompt is
  about 1,300 to 1,700 tokens for a 1280 px frame on qwen, about 720 on gemma4.
- `claude -p` "TTFT" is the time to the first assistant message containing the JSON (stream-json), not a raw token.
  The coding CLIs start an agent, load tools and system prompts, then read the file: 8 to 70 s per turn. Claude Code
  reported 66k cached plus 26k new input tokens per turn for a 120-token answer.
- `codex exec` printed a "failed to refresh available models: request timed out" warning on start; it still answered.

## Speed

From the Mac over Tailscale (includes upload of a 1280 px JPEG, about 100 to 300 KB) and from the box (server
counters), n = 48 per backend:

| Backend | TTFT p50 / p90 (Mac) | Total p50 / p90 (Mac) | TTFT p50 / p90 (box) | Total p50 / p90 (box) |
|---|---|---|---|---|
| pipe caption -> qwen3.5:9b text | 0.32 / 0.92 s | 0.76 / 1.58 s | 0.07 / 0.08 s | 0.47 / 0.53 s |
| gemma4:12b image | 1.25 / 1.51 s | 1.67 / 1.94 s | 0.91 / 1.21 s | 1.46 / 1.74 s |
| gemma4:26b-a4b image | 1.33 / 1.77 s | 1.81 / 2.18 s | 1.02 / 1.35 s | 1.58 / 1.95 s |
| qwen3.5:9b image (shared box) | 1.76 / 3.58 s | 2.37 / 4.05 s | 1.32 / 3.00 s | 1.91 / 3.52 s |
| qwen2.5vl:7b image (shared box) | 1.92 / 3.87 s | 2.38 / 4.83 s | 1.50 / 2.93 s | 2.01 / 3.54 s |
| claude -p (sonnet) | 7.8 / 10.6 s | 11.4 / 13.9 s | n/a | n/a |
| codex exec | n/a | 12.2 / 16.6 s | n/a | n/a |
| grok -p | n/a | 44.5 / 81.8 s | n/a | n/a |
| Claude Sonnet 5.5 API | 1.44 / 2.50 s | 2.45 / 4.09 s | n/a (cloud) | n/a |
| Claude Haiku 5.5 API | 1.60 / 2.42 s | 2.14 / 2.85 s | n/a (cloud) | n/a |

The network and upload add about 0.2 to 0.4 s at p50 (Mac minus box). For comparison, docs/pc-benchmarks.md
measured 0.28 s for a one-label box call on the box: our answers are longer (a spoken sentence plus JSON, 58 to 71
output tokens) and include the conversation, which is why the image rows are 1.5 to 2 s.

## Cost

Prices are list prices checked 2026-10-23:

- Anthropic ([pricing page](https://platform.claude.com/docs/en/about-claude/pricing)): Sonnet 5.5 $2 in / $10 out
  per million tokens; Haiku 5.5 $0.10 / $0.50; Opus 5.5 $4 / $20. Image tokens: about width x height / 750, so a
  1280 x 960 frame is about 1,600 tokens (the [vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
  formula; not re-read tonight).
- OpenAI ([pricing page](https://openai.com/api/pricing/), page returned 403 to our fetcher; figure from a search
  snippet of it): GPT-5.4 mini $0.75 / $4.50. Not run; reference only for what `codex` would cost as an API.
- xAI: only third-party aggregators reached (for example [morphllm](https://www.morphllm.com/grok-api-pricing)),
  about $2 / $6 for current Grok 4.x; unverified.
- Electricity: California residential about $0.34/kWh (April to May 2026 EIA-based figures via
  [NRG](https://nrgcleanpower.com/learning-center/california-electric-rates-have-surged/) and
  [Voltflow](https://www.voltflow.net/electricity-cost-calculator/state/california)).
- GPU: used RTX 3090 Ti about $1,300 to $1,800 in 2026 ([resaleprices](https://resaleprices.com/gpu/nvidia-rtx-3090-ti),
  [GPU Poet](https://gpupoet.com/gpu/learn/price/october-2026/nvidia-geforce-rtx-3090-ti)).

**Local box (estimate):** box value about $2,500 (GPU plus the rest), 3 years straight-line = $0.095/hour; about
0.55 kW at the wall under load = $0.19/hour; so about $0.28 per busy hour, or $0.000078 per busy second. Not
measured: wall power, real sessions per box.

Measured per-turn API usage (n = 48 each): 1,763 input tokens (frame plus conversation), Sonnet 133 and Haiku
218 output tokens; **$0.00485 per turn on Sonnet 5.5, $0.00029 on Haiku 5.5** (computed from the returned usage and
the list prices). Assumptions for a live session (stated, not measured): 4 voice turns per minute; a caption-only
keyframe call is about 1,400 input and 30 output tokens.

| Per unit | Sonnet 5.5 API | Haiku 5.5 API | Haiku talker + Sonnet planner (voice agent today) | Local box (estimate) | claude -p (API-equivalent, dev only) |
|---|---|---|---|---|---|
| One voice turn with a frame | $0.0049 (measured) | $0.00029 (measured) | about $0.005 | about $0.00012 (1.5 s busy) | $0.108 (measured, agent overhead) |
| One minute, fixed 1 fps video (60 frames) + 4 turns | about $0.21 | about $0.011 | about $0.21 | cannot keep up (66 s of VLM work per minute) | n/a |
| One minute, change-triggered keyframes (6 frames, measured) + 4 turns | about $0.038 | about $0.0021 | about $0.039 | about $0.0007 (about 9.6 s busy) | n/a |
| One minute, audio-first, one frame per turn | about $0.019 | about $0.0012 | about $0.020 | about $0.0005 (6 s busy) | about $0.43 |
| One minute, hybrid: local keyframes and turns, Sonnet on 1 of 5 turns | about $0.0039 cloud | | | about $0.0007 | n/a |
| 1,000 users x 10 min/day (300,000 min/month), change-triggered + turns | about $11,400/month | about $630/month | about $11,700/month | about 7 boxes: about $800/month running + about $17,500 up front | not allowed |
| Same, audio-first | about $5,800/month | about $350/month | about $6,100/month | about 5 boxes: about $570/month + about $12,500 | not allowed |
| Same, hybrid | about $1,160/month cloud plus the local boxes | | | | |

The voice agent's planner gets the scene as text, not the frame (docs/voice-options.md: about 1.5k input tokens
per call), so its real cost per turn is close to the Sonnet column without the image share.

Box count: 10,000 session-minutes a day over about 8 busy hours is about 21 concurrent sessions on average, about 42
at a 2x peak; one box serialises about 6 sessions at 9.6 s of GPU work per session-minute (about 10 at 6 s for
audio-first). Ollama parallel requests were not measured, so this is conservative. Running cost per box = 24 h of
amortisation plus 8 h of load power, about $3.80/day.

## Live video: strategies

Most model APIs take still images per request, not a live stream. Measured on a synthetic 60 s clip (`video.py`):
three public stills, 20 s each, 5 fps, every frame shifted a few pixels with a brightness change; qwen2.5vl
captions, qwen3.5:9b answers "what is the user working on?" at 20, 40 and 60 s from the last 8 captions, then "what
did we look at first?" at 60 s. Scene change by mean absolute difference of 32x32 grayscale frames (same scene p50
9.9, max 17.8; scene cut 51.3; threshold 34.5) plus a 10 s heartbeat.

| Strategy | VLM calls/min | VLM tokens/min | VLM call p50/p90 | GPU busy per minute | Topic kept (4 probes) | Scene-change lag |
|---|---|---|---|---|---|---|
| Fixed 1 fps sampling (measured) | 60 | 90,500 | 1.07 / 1.30 s | 65.7 s: **does not keep up** | 3/4 (lost "what was first": 8 captions only span 8 s) | up to 1 s + call |
| Change-triggered keyframes (measured) | 6 | 9,000 | 0.46 / 0.90 s | 3.6 s | **4/4** | next frame (0.2 s) + call |
| Rolling scene memory | carried as text: 8 captions about 250 tokens per brain call | | | | both rows above use it | |
| Local VLM continuous + cloud on demand | as change-triggered, plus 1 cloud call per hard question | | | | not measured | |
| Audio-first, one frame per turn | 4 (one per turn) | about 6,000 | about 1.5 to 2 s per turn (the image rows above) | about 6 s | not measured on the clip | none between turns |

What this shows: change-triggered keyframes cut VLM work 10x for the same or better topic tracking, because the
memory holds one caption per scene instead of 8 near-duplicates. Fixed 1 fps cannot be sustained by one VLM even for
one user. One wrinkle: at 60 s the brain mixed the old scene into the answer ("the drill and vegetables nearby"), so
memory entries should carry age and the newest caption should be marked "now".

## Recommended routing

| Job | Use | Why |
|---|---|---|
| Fast default, every spoken turn | Claude Haiku 5.5 talker (as voice-options.md already ships), scene memory as text from local change-triggered keyframes | quality 4.81, 16/16 topic; 1.6 s TTFT with a frame here, 0.55 s speech-only (voice-options.md); $0.0003 per turn |
| Pointing (box) on the current frame | Local qwen3.5:9b or gemma4:12b, one label, 0 to 1000 coordinates (frames stay on our box) | 15/16 and 14/16 boxes vs 12/16 for qwen2.5vl at similar speed; Sonnet 16/16 but needs the frame in the cloud |
| Hard question escalation | Claude Sonnet 5.5 (the planner), with a crop through `server/llm.py`'s size check | best quality 4.88 and 16/16 boxes on full frames; $0.005 per turn |
| Offline fallback (`LOCAL_ONLY=1`) | qwen3.5:9b with the frame, or the caption pipe for speed | 16/16 topic, 15/16 boxes, 2.4 s; pipe 0.32 s TTFT |
| Development only | `claude -p` / `codex exec` / `grok -p` | good answers but 11 to 82 s per turn, subscription terms |

Video: ship change-triggered keyframes plus a rolling scene memory as the default, audio-first with the newest
keyframe on each turn, local VLM continuously and the cloud only on demand. Do not run fixed 1 fps through a VLM.

## Best for

| Best for | Pick | Evidence |
|---|---|---|
| Fastest | Caption pipe -> qwen3.5:9b (local text) | 0.32 s TTFT, 0.76 s total p50 from the Mac |
| Cheapest | Local box; Claude Haiku 5.5 if cloud | about $0.0007 per session-minute (estimate); Haiku $0.0003 per turn (measured) |
| Most accurate | Claude Sonnet 5.5 API (Haiku 5.5 close behind) | 16/16 topic, 16/16 boxes, quality 4.88 (Haiku 4.81, 15/16 boxes) |
| Offline | qwen3.5:9b on the box (gemma4:12b if it has the GPU alone) | 16/16 topic, 15/16 boxes, about 2.4 s from the Mac |

## Not measured

- Gemini CLI (not signed in), any OpenAI or xAI API (no key in `.env`), Claude on crops instead of full frames.
- Ollama parallel requests, wall power, the venue network, a real camera clip, the hybrid and audio-first strategies
  end to end, and gemma4 next to the full app stack: a first attempt at gemma4:12b while qwen2.5vl, qwen3.5 and the
  speech models were loaded left it only 1.1 GB on the GPU and 2 of 4 calls timed out at 120 s (kept as
  `out/coresident_gemma4_12b.jsonl.txt`). gemma4:12b and the app's two qwen models do not fit together with
  boxsvc on 24 GB.

Reproduce: `.venv/bin/python eval/backends/fetch_images.py`, then
`.venv/bin/python -m eval.backends.run --backends <names> --reps 3 --warm`, `--judge`, `--table`, and
`.venv/bin/python -m eval.backends.video`. Raw outputs: `eval/backends/out/` (gitignored).
