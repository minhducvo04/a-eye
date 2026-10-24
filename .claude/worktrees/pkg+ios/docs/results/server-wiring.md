# server-wiring

Implemented market queries and contextual text replies without changing contracts.

Files changed:
- `server/steps.py`: build market queries from the session board's specs; route ordinary text with board, headers, state, item and target context after existing safety checks.
- `server/app.py`: run market search and injectable LLM completion in worker threads; send market results and a fit summary; contain LLM failures with a manual-page fallback.
- `server/test_wiring.py`: five WebSocket cases covering fixture offers, budget filtering, empty and unverified results, unchanged safety/active steps, injected LLM context, worker-thread execution, refusal bypass and provider failure recovery. Every received message is schema-validated; new tests use no network.
- `RESULT.md`: observed results and limitations.

Test: .venv/bin/python -m pytest -q server - FAIL (1 failed, 57 passed in 1.12s)
Test: .venv/bin/python -m pytest -q - FAIL (1 failed, 215 passed in 1.60s)
Test: git diff --check - PASS (no output)

All five new tests pass in both suite runs. The only failure is the pre-existing `server/test_ws.py::test_unwired_hooks[market-fields0]`, which explicitly requires market to return `not wired yet`. This contradicts the requested market behavior. That file is outside this package's authorized ownership; permission to remove only the obsolete market parameter is pending. The other three unwired hooks remain unchanged.

Limitations: only the board is treated as an owned part. Prices and compatibility follow the existing market module and source environment setting. No live provider/network calls were made. LLM canned, empty, malformed or failed responses use a fixed manual-page reply. Market provider failures return an internal error without changing the step.

Changes are unstaged. Nothing was pushed or published.

Integrator: removed the obsolete market case from test_ws.py test_unwired_hooks (market is now wired). Suite green after.
