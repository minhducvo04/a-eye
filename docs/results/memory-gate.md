# Memory gate: a time-scope decision before Gemini Live answers (2026-10-25)

Branch `pkg/memory-gate`. Behind `LIVE_MEMORY_GATE` (on by default; `LIVE_MEMORY_GATE=0` turns it off).
No real Gemini or TwelveLabs call was made. Everything below comes from unit tests with a fake Live socket and
from the local router run on this Mac's CPU (Apple M5 Max).

**Not verified yet:** a real Google Live call. The script at the bottom is the check still to run.

## What it does

```
user speaks -> Live inputTranscription (streaming)
   safety stop_line ......... wins, fixed line
   guide claims ("done") .... guide owns the turn
   memory gate .............. strong time words -> hold Live's reply at once
                              (no time words, ROUTER=on) -> scope head after a 0.3 s debounce
      scope: now | seconds | minutes | this_call | past_calls
      lookup: seconds/minutes -> RAM log (10 min) -> keyframe memory (never the current frame)
              this_call       -> Rewind (sure hit) -> RAM log -> Rewind guess -> earlier call (labelled)
              past_calls      -> task history by date window -> kept sightings in that window
      lookup > 700 ms  -> fixed line "Let me think back, one sec." (once)
      lookup > 4 s     -> honest timeout line
      found            -> prompt_turn: MEMORY vN evidence, Live says it in the Dad voice
      not found        -> code speaks the honest line (fixed_say); Live gets no turn, so no made-up place
```

- Hold uses the same path as the Live guide: `bridge.hold()` drops Live's own audio; `prompt_turn()` waits for
  the held turn to finish, then sends `clientContent` with `turnComplete: true`.
- A late `recent_memory` / `rewind_search` tool answer for the held turn is dropped (the hold bumps the prefetch
  version that `_tool_response` checks).
- Cards: the existing `rewind_hit` and `find_item` messages, the same ones the prefetch already sends. No new
  card, stage detail or screen.
- Log: one `memory_turn` event, fixed metadata only: `reason={scope, source, found, via, filler, delivered}`,
  `ms` (lookup time). No transcript text.
- Present-tense checks that sound past ("what did I do wrong", "did I put this in right") never hold on regex
  alone; only the scope head can make them a memory turn. A sure "now" from the head (P(past) <= 0.2) releases
  an early hold back to Live.

## Decision model (router/scope.py)

Same EmbeddingGemma vector the router already computes (one embed call, then two small heads), plain
logistic regression exported as JSON, pure-Python inference. The scope head reads the question alone.
On the home PC route (`ROUTER_OLLAMA_URL`, backend `gemma`) the embeddings stay there and both heads stay local,
as today; the head only runs when its input size matches the embedder.

| Data | Rows | Source |
|---|---|---|
| `router/data/scope_train.jsonl` | 280 (60 to 80 per scope) | handwritten for this package; 5-fold CV picks C and the threshold |
| `router/data/scope_heldout.jsonl` | 100 (20 per scope) | handwritten separately; never read by training; no overlap (tested) |

Held-out result (`router/results/scope_heldout_eval.json`):

| Metric | Value |
|---|---|
| 5-class accuracy | 0.96 |
| Recall now / seconds / minutes / this_call / past_calls | 1.00 / 0.95 / 0.95 / 0.90 / 1.00 |
| Now questions held by mistake | 0 of 20 |
| Gated (P(past) >= 0.80) that were truly past | 78 of 78 |
| Past questions gated | 78 of 80 |
| Scope right among gated | 0.95 |

Latency, full `route()` (embed + router head + scope head), 100 held-out questions, warm, CPU:
median 45.7 ms, p90 47.9 ms, max 97 ms (first call after warm-up).

Retrain: `python -m router.scope train --cache DIR`; evaluate: `python -m router.scope eval --cache DIR`.

## Bugs fixed (Board, 2026-10-25)

1. RAM log kept 120 s, so "two minutes ago" mostly missed. Now 10 minutes; asked ages up to 5 minutes read the
   RAM log; the time window is `max(20 s, 25% of the age)`.
2. "last week" always returned no memory. `long_term` now takes date windows (yesterday, N days ago, last
   week / the other day, last time) and answers "what did we fix / do" from the growth log with dates; an empty
   window says "I don't have a saved task from last week."
3. Word match was strict. Plurals fold ("wrenches" = "wrench") and a short synonym list maps cup/mug,
   rag/cloth/towel, spanner/wrench and a few more.

## Tests

- `router/test_scope.py`: held-out accuracy >= 0.9, no now held by mistake, median latency < 60 ms (real
  local EmbeddingGemma; skips if its files are missing), data files disjoint.
- `server/test_live_memory.py`: hold and one evidence turn; two-minutes-ago; wait line once for a slow lookup;
  not-found spoken by code with no Live turn; 4 s timeout line; now question not held; safety and guide win;
  private mode and gate off do no lookup; late tool answer dropped; router-only decision and veto.
- `server/test_recent_memory.py`: two-minutes-ago, plurals and synonyms, last-week task history and its
  honest empty case. Three older tests encoded the 120 s window and were updated to the 10-minute rule.
- `server/test_gemini_live.py`, `server/test_live_prefetch.py`: the tool/prefetch tests run with
  `LIVE_MEMORY_GATE=0`, since the gate now owns those turns.

## Real-call script (from the Board file, section 6)

Setup: sink pack, Rewind on with TwelveLabs consent, `LIVE_MEMORY_GATE=1`, `ROUTER=on`, `REWIND_FLUSH_S=15` only
if the owner approves the cost, a fresh `CLOUD_BUDGET_PATH`. Camera on a table with a wrench, a towel and a mug.
Times are from call start. Pass means: the `memory_turn` event shows the source, a card appears when the source
has one, and Dad's spoken words (output transcript) contain the fact from the evidence, not from the current
frame.

| t | Action | Say exactly | Pass |
|---|---|---|---|
| 0:05 | Wrench in view, then set it on the towel | "Dad, I'm putting the wrench on the towel." | normal reply, no memory turn |
| 0:20 | Move the wrench out of view | (nothing) | |
| 0:30 | Seconds scope | "What did I just do with the wrench?" | `memory_turn source=recent found=true`; Dad mentions the towel; no "I can't see" |
| 0:45 | Not-found check | "Where did I put the screwdriver a minute ago?" | `found=false delivered=fixed_say`; Dad says he did not see it; names no place |
| 2:10 | Minutes scope | "Where did I put the wrench two minutes ago?" | `source=recent` (or `scene_memory`); towel mentioned |
| 2:30 | This call, Rewind | "Rewind: when did I first pick up the wrench?" | `source=rewind`; `rewind_hit` card; Dad says about 0:05; wait line only if lookup over 700 ms |
| 2:45 | Guide priority | "Okay, the water is off." | guide check runs, no memory turn |
| 3:00 | Past calls | "What did we fix last week?" | `source=history` if a growth row exists, else the fixed "no saved task" line; never a made-up task |
| 3:15 | Now question control | "What am I holding right now?" | no memory turn; answer from the current frame |

Record per row: t(end of speech), t(card), t(first Dad audio), t(fact word in output transcript), and whether
Live's held reply was suppressed (no `reply_delta` before the evidence turn).

Local dry run of the decision for these lines (real router, Rewind off, so this_call maps to the RAM log):

| Line | Early hold | Scope head | Decision |
|---|---|---|---|
| "Dad, I'm putting the wrench on the towel." | no | now (P(past) 0.12) | none |
| "What did I just do with the wrench?" | yes | seconds 1.00 | recent |
| "Where did I put the screwdriver a minute ago?" | yes | minutes 1.00 | recent |
| "Where did I put the wrench two minutes ago?" | yes | minutes 1.00 | recent |
| "Rewind: when did I first pick up the wrench?" | yes | this_call 1.00 | rewind when on (recent here) |
| "Okay, the water is off." | no | now (0.004) | none |
| "What did we fix last week?" | yes | past_calls 1.00 | long-term |
| "What am I holding right now?" | no | now (0.08) | none |

## Open risks

- `prompt_turn` still waits up to 3 s for the held Live reply to finish. Not measured in a real call; sending
  earlier would let late held audio play as the evidence answer, so it was left as is.
- Model-only holds (no time words) happen about 0.35 s after the last partial transcript; if Live already
  started speaking, its reply is cut and replaced.
- The scope head was trained on `gemma_local` (int8 ONNX) vectors; on the Ollama backend it runs only if the
  vector size matches and is not separately measured there.
- The wait line uses `fixed_say` (app TTS), the same voice mismatch safety and growth lines already have.
