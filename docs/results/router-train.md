# Trained question router (now / past / expert)

`router/route.py` decides per user question whether the Haiku talker answers from the live scene (`now`), Rewind
searches earlier footage (`past`), or the turn escalates to the expert model (`expert`). It is one model for every
mode. It runs on the Mac CPU in about 43 ms and needs no API call. (`docs/results/router.md` is a different
package: the `server/llm.py` model router.)

## Read first: what is not verified

- **Not wired into the server.** `server/ws2.py` and the talker are unchanged. The lead integrates `route()`.
- **The held-out set was written by the same agent that wrote the generation prompt.** It was not produced by the
  generation pipeline, but it can share that agent's idea of the labels. the team's own lines
  (`router/data/heldout_team.jsonl`, empty now) are the real test.
- **The runtime needs new dependencies**: `onnxruntime`, `tokenizers` and `numpy`
  (`router/requirements-router.txt`), plus a one-time download of about 310 MB of model files. Without them,
  `route()` returns `unsure` with `error: ModuleNotFoundError`, and the server falls back to Haiku.
- No fine-tune was run. the team's rule was to fine-tune only under 90% held-out accuracy, and the router scored 96%.
  An MLP head was tried and did worse (below).
- There are 100 held-out questions, so one question is 1 point. Expert has only 20 questions.

## Results on the held-out set (n = 100: 53 now, 27 past, 20 expert)

| Router | Accuracy | now | past | expert | Latency p50 / p90 | Cost per 100 questions |
|---|---|---|---|---|---|---|
| **Trained router** (EmbeddingGemma int8 on Mac CPU + logistic regression) | **96%** (3 unsure count as wrong) | 98.1% | 100% | 85% (+3 unsure) | **43 / 50 ms** | $0 |
| Same, ignoring the unsure threshold | 98% | 98.1% | 100% | 95% | 43 / 50 ms | $0 |
| Router, with `unsure` sent to Haiku | **98%** | | | | 43 ms, or about 0.8 s on the 3% unsure | about $0.0003 |
| Haiku 5.5 tool choice (1 real call per question, thinking off, effort low) | 97% | 98.1% | 100% | 90% | 803 / 1573 ms | $0.0109 (85,610 in, 4,749 out tokens) |
| Current regex (`server/rewind.is_rewind_question`) | 64% | 100% | 40.7% | 0% (has no expert route) | under 1 ms | $0 |

Confusion matrices (rows are the true label):

| Trained router | now | past | expert | unsure |
|---|---|---|---|---|
| now | 52 | 1 | 0 | 0 |
| past | 0 | 27 | 0 | 0 |
| expert | 0 | 0 | 17 | 3 |

| Haiku tool choice | now | past | expert |
|---|---|---|---|
| now | 52 | 0 | 1 |
| past | 0 | 27 | 0 |
| expert | 2 | 0 | 18 |

| Regex | now | past | expert |
|---|---|---|---|
| now | 53 | 0 | 0 |
| past | 16 | 11 | 0 |
| expert | 20 | 0 | 0 |

Router misses:
- h094, "what did you tell me earlier about the second step": routed to `past`, labelled `now`, since the
  transcript already holds the answer.
- `unsure` on h044 (anchoring a bookshelf with a toddler in the house), h085 (changing a switch without turning
  off the breaker) and h098 (red CPU light plus white VGA light). Haiku routed all three correctly, so the fallback
  fixes them.

Haiku misses:
- h045, "can you double check that before I drill": routed to `now`.
- h098: routed to `now`.
- h084, "which of these wires is the neutral?": routed to `expert`.

The regex sends "when did..." and "where did I put..." to Rewind. It misses "where'd I leave", "did I water this
row", "how many eggs so far", "show me when" and "go back to".

Latency was measured on the MacBook (M5 Max CPU, 4 ONNX threads) across all 100 questions, with question and
context embedded together in one call. The first call in a process takes about 1.0 s, for the session load and
warm-up, so call `route('hi')` once at server start. Haiku latency is the full API round trip at 4-way concurrency.

## Backends and heads compared (selection by 5-fold CV on train only)

| Embedder | Head | CV accuracy | CV macro recall | Held-out | Held-out, unsure ignored | p50 |
|---|---|---|---|---|---|---|
| **EmbeddingGemma 300M int8 ONNX, Mac CPU** | **LR, C=10** | 98.5% | 98.3% | 96% | 98% | 43 ms |
| EmbeddingGemma 300M int8 ONNX, Mac CPU | MLP (64) | 97.8% | 96.6% | 95% | 96% | 46 ms |
| EmbeddingGemma on the PC's Ollama (`embeddinggemma:300m`) | LR, C=30 | 98.4% | 98.3% | 96% | 97% | 271 ms (p90 455; earlier probe p90 1.5 s while the box served vision) |
| all-MiniLM-L6-v2 ONNX, Mac CPU | LR, C=1 | 94.6% | 94.6% | 78% (20 unsure) | 95% | 1.6 ms |

The Mac-local EmbeddingGemma was chosen on CV. It matches the Ollama copy's accuracy at a sixth of the latency,
uses no GPU-box time (live vision keeps the GPU), and keeps working when the PC is down. MiniLM is 25x faster, but
its CV is 4 points lower and it is unsure on 20% of questions at the same 99% target.

## How it is built

- **Features:** the question and its context are embedded together in one call: `embed(question)` and
  `embed(context turns / question)`, 768 + 768 dimensions, using EmbeddingGemma's
  `task: classification | query:` prefix. Only the last 2 turns are used.
- **Head:** class-balanced logistic regression, exported to `router/model.json` (96 KB). Inference is a pure-Python
  dot product, with no numpy on the classifier path.
- **Unsure threshold:** 0.64, the lowest top probability at which out-of-fold CV accuracy on the kept rows reaches
  99%. That keeps 97.7% of CV rows. It was tuned on train only.
- **Training data:** `router/data/train.jsonl`.
  - Generated by `router/gen.py` with Claude Sonnet 5.5 (structured JSON output, effort low), seed 13, in 120 calls
    of 25 questions each.
  - Each call has a seeded mode, a speaking style (fragments, polite sentences, voice transcript with fillers or
    rough grammar, pronoun-only questions) and a share of questions with context.
  - Every route's prompt also asks for near-miss questions: "where does this go" is `now`, "did I already..." is
    `past`, "still nothing" after a failed try is `expert`.
  - 2,731 rows after removing duplicates and anything matching the held-out set: 1,627 now (60%), 723 past (26%)
    and 381 expert (14%). 763 rows carry context.
  - 12 modes: bike repair 384, general 307, PC build 288, crafts 280, car maintenance 251, cleaning 221, assembly
    209, electronics 207, home repair 186, gardening 159, makeup 122, cooking 117.
- **Cost:**

  | Item | Tokens | Cost |
  |---|---|---|
  | Generation | 112,220 in, 112,720 out | $1.35 |
  | Two 40-question trial runs | | about $0.05 |
  | Haiku comparison | | $0.011 |
  | **Total** | | **about $1.41** |

## Interface for the lead

```python
from router.route import route, aroute   # aroute: same thing via asyncio.to_thread
r = route(text, recent_turns)            # recent_turns: up to 2 earlier turns, str or {role, text|content}
# -> {'label': 'now'|'past'|'expert'|'unsure', 'confidence': 0.0-1.0, 'probs': {...}, 'ms': 43.0,
#     'backend': 'gemma_local', 'error'?: 'ExceptionName'}
```

`unsure` means confidence < 0.64, or the embedder failed. The server should then use Haiku's tool choice. The tool
descriptions are in `router/labels.py` and the call is `router/eval.py:haiku_route`. `route()` never raises.

Setup on the server machine:

```sh
uv pip install --python .venv/bin/python -r router/requirements-router.txt huggingface_hub
.venv/bin/python -m router.embed_local --fetch gemma_local     # ~310 MB to ~/.cache/a-eye/router/gemma_local
```

`ROUTER_MODEL_DIR` overrides the model folder and `ROUTER_THREADS` the ONNX thread count (default 4).
`pyproject.toml`'s `testpaths` does not include `router`; add it, or run `pytest router/`.

## the team's held-out questions

Add lines to `router/data/heldout_team.jsonl`, one JSON object per line. Lines starting with `#` are notes. Example:

```json
{"id": "d001", "mode": "cooking", "label": "past", "text": "where did I put the lid", "context": []}
```

Then rerun `python -m router.eval` (add `--skip-haiku` to avoid API calls). The file is never used for training or
tuning. Results go to `router/results/heldout_eval.json`, with each row's predictions.

## Rerun

```sh
S=<scratch dir>; python -m router.gen --env ~/Projects/a-eye/.env              # regenerate (about $1.35)
ROUTER_MODEL_DIR=~/.cache/a-eye/router python -m router.features --backend gemma_local --cache $S
python -m router.train --backend gemma_local --cache $S                        # writes router/model.json
python -m router.eval --env ~/Projects/a-eye/.env                              # held-out comparison
```

Training needs `scikit-learn` and `numpy`. The run used a separate uv venv, so the server venv is unchanged.

Test: .venv/bin/python -m pytest router/ - PASS (9 passed)
