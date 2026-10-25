# Context agent — 2026-10-24

Implemented in `pkg/context-agent`; changes remain uncommitted. The synthetic call rehearsal opens with
“How was the trip to SF?”, does not repeat it on the next call, and deletes it on “don't bring that up”.
This is application-handler proof with synthetic talker output, not a real Google or physical-device result.

## What runs

`server/context_agent.py` gathers at hello and on classic user turns. It ranks by matching question words,
then recency, and selects at most eight short entries in a context block under 1,800 characters. Entries
are quoted as evidence, with their source; previous observations are explicitly not current facts.

| Input | Store and boundary |
| --- | --- |
| Camera | Existing scene caption, only with camera on, matching frame sequence and frame age ≤1.5 seconds. No additional image request. |
| Recent memory | Existing call RAM log, restricted to the last 120 seconds; scene, user and helper provenance retained. |
| Places | Latest placements from the selected local or Spacetime store. A preferred home is not treated as an observation. |
| Growth | Existing task log: task name, completion, tries and hints. No completion is inferred. |
| Long-term notes/plans | Consent-enabled memory notes and dated first-person plans. No crops, embeddings or full records enter the prompt. |

Classic turns receive the block in their system prompt. Gemini Live receives it in setup and typed turns;
before the first audio chunk of an utterance it receives a context-only `clientContent` update with
`turnComplete:false`. Transcripts refresh the ranking locally, and `gather_context(question)` returns
question-specific context through the existing validated tool path. The Live system instruction requests
that tool before spoken answers. Actual Google tool selection and use of this context have not been measured.
The [Live wire reference](https://ai.google.dev/api/live) documents client-content history updates and warns
that mixing realtime and client content has no ordering guarantee; this addition needs a live rehearsal
before claiming provider timing or camera-context parity.

The debug Connection section shows `used: camera, memory, places, growth` when those sources contributed
to the selected block. Recent and long-term notes share the `memory` label. Empty/unavailable cases show
`none`/`unknown`, rather than claiming all stores were used. The authenticated, owner-scoped `/api/proof`
response carries only source names in `context_sources`. Existing turn event ordering is unchanged.

## Plans, consent and deletion

- Extraction is local rules only, from final classic user text or completed Live input transcripts, never
  helper speech. Supported dates: tomorrow, weekday names, this/next weekend, and ISO calendar dates.
  Undated, tentative, negative and third-person statements abstain. Dates use the server's local calendar;
  a day ends at the following midnight, and a weekend ends after Sunday. No timezone is inferred from voice.
- Remembering and both existing memory consents must be enabled. `A_EYE_MEMORY_KEY` must provide the existing
  Fernet encryption. Without it, plan persistence is skipped; there is no plaintext fallback. No key/settings
  were created for the user. Rehearsals generate a temporary key and delete the scratch store afterward.
- Plans keep the user's bounded original words, recording time, planned date and follow-up time. They use
  the owner-scoped local encrypted log even when places/other notes use Spacetime. Plan retention is measured
  from the follow-up time, capped at seven days or the shorter configured retention window, so an advance
  plan is not discarded before its date. Identical text/date submissions are deduplicated.
- Only General calls offer a proactive opener. Home/PC/engineering and other pack openings retain precedence.
  A plan is due only after its day ends and within seven days. The server atomically marks it before delivery;
  a failed/disconnected delivery is not retried. Claims are serialized within one server process.
- Cloud context requires the relevant Google or Claude switch (the hosted open-model talker uses Claude's
  switch), plus memory consent for stored notes. Private/LOCAL_ONLY blocks cloud context and cloud openers
  without consuming a plan. Local context remains usable in Private mode. Store failures omit the source.
- “Don't bring that up” deletes the last offered plan from the local log, clears current context/history and
  recent notes, and returns a fixed acknowledgment. In Live it also closes the provider session so an old
  setup/tool note is not reused; the existing reconnect/fallback policy applies. This cannot erase data
  already sent to a provider. No deletion request is sent to another service.

## Rehearse

```sh
/Users/minhducvo/Projects/a-eye/.venv/bin/python -m scripts.context_agent_rehearsal
```

The script seeds “I'm going to SF Saturday” on the Friday preceding the last completed Saturday, starts
actual `/ws2` ASGI sessions with Private mode on, checks the exact opener, deletes it through user text,
and verifies a separate claimed plan does not repeat on a later call. The last turn must finish successfully.
All memory and budget files use a temporary directory. No camera, microphone or cloud provider is used.

```json
{"result":"PASS","opener":"How was the trip to SF?","repeated":false,"deleted":true}
```

Retained output: `/private/tmp/context-agent-rehearsal-final.log`.

## Checks

Tests were written first; the initial run failed collection on the missing `server.context_agent` module.
New checks cover ranking/recency, all sources, context size and expiry, encrypted plan persistence,
due-date/once-only and concurrent claims, Private/provider switches, deletion, absent keys/consent,
user-only extraction, classic prompt delivery, Live pre-audio context/tool delivery, and the call rehearsal.

The first full run found additional turn events from the debug chip disrupting existing lifecycle tests.
The implementation was corrected to use the existing proof HTTP endpoint. Those lifecycle assertions were
preserved. The proof endpoint's exact-response assertion was extended for the new field; owner isolation
and the existing counter assertions remain. No contracts or dependencies were changed.

The first final-suite attempt stalled in an existing latency test, which passed all 15 checks in isolation.
The normal turn path was gathering twice and scheduling tiny local reads behind worker-thread work. It now
gathers once and reads local context directly; remote reads remain off the event loop. The final full run
with timeout tracebacks completed without a stall. No latency assertion was relaxed.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q -o faulthandler_timeout=15` - FAIL overall:

```text
FAILED vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared
1 failed, 1245 passed, 2 warnings in 63.96s (0:01:03)
```

The sole failure is the pre-existing missing `vision/fixtures/gemini_payment_required.json`, also recorded
in the supplied prior handoffs. No vision test was skipped or fixture fabricated. The vision owner needs
to restore it. The warnings concern existing short synthetic JWT test keys. Log:
`/private/tmp/context-agent-full-final.log`. Loopback permission was enabled for synthetic local services.

Test: `node --test client-web/` - PASS:

```text
ℹ tests 165
ℹ pass 165
ℹ fail 0
ℹ skipped 0
ℹ duration_ms 1291.498875
```

Log: `/private/tmp/context-agent-node-final.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m scripts.context_agent_rehearsal` - PASS
(`opener="How was the trip to SF?"`, `repeated=false`, `deleted=true`; successful subsequent turn).

Test: `git diff --check` - PASS.

## Changed files and limits

- `server/context_agent.py`, `server/test_context_agent.py`: retrieval, encrypted plans and acceptance checks.
- `server/agent.py`, `server/ws2.py`, `server/gemini_live.py`: call/turn/talker integration.
- `server/memory.py`: dated-plan retention through the existing log maintenance path.
- `server/proof_wall.py`, `server/test_proof_wall.py`: authenticated source-name evidence.
- `client-web/agent.html`, `client-web/agent.js`, `client-web/turn.test.mjs`: visible source chip and UI check.
- `scripts/context_agent_rehearsal.py`, this report, `RESULT.md`: rehearsal and handoff.

Rules and lexical ranking are intentionally small, not semantic understanding of arbitrary plans. There is
no new native iOS chip, export-schema extension, multi-process claim service, or deployed Spacetime proof.
Plan claims and spoken deletion use the local encrypted log; this package does not extend remote-store
Forget/export APIs to manage that separate local log. Remote-store deployments need that integration before
claiming unified data lifecycle behavior. The local backend's existing Forget/retention operates on plans
in its normal log.
An unavailable camera/store contributes no invented context. Real Google audio/tool selection, browser
visual appearance and physical-device playback remain unverified. Nothing was committed, pushed or deployed.
