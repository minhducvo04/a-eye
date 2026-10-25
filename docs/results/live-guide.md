# Live guide: coded step guides inside the Gemini Live call (2026-10-25)

## What changed
- `server/live_guide.py` (new): `LiveGuide` wraps the existing `HomeGuide` / `ElectronicsGuide` (unchanged) and keeps them on `session.home_guide` / `session.ee_guide`, so growth, hint fading, `save()` and `stopped()` behave as on the classic path.
- `server/gemini_live.py`: on by default (`LIVE_GUIDE=0` turns it off).
  - When a user transcript starts a task ("my sink is dripping", "light an LED", hinge, breaker) or, during a task, says done/next/continue/ready, "it's off", "walk me through it", "try again" or "forget my progress", the bridge holds the turn (`hold()`): Live's own reply is never played.
  - A debounced background task (0.3 s, same idea as Prefetch) runs the guide's own rules. No slow call is awaited in the socket reader.
  - On a step line, `prompt_turn()` waits for the provider to go idle (3 s cap), then sends `clientContent` with `turnComplete: true`. The text is a versioned GUIDE block (task, step N of M, the exact or faded line, plus "Say only this step in your own words; do not skip ahead; ... the app decides when to move on"). Live speaks it, and its output still goes through `stop_line(output=True)`.
  - Safety lines, `RETRY_LINE` and growth comparisons go through `fixed_say` via `stop()`, never through Live.
  - `publish_guide()` sits next to `publish_memory()` at turnComplete. It uses the idle-only `publish_context` and re-sends only when the version changed. After a reconnect it publishes again. The setup prompt gains one sentence about GUIDE blocks.
- Shutoff step: `agent.check_water_off()` was pulled out of `run_turn` verbatim, and both paths use it. A missing camera, checker or fixture, or any error, means no pass. The pass is granted and consumed with no await in between. "It's off" only asks for the check; the words never pass it.
- Client messages reuse existing `turn` details: `Step: checking`, `Valve: checking`, `Valve: closed` / `test closed` / `unsure`, `Guide: sink 3/7`, `Stopped by code`, `Home: complete` / `Engineering: complete`. It never sends `Home: sink`, because `client-web/agent.js:683` would switch the client pack and leave Live. The step's target is boxed with `pointer.ground(witness=True)` (new `home.TARGETS`; ee uses `guide.target`).
- `server/context_agent.py`: the background-context evidence now carries `guide` (task, step, line), so the summary cannot describe a different step.

## Tests
- New `server/test_live_guide.py` (6): sink start in General Live with Live's reply held and no `Home: sink`; no advance on "it's off"/"next" without a valve pass (RETRY_LINE fixed); advance with a presenter-fixture pass, consumed after one use; GUIDE block published only while idle and not re-sent unchanged; hints fade at growth level 2 and "walk me through it" restores the full step; a hazard in a guide turn gets the fixed line.
- `pytest -q server`: **809 passed, 2 warnings** (run with the main checkout's `.venv`; the worktree has none).

## Not verified
- No real Gemini Live call (cost; the coordinator runs it). Provider timing is unverified: whether a held turn's late audio can slip out after `prompt_turn` resets the reply, whether Live answers the user's own audio turn again after the prompt, and the real latency of a "done" turn (estimate 1.6 to 3.3 s).
- Steps other than the valve advance on the guide's words alone, as on the classic path. The Board's per-step "target in view" visual gate was cut for time.
- The electronics observed-caption stop (classic `run_turn` scene check) is not mirrored in Live.
- A transcript that mentions "done" inside a longer question is held and checked as a "done".
