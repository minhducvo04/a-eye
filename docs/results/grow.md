# Growth guide — lead review

Implemented in the working tree; no commit, merge or deployment. API routes and contracts are unchanged.

## Praise-check review fix (2026-10-24)

- Replaced raw substring checks with NFKC-normalized, lowercase word tokens and bounded patterns allowing zero to three intervening words between claim tokens. Punctuation and apostrophe variants are token separators; role words retain whole-word matching.
- Rewind/memory captions now use the checked speech text, closing the review's caption bypass.
- Home completion already returns only the code-built numeric comparison (or silence). New turn-level tests prove both paths and repeated completion never invoke the model or append free praise.
- Added filler-word, punctuation, casing, streamed-token and caption regressions, with factual-language controls. Before the fix: **9 failed, 55 passed in 0.86s**. Evidence: `/private/tmp/grow-review-before.log`.
- Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest server/test_product_rules.py server/test_growth.py server/test_rewind.py -q` — PASS (**86 passed in 1.82s**). Evidence: `/private/tmp/grow-review-targeted.log`.
- Test: `node --test client-web/` — PASS (**151 tests, 151 pass, 0 fail, 0 skipped**). Evidence: `/private/tmp/grow-review-node.log`.
- Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q` with localhost access — PASS (**912 passed, 2 warnings in 81.30s (0:01:21)**). Warnings are the existing short HMAC fixture-key warnings. Evidence: `/private/tmp/grow-review-python-localhost.log`.
- The first full Python run was sandbox-blocked: **2 failed, 906 passed, 2 warnings, 4 errors in 40.44s**, all six failures/errors from denied localhost binds. The full rerun above resolved them without code changes or skips. Evidence: `/private/tmp/grow-review-python.log`.
- Test: `git diff --check` — PASS.

Changed files for this review fix: `server/product_rules.py`, `server/rewind.py`, `server/test_product_rules.py`, `docs/results/grow.md`, `RESULT.md`. Changes are uncommitted. The finite claim vocabulary and three-word gap limit are not a general language classifier; completion does not rely on that detector because its text is built by code.

## Behavior

- Product copy now supports independent practice. The sharing flow is **Want to show someone?** and uses the explicitly added contact. Before a contact exists, the UI shows only People settings, hides the sharing controls, disables drafting and never opens the composer on completion. The API rejects a draft without a consenting contact. Removing the last contact disables sharing again.
- `server/growth.py` stores numeric progress per authenticated identity and home task. Each run records UTC date, tries, elapsed minutes, hints, safety-stop flag and completion. Persistence uses the existing local-memory Fernet cipher in `growth.json`. No images, audio, transcripts or contact details enter this log.
- Completed runs select levels 1, 2, then 3. Level 1 gives full steps; level 2 gives one short hint and waits for user input; level 3 gives no ordinary guidance. The shutoff/no-flow instruction and every trusted valve check remain active, as do coded hazard stops. Quiet turns return without a model call. Explicitly selecting a finished task starts another run.
- **Walk me through it** restores full steps for the current task, without bypassing a check. **Forget my progress** deletes that user's progress across tasks and resets guidance. A generation check prevents an older active guide from restoring forgotten entries; other users' logs remain intact.
- Completion emits at most one factual comparison, using the previous and current completed rows. No comparison is spoken without evidence of fewer tries or hints. Repeated completion input does not repeat feedback.
- `server/product_rules.py` contains input detector words and a forbidden output phrase list. Speech, captions and drawing labels pass a code check. Streamed captions now wait for checked speech chunks rather than exposing raw model tokens. Neutral and serious family complaints get fixed lines before routing to a model; the serious line offers a trusted adult or local helpline and emergency services for immediate danger.

## Measurement

The existing rehearsal entry point runs three consecutive sink calls for one fixture identity. The fixture log is encrypted with a temporary in-process key. It uses real localhost HTTP/WebSocket, configured local Kokoro TTS/STT, and explicit checker TEST MODE. The note and reply remain synthetic and local.

| Run | Guide level | Hints used | Tries | Safety stop |
|---|---:|---:|---:|---|
| 1 | 1 | 11 | 4 | true |
| 2 | 2 | 6 | 4 | true |
| 3 | 3 | 0 | 4 | true |

A hint is one spoken instructional sentence. Full steps can contain an action and a camera instruction; short hints contain one sentence. Intro, mandatory valve/safety lines, completion feedback and sharing are excluded. Tries start at one and increase for explicit retry requests or failed valve checks. All three runs deliberately exercise normal-mode refusal, an open simulated valve, and a hazard that revokes an armed pass. Elapsed minutes measure time between task turns, not physical work verified by a camera.

```text
GROWTH HINTS: [11, 6, 0]; levels 1 -> 2 -> 3; decreasing=True
GROWTH FLOW REHEARSAL: 3/3 PASS, 0/3 FAIL; checker TEST MODE; no real-photo claim
```

Each run also passed Pictures saved 0, Pictures sent 0, Cloud AI calls 0 and bytes-to-cloud 0 checks. Evidence: `/private/tmp/grow-rehearsal-final.log`.

## Checks

The initial growth regressions failed before implementation (4 missing-module failures). Focused regressions then covered encrypted reload, no plaintext fallback, user/task isolation, deletion, fading/override, retained safety gates, fixed complaint responses, blocked output including split stream tokens, factual one-time feedback, contact gating, and authenticated WebSocket ownership.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q` — PASS (893 passed, 2 warnings in 70.99s). The warnings are the existing short HMAC test-key warnings. Evidence: `/private/tmp/grow-python-final.log`.

Test: `node --test client-web/` — PASS (151 tests, 151 pass, 0 fail, 0 skipped). Evidence: `/private/tmp/grow-node.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/dad_flow_rehearsal.py` — PASS (3/3; hints 11, 6, 0). Evidence: `/private/tmp/grow-rehearsal-final.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest server/test_growth.py server/test_product_rules.py -q` — PASS (45 passed in 0.85s). This closing check follows a one-line fix preserving the selected task when forgetting progress; the full suite above ran immediately before that fix. Evidence: `/private/tmp/grow-closing.log`.

Test: `git diff --check` — PASS.

The first sandboxed full Python run had 883 passed, two caption-stream expectation failures and six denied localhost-bind cases (four errors, two failures). Caption ordering was corrected; the raw-token coalescing test now requires a checked speech boundary before any caption appears. The final full run uses localhost access. No test was skipped to hide a failure.

## Limits

- Set `A_EYE_MEMORY_KEY` for encrypted progress across server restarts. Without a key, progress stays in process memory only; it is never written as plaintext. This follows the existing memory configuration without inventing or persisting a new key.
- User identity follows existing authentication: stable verified sign-in, or the existing shared-token owner capability. A new capability is a different identity; this change does not merge people who share a token. The unconfigured trusted-loopback mode is one local identity.
- Fading applies to the deterministic home tasks: sink, hinge and read-only breaker. Completing the guide is not proof of a physical repair. Real valve-photo accuracy and physical microphone behavior were not verified here.
- Complaint routing and blocked-language detection are finite code word lists, not a comprehensive language classifier. The listed words remain only where required for input recognition/output rejection, stable internal names, API paths or existing evidence paths. Human-authored contact names/replies are not generated praise.
- This task ran the full Node suite and server rehearsal, not a new visual browser or iPhone review. The iPhone handoff describes the new behavior; native UI implementation remains its owner's work.

## Files

- Server: `server/growth.py`, `server/product_rules.py`, `server/agent.py`, `server/ws2.py`, `server/packs/home.py`, `server/packs/__init__.py`.
- Server tests: `server/test_growth.py`, `server/test_product_rules.py`, `server/test_home_pack.py`, `server/test_dad_flow.py`, `server/test_family_note.py`, `server/test_pipeline.py`.
- Browser: `client-web/agent.html`, `agent.js`, `agent.css`, `family-note.js`, `family-note.css`, `family-reply.html`, `family-reply.js`; tests in `family-note.test.mjs`, `turn.test.mjs`, `voice.test.mjs`.
- Rehearsal/copy fixtures: `scripts/dad_flow_rehearsal.py`, `scripts/dad_flow_browser_smoke.py`, `scripts/family_note_smoke.py`.
- Handoffs: `docs/ios-dad-handoff.md`, `docs/results/grow.md`, `docs/results/dad-flow.md`, `docs/results/family-note.md`, `docs/results/home-fix.md`, `RESULT.md`.

Finished: growth behavior and measured rehearsal. Next: lead review. Suggested: GPT-6.1 / high.
