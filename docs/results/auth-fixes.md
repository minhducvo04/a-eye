# Auth and Rewind fixes

Implemented the five findings in `aeye-review-auth/REVIEW.md` and findings 1–2 in
`aeye-review-rewind/REVIEW.md`. Changes are uncommitted for the lead reviewer.

## Changes

- With no credentials, API and call sockets accept only `127.0.0.1` / `::1` unless
  `A_EYE_OPEN=1`. Startup logs explicitly warn about either loopback-only or open access.
- Pair codes use eight readable uppercase letters/digits. Five failed joins per address
  block further joins for 60 seconds; five misses against a code retire it across addresses.
  The address table is bounded. Codes and secrets expire after five minutes.
- Pair links/QRs contain a random, single-use secret bound to the code, never the master
  token. The secret admits only a matching camera hello; it cannot authenticate API calls,
  v1 sockets, normal call sockets, or a second join. `ws2.py` has only a three-line routing hook.
- Token calls receive random, server-signed owner capabilities. The browser shares that
  capability between its socket and memory/Rewind HTTP requests, and rotates it for a new
  call. Knowing the shared token, another session ID, or another owner's identifier cannot
  find or forget that owner's memory. Verified Access identities remain unchanged.
- Transport logs redact `pair`, `join`, and `owner`, as well as `token`, including encoded
  parameter names. The standalone browser runner also redacts these values.
- Rewind upload/index creation/task failures and indexing timeout mark clips failed and
  say recording search is not available right now, rather than indexing or not found.

Changed implementation: `server/{auth,app,pairing,rewind,logs,ws2}.py`,
`client-web/{agent,caregiver,call-owner,memory,pair,qr,rewind}.js`.
Updated contract schema/types/examples/changelog together for alphanumeric pair codes;
wire `v:2` and legacy numeric syntax remain accepted. Updated relevant tests, `conftest.py`,
and `scripts/browser_smoke.py`.

## Verification

- Before implementation, the new Python regressions produced **9 failures** covering all
  server findings and the four Rewind failure cases. The token-copying browser regression
  also failed before its fix. Final security regressions: **10 passed**.
- Test: `make test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` — **PASS**:
  **658 Python tests**, **137 JavaScript tests**. Two existing Python deprecation warnings.
  An initial restricted run could not bind four test sockets; the permitted rerun passed.
- Test: `make test-web` — **PASS, 138 tests**, after the QR/caregiver review fixes.
- Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_access.py`
  — **PASS, 27 tests**, after the final standalone smoke-runner correction.
- Test: `make browser-smoke URL=http://127.0.0.1:61947` (synthetic token supplied in the
  environment) — **PASS** against a mock server bound to a dynamically allocated local
  port: `frames_sent: 2`, `problems: []`, longest find-card task **0 ms**. Real Chromium
  exercised camera/mic, replies, settings scrolling, visible QR, token-free phone join and
  disconnect, and disabled shared-token caregiver controls. Synthetic devices only.
- Test: `git diff --check` — **PASS**.

Independent candidate review found a QR capacity regression and misleading token caregiver
controls. Both were addressed: the long-URL QR regression failed before the capacity fix;
version-6 QR matrices matched an independent encoder at 115 and 134 bytes. The final browser
smoke checked caregiver behavior. The revised tree still awaits the lead's review.

## Limits for integration

- Pairing, rate limits, and owner signing keys are process-local. Restart invalidates owner
  capabilities; use the existing single-process deployment. QR capacity is now 134 bytes.
- Shared-token owners are deliberately temporary and separate per call. Reloading loses
  the browser capability; older token clients without it receive isolated request/socket
  owners. Cross-call caregiver settings require personal Access sign-in; the token UI says so.
- TwelveLabs failure behavior used controlled failures; no live cloud outage, Cloudflare
  deployment, physical phone, or production rollout was exercised. No new dependencies,
  commits, pushes, or deployment.
