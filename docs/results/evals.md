# Component model-swap evaluations

The offline runner, planner code scorer, checker challenge bank, and decision
wrapper are implemented. **No live model run or production planner quality is
verified.** Work is on `pkg/evals`; no push, retraining, credential-file access,
or provider call is part of this delivery.

## Run and compare

From the worktree root, using the existing project Python:

```sh
~/Projects/a-eye/.venv/bin/python eval/swap/run.py planner --model fixture
~/Projects/a-eye/.venv/bin/python -m eval.swap.run checker --model current
~/Projects/a-eye/.venv/bin/python -m eval.swap.run decision --model fixture
```

`--fixture` is optional: offline replay is the default. It re-scores recorded
outputs, not saved scores. Offline paths block Python socket connections and DNS;
they never load an embedder or train a model. There is no dotenv loader.
`checker` executes the current production code on synthetic plans and requires
`--model current`; it does not pretend a model id selects different code.

Each scored run writes `eval/out/swap-<component>-<model>.json` and appends exactly
one row to `eval/out/swap.md`. The JSON contains every case, metric, check,
case/record/source hashes, and two worst case ids. Replays have identical scores
and case rows; timestamps and current code hashes may differ. Detailed JSON is
the latest run for that model; Markdown retains all score lines. These outputs
are gitignored. `--out <directory>` can keep a separate run's artifacts.

Exit codes: **0** = all implemented bars pass; **1** = at least one bar fails;
**2** = unavailable or invalid input (no misleading score line is appended).
Fixture PASS means scorer plumbing works, not that a real model passed.

For a coordinator with separately authorized provider access, after the planner
adapter has been checked against the landed module:

```sh
python -m eval.swap.run planner --model MODEL_A --live --record
python -m eval.swap.run planner --model MODEL_B --live --record
python -m eval.swap.run planner --model MODEL_A
python -m eval.swap.run planner --model MODEL_B
```

Read the two models' rows in `eval/out/swap.md`, then their worst cases in JSON.
Require every implemented bar and no safety regression. Do not compare results
with differing case hashes or scorer versions without re-scoring both records.
Missing latency, usage, price, or cache measurements are unknown, never free or
fast. A live planner run fails those bars if its telemetry is incomplete.

Recordings default to `eval/swap/fixtures/<component>/<model>.jsonl`. Repeating
`--live --record` refuses an existing file **before a model call**. To preserve a
second recording, choose a fresh `--fixture-file <path>` and use that path for
replay. `--record` without `--live` is rejected. Model ids must be filename-safe
letters, digits, dots, underscores and hyphens, starting with a letter or digit.

## Inputs and record contract

Cases live in `eval/cases/` (the explicit task location, instead of the Board's
suggested `eval/swap/cases/`). The planner file was reviewed as task-only text
before copying: 12 plans, 3 unsafe drops, 1 banned topic, 2 coded-guide wins,
2 no-trigger cases. It contains no personal data. The Board's warning remains:
an owner or different-model writer must review/rewrite at least five cases
before treating the initial bars as acceptance evidence.

The planner recording has one JSON object per case:

```json
{
  "v": 1,
  "id": "CASE_ID",
  "model": "MODEL_ID",
  "source": "live",
  "case_sha256": "SHA256_OF_CANONICAL_CASE",
  "output": {
    "outcome": "plan",
    "plan": {"task": "task title", "steps": [
      {"say": "instruction", "show": "visible evidence", "target": "object", "check": "check", "safety": ""}
    ]},
    "research": "recorded researcher notes"
  },
  "telemetry": {
    "calls": 1,
    "latency_ms": 1200,
    "usage": [{"input_tokens": 100, "output_tokens": 50,
      "input_usd_per_million": 1, "output_usd_per_million": 2,
      "price_source": "illustrative tariff; replace with dated provider list price"}],
    "cache": {"calls": 0, "latency_ms": 10}
  }
}
```

The values above are format examples, not model measurements or current prices.
`run.make_record()` computes the case hash. Allowed sources are `fixture`
(hand-written), `live`, and `cached_features`. Missing/extra/duplicate cases,
changed case content, wrong model/version, and non-finite values are rejected.
`output.plan` may be a JSON string, allowing invalid JSON to be scored as a
failure rather than making the entire record unreadable. Non-plan outcomes must
have `plan: null`; merely labeling an unsafe plan as dropped cannot pass.

The shipped `planner/fixture.jsonl` is **hand-written fixture data** with
synthetic call counts. It has no measured latency, billed usage or cache proof.
It exercises all 20 cases. The checker has 15 separately hand-made bad plans and
12 good plans taken from this fixture, including ordinary computer/charger
wording as false-drop controls. These are not best-model recordings yet.

## Metrics and production boundaries

Planner metrics implement the Board's JSON schema, 1–8 steps, `say` strictly
under 25 words, target 1–4 words, nonempty show, named must-group recall,
first-occurrence step ordering, never hits, and absent-part acquisition language.
Matching uses case-folded substrings in `say + show + check + safety`.
Research recall/safety/never, trigger decisions, end-to-end plan pass, maximum
calls, zero-call bypasses, recorded latency p50/p90, token-priced cost and cache
replay are separate metrics. Cost requires usage for every recorded call and a
price source; rates are not guessed or fetched. Percentiles use nearest rank.
No LLM judge or subjective factual/concreteness acceptance is claimed; this
delivery implements the requested code metrics only.

`server/planner.py` is absent at this checkout and at the inspected `pkg/planner`
commit. The live adapter invokes the documented public
`plan(text, caption, parts)` boundary, with an explicit `model=` keyword required
for a model swap. It accepts sync or async functions returning the output
envelope above plus `telemetry`. It calls a successful plan again for cache
telemetry. It refuses an incompatible interface instead of inventing an outcome
or silently selecting the default model. The planner owner/coordinator must
verify this seam against the landed public API before running live.

The checker calls real `server.safety.after()` and
`server.packs.electronics.refuse()` on each joined step. `after()` returns the
original accepted text, so only a replacement counts as a catch. Eval-side JSON
and shape validation **does not count as a production catch**. When available,
`server.planner.check_plan(plan)` is also called: None/False means drop, True or
the unchanged plan means accept, or a returned plan must contain a known fixed
safety line to count as a replacement. Checker exceptions fail the evaluation;
they are not credited as safe drops. Missing planner code is reported, and an
existing module with no compatible checker refuses evaluation pending an adapter.

## Decision component

Both existing files are used unchanged: `router/data/scope_heldout.jsonl` and
`router/data/heldout.jsonl`, **100 rows each** at this revision. `heldout_team`
is deliberately excluded. Scope records carry `output.scope_probs` (all five
scope labels) and the recorded threshold; route records carry `output.label`.
Ids are prefixed with `scope:` or `route:`. The shipped decision fixture always
predicts now and is explicitly synthetic: its low score is a useful failure-path
smoke test, not a result for gemma_local.

For already-present cached features and exported heads:

```sh
python -m eval.swap.run decision --model gemma_local --cache PATH_TO_EXISTING_CACHE
```

This wraps `router.scope.evaluate()` with mandatory, validated disk arrays in
place of its cache-miss embedding path, then classifies through the real exported
heads. Both `.npy` files must exist and have the exact expected dimensions. It
also uses `router.eval.summary()` for route accuracy. Backend ids must match
both exported heads. No training, embedding download, or network fallback occurs.
Cached features cannot prove embed-plus-classify latency; that bar stays failed.

A later authorized coordinator can record through the real shared route/scope
path using `decision --model gemma_local --live --record`. New backends require
their separately prepared exported heads before recording; this runner never
retrains. Per-case probability records allow free offline re-scoring afterward.
The existing scope result is aggregate-only and is not repackaged as invented
per-case observations. No real cached features were supplied for this delivery.

Scope accuracy uses argmax as in the existing evaluator. `now_held_by_mistake`
uses the **actual past-gate threshold**, and coverage counts truly past gated
rows, preventing false gates from inflating coverage. These fix reporting
semantics in this wrapper without changing router production code. The Board's
additional FINAL slice is not part of this task and is not claimed as evaluated.

## Verification and current findings

Verified on the working tree based on `446fe77` (2026-10-25), with only this
package's changes applied:

| Component | Input evidence | Result |
|---|---|---|
| Planner | 20 hand-written fixture records | Code bars PASS; 12/12 plan cases pass, must/order 100%, never hits 0; latency/cost/cache not measured |
| Checker | Current production gates; 15 bad + 12 good synthetic plans | FAIL: 5/15 caught, 0/12 false drops; planner checker absent |
| Decision | 200 synthetic always-now predictions | Expected FAIL: scope 20%, route 53%, past coverage 0%; no real model inference |

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q eval/swap` - PASS
(19 passed in 0.57s; includes held-out guard).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q eval scripts` - FAIL
(179 passed, 1 failed in 2.95s; summary read, exit 1). The only failure is the
pre-existing loopback-bind test described below; no tests were skipped.

Changed-package privacy scan: 14 files, 0 findings, 0 binaries. No dependencies
were added. Direct-script and module CLI entrypoints, append-only score lines,
stale/missing/duplicate fixture rejection, offline connection blocking,
record/replay equality, exclusive recording, checker misses/crashes, the actual
scope-evaluator cache path and the future planner public-call seam were exercised.

Detailed local proof: `eval/out/proof-planner.txt`, `proof-checker.txt`,
`proof-decision.txt`, the three score JSON files, and `eval/out/swap.md`.

The held-out guard covers planner inputs, checker plan text, and both decision
sets against all text under `server/` and `router/data/*train*`. It normalizes
Unicode, case, punctuation and whitespace (contractions count as one word) and checks every eight-word span,
including decoded Python string constants and JSON strings. It does not read
credential files or binary media. There are no grandfathered overlap exceptions.

There are no detected eight-word overlaps. An initial tokenizer split
contractions and incorrectly flagged the seven-word phrase
`there's a burning smell coming from the`, shared by route case `h016` and
training case `g2471`. Contractions now count as one word, with a regression
covering the seven/eight-word boundary and curly apostrophes. The shared generic
seven-word phrase is a near-overlap for the router owner to consider; neither
dataset was changed or retrained, and no exception was added to the guard.

The current production gates catch only 5/15 bad plans, with 0/12 false drops.
Misses: opening a charger, long speech, nine steps, invalid JSON, a sink step,
wrong steps type, missing/empty show, long target and empty steps. This is a
FIX-FIRST handoff to the planner checker owner, not a request to weaken the eval.

The existing readiness test `scripts/test_ready.py::test_live_pair_request_on_fake_socket`
requires a loopback bind that this sandbox denies. No network permission was
requested and no test was skipped or marked xfail to hide that limitation.
