# Model tiers for a wearable or home device (2026-10-24, overnight)

TIERS_RESULTS

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

No Chinese-origin models other than Qwen were used. All downloads came from the Ollama registry, Hugging Face org
pages (HuggingFaceTB, ggml-org, microsoft, moonshine-ai, rhasspy, Systran, Qwen) or PyPI.
