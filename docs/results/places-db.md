# Places-db result

Implemented in the `places-db` worktree on base `2943a48`; changes are uncommitted.

## Delivered

- Small owner-scoped thing/placement graph with retained history, newest-location lookup, component-prefix
  contents lookup and last observed move. Preferred homes do not manufacture current placements.
- One Store interface: existing local behavior by default; `STORE=spacetime` uses the official HTTP API,
  typed reducers and caller-filtered views. Personal remote fields are encrypted before HTTP with a
  server-derived per-user key; ciphertext is bound to its owner, row and field.
- `find_item`, `tag_item`, HTTP memory routes, vision observations and consent-enabled recent memory use
  the selected store. Remote records contain allowlisted text metadata, never crops, frames or embeddings.
- Private/LOCAL_ONLY checks on every remote request, including deletes; fail-closed owner/key checks,
  sanitized errors, no redirects/retries. Failed recent cleanup cannot interrupt call teardown.
- [Module handoff](../spacetime-places.md): exact private tables, typed reducers, `ctx.sender` views,
  example rows, setup, limitations and the client-held-key plan.

## Files changed

| Files | Purpose |
| --- | --- |
| `server/memory_places.py` | Shared graph and recent-entry storage methods |
| `server/memory_storage.py` | Store selection, encrypted SpacetimeDB HTTP adapter |
| `server/memory.py` | Store factory, graph observations, find, retention and owner/consent wiring |
| `server/memory_api.py`, `server/rewind_tools.py` | Optional explicit `place_path` for tags |
| `server/memory_capture.py` | Preserve capture provenance |
| `server/recent_memory.py` | Consent-gated storage, temporal bounds and teardown |
| `server/test_memory_places.py` | Fake HTTP backend, local/remote graph, privacy/encryption and cleanup tests |
| `server/places_probe.py`, `Makefile` | Make-loaded synthetic write/read/delete probe |
| `docs/spacetime-places.md`, `docs/results/places-db.md`, `RESULT.md` | Handoff and verification receipts |

Read `AGENTS.md`, `docs/data-export.md`, `schemas/export-v1.json` and the existing memory modules before
implementation. Contracts and the v1 offline export schema were not changed. No dependencies were added
to the application and no module was published.

## Verification

Tests were written before the implementation; the first run failed on the missing storage module.
The Private-mode teardown regression also failed before its fix. Fake-backend tests cover both owner
isolation cases, ciphertext substitution, private-mode request blocking, media exclusion, history ordering,
prefix matching, consent, temporal bounds, retention and probe cleanup after a possibly committed failure.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_memory_places.py server/test_memory.py server/test_memory_capture.py server/test_recent_memory.py` - PASS (`85 passed in 1.72s`).

Test: `make -k test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - FAIL overall (exit 2), with these final summary lines:

```text
FAILED vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared
1 failed, 1128 passed, 2 warnings in 60.56s (0:01:00)
ℹ tests 158
ℹ pass 158
ℹ fail 0
ℹ skipped 0
ℹ duration_ms 1273.985542
```

The sole Python failure is `FileNotFoundError` for
`vision/fixtures/gemini_payment_required.json`, referenced by `vision/test_gemini.py:85`.
That fixture is absent from this checkout and is not tracked by Git. No vision files were changed; the
vision owner needs to supply the expected fixture. The two warnings concern existing short synthetic JWT
test keys. All 158 web tests passed.

The initial restricted run could not bind the loopback sockets used by ten tests. The full suite was then
run with loopback networking permitted; `-k` lets Make also run the web suite after a Python failure.

Test: `make places-live-check PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - SKIP:

```text
SpacetimeDB env: SPACETIMEDB_URI=unset, SPACETIMEDB_MODULE=unset, SPACETIMEDB_TOKEN=unset
SpacetimeDB live: SKIP (configuration incomplete; no network request)
```

Make loaded the environment. No credential values were printed. There was no real SpacetimeDB write/read
or cleanup proof because the connection variables were absent. The probe's write/read/delete behavior was
exercised against the fake HTTP backend, including cleanup after a failed response.

Test: `node /private/tmp/aeye-places-module-check/package/bin/tsc --noEmit --strict --skipLibCheck --target ES2022 --module ESNext --moduleResolution Bundler /private/tmp/aeye-places-module-check/index.ts` - PASS (exit 0).
The input was the exact TypeScript module block from the handoff, using TypeScript 5.9.3 and official
SpacetimeDB SDK 2.13.0 in a temporary directory. This is a type check, not deployed-module runtime proof.

Test: `git diff --check` - PASS.

## Limits and next integration

One configured SpacetimeDB caller token is bound to one application owner. Multiple users require separate
tokens/server instances until per-user authentication is integrated. Encryption keys are server-held today,
not end-to-end. The local store retains its existing optional-encryption behavior.

The teammate must integrate the documented module, then configure the environment and run the live probe.
Production owner-only access is specified and fake-tested but has not been verified against a deployed
module. No automatic migration, export extension or key rotation was added. Whole-owner reads and
last-write-wins documents assume one writer per owner. Recent entries expire lazily; when privacy/network
blocks teardown cleanup, the remote copy remains until a later successful expiry/Forget write.
