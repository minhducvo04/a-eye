# Auth and Rewind fixes

## Second independent auth review — 2026-10-24

Outcome: **fixed**, left uncommitted for the lead reviewer. Source assignment:
`$HOME/kyra-grok/aeye-review-auth2/RESULT.md`. Base commit:
`39201cd60389830a31ce3a15e9dec304a541d570`.

### Changes and boundaries

- `server/auth.py`: unconfigured loopback is local only without any of the seven
  proxy headers: `CF-Connecting-IP`, `X-Forwarded-For`, `Forwarded`, `X-Real-IP`,
  `Tailscale-User-Login`, `Tailscale-User-Name`, `CF-Ray`. Presence, even empty or
  loopback-valued, removes local trust. Header values never authorize requests.
  Explicit open mode and valid configured credentials retain their existing behavior.
  The shared gate protects API, v1/v2 call sockets, and the unconfigured QR join path;
  a tunnel caller cannot bypass the camera secret using code-only pairing.
- `server/pairing.py`: both QR and authenticated code-only joins use one address helper.
  Loopback proxy peers use CF's visitor address, then the trimmed first XFF hop,
  falling back to the TCP peer. Non-loopback peers ignore forwarding headers.
  Per-code retirement and existing single-use/expiry rules remain intact.
- `Makefile`: `phone` prints the token prerequisite first and exits unsuccessfully
  without a token or both Access settings, including when only `A_EYE_OPEN=1` is set.
  It prints no tunnel commands on refusal and honors `SERVER_PORT`. Server/mock
  launches disable Uvicorn proxy-header rewriting to preserve the actual TCP peer.
- `conftest.py`: retained the direct-local TestClient default; clarified its scope.
  `server/test_auth_fixes.py` now explicitly tests proxied IPv4/IPv6 loopback and uses
  `client=('192.0.2.10', 1234)` for token-configured, token-free QR camera joins,
  including API denial, wrong-role denial and replay rejection.
- `client-web/README.md`, `docs/api.md`, `docs/home-setup.md`: put credentials before
  Serve/Funnel/Cloudflare instructions and document proxy refusal and custom-launch flags.
  `RESULT.md` carries the current handoff; this report preserves the earlier work below.

### Failing tests first

Before implementation, `server/test_auth_fixes.py` reported **38 failed, 12 passed**:
28 proxy-header cases, one tunnel camera-join bypass, four shared-bucket cases, and
five phone-command cases failed. The new proxied cases also reproduce the test-harness
coverage finding. The explicitly remote QR control already passed before the fix;
that case adds the missing coverage rather than claiming a separate runtime failure.
The additional Uvicorn launch checks then reported **2 failed, 50 deselected** before
the launch flags changed. All these regressions are included in the passing suite.

### Verification of the final working tree

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_auth_fixes.py server/test_access.py server/test_pairing.py --tb=short` - PASS (**83 passed in 2.30s**).

Test: `make test PY=$HOME/Projects/a-eye/.venv/bin/python` - PASS:

```text
700 passed, 2 warnings in 58.65s
ℹ tests 138
ℹ pass 138
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
```

The warnings are existing short synthetic HMAC keys in `server/test_identity.py`.
The initial restricted run reported 696 passed and four socket-bind setup errors;
the permitted full rerun above passed, including those four tests.

Test: live Uvicorn HTTP probes with `--no-proxy-headers`, mock mode and an allocated
loopback socket - PASS:

```text
LIVE AUTH PASS: http://127.0.0.1:51329; direct loopback 200; 14 proxy-header requests 401
```

Test: `make -e browser-smoke URL=http://127.0.0.1:51334` - PASS. The temporary mock
server used a dynamically allocated loopback socket, `--no-proxy-headers`,
`LOCAL_ONLY=1`, a random token supplied in memory, and temporary memory storage.
Playwright used the existing offline cache and synthetic camera/microphone devices.
The protected server also returned 401 without the token and 200 with a valid token
plus proxy headers. Browser summary:

```text
longest task after the find card: 0 ms
{"frames_sent": 2, "problems": []}
BROWSER SMOKE PASS
```

Chromium exercised camera/mic, a reply, settings, displayed QR, secret-only camera join,
disconnect, and token caregiver restrictions. Both task servers were stopped.

Test: `git diff --check` - PASS.

An independent read-only boundary investigation and a fresh candidate review were
completed. Candidate review found no concrete surviving bypass or workflow regression;
it did not run tests. The execution results above are the builder's verification.

### Remaining limits

No public tunnel, live Cloudflare Access login, or physical phone was exercised.
The defense depends on at least one listed proxy marker reaching the app; a proxy
stripping every marker is outside this requested policy. Custom Uvicorn launchers
must also use `--no-proxy-headers` for TCP-peer-based rate-limit selection. Pairing
limits remain process-local. No dependencies, contracts, deployment, commits or pushes
were added. The lead reviewer owns integration.

## Earlier auth and Rewind review (historical verification)

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
- Test: `make test PY=$HOME/Projects/a-eye/.venv/bin/python` — **PASS**:
  **658 Python tests**, **137 JavaScript tests**. Two existing Python deprecation warnings.
  An initial restricted run could not bind four test sockets; the permitted rerun passed.
- Test: `make test-web` — **PASS, 138 tests**, after the QR/caregiver review fixes.
- Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_access.py`
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
