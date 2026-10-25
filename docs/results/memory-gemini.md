# Memory captions through Gemini

Implemented in this worktree; changes remain uncommitted. Gemini live check: **HTTP 402**.

## Behavior

- `Writer.observe()` uses Gemini for the current frame's caption and tagged-object boxes only when
  `privacy.google_allowed()` is true. Private, LOCAL_ONLY, Google-off, and missing call consent block it.
  The existing Gemini adapter checks consent again immediately before sending and accounts for cloud usage.
- Gemini failure/abstention retains the incoming scene caption and local grounding. Production memory
  grounding now calls Ollama directly, independent of `VISION_BACKEND`, so a global Gemini setting cannot
  redirect that fallback. Existing injected vision clients remain supported.
- `worth_noting()` can caption the last RAM-only still with Gemini in an explicitly consenting call context;
  otherwise it keeps the existing Qwen burst request. It asks only what/where, never infers movement from one
  still. The existing HTTP `/api/memory/event` endpoint has no per-call consent context and remains local.
- Storage and encryption code is unchanged: notes/tags/crops stay in the local store, encrypted with Fernet
  when A_EYE_MEMORY_KEY is configured, with the existing filesystem-only fallback otherwise. No stored crop,
  history, or embedding is uploaded. Google receives only the inference request (current downscaled image,
  prompt, requested object labels). Person checks still use the original scene and local detector; crop limits,
  retention, deletion, and capture consent checks are unchanged.
- No contracts, settings UI, vision adapters, or provider defaults were changed. This adds an inference call
  per observed memory frame when consent permits it; it does not claim measured label improvement.

## Tests first

`server/test_memory_gemini.py` was written before implementation. Initial result:
**2 failed, 4 passed in 0.23s**. Both positive Gemini controls failed because no Gemini request happened;
Private/Google-off/LOCAL_ONLY refusal cases passed.

Final focused checks cover Private/Google-off/LOCAL_ONLY vetoes for both notes and event captions, positive
Gemini controls, encrypted note/crop round trips, local grounding despite a global Gemini backend, and retaining
local captions on Gemini failure. Existing memory tests cover storage, person refusal, deletion and ownership.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_memory_gemini.py server/test_memory.py server/test_memory_capture.py` - PASS (48 passed in 0.94s).

## Live provider check and comparison

Ran a single real `generateContent` request through `make`, using the main checkout's existing Makefile to load
its `.env` (the worktree has no `.env`). The key and response body were never printed. Probe:
`make -s -C $HOME/Projects/a-eye -f /private/tmp/memory-gemini-probe.mk memory-gemini-probe`.
The temporary recipe runs `/private/tmp/memory-gemini-probe.py`; its success branch invokes the worktree's
`scripts/gemini_vision_check.py`. The initial sandbox attempt could not connect; the network-enabled run returned:

```text
HTTP 402
```

The benchmark was not run because the key check failed. No Gemini hits, median or p95 are claimed.
Qwen3.5's existing baseline is **15/16**, documented in [backend benchmarks](../backend-benchmarks.md);
it was not rerun here. That report gives p50/p90, not p95.

## Full suite

Initial `make -k test PY=$HOME/Projects/a-eye/.venv/bin/python`:
**3 failed, 995 passed, 2 warnings, 4 errors in 41.24s**; browser **151 passed, 0 failed**.
Six failures/errors were sandbox loopback binds; one was the absent fixture
`vision/fixtures/gemini_payment_required.json`. Temporarily supplied that fixture byte-for-byte from the main checkout
(no vision code change), then reran the full suite with loopback permission after the final test additions.

Test: `make -k test PY=$HOME/Projects/a-eye/.venv/bin/python` - PASS with the supplied fixture and loopback permission.

```text
1006 passed, 2 warnings in 64.27s (0:01:04)
tests 151; pass 151; fail 0; cancelled 0; skipped 0; todo 0
```

The borrowed fixture was removed after verification to keep this change within the memory package.
A fresh full run in this worktree requires that same main-checkout fixture; it is not included in the diff.
`git diff --check`: PASS.

Logs: `/private/tmp/memory-gemini-suite.log` (initial), `/private/tmp/memory-gemini-suite-final.log` (final).

## Files

- `server/memory.py`: consent-gated caption/tag enrichment and explicit local grounding.
- `server/memory_capture.py`: consent-gated still caption with local Qwen fallback.
- `server/test_memory_gemini.py`: regression tests.
- `docs/results/memory-gemini.md`, `RESULT.md`: handoff and verification.
