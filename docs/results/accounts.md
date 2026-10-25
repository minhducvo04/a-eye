# Accounts result — 2026-10-24

Implemented in this worktree and left uncommitted. Google verification is tested with synthetic RSA-signed
tokens; a real Google account login remains an owner setup check. Guest sign-in and My data passed a real
local HTTPS Chromium run. No deployment, console changes, real media, or real credentials were used.

## Behavior

- `/signin.html`: Google Identity Services popup and one-tap Guest. Google tokens are verified on the server
  against Google's HTTPS JWKS: RS256 signature, issuer, `aud = GOOGLE_CLIENT_ID`, expiry, and the browser's
  signed nonce challenge. Identity is `google:` plus SHA-256 of stable `sub`, then uses the existing memory
  owner mapping. Email/name changes do not change identity; neither is stored.
- Signed session cookies last 30 days for Google and 24 hours for Guest. They are Secure, HttpOnly,
  SameSite=Lax, path `/`. Only hashes of random session IDs are stored in SQLite. Session revocation and
  guest expiry survive restart. Browser mutations and account WebSockets require the same HTTPS origin.
- Guest IDs are random. Existing limits enforce at most 10 admitted actions/minute (or the configured lower
  limit) and 100 total admitted actions per guest. These are admission units, including call setup and
  relevant API actions, not just spoken sentences. Total usage survives restart. Existing IP/socket and
  cloud budget limits still apply. A fresh guest is a new identity, so this is a demo quota, not a billing system.
- Shared token, verified Cloudflare Access, configured open mode, and loopback behavior remain available.
  Explicit legacy credentials take precedence over the new cookie. Invalid account cookies fail closed.
  Open-mode `local` has no personal-data entitlement; choose Guest to get an isolated owner.
- `/my-data.html` provides a personal view, ZIP export, deletion, and sign-out. Agent Settings links to both
  pages. `/api/me`, `/api/me/export`, and `DELETE /api/me` derive the owner from verified authentication;
  callers cannot choose another owner. Personal-data operations bypass usage quotas and cloud spending
  gates. Google public-key retrieval also remains available when the cloud budget is exhausted.
- Export calls the existing `scripts/export_data.py` implementation with only the owner's retained calls
  and known privacy provenance. Its seven NDJSON files and manifest keep the existing privacy exclusions.
  `my-data.json` adds the owner's stored memory metadata, settings, tags, growth, family notes/contacts,
  file inventory, and runtime call metadata. Media, embeddings, and contact delivery links are excluded.
  No complete historical call archive exists, so missing history is not invented. Private calls stay out of
  the schema export; the separate personal JSON is intended only for the authenticated person.
- Deletion revokes every session for that owner, ends active account calls, removes owned memory/crops,
  growth, family notes/contacts/delivery state, retained calls, and account rows. Stale memory writers are
  invalidated. Cloud Rewind deletion uses the existing deletion client. A cloud failure returns HTTP 202
  and keeps only the owner/video retry manifest plus a deletion marker, blocks a new account session for
  that owner, and retries. HTTP 200 means those tracked deletions succeeded.
- Guest expiry is enforced immediately on authentication and active sockets. A background sweep runs every
  second while the server is running and resumes at restart; cleanup also waits for active-call shutdown
  and cloud deletion attempts. An offline server cannot physically erase files until it restarts. Failed
  cloud deletion remains pending rather than being reported as complete.

Accounts use the existing single-worker deployment. SQLite is stored beside the memory root as
`accounts.sqlite3` with mode 0600; no Google ID token, raw Google subject, name, email, or raw session ID is
persisted. Keep this directory private and persistent across restarts. Existing open/legacy data is not
automatically linked to a Google identity. LOCAL_ONLY disables Google sign-in and keeps Guest available.
New accounts require HTTPS and SESSION_SECRET; leaving these unset preserves existing access paths.

## Owner: Google Cloud setup

1. Open [Google Cloud Console](https://console.cloud.google.com/), select the project's private Google Cloud
   project (or create one). Open **Google Auth Platform**. If prompted, click **Get started**; complete
   **Branding** with app name `A-eye`, your support/contact email, and the app's homepage/privacy details.
   Add the real parent domain under authorized domains where required. Save.
2. Under **Audience**, use **External** for accounts outside your organization; use Internal only for an
   eligible organization-only deployment. Keep the app in Testing for the demo and add the intended team
   and judge Google accounts as test users where the console requires it. Publishing is an owner decision.
3. Open **Clients → Create client → Web application**. Name it `A-eye web`. Under **Authorized JavaScript
   origins**, add the exact HTTPS origin serving the app, for example `https://aeye.example.com` (replace
   with your real host). Include a non-default port if used; omit paths, query strings, and wildcards.
4. Leave redirect URIs empty for this implementation: it uses a popup JavaScript callback and a JSON POST
   to `/auth/google`. That route is not a browser redirect callback. Click **Create** and copy the client ID.
   The browser token flow does not use a client secret.
5. Set `GOOGLE_CLIENT_ID` to that client ID in the server's private deployment environment. Generate at least
   32 random bytes with a secret manager and set their encoded value as `SESSION_SECRET` (at least 32 bytes
   as supplied). Keep it stable across restarts; changing it signs everyone out. Blank placeholders are in
   `.env.example`. Do not put either a real session secret or an OAuth client secret in source control.
6. Serve the app over HTTPS with the reverse proxy preserving the public Host. Keep one application worker.
   If Cloudflare Access protects the whole hostname, its edge login still occurs before A-eye sign-in;
   adding Google here does not change edge policy. Configure the intended edge access yourself. Do not
   remove protection from the backend origin. LOCAL_ONLY must be unset/0 to use Google.
7. Restart the configured server and open `https://YOUR_HOST/signin.html`. Select Google, then use the
   rendered Google button. Confirm `/my-data.html` shows account kind `google`; reload to confirm the session
   persists, export, sign out, sign back in, and delete a disposable test account. Also verify Guest on the
   deployment. These live Google/deployment checks have not been performed in this worktree.

Google's [client setup guide](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid),
[popup/nonce reference](https://developers.google.com/identity/gsi/web/reference/js-reference), and
[server verification guide](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
describe the provider configuration and token checks. No Google API access scopes beyond sign-in are needed.

## iOS follow-up — documented, not built

### Google

1. Create an **iOS** OAuth client for the app's actual bundle ID. Add Google's `GoogleSignIn-iOS` Swift package,
   configure `GIDClientID` with the iOS client ID, and register its reversed-client-ID URL scheme.
2. Set `GIDServerClientID` to the web client ID used by `GOOGLE_CLIENT_ID` so backend tokens target the same
   audience. Present the SDK sign-in flow and obtain its ID token; do not send profile email as identity.
3. Implement a dedicated native backend exchange with a server-issued nonce bound to the login attempt,
   verify the same Google claims, and issue a revocable app session stored in Keychain. The current web
   `/auth/google` route requires browser Origin, a signed challenge cookie, and nonce header; it is not a
   drop-in native endpoint. Keep those web checks intact. Use the SDK's supported nonce binding for the
   selected version; if it lacks one, design and verify an authorization-code/PKCE flow before shipping.
4. Wire cancellation, sign-out, revocation, and My data. Test that web/native share the stable provider
   subject and that a different user cannot reuse the session. Never link accounts by email alone.

See Google's [iOS setup](https://developers.google.com/identity/sign-in/ios/start-integrating) and
[sign-in implementation](https://developers.google.com/identity/sign-in/ios/sign-in).

### Apple

1. Enable **Sign in with Apple** for the app's explicit App ID and add that capability to the Xcode target;
   update signing/provisioning as needed.
2. Use `AuthenticationServices` / `ASAuthorizationAppleIDProvider` with a server-bound random nonce and state.
   Send the returned identity token and authorization code to a new Apple-specific backend exchange.
3. Verify Apple's signature using its public keys, issuer `https://appleid.apple.com`, exact configured
   native bundle-ID audience (or Services ID for a separate web flow), expiry and nonce. Namespace and hash
   Apple's stable subject separately from Google. Do not merge based on email or private relay addresses.
4. Configure the required Apple server credentials for code exchange/revocation, issue a revocable session,
   store it in Keychain, and connect logout/account deletion and credential-state handling. Test revoked,
   expired, forged, and wrong-audience tokens plus cross-user access before enabling it.

See Apple's [Xcode setup](https://developer.apple.com/documentation/xcode/configuring-sign-in-with-apple)
and [environment guide](https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple).
No Apple verifier, native session exchange, Apple developer configuration, or iOS build is included tonight.

## Files and verification

New implementation: `server/accounts.py`; `client-web/account-api.js`, `accounts.js`, `accounts.css`,
`signin.html`, `my-data.html`. Integration: `server/auth.py`, `app.py`, `rewind.py`, `limits.py`, `memory.py`,
`growth.py`, `cloud_meter.py`, and `client-web/agent.html`. Configuration: `.env.example`, `conftest.py`.
Evidence: `server/test_accounts.py`, `client-web/accounts.test.mjs`, `scripts/accounts_smoke.py`, this report,
and the accounts addendum in `RESULT.md`. No contract or dependency changes.

Tests were written before implementation: the initial account tests failed against absent routes. Final
coverage includes forged Google/session signatures, wrong issuer/audience/nonce, expiry, stable subject,
guest expiry without another visit, restart-persistent quota, cross-user view/export/delete isolation,
active-call shutdown, revoked writers, pending cloud deletion/recovery, and exhausted-budget data access.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_accounts.py` — PASS
(`15 passed in 1.22s`).

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q contracts device server vision voice market eval boxsvc router scripts --tb=short` — FAIL
(`1 failed, 1103 passed, 2 warnings in 61.63s (0:01:01)`).

The sole failure is `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`:
`FileNotFoundError` for `vision/fixtures/gemini_payment_required.json`. `git cat-file -e
HEAD:vision/fixtures/gemini_payment_required.json` confirms that fixture is absent from the committed tree;
the committed test already references it. The vision owner's missing fixture was not changed. Both warnings
are existing short synthetic HMAC keys in identity tests. This is not a green full-suite result.

Test: `node --test client-web/` — PASS
(`tests 161; pass 161; fail 0; cancelled 0; skipped 0; todo 0; duration_ms 1279.330916`).

Test: `uv run --offline --no-project --with playwright python scripts/accounts_smoke.py --python $HOME/Projects/a-eye/.venv/bin/python` — PASS
(`ACCOUNTS HTTPS BROWSER PASS: Guest, Secure/HttpOnly cookie, isolated data, ZIP export, delete, other user preserved`).
The smoke script starts a temporary local HTTPS server and two isolated browser contexts with synthetic
media and temporary storage, then stops it. Screenshot: `/tmp/aeye-accounts-smoke.png` (local evidence,
not checked in). Google login was not exercised. No physical iOS-device proof is claimed.

Test: `git diff --check` — PASS.

Owner follow-up: configure the Google client and secret, perform the live sign-in check, and ask the vision
owner to restore the missing fixture. Integrator review/merge/deployment remain outstanding; all edits are
uncommitted.
