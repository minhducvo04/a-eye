# Home-fix package result

Implemented and left uncommitted for lead review. Router and contract files are unchanged.

## Behavior and changed files

- `server/packs/home.py`: home pack for people 16+, with a dripping sink supply line/tap guide, a strictly read-only tripped-breaker guide, and a cabinet-hinge guide. A per-session deterministic sequence speaks one step per turn, at most two short sentences, with a camera request in each step. The opening line appears once per session. Safety refusals take priority over the opening.
- `server/packs/__init__.py`: registers `packs.get('home')` with the existing safety wrapper.
- `server/agent.py`: owns one home guide per session and speaks its fixed steps through the existing reply/TTS path before model, vision, shopping or router calls. Reads only the local memory store already attached to that call. A stored `shutoff valve` text tag supplies its saved location; missing memory uses the generic camera request. No new persistence or media capture.
- `server/safety.py`: fixed code lines for water near electricity, opening an electrical panel, gas lines, unsafe ladders and water still on. Existing gas-smell emergency refusal takes priority. New gates apply to all packs before model calls and to hazardous generated speech afterward. `plumbing_stop()` requires literal `True`; absent, false and truthy substitutes fail closed.
- `server/test_home_safety.py`, `server/test_home_pack.py`: hazard/no-model tests, nearby safe controls, all three task replays, once-only opening, local-store isolation, checker bypass and revoked-check regressions.
- `server/test_agent.py`: gas-line refusal now also asserts the existing `Stopped by code` proof event, since it moved into the shared safety gates.
- `RESULT.md`: appended this package's handoff without replacing the existing result.

## Integration limits for the lead reviewer

1. `contracts/schema.json` currently excludes `home` from `pack_id`. Per repository ownership rules, this package does not change contracts. The integrator must add the pack through the contract change process and expose it in the client. Python `Session(pack=packs.get('home'))` is exercised; browser selection is not available yet.
2. The valve checker is a separate integration. It must supply and invalidate `session.home_guide.water_off_passed` from a trusted, current checker result. No client message, spoken confirmation or LLM response sets it here. Without that integration, the sink sequence stops after the shutoff/flow-check step. A reported hazard clears a previous pass; repeated repair instructions cannot bypass that reset.
3. Other steps advance on `next`, `done`, `continue` or `ready`. Camera requests are explicit, but this package does not certify visual completion or implement the valve classifier. Text gates are conservative pattern backstops, not comprehensive language understanding or automatic camera hazard detection.
4. Repairs stay narrow: only a manufacturer-permitted hand-snug supply connection; unknown fittings, stuck/leaking valves and tap cartridge work go to a plumber. Breaker steps never instruct touching, opening or resetting a panel. The guide is not an age-verification system.
5. No real sink, physical repair, browser call, cloud model or voice-device validation was performed. No router retraining, contract mutation, commit, push or deployment. No private planning notes were copied into this repository.

## Tests and summary lines

Tests were written first:

- `python -m pytest -q server/test_home_safety.py`: **14 failed, 5 passed in 0.96s** before implementation.
- `python -m pytest -q server/test_home_pack.py`: **4 failed in 0.55s** before implementation.
- The repeat-after-revocation regression also failed before its fix: **1 failed in 0.56s**.

Interpreter used below: `/Users/minhducvo/Projects/a-eye/.venv/bin/python` (this worktree has no `.venv`).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_home_safety.py server/test_home_pack.py server/test_agent.py voice/test_safety.py voice/test_memory_pack.py` - PASS (**67 passed in 0.59s**).

Test: `make test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - FAIL in the sandbox (**1 failed, 800 passed, 2 warnings, 4 errors in 40.91s**). All five failures were localhost socket binds rejected with `PermissionError: [Errno 1] Operation not permitted`; make stopped before the web target. The two warnings were existing short synthetic JWT test keys.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q device/test_capture.py::test_event_real_http_person_drop_and_no_files device/test_client.py::test_button_turn_reply_audio_then_idle_off device/test_client.py::test_frames_with_a_person_never_leave_the_device device/test_client.py::test_nothing_is_sent_while_off server/test_cloud_meter.py::test_real_websocket_send_boundary` - PASS with approved localhost access (**5 passed in 17.50s**).

Test: `node --test client-web/` - PASS (**tests 141; pass 141; fail 0; skipped 0**).

Together, the unchanged tree has passing evidence for all **805 Python tests** across the full run and the five-test environment rerun, plus **141 web tests**. This is not a single green `make test` invocation.

Test: `git diff --check` - PASS.

## Direct runtime replay

An actual in-process `run_turn` replay with `vision=None` and `llm=None` produced:

```text
fix a dripping sink => I'm not your dad, but I can help you do this. Show the dripping tap or supply line and the surrounding floor.
next => Find the sink shutoff without touching any wet electrical items. Show the valve and its handle.
next => Gently close the sink shutoff; stop if it sticks or leaks. Show the valve and the open tap with no flow.
next => Stop here until the step checker confirms the water is off. Show the shutoff valve and the tap with no water flowing.
water near the outlet => Stop and move away from the wet area; don't touch cords, outlets or switches. Keep others away and call an electrician before continuing.
```

Finished: home pack, coded stops and tests. Next: lead review and contract/checker integration. Suggested: GPT-6 / high.
