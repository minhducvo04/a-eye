# False Live safety stop and next-voice-turn recovery

2026-10-25. Branch: `pkg/fix-false-stop`. Base: `8efa591`.

## Reproduction and exact gates

The supplied question and reply prefix were replayed through `LiveBridge.handle`
as multiple `inputTranscription` packets followed by multiple
`outputTranscription` packets. That exact prefix passes on the base revision;
it does not establish which later packet or background summary stopped the real call.
No original provider capture or context summary was available, and no network or
real call was used. The continuations and summaries below are synthetic probes,
not claimed quotations from the incident.

Two paths reproduced the reported `live_power` fixed line:

- Output continuation: `Use the hot soldering iron to join the wires.`
  `handle -> stop_line(output=True) -> session.pack.refuse -> safety.before`
  matched the old `live_power.ask` expression: `hot` within 50 characters of
  `wires`. Heat at the iron was incorrectly treated as live electrical power.
  This happens before the output guard (`safety.after`) runs.
- Background summary: `Live is explaining wire repair using a hot soldering iron.`
  `LiveContextBuilder.build -> safety_line -> stop_line -> pack.refuse ->
  safety.before` matched `Live` near `wire`. The product name was incorrectly
  treated as a live conductor. The test builds the real context worker with a
  synthetic assessment response, after streaming the reported question/reply.

A third false stop came from `Don't touch the hot tip; keep the iron in its stand.`:
Live's output was checked by the input `hot_tool.ask` pattern, which ignored the
negation even though the output checker already respected it.

The separate mute bug was reproduced with a real coded output stop. `stop()`
latched `blocked` and `safety_stopped`; typed input cleared them, but a subsequent
voice transcription did not. Late interruption and completion packets retained
that latch, so the next otherwise valid reply was suppressed.

Before production changes, the cleaned-up regression harness reported
**7 failed, 7 passed**. Failures covered both live-power false positives, the
hot-tip warning, both recovery orderings, and the missing `rewire ... plugged
into the wall` hazard in both input and output.

## Changes

- `server/safety.py`: tie `live`, `hot`, and `powered` to an electrical noun or
  stated electrical condition instead of arbitrary nearby words. Keep power-on
  and breaker-off checks; recognize `rewire` and `plugged into` as well as
  `plugged in`. Preserve the existing safe PSU connection question control.
  Use the existing negation-aware hot-tool action check for input refusals too.
- `server/gemini_live.py`: record when a stop rejected model output. Only a new
  nonempty user transcript clears that stop; recheck the new question normally.
  Fresh microphone input can also arm recovery from an input/context stop, but
  microphone bytes alone never release blocked output. Late output, completion,
  and interruption acknowledgements cannot release playback.
- `server/test_false_stop.py`: streamed headphone repair, unplugging, heat shrink,
  soldering, and hot-tip precautions; both input/output hazards for touching a
  hot tip, live mains, and plugged-in rewiring; context-summary reproduction;
  next-voice-turn caption and emitted PCM after a stop, with no provider boundary,
  interruption, or completion. These are in-process packet tests, not hardware proof.

## Verification

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_false_stop.py server/test_recall_review.py server/test_home_safety.py eval/swap/test_checker_regressions.py --tb=short` - PASS
(103 passed in 1.62s; summary read).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts eval` - FAIL
(1291 passed, 16 failed, 2 warnings in 100.95s; full summary and failure evidence read).
Full output retained locally in `.pytest-false-stop.log` (gitignored).
Fifteen failures are sandbox-denied loopback socket binds. One is
`test_ws2_hazard_sends_stop_caption_and_fixed_audio`, whose missing state follows
`live_start_failed` with `PermissionError`. These match the previously recorded
socket failures in RESULT.md. The warnings concern synthetic short JWT test keys.
No new behavioral test failure remained in this run.

After that full run, the recovery test matrix gained the no-interruption/no-completion
ordering; production code did not change. The final focused result is recorded below.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_false_stop.py --tb=short` - PASS
(15 passed; summary read).
Test: `git diff --check` - PASS.

## Limits

The exact original call's triggering packet remains unconfirmed: its supplied
prefix does not reproduce a stop. The identified gates reproduce the reported
line on ordinary repair language and are covered by regression tests. Regex
checks remain bounded language backstops, not semantic safety guarantees for
every possible phrasing. No `.env` access, network permission change, real
provider request, raw media, push, merge, deployment, or physical-device proof.
