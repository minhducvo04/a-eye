# Family note — lead-reviewer handoff

Implemented and left uncommitted on base `a2eab5f`. No contracts changed, dependencies added, private planning text copied, or third-party messages sent.

## Behavior and boundaries

- The call offers **Task finished · Tell Dad?**. There is no default recipient. The user enters a name/relation and explicitly checks consent. Contacts and their generated delivery links are held in process-local, call-owned data. Removing a person revokes their pending notes, links and reply sessions.
- There was no structured completion log in this checkout. This package adds a bounded, user-confirmed task log (`task`, `detail`), selected in the composer. It does **not** infer successful repairs from model prose. The supported facts cover sink repair, alarm battery replacement and chair repair. The confirmation checkbox states that these are the facts of the task just completed.
- A deterministic composer produces three sentences: the fix, one confirmed detail and one task-specific question. An exact provenance check rejects any other text, extra sentence, media field, location or prior-task memory. No model writes the note; its contribution to Pictures sent and Cloud AI calls is zero. Existing call cloud accounting remains intact.
- The browser uses only an installed, on-device English speech voice for the note and parent reply. Send stays disabled until speech completes and the server receives the read-aloud acknowledgement. Exact spoken `send` or tapping Send authorizes delivery; other text cancels. Typed chat text is not a spoken confirmation. The server STT path intercepts pending-note confirmations before noise filtering or a brain call; empty transcription and transcription failure cancel.
- Send creates a same-server private delivery link. The user shares that link directly with the selected person; no automatic SMS, email or messenger transport is implemented. The UI says the note is ready and asks the user to share the private link, rather than claiming the person received it.
- A 256-bit random token in the URL fragment is exchanged once, through POST, for a restricted reply capability. Fragment tokens never appear in request URLs. The shell contains no note; the authenticated exchange supplies it. The parent may submit one text reply, then the capability is invalidated. Both capabilities expire at the original 24-hour deadline. Reloading after exchange requires a new delivery link.
- Parent endpoints have peer-based rate limits (60 requests/minute), bounded request sizes, exact field validation, same-origin checks, hashed token lookup and no-store responses. User endpoints use existing server authentication plus call ownership and owner rate limits. The existing server's trusted-loopback mode remains available for local use.
- Replies poll into the proof-strip area every two seconds and are read locally. The composer collapses on reply; a small Read reply aloud button remains.

## Verification

Tests were written first. Initial Python and Node runs failed because their implementation modules did not yet exist. Final results:

```text
Family note corpus: 20 accepted / 20 rejected - PASS
52 passed in 17.28s
Node: tests 143; pass 143; fail 0; cancelled 0; skipped 0
Family two-tab E2E: PASS; reply visible in 1.36s; single-use replay refused; Pictures sent: 0; Cloud AI calls: 0
Read aloud: native on-device speech completed for note and reply (physical hearing not measured).
git diff --check: PASS
```

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest server/test_family_note.py server/test_ws2.py server/test_proof_wall.py server/test_rt.py server/test_pipeline.py -q` - PASS (52 tests).

Test: `node --test client-web/` - PASS (143 tests).

Test: `uv run --no-project --with playwright python scripts/family_note_smoke.py` - PASS (two real Chromium tabs, local server; parent viewport 390 × 844).

Local server command:

```sh
env A_EYE_MOCK=1 LOCAL_ONLY=1 /Users/minhducvo/Projects/a-eye/.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8034 --no-access-log --no-proxy-headers
```

The browser run used fixture names/replies, blocked all non-local browser HTTP requests, exercised native speech without a speech stub, and used Send by tap. Spoken send/no/empty transcription were separately exercised through the actual WebSocket handler with a fixture STT adapter. The 40-case corpus uses 20 authored valid task/detail combinations and 20 handwritten invalid notes. Authenticated HTTP tests also cover unrelated owners, extra media payloads, read-aloud gating, cancellation, revoked contacts, one-time exchange/reply, expiry and rate limiting.

Screenshots inspected: `/private/tmp/family-note-user.png` (1280 × 720; compact proof strip and collapsed composer) and `/private/tmp/family-note-parent.png` (390 × 844). Only synthetic text/UI is present; no camera or audio artifact was saved. Screenshots remain outside the repository.

During verification, a real global timer kept the existing fake-browser test alive; it was changed to the page's timer API. The replay smoke initially navigated only the URL fragment, preserving the loaded page; it now leaves the page before replaying the original link. A missing close method in the new STT test double was corrected. Final runs above passed after those fixes.

## Files

- `server/family_note.py`, `server/test_family_note.py`: task-log composer, local consent store, delivery/reply capabilities, rules and API tests.
- `server/app.py`, `server/ws2.py`: router mount and server speech confirmation integration.
- `client-web/family-note.js`, `client-web/family-note.test.mjs`, `client-web/family-note.css`: composer, local speech, approval gate, polling and styles.
- `client-web/family-reply.html`, `client-web/family-reply.js`: private-token parent flow.
- `client-web/agent.html`, `client-web/agent.js`: call/proof-strip entry and browser transcript interception.
- `scripts/family_note_smoke.py`: reproducible two-tab local run.
- `docs/results/family-note.md`, `RESULT.md`: reviewer handoff.

## Limits for integration

Contacts are intentionally call-scoped and process-local, not persisted across server restarts. Outstanding links also stop working after restart; use one server process for this demo. The completion log is user-attested, not a vision verification result. Free-form note editing is not supported: change the selected fact and draft again. The read-aloud acknowledgement records client completion; it cannot prove a human heard the speaker. Missing local speech voices block Send rather than using cloud TTS. No physical phone, real microphone recognition, public deployment or remote-recipient transport was verified. At the original handoff, the application-wide Python suite and `make smoke` had not been run. The review-fix verification below supersedes the suite status; the lead integrator retains the merge/smoke gate.

## Independent review fixes — 2026-10-24

Both findings from `/Users/minhducvo/kyra-grok/aeye-review-note/RESULT.md` are fixed in the uncommitted working tree.

- **High:** note, automatic reply and Replay now use the call's `voice.speak(..., { localOnly: true })`. It records `spokenText`, requires an installed on-device English voice, and returns a completion promise. Browser recognition, VAD barge-in, hold-to-talk and server PCM capture are blocked during playback. Pending interim text and captured preroll are cleared before playback. Completion restores input; speech errors/cancellation reject the read-aloud acknowledgement so they cannot enable Send.
- **Low:** HTML responses carry `Content-Security-Policy: frame-ancestors 'none'` and `X-Frame-Options: DENY`. HTTP regressions cover `/`, `/agent.html` and `/family-reply.html`.

Tests were added and failed before the runtime fixes: voice regressions **29 passed / 2 failed** (command callback and PCM escaped during speech); HTML regressions **15 passed / 3 failed** (missing headers). Logs: `/private/tmp/family-voice-red.log`, `/private/tmp/family-headers-red.log`.

The call-page regression loads the actual agent module with browser adapters, polls a parent reply containing **stop**, injects both **stop** and **find a replacement part** through recognition, and observes no WebSocket `user_text` during speech. After completion, the same tool request produces `user_text`. The server-capture test observes zero PCM chunks during speech, then normal chunks afterward. Thus the tested local microphone paths cannot feed `start_text` during playback. These are synthetic input tests, not physical microphone/acoustic proof.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest server/test_family_note.py -q` - PASS (18 passed in 0.66s).
Test: `node --test client-web/voice.test.mjs client-web/family-note.test.mjs client-web/turn.test.mjs` - PASS (43 tests; pass 43; fail 0; cancelled 0; skipped 0).
Test: `node --test client-web/` - PASS (146 tests; pass 146; fail 0; cancelled 0; skipped 0).
Test: `/Users/minhducvo/.cache/uv/archive-v0/hcY8qU8TLWbqDTHje52_-/bin/python scripts/family_note_smoke.py http://127.0.0.1:8035` - PASS.

Real-run summary:
```text
Family two-tab E2E: PASS; reply visible in 1.46s; single-use replay refused; Pictures sent: 0; Cloud AI calls: 0
Read aloud: native on-device speech completed for note and reply (physical hearing not measured).
```

The browser used the local mock server (`A_EYE_MOCK=1 LOCAL_ONLY=1`), fixture text, and blocked non-local HTTP. It reused the existing smoke script. Logs: `/private/tmp/family-browser.log`, `/private/tmp/family-touched-python.log`, `/private/tmp/family-touched-node.log`, `/private/tmp/family-full-node.log`.

Changed files for this revision: `client-web/agent.js`, `client-web/family-note.js`, `client-web/voice.js`, `client-web/voice.test.mjs`, `client-web/turn.test.mjs`, `server/app.py`, `server/test_family_note.py`, this handoff and `RESULT.md`. No contracts or dependencies changed. No commit, merge or deployment.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q` - PASS (823 passed, 2 warnings in 68.01s). Log: `/private/tmp/family-full-python-unrestricted.log`.
Test: `git diff --check` - PASS.

The initial sandboxed full Python run reported 818 passed, 1 failed and 4 errors: every failure/error was a denied localhost socket bind. The complete rerun with socket access passed. The two remaining warnings concern existing short JWT keys in identity test fixtures. No tests were skipped or changed to hide these environment failures. The local browser server was stopped after verification.

Finished: both review fixes, full suites and native speech smoke. Next: integrator review and merge/smoke gate. Suggested: GPT-6.1 / high.
