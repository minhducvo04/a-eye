# cf-access result

Implemented Cloudflare Access authentication in the existing shared HTTP/WebSocket check. No callers, contracts, deployment settings or global settings changed. No push or publication. Files remain unstaged.

## Changed files

- `server/auth.py`: RS256-only Access validation through header/cookie, required expiry/issuer/audience, 30-second leeway, existing constant-time token alternative, fail-closed partial configuration, injectable cert fetcher/monotonic clock, kid cache with a 60-second refresh floor and hourly refresh for known keys. Fetch failures clear cached keys and emit one dependency event per failed attempt. Only hashed email and fixed reason codes enter auth events.
- `server/logs.py`: allowlist additions only (`user`, `reason`).
- `server/test_access.py`: 27 offline regressions, generated RSA keys, real ASGI HTTP/WebSocket boundaries including phone pairing, forged tokens, configuration combinations, cooldown/failure logging, Node execution of socket URL/4401 handlers, smoke URL/redaction helpers.
- `client-web/agent.js`: omit absent token, stop 4401 retries and render sign-in/reload control.
- `client-web/pair.js`: sign-in/reload control on 4401; existing conditional pairing-token handling preserved.
- `scripts/browser_smoke.py`: read token from environment, encode page query, redact reported URLs/errors.
- `requirements.txt`: `pyjwt[crypto]` for RSA JWT verification.
- `.env.example`: Access team and audience settings.
- `docs/api.md`: Cloudflare Access auth note.
- `RESULT.md`: this handoff and test evidence.

`Makefile` already exports environment variables to `browser-smoke`; no change needed. To respect ownership, the new Node-executed regressions live in `server/test_access.py`, leaving existing `.test.mjs` files untouched.

## Verification

Test: .venv/bin/python -m pytest -q server/test_access.py - PASS (27 passed in 1.41s)
Test: node --test client-web/ - PASS (95 tests, 95 passed, 0 failed)
Test: .venv/bin/python -m pytest -q - FAIL (1 failed, 453 passed in 16.00s)
Test: git diff --check - PASS (no whitespace errors)

Full-suite failure: `server/test_rewind.py::test_voice_path_through_ws2`, line 257, finds a clip with no frames after receiving `track`. Reproduced the same assertion failure using `HEAD:server/auth.py` loaded into the auth module before running that isolated test (1 failed in 1.03s). This is outside the owned files and was not changed. Initial pre-implementation regressions failed (missing Access cache implementation and the empty `token=` URL).

## Limits and integration notes

- Full suite is not green because of the existing Rewind failure above; its owner must resolve it.
- No live Cloudflare tenant/login or Chromium smoke session was run. Playwright is not installed in this worktree's venv. Cert fetches in the regression suite use injected local data; no real credentials or media were used.
- The existing `server/app.py` startup event says `auth_disabled` whenever `A_EYE_TOKEN` is absent, including Access-only deployments. Its HTTP middleware also emits an additional reasonless `auth_rejected` after the new reason-bearing event. Both are outside this package's ownership; authentication itself remains enforced.
- A WebSocket closed before acceptance is an HTTP upgrade rejection on real ASGI servers. Browsers can surface that as 1006 rather than the application 4401 used by TestClient. The requested 4401 handler is verified; public-site expiry/redirect behavior still needs a real Access/browser check.
- The synchronous shared check preserves all callers. A cold/rotating-key lookup can occupy the server event loop during the HTTP fetch (httpx timeout 3 seconds). Cache refresh throttling is per process; a newly rotated kid may wait up to 60 seconds after the last fetch.
- Email PIN and email allowlist must be configured in Cloudflare Access by the deployment owner. No configuration was published by this task.

Integrator review (Claude, second provider): RS256 only with the header alg checked, kid looked up in cached JWKS with a 60 s refetch floor, aud, iss and exp required, fail closed when Access is set without a token or certs are unavailable; logs carry only reason codes and a 12-hex email hash. Added: the page now sends the token on /api/voices and /api/voice_sample (they returned 401 on any token server). Real runs: browser smoke against a token server (test token): PASS with A_EYE_TOKEN in env, FAIL without; token appears 0 times in smoke output and server log. Full suite 454 passed (one earlier order-dependent rewind failure did not reproduce; passes alone on main and branch). Not run: a real Cloudflare Access login.
