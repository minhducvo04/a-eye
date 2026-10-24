# Fine-tune plan: qwen-aeye:9b (2026-10-24)

Status: **plan only. Nothing downloaded, nothing trained.** Waiting for "go" and for Duc to say the GPU box is free.

## Answer

LoRA-tune **Qwen3.5-9B** (the app's grounding model today, 15/16 boxes) on about 4,000 examples written in A-eye's
exact JSON, then register it in Ollama as a **new tag `qwen-aeye:9b`**. The current `qwen3.5:9b-q4_K_M` and
`qwen2.5vl:7b-q4_K_M` stay untouched and remain the defaults. Switching is Duc's call
(`VISION_GROUND_MODEL=qwen-aeye:9b`; `box_format()` already reads an unknown tag as qwen3.5's 0 to 1000 boxes).

Box time: about 6 to 8 hours with the GPU to itself (setup 1 h, data 1 h, training 3 to 5 h, export and eval 1 h).
Live vision is down for the whole training window.

## Risks and what is not verified

- **Memory is tight.** Unsloth's Qwen3.5 guide gives about 22 GB for 9B bf16 LoRA and says 4-bit QLoRA is
  "not recommended" for any Qwen3.5 model. The card has 24 GB, and Windows desktop apps plus boxsvc's Python
  (YOLO) also hold some VRAM. Mitigation: LoRA on the language layers only (vision tower frozen), batch 1,
  gradient checkpointing, images capped at about 0.4 MP. A 20-step memory smoke runs first; if it OOMs, the
  fallbacks are, in order: Qwen3.5-9B QLoRA (accept the quality warning, the eval decides), then
  Qwen2.5-VL-7B QLoRA (well-trodden in LLaMA-Factory and Unsloth, but its base is weaker: 12/16).
- **Export path not yet proven for a tuned Qwen3.5 vision model.** Ollama's source has a Qwen3.5 import transform
  (`create/qwen35.go`) and `ollama create --quantize`, but the docs do not list supported architectures. Step 0
  below proves the path on the untouched base weights before any training hour is spent.
- **Small eval.** 16 held-out cases; a 1-case change is noise. The tuned model must not lose boxes or quality to
  count as better.
- **Answer quality can drop.** Templated training answers make replies flat. Turn-format answers are written by the
  local `qwen3.6:35b-a3b` (text only, from COCO captions), and the turn share is kept small.

## Datasets (from the official pages, 2026-10-24)

| Dataset | Size | Licence (as stated) | Use in v1 | Notes |
|---|---|---|---|---|
| COCO 2014 images + captions | 83k train images, 5 captions each | Annotations CC BY 4.0; images "must abide by the Flickr Terms of Use" (COCO does not own them; per-image Flickr licences, some NonCommercial) | **Yes**: images and short captions | Download only the ~3k images we use, one by one from `images.cocodataset.org` (official host), not the 13 GB zip |
| RefCOCO / RefCOCO+ / RefCOCOg (UNC and UMD splits), via `jxu124/refcoco*` on HF | RefCOCO 42.4k train / 3.8k val / 2.0k testA / 1.8k testB expressions; boxes `[x1,y1,x2,y2]` px | Repo `lichengunc/refer` is Apache-2.0 (code); **annotation licence not stated** on the repo or the HF card. Images are COCO train2014 | **Yes**: referring expression to box | `lmms-lab/RefCOCO` has only val/test (with images), so it is eval-only |
| Visual Genome | 108,077 images; 5.4M region descriptions; 3.8M objects; 1.7M QA | CC BY 4.0 (HF card) | Optional v2 | Large; regions are good for "name objects" |
| PixMo-Points (Ai2) | 2,376,222 rows | ODC-BY-1.0, "intended for research and educational use" per Ai2's Responsible Use Guidelines | No (v2 candidate for points) | Images are third-party URLs to fetch site by site (about 2.9% opted out); point scale unclear (page says pixels, samples look 0 to 100) |
| PixMo-Cap (Ai2) | 717,042 rows, 1.1 GB parquet | ODC-BY-1.0, research and educational use; captions are Claude output (Anthropic terms apply) | No | Captions average about 200 words; A-eye wants one short sentence |
| LVIS | 164k images (COCO), 1,000+ categories | lvis-api code is BSD-2; HF mirror lists a "Custom License", "freely available for research use"; official dataset page returned 404 | No | Licence not confirmed from the official page |
| Objects365 | about 2M images, 30M boxes, 365 classes | Official overview page states no licence | No | Too large for tonight, licence unknown |

Forbids a hackathon demo: none of the above, as far as the pages say. Limits to note: COCO images with
NonCommercial Flickr licences, and PixMo's research/educational wording, rule out a commercial product built on
these weights. We do not redistribute images or publish the weights. No scraping (no Apify); sponsor pages were
not checked for training data.

## Data mix (A-eye's exact formats)

All boxes are qwen3.5 native: `[x1,y1,x2,y2]` normalized 0 to 1000. Prompts are copied from the code, not
paraphrased:

| Share | Task | Prompt (source) | Target JSON | From |
|---|---|---|---|---|
| 1,600 | Ground one object | `box_prompt(label, model="qwen3.5")` in `vision/ollama.py` | `{"label": <exact label>, "bbox_2d": [..]}` | RefCOCO/+/g train expressions, plus COCO category names |
| 400 | Absent object | same | `{}` | COCO category not present in that image |
| 800 | Brief scene | `'Describe the frame briefly. Return JSON {"caption":str}. No boxes.'` | `{"caption": <shortest COCO caption>}` | COCO captions |
| 1,200 | Conversation turn | `SYSTEM` + `user_text(..., "norm1000")` in `eval/backends/run.py` | `{"topic", "target", "bbox", "answer"}` | RefCOCOg expression = target and box; 1 to 2 prior turns and the reply written by local qwen3.6:35b-a3b from the captions (text only) |

Total about 4,000 train, plus **300 held-out validation** examples built from the RefCOCO `val` split
(different images). `eval/backends/data/` (16 Wikimedia Commons frames) is never read by the data builder; a
SHA-256 and perceptual-hash check against those 16 files runs before training and fails the build on any match.

## Method

- WSL2 Ubuntu on KietPC (32 cores, 45 GB RAM, 955 GB free). Python 3.12 venv via `uv` (system Python is 3.14,
  too new for the CUDA wheels), PyTorch CUDA 12.x, Unsloth, Transformers v5 (Unsloth says older versions do not
  work for Qwen3.5).
- `FastVisionModel.from_pretrained("Qwen/Qwen3.5-9B", load_in_4bit=False, load_in_16bit=True)`,
  `get_peft_model(finetune_vision_layers=False, finetune_language_layers=True, r=16, lora_alpha=16)`.
- 2 epochs, lr 1e-4 cosine, batch 1 x grad-accum 16, max sequence 2,048, gradient checkpointing, loss on the
  assistant turn only. About 500 optimizer steps; estimate 3 to 5 h on the 3090 Ti. Logs to
  `~/aeye-ft/logs/train.log` (loss every 10 steps, val loss every 100).
- Same chat template and EOS at inference as in training (Unsloth's top cause of worse behavior after export).

## Export to Ollama (new tag only)

1. Merge LoRA into bf16 safetensors: `model.save_pretrained_merged(..., save_method="merged_16bit")`.
2. Copy to `C:\kyra-work\models\qwen-aeye-9b\` so Windows Ollama can read it.
3. Modelfile `FROM C:\kyra-work\models\qwen-aeye-9b` (plus the base's template/params copied from
   `ollama show qwen3.5:9b-q4_K_M --modelfile`), then `ollama create qwen-aeye:9b --quantize q4_K_M -f Modelfile`.
4. Fallback if Ollama refuses the directory: llama.cpp `convert_hf_to_gguf.py` (text GGUF + `--mmproj`),
   `llama-quantize` to Q4_K_M, import the GGUF.

**Step 0 (before training, about 30 min):** run steps 2 and 3 on the untouched `Qwen/Qwen3.5-9B` weights as
`qwen-aeye-base-test:9b`, check it answers one eval case with a box, then `ollama rm` that test tag. If this fails,
we know before burning training hours.

## Box time and the live app

Training must never run while Duc demos. Proposal:

1. Train only after Duc says "the box is free" (tonight or overnight).
2. Before: note `ollama ps`, then unload the app's models (`keep_alive: 0` on each). No change to Ollama or boxsvc
   config. Live vision falls back to the fake backend meanwhile (AutoBackend).
3. During: nothing else uses the GPU; I check every 20 min and stop on OOM or a stall.
4. After (or on "stop"): kill the trainer, reload and warm `qwen3.5:9b-q4_K_M` and `qwen2.5vl:7b-q4_K_M`,
   confirm `ollama ps` matches the before list and `/health` on vision answers.

## Benchmark

`eval/backends/run.py` with a new backend row `ollama:qwen-aeye:9b` (norm1000), same 16 cases, 3 reps, same judge
(gemma4:31b), against `ollama:qwen3.5:9b-q4_K_M` re-run in the same session with the same GPU state. Report:
boxes IoU >= 0.3, target named, judge quality, bad JSON, TTFT and total p50/p90, plus held-out val loss. Also
`vision.probe_ollama --model qwen-aeye:9b --bench 5` for the scene/locate path.

## Command log

| Time (PDT) | Where | Command | Result |
|---|---|---|---|
| 10-24 00:0x | Mac | `curl :11434/api/tags`, `/api/ps`, `/api/version` | Ollama 0.40.8; qwen3.5:9b and qwen2.5vl:7b loaded (5.6 and 5.4 GB VRAM) |
| 10-24 00:0x | box (Windows) | `nvidia-smi` | 3090 Ti, 17.1 of 24.6 GB used; ollama llama-server x2, a Python 3.12 process (boxsvc), desktop apps |
| 10-24 00:0x | box (WSL) | `probe.sh`: df, free, nproc, python, pip | Ubuntu, 955 GB free, 45 GB RAM, 32 cores, Python 3.14.4, no torch or training libs yet |
