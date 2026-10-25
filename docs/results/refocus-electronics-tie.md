# Electronics and tie refocus — 2026-10-25

Implemented on `pkg/refocus` in this worktree. No push or deployment.

## Behavior

- Live and classic share deterministic task selection. Home tasks are disabled unless the process explicitly sets `HOME_TASKS=1`. Disabled requests receive an electronics/tie redirect before model work; shared speech guards also reject home-topic output. Selecting the legacy home pack defaults to the general pack when disabled. Home guide code and water-check safety tests remain, with legacy tests explicitly opting in.
- Natural starts include “I want to make an LED blink”, “how do I read this resistor”, “which leg is plus”, “read resistor color bands”, and “check LED polarity”.
- “Use a multimeter to check a resistor” starts six steps covering disconnected power, correct probe jacks, ohms mode/range, loose-resistor measurement, units, and cleanup. Advancing requires the closed-set report “power disconnected” (or “power disconnected, next”); USB-only confirmation is insufficient. Reported or freshly observed connected USB revokes that confirmation. The initial safety instruction never fades.
- “How do I tie a tie” and “help me with my tie” start eight four-in-hand steps. Targets cover collar, wide end, narrow end, knot and dimple. Completion clauses advance; negation and “next to” do not. Growth reduces full steps to hints, then independent practice. “Walk me through it” restores full instructions; forgetting resets progress. No camera checker certifies the knot.
- The parts shelf contains electronics cards only and rejects legacy task cards. The existing multimeter card links to the new guide. Tie steps need no cards.
- Live setup and persona text describe a dad guiding his son through electronics and tying a tie. The existing actual-parent claim restriction remains. The active setup's plumbing example was replaced. Remaining home terms belong to gated legacy implementation, retained safety checks, and existing historical records, not default guide examples.

## Verification

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts` - PASS (**968 passed, 2 warnings in 53.16s**, exit 0; summary read).

The two warnings are existing JWT identity fixtures using an 11-byte synthetic HMAC key.

The initial new acceptance checks failed 13/13 before implementation. Focused verification exercised natural starts in both paths, default home rejection and opt-in controls, all eight tie steps through the real grounding function with synthetic scene responses (eight validated box messages), hint fading, full-step restoration, forgetting, and multimeter power revocation. Existing water-gate tests remain in the full run.

A first full run found one stale assertion in `scripts/test_ready.py`: it expected a Vision Pro build even though `ready.local_checks()` no longer invokes one. The assertion now verifies exactly the two existing local probes. Production readiness behavior and UI were not changed. Loopback tests required sandbox escalation; all Gemini/provider responses in these tests were synthetic.

Test: `git diff --check` - PASS.

## Files and limits

Runtime: `server/task_scope.py`, `server/agent.py`, `server/ws2.py`, `server/live_guide.py`, `server/gemini_live.py`, `server/packs/{__init__,general,home,electronics,tie}.py`, `server/personas.py`, `server/recent_memory.py`, `server/parts_shelf.py`, `data/kb/cards.json`.

Tests: `conftest.py`, `server/test_refocus.py`, `server/test_live_guide.py`, `server/test_guide_review.py`, `server/test_live_memory.py`, `server/test_parts_shelf.py`, `server/test_home_pack.py`, `server/test_growth.py`, `server/test_step_check.py`, `server/test_dad_flow.py`, `server/test_product_rules.py`, `scripts/test_ready.py`. Handoff: this file and `RESULT.md`.

No `.env` reads, real Gemini calls, real media, UI edits, contract changes, pushes or deployment. Spoken confirmations report user actions; they do not prove electrical isolation. Grounding abstains without a fresh visible target. Real camera accuracy, speech recognition, audible playback and physical knot/electronics results remain for the owner's 05:00 PDT test.
