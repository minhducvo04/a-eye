# Proof wall — rehearsal reliability follow-up to d248252

Working tree on `pkg/proof-wall`; changes remain **uncommitted**. AGENTS.md and CLAUDE.md read. No contract changes.

## Diagnosis and fix (2026-10-24)

The unchanged rehearsal reproduced the lead's **3/5 PASS, 0/5 SKIP, 2/5 FAIL**, including failures on trials 1 and 3. Both emitted a `dependency_error` with **ConnectTimeout**, then `turn_failed` about **5004 ms** after input. The exception came from Kokoro `/tts` while speaking the non-final “Let me think back.” `rewind.memory_turn` awaited that audio before doing the lookup, so the exception prevented both `find_item` and final `say` from being sent. The final message was never generated: this was not a dropped WebSocket message, a previous-trial race, the rehearsal's 45-second deadline, or a cold local talker. The exact-label text fixture bypasses talker inference and embeddings.

- `voice/kokoro.py`: retry a connection failure once, retaining the existing five-second timeout. Retry only `ConnectError` / `ConnectTimeout`, before a request reaches synthesis; never replay a read failure or partially received speech. Retry metadata is logged without text or media.
- `server/ws2.py`: isolate HTTP voice errors at the shared speech boundary, report `Voice unavailable (<exception class>)`, close the audio utterance, and continue generating the memory card and final text. Cancellation still propagates. Exhausted voice failures remain visible and do not qualify as full rehearsal success.
- `voice/adapter.py`: an intermediate live run exposed another failure path: the initial one-second health probe selected silence, and the negative result was cached for 60 seconds, skipping audio in all five trials. A subsequent direct health probe returned HTTP 200, `tts=True`, in **460 ms**. Read-only health requests now retry one transport failure, log its class, and do not cache exceptions as a health report. Explicit health responses retain the existing cache behavior. The old run did not log its exception class, so its exact transport error cannot be established retrospectively.
- `scripts/proof_wall_rehearsal.py`: picture verdicts depend only on their own count: exactly integer zero passes, a positive count fails with “expected 0 saved pictures,” and missing/invalid counts fail as unavailable. A separate trial verdict names recall, safety, audio or counter failures. Final text, `done`, and completed nonempty **final-answer audio** are required for a full PASS; hearing only the preface is insufficient. Missing audio stays SKIP; explicit voice errors fail. Timeout/cancellation is named, and a timed-out socket is not reused for another question. Medians include sample counts.

## Follow-up verification

Python for all commands: `/Users/minhducvo/Projects/a-eye/.venv/bin/python`.

Failing tests first (no GPU required):

- `python -m pytest -q server/test_proof_wall.py -k memory_final`: **2 failed, 5 deselected** before the fix. Injected `ConnectTimeout` / `ReadTimeout` during the preface reproduced the missing card/final. Both pass after the fix and receive final-answer audio from the recovered synthetic service.
- `python -m pytest -q voice/test_kokoro.py -k retry_connection`: **2 failed, 4 deselected** before the connection retry; both pass afterward.
- `python -m pytest -q voice/test_kokoro.py -k transient_health`: **2 failed, 8 deselected** before the health fix; both pass afterward.
- Reporting regressions cover zero/positive/unknown/boolean picture counts, missing final text, failed turns, preface-only audio, and visible voice errors. Their initial collection failed because the new reporting helpers did not yet exist; this is not claimed as behavioral fail-before proof.

Test: `python -m pytest -q scripts/test_proof_wall_rehearsal.py server/test_proof_wall.py voice/test_kokoro.py` - PASS (**16 passed**, before the additional bounded-retry and health regressions).

Test: `python -m pytest -q server/test_ws2.py server/test_rewind.py server/test_memory.py server/test_cloud_meter.py voice/test_private.py voice/test_home_first.py voice/test_kokoro.py scripts/test_proof_wall_rehearsal.py server/test_proof_wall.py` - **89 passed; one loopback-listener test blocked by sandbox PermissionError**. Reran only `server/test_cloud_meter.py::test_real_websocket_send_boundary` outside the sandbox: **1 passed**.

Test: `python -m pytest -q voice/test_kokoro.py -k bounded` - PASS (**2 passed**); connection retries stop after two attempts, and read failures are never retried.

Test: `python -m pytest -q voice/test_kokoro.py voice/test_private.py voice/test_home_first.py` - PASS (**23 passed**) after the health fix, including cancellation, voice selection and Private cloud guards.

### Live evidence

Every invocation uses the real configured home services, production HTTP/WS handlers, `LOCAL_ONLY=1`, and temporary text-only memory; no camera or media files. Internet stays connected. First audio means the first nonempty PCM message received by the WS client (it can be the recall preface); answer means receipt of final text, not completion of playback. These runs do not exercise STT, camera vision, physical speakers or local talker inference.

Intermediate results are retained rather than discarded:

- Before changes: **3/5 PASS, 0/5 SKIP, 2/5 FAIL** (trials 1 and 3; TTS ConnectTimeout).
- After speech retry/isolation, before the health fix: **5/5 PASS**, then **0/5 PASS, 5/5 SKIP, 0/5 FAIL**. Logs: `/private/tmp/proof-wall-followup-run1.log`, `/private/tmp/proof-wall-followup-run2.log`. The skipped run led to the health fix above.

Final three runs, each `python scripts/proof_wall_rehearsal.py`, exit **0**, on the final runtime code:

```text
Run 1: REHEARSAL: 5/5 PASS, 0/5 SKIP (missing local audio), 0/5 FAIL; text fixture removed
Run 2: REHEARSAL: 5/5 PASS, 0/5 SKIP (missing local audio), 0/5 FAIL; text fixture removed
Run 3: REHEARSAL: 5/5 PASS, 0/5 SKIP (missing local audio), 0/5 FAIL; text fixture removed
```

| Run | Recall first-audio median | Recall final-answer median | Safety first-audio median | Safety final-answer median | All first-audio median | All final-answer median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 520 ms | 738 ms | 366 ms | 4 ms | 455 ms | 268 ms |
| 2 | 414 ms | 827 ms | 393 ms | 4 ms | 398 ms | 365 ms |
| 3 | 461 ms | 698 ms | 498 ms | 4 ms | 480 ms | 312 ms |

Each question's median uses **5/5** observations; “All” uses **10/10** per run. In all **15/15 trials**, both cloud counters and the picture count were exactly zero. Each of the **30 questions** produced final text and completed final-answer audio. No full-suite, microphone-input or physical-device claim is made.

Logs: `/private/tmp/proof-wall-final-run1.log`, `/private/tmp/proof-wall-final-run2.log`, `/private/tmp/proof-wall-final-run3.log`. These contain timings and allowlisted event metadata, not media or credentials. Run 1 recovered two TTS ConnectTimeouts; run 2 recovered one; run 3 recovered one health-probe ConnectTimeout. These prove both recovery paths were exercised live. The underlying link can still time out; a recovered TTS connection adds about five seconds to that turn, which the medians can hide. Persistent failures are bounded, reported, and preserve text; this does not claim to repair the network.

Test: `git diff --check` - PASS.

Follow-up files: `voice/kokoro.py`, `voice/adapter.py`, `voice/test_kokoro.py`, `server/ws2.py`, `server/test_proof_wall.py`, `scripts/proof_wall_rehearsal.py`, `scripts/test_proof_wall_rehearsal.py`, `docs/results/proof-wall.md`, `RESULT.md`. No dependency or contract changes. Left uncommitted; no merge, push or deployment.

## Previous cloud-boundary receipt (implemented in d248252)

The following records the prior work and its original verification; it is not the status of this follow-up.

### Cloud boundary follow-up to 67ffd3e

Implemented in the working tree; changes are **uncommitted**. Read AGENTS.md and CLAUDE.md. No contract changes.

## Demo claim and setup

**Keep the internet connected.** The phone reaches the home GPU PC over the private link; the presenter's laptop stays a light client. The claim is “nothing goes to any cloud AI,” not offline operation. The old WAN-unplugged setup and connectivity-probe evidence from 67ffd3e are superseded.

1. Keep the configured home GPU, vision, STT and Kokoro services reachable. `OLLAMA_URL`, `BOX_URL`, `VISION_URL` and `ROUTER_OLLAMA_URL` identify trusted home services. No model download or network setting change is performed by this work.
2. Run the server with `LOCAL_ONLY=1` and select Private in Settings: local brain, server STT/TTS, Rewind off. Keep existing authentication and the phone's trusted HTTPS/private-link setup. Do not copy real tokens into receipts.
3. Start a fresh call. Keep **Cloud AI calls: 0** and **Bytes to cloud: 0** visible while trying recall, a normal local answer and the safety refusal. Changing settings within the same call does not erase earlier cloud traffic.
4. Run `python scripts/proof_wall_rehearsal.py` using the configured home services. Each of its five Private trials checks both counters are exactly zero. Internet stays connected.

## What changed

- Replaced Online/Offline with **Cloud AI calls: N** and **Bytes to cloud: N**. Removed the TCP probe to `1.1.1.1` entirely.
- Count at the shared HTTPX/HTTPX2 single-request send boundary and outgoing `websockets` client message boundary. Anthropic SDK retries, hosted OpenAI-compatible requests, Cartesia HTTP/WebSocket messages and TwelveLabs requests/uploads pass through these boundaries. New destinations using these clients are automatically counted; there is no provider-name allowlist to update.
- A mutable, locked counter belongs to the call context. Turn/expert/voice/Rewind tasks and `asyncio.to_thread` inherit it. Repeated hello/reconnect for the same retained owner/session preserves totals; a new call starts at zero. Rewind HTTP actions and voice samples bind to the authenticated call.
- `/api/proof?session_id=...` uses existing authentication and owner identity. An absent/unknown/other-owner session returns unknown counters, never an invented zero. The browser sends its owner header and refreshes every two seconds. Counter failures display unknown.
- **Pictures saved**, actual **Brain** metadata and **Stopped by code** behavior are preserved. Pictures still counts image-named files under this checkout's `data/`, without opening content or following symlinks; unreadable is unknown.

## Counting semantics and limits

- Calls count outgoing request attempts, including failed attempts, retries, redirects and WebSocket messages (including cancellation). They do not mean completed model responses.
- Bytes count outgoing HTTP body / WebSocket message payload bytes, including serialized JSON and multipart upload framing. Buffered bodies count at send; streamed bodies count as consumed. Headers, response bytes, WebSocket framing, TLS and IP overhead are excluded. The strip tooltip states this scope. No payload or credential is retained by the meter.
- Loopback, RFC1918 LAN, link-local, IPv6 private ranges, `100.64.0.0/10` tailnet addresses, local/tailnet hostnames and explicitly configured home-service hosts are excluded. Unknown/public hosts count; OpenAI-compatible base URLs are not automatically exempted.
- To avoid silently missing a newly added provider, these shared boundaries conservatively count **other public HTTP/WebSocket requests made within the call too**. Thus nonzero is an outgoing public request indicator, not an AI billing total.
- This is server call instrumentation, not an OS packet monitor. Browser-native cloud speech and unrelated server/startup traffic are outside its scope; use Private/server STT for this demonstration. A future provider using a different networking library must integrate its send boundary. Operator-configured home endpoints are trusted; this does not validate their downstream behavior.
- The retained registry bounds session history. An evicted or restarted-server session is unknown. Physical phone/home-GPU proof and local audio readiness remain separate from the synthetic browser smoke.

## Verification

Python: `/Users/minhducvo/Projects/a-eye/.venv/bin/python` (no worktree venv).

Failing test first:

`python -m pytest -q server/test_proof_wall.py -k private_and_cloud_turn_counters`

**1 failed, 4 deselected**: the counter module did not exist. After implementation, the same regression runs real turn routing against an intercepted HTTP provider: Private calls/bytes stay zero; the cloud turn produces one request and positive bytes.

Transport checks caught the installed Anthropic SDK's use of **HTTPX2**, which is now instrumented alongside HTTPX. Tests cover SDK retry counts, exact payload sizes, streamed bodies, unknown providers, local exclusions, concurrent calls, actual loopback WebSocket sends, owner isolation and repeated-hello retention. No paid cloud request was made.

Test: `python -m pytest -q server/test_cloud_meter.py server/test_proof_wall.py server/test_ws2.py server/test_rewind.py server/test_rewind_activity.py server/test_llm.py server/test_brain_openai_compat.py voice/test_cartesia_ws.py voice/test_voice.py voice/test_home_first.py voice/test_private.py` - PASS (**121 passed in 16.70s**).

Test: `python -m pytest -q server/test_cloud_meter.py server/test_proof_wall.py server/test_auth_fixes.py` - PASS (**71 passed in 1.20s**) after final middleware scope/transport cleanup.

Test: `node --test client-web/` - PASS (**138 passed, 0 failed**, 859 ms). Includes current session query, both numeric labels, unknown on HTTP failure, and unchanged brain/safety handler checks.

Test: `python scripts/proof_wall_rehearsal.py` - **cloud counters PASS in all five trials; audio SKIP** (exit 1, correctly retained):

```text
trial 1 Cloud AI calls: 0; Bytes to cloud: 0; PASS
trial 2 Cloud AI calls: 0; Bytes to cloud: 0; PASS
trial 3 Cloud AI calls: 0; Bytes to cloud: 0; PASS
trial 4 Cloud AI calls: 0; Bytes to cloud: 0; PASS
trial 5 Cloud AI calls: 0; Bytes to cloud: 0; PASS
REHEARSAL: 0/5 PASS, 5/5 SKIP (missing local audio), 0/5 FAIL; text fixture removed
```

Recall and safety text checks passed in all five; Pictures saved was zero. Kokoro was unavailable from this environment, so no first-audio timing or full audio success is claimed. The rehearsal uses production HTTP/WS handlers, temporary text-only memory, no camera, and real configured local service selection. These recall/refusal trials do not establish GPU inference quality; the normal local/cloud turn distinction is covered by the provider regression.

Test: real Chromium browser smoke against an authenticated loopback mock server, synthetic camera/mic, `LOCAL_ONLY=1`, temporary memory - PASS. Command: `env A_EYE_TOKEN=<temporary fixture> uv run --offline --no-project --with playwright python scripts/browser_smoke.py http://127.0.0.1:<temporary port>`. Checks include both zero counters after call creation and the unchanged picture count. Summary: **BROWSER SMOKE PASS**, `frames_sent: 2`, `problems: []`, longest find-card task **0 ms**. Temporary server stopped; fixture removed. This is browser wiring proof, not physical-device/GPU proof.

Test: `git diff --check` - PASS.

## Changed files

- `server/cloud_meter.py`, `server/test_cloud_meter.py`: shared send-boundary counters and regression checks.
- `server/ws2.py`, `server/app.py`, `server/rewind_api.py`: call-context binding and authenticated HTTP attribution.
- `server/proof_wall.py`, `server/test_proof_wall.py`: owner-scoped proof API, removed connectivity probe, Private/cloud turn and retention checks.
- `client-web/agent.html`, `client-web/agent.js`, `client-web/turn.test.mjs`: two labels, owner-authenticated polling, voice-sample attribution and UI checks.
- `scripts/proof_wall_rehearsal.py`, `scripts/browser_smoke.py`: zero-counter assertions.
- `docs/results/proof-wall.md`, `RESULT.md`: current receipt and limits.

No commit, merge, push, deploy, auth relaxation, or internet disconnection.
