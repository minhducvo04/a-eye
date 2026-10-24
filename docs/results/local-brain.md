# Local brain: open models for the talker and the expert (2026-10-24)

Status: **Phase A built and benchmarked in part; Phase B is a plan only.** Runs paused on Duc's request
(2026-10-24 01:10 PDT). No new slots until told. The gpt-oss:120b pull is paused at about 1.3 of 65 GB.

## Answer

- **No local model matches Claude yet.** Talker quality: Haiku 4.00, best local 3.25 (qwen3.5:9b and
  qwen3.6:35b-a3b tie). Expert quality: Opus 4.00, best local 3.00 (qwen3.6:35b-a3b), and its answers take about
  70 s instead of 3.6 s.
- **Both local talkers failed the hot-oil safety case** (qwen3.6 and qwen3.8 said smoking oil is fine for searing;
  judge 1). Haiku got it right. Hot oil is not covered by any `refuse()` gate today.
- **Best local pick for `BRAIN=local`:** qwen3.6:35b-a3b (MoE) for talker and expert, run CPU-only with 8 threads
  (now the adapter's default for non-vision models). That is the only setup measured to keep vision within noise.
- **Never put the local expert on the vision model.** qwen3.5:9b as the expert (thinking on) made vision grounding
  go from 0.73 s to 11 to 24 s for about 4 minutes. The adapter now refuses that (and `pkg/expert` does too).
- **Not measured:** gemma4:31b and gpt-oss:120b (no slot run); qwen3.8 expert has only 4 of 10 rows; CPU-only talker
  latency for qwen3.6 (its talker rows ran with 7 GPU layers).

## Results (n = 20 talker turns, 10 expert questions, 1 rep, one request at a time)

| Backend | Talker quality 1-5 | SAY format | Words p50 | Talker first token p50/p90 s | Talker total p50 s | Expert quality 1-5 | Expert total p50/p90 s | Expert speed |
|---|---|---|---|---|---|---|---|---|
| Claude Haiku 5.5 (talker) / Opus 5.5 (expert) | **4.00** | 20/20 | 33 | 0.52/0.73 | 0.84 | **4.00** | **3.64/9.60** | cloud |
| qwen3.5:9b-q4_K_M (all on GPU, the vision model) | 3.25 | 20/20 | 26 | **0.25/0.30** | **0.53** | 2.60 | 14.4/30.2 | n/a (shares the vision runner) |
| qwen3.6:35b-a3b-q4_K_M (MoE, mostly CPU RAM) | 3.25 | 19/20 | 22 | 1.09/1.16 | 2.36 | 3.00 | 69.1/97.0 | 19 to 24 tok/s |
| qwen3.8:27b-q4_K_M (dense, mostly CPU RAM) | 2.95 | 19/20 | 14 | 1.32/1.43 | 6.58 | 2.50 (n=4 of 10) | 103.9/134.6 (n=4) | 3.5 to 4.0 tok/s |
| gemma4:31b-it-q4_K_M | not run | | | | | | | |
| gpt-oss:120b (expert only) | not run (pull paused) | | | | | | | |

How it was measured:

- Harness `eval/brain/run.py`, cases `eval/brain/cases.json` (20 talker turns across pc_build, cooking,
  assemble and general packs, 3 safety turns; 10 expert questions). Prompts are built as in `server/agent.py`
  (duo talker: pack prompt + memory line + `TALKER_RULES`, user JSON with caption, objects, memory, conversation,
  text) and `server/expert.py` (`EXPERT_RULES`, user JSON with scene, memory, transcript, question). Text only, no
  images.
- Claude: talker `claude-haiku-5-5` with `fast_options` (thinking disabled, effort low); expert `claude-opus-5-5`
  effort medium, **no web search** (the real expert may search). Local: through `server/brain_local.LocalBrain`
  (the real adapter); talker think off, expert think on (thinking tokens are counted in the speed, not shown).
- Times are wall clock from the Mac over Tailscale. "Expert total" is the time until the full answer.
- Judge: Claude Sonnet 5.5, blind (text only, fixed rubric in `run.py`), n = 1 per answer. **It is a Claude
  model judging Claude against others, so it may favour Claude's style.** With 20 and 10 cases, a gap under about
  0.3 is noise.
- Offload: qwen3.6 talker rows ran with 7 GPU layers and 16 threads while the gpt-oss pull was also running. Its
  expert rows ran in three parts: 7 GPU layers with 16 threads, 7 GPU layers with 8 threads, then CPU only with
  8 threads. qwen3.8 ran 15 GPU layers with 8 threads, then CPU only for its last row. Speeds are Ollama's
  `eval_count / eval_duration`.

### Vision impact (grounding probe every 30 s: qwen3.5:9b, desk_mug.jpg, Ollama box time)

| Segment (PDT) | What ran | Vision median / max ms | vs baseline |
|---|---|---|---|
| 00:30 | nothing (before the Ollama restart) | 730 / 1428 | baseline |
| 00:32 to 00:35 | qwen3.5:9b expert, thinking on (same runner as vision) | **11,360 / 24,301** | **15x slower**, never again |
| 00:42 | gpt-oss:120b pull only | 1308 / 1419 | +38% vs 947 without the pull |
| 00:44 | nothing (after the restart, pull paused) | 947 / 1124 | new baseline |
| 00:45 to 00:52 | qwen3.6, 7 GPU layers (16 then 8 threads) | 1062 / 1512 and 1049 / 1185 | +12%, auto-stopped at +23% |
| 00:53 to 00:58 | qwen3.6, CPU only, 8 threads | 1036 / 1139 | +3% (base 1001), no stop |
| 00:59 to 01:07 | qwen3.8, 15 GPU layers, 8 threads | 1017 / 2386 | spikes to 2.4 s, auto-stopped |
| 01:08 to 01:10 | qwen3.8, CPU only, 8 threads | 873 / 1112 | within noise |

No vision model was evicted in any run (`/api/ps` checked every 30 s). After every slot the big model was unloaded
(`keep_alive: 0`). Vision `/health` answered ok and a real `/scene` call returned a box and a caption at 01:11.

## Box change (Duc's "A now", 2026-10-24)

The box's Ollama runs from the scheduled task "Kyra Ollama" (`cmd /c set OLLAMA_HOST=0.0.0.0:11434&& ollama.exe
serve`, user tomdu). With the default `OLLAMA_MAX_LOADED_MODELS=3`, a 4th model (even CPU only) evicts one of
qwen3.5:9b, qwen2.5vl:7b or embeddinggemma:300m (the router). Command used at 00:36:45 PDT, from the Mac:

```
ssh tomdu@100.93.176.7 "powershell -NoProfile -Command \"[Environment]::SetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS','4','User'); Stop-ScheduledTask -TaskName 'Kyra Ollama'; Start-Sleep 3; Get-Process ollama,llama-server -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2; Start-ScheduledTask -TaskName 'Kyra Ollama'\""
```

Then the three app models were warmed with the app's own options (num_ctx 4096, keep_alive 30m; embeddinggemma
24h). Ollama was back at 00:36:57.

**Undo:** the same command with `[Environment]::SetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS',$null,'User')`
in place of the first statement (removes the variable and restarts Ollama), then warm the three models again.

## Interface for the lead (Phase A, merged)

- `server/brain_local.py`: `make_llm()` returns `LocalBrain` when `BRAIN=local`, else `LLMClient`. To switch the
  app, replace `LLMClient()` with `make_llm()` in `server/app.py` (line ~58) and `server/ws2.py` (line ~249). No
  other change: `LocalBrain` keeps LLMClient's calls: `stream(system, user, *, max_tokens, on_backup, model,
  images)` yields text, `expert(system, user, *, model, images)` returns `{"text", "metrics"}` with the same metric
  keys as the Claude expert (cost 0), and `complete()` returns an `LLMResult`.
- Claude names map to local roles: `claude-haiku-*` or no model = talker; any other Claude name on `stream` =
  planner; `expert()` = expert. A local tag passes through unchanged.
- Env: `BRAIN=local`; `BRAIN_TALKER_MODEL` (default `qwen3.6:35b-a3b-q4_K_M`), `BRAIN_PLANNER_MODEL` (default: the
  talker), `BRAIN_EXPERT_MODEL` (default `qwen3.6:35b-a3b-q4_K_M`); `BRAIN_NUM_GPU` (default 0) and
  `BRAIN_NUM_THREAD` (default 8), never applied to the vision models, `auto` lets Ollama decide; `BRAIN_NUM_CTX`
  4096; `BRAIN_KEEP_ALIVE` 30m; `BRAIN_LOCAL_FIRST_TOKEN_S` 10; `BRAIN_EXPERT_THINK` 1; `BRAIN_EXPERT_MAX_TOKENS`
  4096.
- Two settings the expert desk needs with `BRAIN=local` (in the lead's files): (1) `server/expert.py` picks the
  model before calling the brain. Without a key and with `EXPERT_LOCAL_MODEL` unset, it says the offline line, so
  set `EXPERT_LOCAL_MODEL=qwen3.6:35b-a3b-q4_K_M`. (2) `EXPERT_TIMEOUT_S` defaults to 45 s, but the local expert
  takes 69 s p50 and 97 s p90, so use at least 150.
- Safety: `refuse()` gates still run before any model. The hot-oil miss above suggests adding hot oil to the
  cooking pack's gate before the local talker is used live.

Tests: `server/test_brain_local.py` (9 with `eval/brain/test_brain_eval.py`), offline with MockTransport.
Real run: every local row in the table went through `LocalBrain` against the box.

## Phase B: distillation plan (plan only, waiting for "go")

**Goal:** make a local talker (and, later, a local expert) answer more like Claude Haiku and Opus on A-eye turns, so
`BRAIN=local` loses less quality.

**Licence check first (blocks the Claude-teacher version).** Anthropic's Commercial Terms, section D.4: the customer
may not "access the Services to build a competing product or service, including to train competing AI models ...
except as expressly approved by Anthropic". Training an open model on Claude outputs to replace Claude is close to
that line. **Duc decides** before any Claude output is used as training data. Two versions:

| Version | Teacher | Licence risk | Cost |
|---|---|---|---|
| B1 (default) | Best local model with thinking on (the top expert row in the table above), distilled into a fast local talker | None: Qwen and Gemma weights are Apache-2.0 / Gemma terms; gpt-oss is Apache-2.0 | $0, box time only |
| B2 (only with Duc's yes, and ideally Anthropic's) | Claude Haiku 5.5 (talker) and Opus 5.5 (expert) | D.4 above | about $10 to $15 in API calls (estimate below) |

**Data (synthetic, no user data):**
- Scene notes from COCO 2014 captions and object lists (annotations CC BY 4.0; text only, no images needed because the
  talker reads notes, not pixels), mapped into the exact `run_turn` user JSON (caption, objects with ids and boxes,
  memory, conversation, text). About 3,000 talker turns across the four packs, including safety turns (PSU, mains,
  hot oil) and "can't see it" turns.
- 600 expert questions written by the teacher from templates (multi-step diagnosis, safety, conflicting evidence,
  "are you sure"), each with scene notes and a 2 to 5 line transcript.
- Teacher answers through the same prompts as production (`TALKER_RULES`, `EXPERT_RULES`). Filters in code: SAY
  format, at most 2 sentences and 40 words for the talker, no markdown, and the pack `refuse()` gate re-run on the
  question (refused questions get the fixed refusal line as the target).
- Held out: `eval/brain/cases.json` (20 talker, 10 expert) is never used for training; a string-overlap check fails
  the build on any near-duplicate question.
- B2 cost estimate (list prices from `server/expert.py`): Haiku 3,000 turns x about 1,500 in / 60 out tokens = about
  $0.55; Opus 600 x about 1,000 in / 600 out = about $9.60; question writing about $2. Not spent.

**Training (student candidates that fit 24 GB):**

| Student | Method | VRAM (est.) | Time (est.) | Why |
|---|---|---|---|---|
| Qwen 3.5 9B (text use) | bf16 LoRA r=16, language layers only | about 22 GB (Unsloth figure) | 2 to 3 h for 3,000 short turns x 2 epochs | Already the fastest talker here (0.25 s first token) |
| Qwen 3.5 4B | bf16 LoRA | about 12 GB | about 1 h | Fallback if 9B does not fit beside other GPU users |
| Qwen 3.6 35B-A3B | QLoRA | does not fit well (MoE in 4-bit is not recommended by Unsloth) | n/a | Cloud GPU only |

- **The 9B student must be a separate Ollama tag** (for example `qwen-aeye-talk:9b`). It must not replace the vision
  model `qwen3.5:9b-q4_K_M`: a talker sharing the vision model's runner queues behind grounding (measured above).
- **Box time:** training needs the whole GPU, so the app's vision models are unloaded for 3 to 4 h. That only
  happens after Duc says "box is free". Otherwise use a cloud GPU later: one A100 80 GB or H100 for about 2 h. Duc
  mentioned BitDeer AI; nothing has been signed up for or spent.
- **Export:** merge the LoRA, `ollama create qwen-aeye-talk:9b --quantize q4_K_M` from the merged safetensors. Run
  this path once on base weights first; it is not proven for Qwen 3.5 here (see `finetune-plan.md`, parked).

**Expected gain (estimate):** the 9B talker's judge score moves from its measured value toward the teacher's,
typically recovering a third to a half of the gap on in-domain style. The safety and format slips (the PSU "yet",
invented physical actions) are the most learnable. Expert depth will not transfer to a 9B model; keep the expert on
the larger local model or Opus.

**How it is measured:** `eval/brain/run.py` on the same 20 talker and 10 expert cases. The same blind judge (Claude
Sonnet 5.5, text only), plus the code checks (SAY format, words, symbols) and time to first token from the Mac.
Accept only if talker quality goes up by at least 0.3 with no new safety failure, and first-token p50 stays under
0.5 s.

## Parked: vision fine-tune

`docs/results/finetune-plan.md` (Duc parked it 2026-10-24: nothing downloaded or trained).
