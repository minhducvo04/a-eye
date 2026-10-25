# Model choices: what runs where, and why

Short answers to the questions people ask about A-eye's models. Numbers marked **measured** come from our own runs
(linked); **estimate** means arithmetic or vendor figures, not measured here yet. Updated 2026-10-24.

## The layers

| Layer | Model | Runs on | Job |
|---|---|---|---|
| Perception | Qwen 3.5 9B (`qwen3.5:9b-q4_K_M`), Qwen 2.5-VL 7B fallback | GPU box (RTX 3090 Ti) | Scene notes and boxes, in the background on scene changes |
| Talker (fast) | Claude Haiku 5.5 | Cloud | Speaks first, short answers |
| Planner | Claude Sonnet 5.5 | Cloud, in parallel | Boxes and arrows to draw; sees a crop only, never the full frame |
| Expert (rare) | Claude Opus 5.5, Fable 5.1 for long research | Cloud | Hard questions, under 1 in 10 turns (`pkg/expert`, in progress) |
| Router | Trained classifier on embeddings (`router/`, in progress) | Mac CPU / box | now / past / expert per question |
| Memory | TwelveLabs Marengo (search), Pegasus (recap, in progress) | Cloud, opt-in | Rewind |
| Voice | Cartesia Sonic 3.6, Kokoro fallback | Cloud / box | Speech out |
| Speech in | Whisper turbo (partials), or the browser's own STT in Chrome | Box / browser | Speech to text |

## Small fast model: Haiku vs local Qwen 3.5 9B

| | Claude Haiku 5.5 | Local Qwen 3.5 9B | Source |
|---|---|---|---|
| Quality on our 16-image set (judge, 1 to 5) | **4.81** | 3.75 | measured, [backend-benchmarks.md](backend-benchmarks.md) |
| First token, image in | 1.60 s p50 | 1.76 s p50 | measured, same |
| First token, text-only from scene notes | 0.56 s (speech-only prompt) | **0.32 s** p50 | measured, [voice-options.md](voice-options.md), backend-benchmarks.md |
| First audio as the full local brain vs Claude Sonnet brain | — | 1.63 s vs 3.29 s | measured, [results/wave6-turn-latency.md](results/wave6-turn-latency.md) |
| Cost per turn | ~$0.0003 | $0 (own GPU) | estimate from the benchmark token counts |
| Privacy | Sees text notes and crops | Nothing leaves the box | design |

Takeaway: Haiku is clearly smarter; the local 9B is faster on text and free, and keeps data local. A-eye uses Haiku
by default and the local model for perception. A full local talker and expert were benchmarked
(`docs/results/local-brain.md`, `BRAIN=local`).

## Why not a small local model in front of everything?

Measured: local caption then text model gave a first word in 0.32 s, but quality 3.75 against 4.88 for Sonnet seeing
the image. A text summary is a bottleneck (detail is lost) and its mistakes compound. A-eye keeps the local layer for
background scene notes and sends the cloud a real crop when detail matters.

## Big open-source models on the box (measured 2026-10-24 where marked)

Generation speed is limited by memory bandwidth: each token reads the active weights once. Only about 6 GB of VRAM is
free while the vision models are loaded, so big models run from CPU RAM. Measured: CPU only with 8 of 16 cores is the
only setup that kept live vision within noise; GPU layers slowed grounding by over 20%
([results/local-brain.md](results/local-brain.md)).

| Model | Size (4-bit) | Active per token | Speed mostly in RAM | Talker / expert quality (Haiku 4.00 / Opus 4.00) | Expert answer time p50 (Opus 3.6 s) |
|---|---|---|---|---|---|
| Qwen 3.8 27B (dense) | ~17 GB | all 27B | **3.5 to 4.0 tok/s, measured** | 2.95 / 2.50 (4 of 10), measured | 104 s, measured (n=4) |
| Gemma 4 31B (dense) | ~19 GB | all 31B | ~3 to 5 tok/s, estimate | not run | not run |
| Qwen 3.6 35B-A3B (MoE) | ~23 GB | ~3B | **19 to 24 tok/s, measured** | 3.25 / 3.00, measured | 69 s, measured (thinking on) |
| gpt-oss-120b (MoE, OpenAI open weights) | ~65 GB | ~5B | ~15 to 25 tok/s, estimate | not run (pull paused) | not run |
| ~235B MoE class | ~130 GB+ | ~20B | ~3 to 5 tok/s, estimate | does not fit | |

Against Opus 5.5 as the expert, measured: the best local model (Qwen 3.6 35B-A3B) scored 3.00 against Opus's
4.00 and took about 69 s against 3.6 s. It thinks for about 1,600 tokens before it answers. Both local talkers
also missed the hot-oil safety turn. Judge: Claude Sonnet 5.5, blind, n = 1 per answer, so a Claude bias is
possible.

## What we train

- Router (now/past/expert): yes, trained on generated questions, scored on a hand-written held-out set.
- Vision fine-tune of Qwen: parked; the base already gets 15/16 boxes and training would take the box's GPU for 6 to 8 h.
- Local brain distillation: planned only ([results/local-brain.md](results/local-brain.md), Phase B). Using Claude's answers as training data needs the team's decision first (Anthropic Commercial Terms D.4); the default plan distils the best local model into a fast 9B talker, 3 to 4 h of exclusive GPU or a cloud GPU.

`BRAIN=openai_compat` uses a hosted OpenAI-compatible API: set `OPENAI_COMPAT_BASE_URL` (including `/v1` where required), `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_TALKER_MODEL` and `OPENAI_COMPAT_EXPERT_MODEL`; the planner shares the talker model.
This cloud option sends text only, supports streaming with bounded timeouts, follows the Claude switch and Private mode, and does not provide provider web search or tool execution.

## GPU providers

Same `BRAIN=openai_compat` path on a home GPU, BitDeer (Cal Hacks sponsor), or a RunPod serverless vLLM endpoint. Home-PC numbers are measured on our box. Cloud rows are wiring plus vendor list prices.

Pitch: a sponsor GPU or a rented vLLM box can host the same open-model brain the home PC already runs, with no measured cloud latency yet.

| Provider | GPU | Price | Speed | Status |
|---|---|---|---|---|
| Home PC | RTX 3090 Ti (own box) | $0/h (hardware already owned) | Qwen 3.6 35B-A3B **19 to 24 tok/s, measured**; Qwen 3.8 27B **3.5 to 4.0 tok/s, measured**; local 9B text first token **0.32 s p50, measured** | measured, [results/local-brain.md](results/local-brain.md), [voice-options.md](voice-options.md) |
| BitDeer | hosted inference at `https://api-inference.bitdeer.ai/v1` | sponsor / vendor | not measured yet | supported, not measured yet |
| RunPod | 4090 | **$0.89/h, list price** | not measured yet | supported, not measured yet |
| RunPod | A40 | **$0.59/h, list price** | not measured yet | supported, not measured yet |
| RunPod | A100 | **$1.79/h, list price** | not measured yet | supported, not measured yet |
| RunPod | H100 | **$2.89 to $3.99/h, list price** | not measured yet | supported, not measured yet |

RunPod OpenAI-compatible base URL: `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1`. Pick a non-Chinese-origin open model for `OPENAI_COMPAT_TALKER_MODEL` and `OPENAI_COMPAT_EXPERT_MODEL`. Probe with `python scripts/provider_check.py` once a key exists. List prices are vendor figures, not our runs.
