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
by default and the local model for perception. A full local talker and expert are being benchmarked
(`docs/results/local-brain.md`, `BRAIN=local`).

## Why not a small local model in front of everything?

Measured: local caption then text model gave a first word in 0.32 s, but quality 3.75 against 4.88 for Sonnet seeing
the image. A text summary is a bottleneck (detail is lost) and its mistakes compound. A-eye keeps the local layer for
background scene notes and sends the cloud a real crop when detail matters.

## Big open-source models on the box (estimates until local-brain.md has numbers)

Generation speed is limited by memory bandwidth: each token reads the active weights once. GPU memory is about
1,000 GB/s; system RAM roughly 60 to 90 GB/s (assumed, not measured on this PC). Only about 6 GB of VRAM is free while
the vision models are loaded, so big models run mostly from RAM.

| Model | Size (4-bit) | Active per token | Est. speed mostly in RAM | Fits the box (93 GB RAM + 6 GB VRAM) |
|---|---|---|---|---|
| Qwen 3.8 27B (dense) | ~17 GB | all 27B | ~4 to 6 tok/s | yes |
| Gemma 4 31B (dense) | ~19 GB | all 31B | ~3 to 5 tok/s | yes |
| Qwen 3.6 35B-A3B (MoE) | ~23 GB | ~3B | ~20 to 40 tok/s | yes |
| gpt-oss-120b (MoE, OpenAI open weights) | ~65 GB | ~5B | ~15 to 25 tok/s | yes, tight |
| ~235B MoE class | ~130 GB+ | ~20B | ~3 to 5 tok/s | no |

Against Opus 5.5 as the expert: a typical expert answer is a few hundred tokens. Opus (cloud) is expected to finish in
several seconds; a 120B MoE from RAM would take roughly 15 to 30 s for the same length, with lower quality. These are
estimates; the benchmark will replace them.

## What we train

- Router (now/past/expert): yes, trained on generated questions, scored on a hand-written held-out set.
- Vision fine-tune of Qwen: parked; the base already gets 15/16 boxes and training would take the box's GPU for 6 to 8 h.
- Local brain distillation (LoRA on Claude's answers): planned only; needs 4 to 6 h of exclusive GPU or a cloud GPU.
