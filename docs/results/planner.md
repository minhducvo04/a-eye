# Background task planner — 2026-10-25

Implemented on `pkg/planner`, based on `446fe77`, with fake LLMs and synthetic Live packets.
No provider call, `.env` read, UI change, contract change, push, or deployment was performed.
The coordinator owns the real call before the owner's 05:00 PDT test.

## Behavior

- `server/planner.py` recognizes explicit do/learn requests without a coded guide. It reuses
  `task_scope.task_for()` and the memory router's explicit time patterns, then applies an intent
  check. Chit-chat, current-view questions, past questions, disabled home topics and unsafe
  requests do not start research. This does not add an embedding or classification API call.
- `server/gemini_live.py` calls the synchronous scheduler for finished input transcription,
  completed typed input, or `turnComplete` when the provider omits a finished flag. Partial
  speech never starts planning. Neither Claude call is awaited by the socket reader; Gemini's
  immediate answer stays unheld. Providers without the finished flag start research after
  their initial answer completes.
- Research gets a bounded recent text transcript, the current question, latest scene caption
  when the camera is enabled, and matching parts-shelf cards. No frame, crop, image or audio
  enters either request. Research notes cover facts, tools, parts, mistakes and safety risks.
- Exactly two Claude requests on a cache miss: researcher, then strict-JSON planner.
  The existing shared Anthropic client is used with retries disabled, no tools, and a single
  12-second deadline across both calls and acceptance. A failed/cancelled task is not retried
  within the same call. Private mode, LOCAL_ONLY and Claude consent are checked before each
  call and before accepting its result.
- Code validates exact fields, 1–8 steps, 1–24 words per `say`, bounded strings, and runs every
  field plus each combined step through `safety.before()`, `safety.after()` and
  `electronics.refuse()`. Disabled HOME_TOPIC content is rejected. Any failure drops the
  whole plan. Common personal identifiers and named-person constructions are also rejected.
- `LiveGuide` owns the generated step index. It publishes the versioned GUIDE through the
  existing idle hook, advances on the existing NEXT intent, and uses
  `pointer.ground(witness=True)` for the step target. Gemini voices the planned steps; planning
  adds no TTS calls. Retry/repeat controls retain the current step. Existing fixed safety
  speech remains unchanged. Stale pointer results are discarded after guide changes/stops.
- Coded guides win and cancel pending planning. An active coded guide is never replaced by a
  generated plan. Requesting a different generated task clears the previous generated guide,
  so failure leaves free-form conversation rather than stale step advancement.
- The client sees the existing `Guide: plan 1/N` turn detail; there are no new screens/events.

## Configuration and cache

| Setting | Default / behavior |
| --- | --- |
| `PLANNER` | On; `0` disables planning |
| `PLANNER_MODEL` | `claude-sonnet-5-5` |
| `PLANNER_CACHE_PATH` | `~/.cache/a-eye/plans.json` |
| `LIVE_GUIDE` | Existing guide switch must remain enabled |
| `HOME_TASKS` | Existing scope restriction; home topics require `1` |

The normalized task is case-folded, request wrappers removed, whitespace/punctuation normalized,
and `my`/`our` changed to `the`. There is no hard-coded list of supported new tasks.
The in-memory and atomic JSON cache hold at most 100 rows, each containing only the normalized
task key, reusable plan and `good` boolean. Transcript, scene, research notes, session identifiers,
media and timestamps are not persisted. File I/O runs outside the event loop. Disk failures keep
the in-memory cache usable. Cached plans are revalidated against current safety/scope rules.
Finishing through the existing intent words marks the plan good; a repeat restarts at step one
with zero model calls. One planner event records only task hash, elapsed milliseconds and result.

## Verification

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` -
**FAIL (1064 passed, 17 failed, 2 warnings in 51.38s)** on the final implementation.
Full local proof: `.pytest_cache/planner-suite.log` (ignored, not committed).

All **51 planner tests passed** within that run. They cover trigger/non-trigger pairs, exact schema
and length rejection, unsafe content in every field, coded-guide priority/cancellation, text-only
two-call SDK wiring with retries off, idle publication, immediate Live answer, target witnessing,
step progression/completion, persistent cache reload/repeat, timeout on either call, failure
fallback, stale-guide clearing, privacy switches, consent revocation and hash-only event output.

An earlier focused run of `server/test_planner.py server/test_live_guide.py
server/test_guide_review.py` passed **70 tests in 2.86s**; the two final regressions for stale-guide
clearing and the shared deadline were subsequently verified in the required full run.

The full suite is not green in this sandbox:

| Failures | Evidence |
| --- | --- |
| 15 loopback fake-server tests | `PermissionError: Operation not permitted` binding `127.0.0.1`; no external provider involved |
| `test_mic_chunk_preserves_code_owned_hold[guide]` | Timeout; reproduced after loading both unchanged Live modules directly from `HEAD` using `git show` |
| `test_ws2_hazard_sends_stop_caption_and_fixed_audio` | `KeyError: state`, preceded by sandbox `live_start_failed` PermissionError; also reproduced with unchanged Live modules |

Test: `git diff --check` - **PASS**.

## Limits and coordinator check

This proves the fake-LLM/code/Live-packet path, not Claude model availability, provider latency,
audible device playback or physical task safety. Intent and safety checks are conservative text
patterns, not a general semantic safety or anonymization system. Generated wording is instructed
to be generic and common personal markers are rejected. `good` means user-reported completion,
not visual certification; a grounded box is also not proof that the physical step is correct.
Generated guides do not add growth scores or a new visual completion gate.

For the coordinator's authorized real call: ask “help me fix my headphones,” then “next” and
“done”; confirm immediate Gemini speech, a hash-only valid planner event, ordered
`Guide: plan N/M` details and witnessed targets. Repeat to confirm zero additional Claude calls.
Then start the coded LED or tie guide and confirm it wins. Repeat with `PLANNER=0` to confirm
free-form fallback. No real call was attempted in this worktree.
