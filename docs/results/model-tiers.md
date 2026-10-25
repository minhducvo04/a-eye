# Model tiers for a wearable or home device (2026-10-24, overnight)

Status: **partial.** Unattended runs continue on the box until about 07:20 PDT. Final rows land in
`<PC_WORK_DIR>\aeye-night\` on the box (see the commands at the end).

## Answer so far

- **On a Pi-class CPU (4 threads, no GPU), no tiny VLM here can follow A-eye's turn JSON or box the asked-for object.**
  Moondream (Ollama build) answers in about 4 s and 1.2 GB, but its boxes miss (0 of 16 at IoU 0.3) and its
  captions are partly garbled. qwen3-vl:2b takes 16 s per turn (1.9 GB) and qwen2.5vl:3b 23 s. A wearable tier
  should stream frames to the box, or run a detector on the device and leave the language model on the box.
- **What is not measured yet:**
  - GPU rows for the tiny VLMs (the overnight runner does them after training).
  - The tiny full-turn quality judge.
  - SmolVLM 256M/500M/2.2B: their GGUF pulls were stopped to save Wi-Fi bandwidth for the Phase B weights.
  - Florence-2: the script is ready (`eval/tiers/florence.py`) but is not in tonight's runner.
  - Piper TTS: no voice file was downloaded.
  - YOLO11n on CPU. On the box GPU the earlier benchmark got 4 of 5 COCO-class targets at 0.01 to 0.02 s
    ([backend-benchmarks.md](../backend-benchmarks.md)).
- Speech (Whisper tiny/base, Moonshine tiny/base, CPU 4 threads, LibriSpeech dummy set) runs on the box CPU during
  training, if the training venv finished installing.

## Tiny VLMs on the 16 held-out frames, CPU only with 4 threads (about a Raspberry Pi 5)

| Model | RAM (Ollama) | Full A-eye turn, total p50 | Caption names the target | Box IoU >= 0.3 (given the name) | Caption / box time p50 |
|---|---|---|---|---|---|
| moondream:1.8b (Ollama) | 1.24 GB | 4.2 s | 6/16 | 0/16 | 1.5 s / 1.2 s |
| qwen3-vl:2b | 1.93 GB | 16.0 s | rerun (thinking ate the answer; fixed, re-running) | rerun | |
| qwen2.5vl:3b | about 3 GB | 23.0 s (12 of 16 so far) | running | running | |

"Full A-eye turn" is `eval/backends/run.py` with the same prompt as the big models
(`--backends ollama-cpu4:<tag>`). Its judge and box scores come with the final table. The CPU-4 setting is
`num_gpu 0, num_thread 4` on the box's Ryzen 9 9950X3D. That approximates a Pi's thread count, but a Pi 5 core is
several times slower, so **expect Pi latency well above these numbers** (not measured on a Pi).

## Licences (from the Hugging Face model cards and PyPI, 2026-10-24)

| Model | Params | Licence | Demo OK | Product note |
|---|---|---|---|---|
| SmolVLM 256M / 500M Instruct, SmolVLM2 2.2B (HuggingFaceTB) | 0.26 / 0.5 / 2.2B | Apache-2.0 | yes | yes |
| Moondream 2 (vikhyatk/moondream2; Ollama `moondream:1.8b` is an older build) | 1.9B | Apache-2.0 | yes | yes |
| Florence-2 base / large (microsoft) | 0.23 / 0.77B | MIT | yes | yes |
| Qwen3-VL 2B Instruct | 2B | Apache-2.0 | yes | yes |
| Qwen2.5-VL 3B Instruct | 3B | **Qwen Research License** (non-commercial) | yes (hackathon) | **no** without a licence from Alibaba |
| YOLO11n (Ultralytics) | 2.6M | **AGPL-3.0** (or paid Enterprise) | yes | AGPL: shipping it in a closed device means releasing the source, or paying |
| Whisper tiny.en / base.en (openai) | 39M / 74M | Apache-2.0 (faster-whisper runtime: MIT) | yes | yes |
| Moonshine tiny / base (moonshine-ai) | 27M / 61M | MIT | yes | yes |
| Piper TTS engine (`piper-tts` 1.8, OHF-Voice/piper1-gpl) | n/a | **GPL-3.0-or-later** | yes | GPL engine; the older MIT `rhasspy/piper` release is an option |
| Piper voice `en_US-lessac-medium` (rhasspy/piper-voices) | 63 MB | repo MIT; voice trained on the Lessac Blizzard 2013 data, whose licence page is linked from the model card | yes | check the dataset licence before a product |

No Chinese-origin models other than Qwen were used. Tonight's downloads came only from the Ollama registry
(moondream, qwen2.5vl:3b, qwen3-vl:2b, and a stopped ggml-org SmolVLM pull), Hugging Face (Qwen/Qwen3.5-9B, and in
the runner the LibriSpeech dummy set, Systran faster-whisper and moonshine-ai), PyPI, and the COCO site
(annotations only).

## Reading the final results

```
ssh <PC_USER>@<PC_TAILSCALE_IP> "type <PC_WORK_DIR>\\aeye-night\\status.txt"
scp -r <PC_USER>@<PC_TAILSCALE_IP>:C:/kyra-work/aeye-night /tmp/aeye-night
cat /tmp/aeye-night/tiers_table.txt      # full-turn table (gemma4:31b judge), GPU and cpu4 rows
cat /tmp/aeye-night/ground.jsonl         # caption and box rows per model and device
cat /tmp/aeye-night/speech.jsonl         # Whisper and Moonshine WER, real-time factor, peak RAM
```

Harness: `eval/tiers/vlm_ground.py`, `eval/tiers/speech.py`, `eval/tiers/florence.py`, generic
`ollama:<tag>` and `ollama-cpu4:<tag>` backends in `eval/backends/run.py`, and the overnight runner
`scripts/night_box.sh`.
