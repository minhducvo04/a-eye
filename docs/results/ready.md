# Readiness and hosted open-model brain

Implemented in the working tree; no commit. `server/ws2.py` is untouched.

- `make ready` prints PASS/FAIL/SKIP with fixes and exits nonzero on failure. It checks server health, status features, configured vision/box health, required Ollama tags, phone pairing, the remembered-phone page, device mock turn, simulator build, Access presence, Tailscale and key presence. No credential, URL, subprocess output or provider error is printed. Tailscale is read-only. Run from the same environment as the server; this worktree does not inherit another running server's credentials.
- `BRAIN=openai_compat` selects the new adapter through the app factory for v1 and v2. Talker/planner share the configured talker model; expert admission works without an Anthropic key. Streams use SSE, with 30-second talker and 45-second expert total deadlines. Private mode, LOCAL_ONLY and the Claude switch block hosted calls and select the local adapter.
- Hosted requests are text-only; crops are omitted. Provider web search and tool execution are unsupported. Costs are unknown, not reported as free. No hosted provider was contacted; the team still needs to configure its base URL, key and model IDs and validate that provider.

## Verification

Python: `$HOME/Projects/a-eye/.venv/bin/python` (`$PY` below).

Test: `$PY -m pytest -q server/test_brain_openai_compat.py server/test_brain_local.py server/test_expert.py server/test_llm.py` - PASS (66 tests).
Test: `$PY -m pytest -q scripts/test_ready.py server/test_backbone.py server/test_pipeline.py server/test_pairing.py server/test_phone_remember.py` - initial run: 53 passed, one localhost bind blocked by sandbox; the 48 server tests passed.
Test: `$PY -m pytest -q scripts/test_ready.py` outside sandbox - PASS (6 tests, including a real localhost fake WebSocket server).
Test: `$PY -m pytest -q server/test_brain_openai_compat.py server/test_tools.py` - PASS (29 tests; overlaps the first group). Hosted HTTP tests use an in-process fake provider via HTTPX MockTransport, with no network calls.
Test: `make smoke PY=$PY` outside sandbox - PASS (`SMOKE PASS`; SAFETY → IDENTIFY → LOCATE → GUIDE → AWAIT; one target overlay).
Test: `git diff --check` - PASS.

Test: `make ready PY=$PY` outside sandbox - PASS (exit 0). Actual table outcomes:

| Checks | Result |
|---|---|
| Server :8000 health; vision health; box health; required Ollama models; remembered-phone page | PASS |
| Tailscale installed and logged in | PASS |
| `python -m device.fake_turn --mock` | PASS |
| Vision Pro simulator build, signing disabled, temporary derived data | PASS |
| `/api/status` features; `/ws2` pair_request | SKIP: running server requires authentication; no credential in this environment |
| CF_ACCESS_TEAM_DOMAIN and cloud API key presence | SKIP: no values in this environment |

The first sandboxed readiness attempt failed because local sockets/build access were restricted; the authorized outside-sandbox run supersedes it. Live pairing and status authentication remain unverified. No physical phone, Pi or Vision Pro proof is claimed. Full app suite was not run; checks target changed adapter, app wiring, expert, privacy, pairing and readiness boundaries.

Changed files: `Makefile`, `.env.example`, `scripts/ready.py`, `scripts/test_ready.py`, `server/brain_openai_compat.py`, `server/test_brain_openai_compat.py`, `server/brain_local.py`, `server/app.py`, `server/expert.py`, `docs/model-choices.md`, this report, `RESULT.md`.
