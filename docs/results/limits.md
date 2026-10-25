# Demo limits and daily cloud budget

Changes are uncommitted. No contracts, client code, credentials, or real media were changed.

## Behavior and configuration

| Environment variable | Default | Enforcement |
| --- | --- | --- |
| `TURNS_PER_MINUTE` | `30` | Rolling 60-second window, independently per owner and per IP |
| `CALLS_PER_IP` | `3` | Concurrent sockets per visitor IP (paired camera sockets also count) |
| `MAX_OPEN_SOCKETS` | `20` | All application WebSockets, including unauthenticated QR joins |
| `DAILY_CLOUD_CAP_USD` | `5` | Shared estimated daily cloud spend; latched off until the next UTC day |
| `CLOUD_BUDGET_PATH` | `/tmp/aeye-cloud-budget-<uid>.sqlite3` | SQLite ledger containing only UTC dates, dollar totals, and cutoff flags |

The socket gate releases capacity in `finally`, including failed auth, early returns, and disconnects. It uses `pairing_address`, so loopback tunnel peers use `cf-connecting-ip` or the first `x-forwarded-for` address; direct remote peers cannot choose their bucket with those headers. Keep Uvicorn's existing `--no-proxy-headers` setting. Verified Access/token owners share their turn budget across IPs; open callers use their IP. Paired microphone traffic inherits the owning call's owner bucket.

Turns include final text, the first PCM chunk through its final marker, hello/setup, v1 photos/confirmations/market requests, and POST/PUT `/api/` requests. Frames and control messages remain usable. Denied audio stays denied for the whole utterance. HTTP refusal is 429; socket capacity refusal sends the fixed error then closes with 4429. All refusals use: “Please pause a moment and try again; the demo is busy.” Logs contain fixed metadata only, never user text or addresses.

Cloud admission is checked at the existing HTTPX and WebSocket send boundaries, including retries and calls without a per-call meter. Request charges are supplemented with Claude tokens/cache/search use, TwelveLabs reported token usage, and prepaid Gemini Live minutes (including idle connections). Per-call estimates accumulate in `Meter.estimated_usd`; existing public metric schemas are unchanged. Separately hosted vision counters contribute estimated request cost.

| Estimate setting | Default USD |
| --- | --- |
| `CLOUD_REQUEST_USD` | `0.01` per public HTTP request / non-Gemini WebSocket send |
| `TWELVELABS_REQUEST_USD` | `0.10` per TwelveLabs request |
| `GEMINI_LIVE_USD_PER_MINUTE` | `0.10` per started connection-minute |
| `CLOUD_INPUT_USD_PER_MILLION` | `5` |
| `CLOUD_OUTPUT_USD_PER_MILLION` | `25` |
| `CLOUD_CACHE_USD_PER_MILLION` | `0.5` |
| `CLOUD_SEARCH_USD` | `0.01` per reported search |

These are configurable budgeting weights, not verified provider prices. Cache creation uses 1.25 times the input weight. SQLite serializes admission across threads/processes using the same ledger and preserves the cutoff across server restarts. Use a durable `CLOUD_BUDGET_PATH` if `/tmp` may be cleared; do not delete the ledger during the demo.

The cap feeds the existing Private/local provider checks. Existing v2 calls close Live, cancel active turns/experts/cloud voice, select local/browser speech, and receive one spoken notice: “Today's cloud budget is used up. I'll keep helping in local mode.” V1 announces it on the next message. New turns retain the local/canned paths. Rewind DELETE cleanup and Cloudflare Access signing-key reads remain available after cutoff.

## Scope and limits

- Socket/turn admission is process-local: run the demo with one Uvicorn worker. The spend ledger is shared only by processes using the same filesystem path.
- An admitted request and already-running provider work can take the estimate above the threshold. This stops subsequent admissions; it cannot guarantee an exact provider invoice. Cancelled streams without final usage still retain the request estimate.
- Public requests are deliberately estimated broadly; retries and some free/read-only provider calls can overcount. A colocated vision service sharing the ledger can also be conservatively counted twice through its returned counters.
- Speech uses the existing local/browser fallback; physical-device audibility and actual paid-provider billing were not tested.
- No new dependencies, contract changes, commits, push, or deployment.

## Changed files

`server/limits.py`, `server/app.py`, `server/pairing.py`: admission and owner/IP binding.

`server/cloud_meter.py`, `server/privacy.py`, `server/llm.py`, `server/gemini_live.py`, `server/rewind.py`, `server/cloud_vision.py`, `server/ws2.py`: estimated spend, cloud cutoff, local fallback and notice.

`server/test_limits.py`, `conftest.py`: regression tests and isolated test ledgers/context. Only the synthetic TestClient host is treated as local by the test fixture.

`docs/results/limits.md`, `RESULT.md`: results and handoff.

## Verification

Tests were written before implementation: the initial focused run failed with four missing limiter/budget API failures; the socket-capacity probe waited for the missing rejection and was interrupted. The implemented tests exercise the observable refusal and local-success paths.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_limits.py server/test_pairing.py server/test_cloud_meter.py server/test_gemini_live.py` - PASS (`51 passed in 7.94s`). Synthetic loopback WebSockets prove idle Live cutoff and transport accounting without a paid call.

Test: `node --test client-web/` - PASS (`tests 158; pass 158; fail 0; cancelled 0; skipped 0; todo 0`).

Test: `env VISION_BACKEND=fake LOCAL_ONLY=1 BOX_URL=http://127.0.0.1:9 OLLAMA_URL=http://127.0.0.1:9 ROUTER_OLLAMA_URL=http://127.0.0.1:9 CLOUD_BUDGET_PATH=/tmp/aeye-limits-smoke.sqlite3 $HOME/Projects/a-eye/.venv/bin/python scripts/smoke.py` - PASS (`steps=['SAFETY', 'IDENTIFY', 'LOCATE', 'GUIDE', 'AWAIT'] target_overlays=1`; `SMOKE PASS`). Real Uvicorn processes, synthetic frame, no cloud.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q` - FAIL (`1 failed, 1045 passed, 2 warnings in 93.48s (0:01:33)`) on the final code. All 12 new limits regressions passed. The sole failure is `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: missing `vision/fixtures/gemini_payment_required.json`. `git ls-tree -r HEAD vision/fixtures` returns no fixture. This belongs to the vision package and was left unchanged.

Test: `git diff --check` - PASS.
