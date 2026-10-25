# Live tools and memory prefetch — 2026-10-25

Implemented items 3 and 4, then 1, 2 and 5 from the Board routing plan. Changes are
uncommitted on top of `807a736`. Local WebSocket behavior is verified; real Google
and TwelveLabs acceptance is not verified in this run.

## Behavior

- Every Live tool call gets a tracked task instead of blocking the socket reader.
  Normal results use `response.scheduling: WHEN_IDLE`; fixed safety lines use
  `INTERRUPT`. All function declarations include `behavior: NON_BLOCKING`.
- Tools time out after 10 seconds. Provider cancellation, new user turns,
  immediate client barge-in, reconnect and close cancel outstanding tasks. A
  safety stop cancels sibling tools and prefetch while retaining its fixed line.
  A filler `turnComplete` does not cancel a pending tool or lose its cache.
- The instruction asks for a short “let me check” line and a `recent_memory` or
  `rewind_search` call for questions about earlier in this call or a past call.
- `Prefetch` consumes the cumulative streaming input transcript, requires four
  words, debounces 150 ms, and runs the existing router. With the router off or
  unsure, it falls back to the existing temporal/Rewind classifiers. The existing
  app startup already warms the router; no second warmup was added.
- Changed transcript queries replace pending work. Each new input turn cancels
  work, clears its text-only cache, and increments a version. Late results with
  an old version/query are discarded. Lookup has a 10-second deadline.
- Rewind cards arrive independently of voice. Both tools check the normalized
  exact-query cache first and wait up to 2.5 seconds for an in-flight match.
  A timeout cancels prefetch before the normal fallback. `rewind_search` only
  reuses a result sourced from Rewind, preserving its current-call scope.
- The prefetch retains only textual result data and retrieval time, never clips
  or image cards. It rechecks Google, Rewind and long-term-memory consent before
  using results. Recent-memory Rewind routing now also enforces TwelveLabs consent.
- Evidence is versioned, aged, labelled as past quoted evidence, and bounded to
  1,800 characters. It uses the existing conservative `publish_context` guard:
  no publication during an input question or generation. Output transcription,
  audio-only `modelTurn`, and tool calls all mark generation active. Pending
  evidence is tried again at `turnComplete`, or dropped on a new question.

## Official wire fields

Checked the [Live tools guide](https://ai.google.dev/gemini-api/docs/live-api/tools):
`behavior` belongs on each function declaration; `scheduling` belongs inside
`FunctionResponse.response`, alongside `result`. The guide specifies `WHEN_IDLE`
and `INTERRUPT`. The [Gemini 3.8 Live model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live)
confirms asynchronous calling support, but spells the interruption enum differently
in its migration prose. This implementation follows the tools guide's concrete
wire example; a real provider acceptance check remains outstanding.

The [WebSocket reference](https://ai.google.dev/api/live) says client content can
interrupt generation. The idle guard is retained, even though the model page's
prose describes less restrictive behavior for incomplete turns.

## Files

- `server/gemini_live.py`: async tools, safety/cancellation lifecycle, prompt,
  cache integration, early cards, and idle evidence publishing.
- `server/live_prefetch.py`: debouncing, router/fallback, turn versions, cache,
  timeout and cancellation.
- `server/recent_memory.py`: optional hit callback for the Live card and
  TwelveLabs consent enforcement; existing temporal scope selection is retained.
- `server/test_live_prefetch.py`: slow-tool audio regression, streaming lookup,
  card/cache/idle proof, debounce/now routing, query changes, cancellation,
  privacy revocation and concurrent safety-stop tests.
- `server/test_gemini_live.py`: expect the new scheduling field while retaining
  strict allowlisting of the tool response.
- `scripts/live_prefetch_probe.py`: standalone loopback timing probe and opt-in
  real Live / real Rewind synthetic-clip modes.
- `docs/results/live-tools-async.md` and appended `RESULT.md`: receipts.

## Verification

The new slow-tool test failed before the fix with a timeout waiting for client
audio while the tool was held open. It passes after task dispatch; the client
receives audio before that tool is released. Tests use a real loopback WebSocket
with synthetic provider packets. Socket checks required permitted loopback access
because the initial sandbox attempt could not bind a port.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_live_prefetch.py server/test_gemini_live.py server/test_live_streaming.py server/test_bg_context.py server/test_recent_memory.py --tb=short` - PASS (62 passed in 5.07s).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q` - PASS (`1272 passed, 2 warnings in 67.04s (0:01:07)`). Final-code proof: `/private/tmp/aeye-live-tools-async-pytest-recheck.log`. Both warnings are existing short HMAC fixture keys in identity tests.

An earlier full run passed with `1272 passed, 2 warnings in 68.07s`. The first run
including the final sibling-tool safety check reported `1 failed, 1271 passed,
2 warnings in 66.52s`: unchanged
`server/test_keyframes.py::test_sixty_second_scene_loop` exceeded its one-second
per-frame deadline. That test then passed alone (`1 passed in 4.24s`) without
code or timeout changes. The final full recheck and both earlier logs are retained
under `/private/tmp/aeye-live-tools-async-pytest*.log`.

Test: `node --test client-web/` - PASS (169 tests, 169 pass, 0 fail, 0 cancelled, 0 skipped; duration_ms 1312.613584).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/live_prefetch_probe.py` - PASS (real loopback socket, synthetic Live and Rewind).

Recorded standalone probe output, milliseconds from start of synthetic input:

```json
{"mid_reply_context":0,"mode":"loopback","rewind":"synthetic-adapter","searches":1,"status":"PASS","timings":{"cache_tool_ms":1.87,"card_ms":807.45,"context_ms":812.53,"fact_transcript_ms":810.27,"first_audio_ms":319.17,"search_start_ms":205.51,"tool_call_ms":808.31},"tools":1}
```

Proof: `/private/tmp/aeye-live-tools-async-probe.json`. This timing run preceded
the final sibling-tool safety cancellation addition; the final focused tests
include that addition. These are synthetic transport measurements, not provider
latency or physical speaker playback. The fact metric matches output text.

Test: `git diff --check` - PASS.

Optional Ruff check unavailable: the project Python has no `ruff` module. No
dependency was installed.

## Live probe and limits

`python scripts/live_prefetch_probe.py --live` exited 2 with:
`SKIP: GEMINI_API_KEY is not exported; no cloud call made.` No `.env` was read,
and the real cloud budget was not changed. The loopback probe uses a temporary
fake-only budget ledger because it makes no external calls.

With credentials already exported, run:

```sh
/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/live_prefetch_probe.py --live
/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/live_prefetch_probe.py --live --rewind --vision http://127.0.0.1:8001
```

The first uses real Gemini with synthetic memory. The second uploads a generated
mug clip, waits for indexing, queries real Rewind with local vision confirmation,
and attempts clip deletion in `finally`. No real user media is needed. The real
Rewind mode has not run here. The optional `--fact-text` regex defines the fact
transcript marker; it is not a semantic correctness or playback measurement.

Exact-query caching intentionally misses paraphrases and materially revised
partial transcripts. Those use the ordinary tool lookup. The conservative idle
guard may defer evidence until after Live's first reply; early cards and tool
responses remain available during the reply. No contract, client, router model,
deployment, merge or commit changes were made.

Finished: async Live tools and memory prefetch. Next: real provider and Rewind rehearsal with configured credentials. Suggested: GPT-6.1 / high.
