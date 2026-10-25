# Parts shelf (voice and context only)

Branch `pkg/parts-shelf`. No UI change. No network in the call path. Not run against a real Live call or the
team SpacetimeDB yet.

## What it does

- `data/kb/cards.json`: 39 hand-written cards for the coded guide tasks (ee_led 20 incl. resistor and polarity
  cards, sink 12, hinge 4, breaker 3). Each card: what it is for, how to identify it, a safe spec taken from the
  guide text or the listing name (for example "220 ohm resistor in series with the LED"), the matching coded
  safety line, and 0 to 2 product ids.
- `data/kb/products.json`: the 22 linked rows (id, name, brand, category, url) copied from the non-personal
  export of the team `product` table (Amazon listings scraped with Apify). The export has no prices, so no card
  or note says a price.
- Sink parts are thin in the data (no supply line, cartridge, faucet or plumber's tape rows; the only "PTFE"
  rows are 3D printer parts). Those cards link no product and say "Plumbing parts: ask a hardware store and
  bring the old part or the tap model label." Only the adjustable wrench card links a real tool row.
- `server/parts_shelf.py`: loads the two files once (server start in `server/app.py` lifespan); a missing or
  invalid file gives an empty shelf and the call runs as before. `check_card` is the field allowlist.
- Step note: `LiveContextBuilder.build()` adds a `parts` field to the Haiku evidence and appends the
  code-owned "Parts for this step ..." line to the published background block. `LiveGuide.block()` appends the
  same line to the guide block. The step's cards come first, ordered by which part the step text names, then
  cards named in the last 4 user/helper turns (only cards for the current task while a task runs). Max 500
  chars. Live is told to mention it only when asked and never to quote a price.
- Tool `look_up_part(name)`: NON_BLOCKING, offered only with `KB_TOOL=1` (off by default), answered from
  memory, at most 600 chars, "No card for that; describe it to me." when nothing matches.

## Hooks in shared files (few lines each)

- `server/gemini_live.py` (owned by the memory-gate builder): import `parts_shelf`; `TOOL_ARGS['look_up_part']`;
  one `TOOL_DESCRIPTIONS` entry; one condition in `declarations()` (`parts_shelf.tool_on()`); two lines in
  `tool()` before `gather_context`. 7 lines added, 3 changed.
- `server/context_agent.py`: import, 2 lines computing `parts`, `parts=parts` in the evidence, block suffix.
- `server/live_guide.py`: import and 2 lines in `block()`.
- `server/app.py`: import and one preload line in `lifespan`.

## Upload to SpacetimeDB (not run; no .env in the worktree)

`scripts/kb_upload.py` validates every card with `check_card` before the first request, then calls reducer
`upsert_kb_card` once per card with exactly these args in order:
`id, kind, name, aliases, task_ids, step_keys, what, identify, spec, safety, product_ids, source, updated`
(all strings except `updated`, u64 Unix seconds). It uses `SpacetimeStore._request` (HTTPS, bearer token from
`SPACETIMEDB_URI`, `SPACETIMEDB_MODULE`, `SPACETIMEDB_TOKEN`, safe errors). The table needs a `spec` column in
addition to the Board plan's list.

Coordinator, from the main checkout after the module has `kb_card` and `upsert_kb_card`:

    make kb-upload                                   # loads .env
    .venv/bin/python scripts/kb_upload.py --dry-run  # validate only, sends nothing

Verify with `SELECT COUNT(*) FROM kb_card` = 39. The server still reads the checked-in files, not the table.

## Tests

- `server/test_parts_shelf.py` (14 tests): checked-in cards load and point at real guide steps and linked rows;
  bad files give an empty shelf; step note order and length; dialogue warming limited to the current task;
  tool answer and no-card line; tool offered only with `KB_TOOL=1`; the builder's evidence and published block
  carry the note; the upload sends only allowlisted fields and nothing when one card fails; unsafe values rejected.
- `pytest -q server`: 824 passed, 2 warnings.
- `scripts/test_ready.py::test_local_probes_only_read_settings` fails on `main` too (unrelated).

## Not verified

- A real Gemini Live call: whether Live uses the note well, and how it behaves with the extra tool on.
- The upload against the team module (table and reducer not seen).
- ruff (not installed in the venv).
