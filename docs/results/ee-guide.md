# Engineering LED guide

Implemented and left uncommitted. Engineering now starts the Arduino UNO LED practice guide in the web and iOS mode rings. The local five-call rehearsal passes; physical electronics, camera accuracy and device audio remain unverified. The full Python suite has one existing missing-fixture failure, detailed below.

## Behavior

- The existing mode id is `engineering`. Both clients use the existing contract-valid `hello.pack="general"` with `/ws2?mode=engineering`; the server selects the internal Engineering pack. This follows the existing query-selected mode mechanism. No contracts were changed.
- Seven deterministic, numbered steps cover the requested UNO, USB cable, breadboard, LED, 220 ohm resistor and two jumper wires. Each full step has at most two sentences and names the camera view. Blink uses **pin 9**, not the UNO's built-in LED pin: select Arduino Uno and its port, open Blink, replace `LED_BUILTIN` with `9`, then upload.
- “Read resistor color bands” and “check LED polarity” select two-step practice tasks. Red red brown is 220 ohms; long leg is plus, short leg/flat rim is minus. Unclear colors require a meter; uncertain polarity requires the part datasheet.
- Numbered speech enters recent memory once. “Where did I put the resistor” reads recent scene notes; “what was step 3” recalls an actual spoken instruction. Neither advances the guide or calls a brain. Missing/expired evidence is explicitly unavailable; recalled instructions do not certify completion.
- The existing authenticated growth log stores `ee_led`, `ee_resistor` and `ee_polarity` separately. Completed runs select full steps, short camera hints, then silence. “Walk me through it” restores full steps. “Forget my progress” resets the log without asserting that USB is disconnected. Existing encryption/no-plaintext-fallback behavior remains in use.
- A fresh, local grounded result boxes the current target: LED, resistor, pin 9, GND or LED again. Existing confidence, freshness, source and geometry checks apply. No box is fabricated on an abstention; quiet runs have no ordinary pointer hints.
- Hero completion emits `Engineering: complete`. The web uses the existing **Want to show someone?** flow, only after a consenting contact exists. The controlled note describes finishing a practice guide, not verified physical success. Draft, read-aloud and send gates remain unchanged. The rehearsal creates drafts only; it sends nothing to anyone.

## Coded stops

Fixed text runs before recall, guidance, routing or any model call:

| Hazard | Fixed line |
|---|---|
| Powered USB / attempted live rewiring | Unplug the USB first |
| Missing series resistor | Unplug the USB first. Use a 220 ohm resistor in series with the LED before connecting USB. |
| Touching a hot soldering iron tip | Do not touch the hot soldering iron tip; leave it in its stand. |
| Mains / wall outlet | Stop; mains power and wall outlets are outside this USB-only build. |

Say **“USB unplugged, next”** to enter wiring. Before step 6, say **“resistor is in series, next”**. These closed-set confirmations are user reports, not trusted electrical measurements. Power-on instructions conservatively mark USB powered. A later power report revokes the unplugged state; removing the resistor after power-on returns to the pre-power checkpoint. Safety stops remain active at all growth levels.

A same-frame, fresh Ollama caption can also trigger a stop. A visible connected USB cannot be overridden by a conflicting spoken unplugged confirmation while entering wiring. These finite language patterns and vision captions do not comprehensively detect electrical hazards. An absent caption is not proof of safety.

## Rehearsal

Run from this worktree:

```sh
/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/ee_guide_rehearsal.py
```

The script starts and stops an isolated loopback server, uses one encrypted scratch identity across five calls, and deletes its temporary text storage afterward. It uses a synthetic frame and a **scripted grounding oracle**, not real object recognition. `LOCAL_ONLY=1` blocks cloud calls; a brain call fails the fixture. The script raises its own process-local turn allowance for the rapid replay. It never reads `.env`.

Each run checks all seven steps, all four stops, power/series gates, both recall questions, completion, encrypted progress, consent-gated note drafting, and zero saved pictures/cloud calls/cloud bytes. Runs 1–2 also require grounded boxes; runs 3–5 require quiet ordinary steps. Browser TTS is selected, but no browser or audio engine runs: timings measure text transport and turn completion only.

```text
EE HINTS: [14, 7, 0, 0, 0]; fading=True
EE GUIDE REHEARSAL: 5/5 PASS, 0/5 FAIL; scripted vision; text transport only
```

| Step | Median completion ms | Maximum ms | Runs |
|---|---:|---:|---:|
| 1 — parts | 14.76 | 17.80 | 5/5 |
| 2 — LED rows | 2.50 | 5.48 | 5/5 |
| 3 — resistor | 2.93 | 5.31 | 5/5 |
| 4 — pin 9 | 2.46 | 5.15 | 5/5 |
| 5 — GND | 2.81 | 5.25 | 5/5 |
| 6 — USB | 2.54 | 5.14 | 5/5 |
| 7 — upload | 2.51 | 5.22 | 5/5 |

Full per-run first-text and completion timings: `/private/tmp/ee-rehearsal-final.log`. Quiet turns have no first-text latency. These small fixture timings do not predict physical microphone, TTS or GPU latency.

## Tests and files

Tests were written first: **10 failed** in `/private/tmp/ee-before.log`; Engineering's web selection also failed before activation. Later review reproduced power-state revocation, missing-resistor continuation, visible mains, and contradictory visible/spoken USB state before their fixes. The initial focused integration set passed **74 tests**; expanded EE coverage contains **12 tests** in the full run.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q` — FAIL (**1 failed, 1180 passed, 2 warnings in 60.59s**). Evidence: `/private/tmp/ee-python-final.log`. The sole failure is `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: `vision/fixtures/gemini_payment_required.json` is missing. `git ls-tree -r HEAD vision/fixtures` is empty, and the supplied recent-memory handoff reports the same failure. No fixture was fabricated and no vision files were changed. The warnings concern existing short HMAC test keys. This is not a green full-suite claim.

Test: `node --test client-web/` — PASS (**165 tests, 165 pass, 0 fail, 0 skipped**). Evidence: `/private/tmp/ee-node.log`.

Test: `swift test --package-path ios/AEyeCore` — PASS (**64 tests, 0 failures**). Evidence: `/private/tmp/ee-swift.log`. Swift manifest compilation required sandbox escalation; no physical iPhone or full native app build is claimed.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/ee_guide_rehearsal.py` — PASS (**5/5**). Localhost binding required sandbox escalation. Evidence: `/private/tmp/ee-rehearsal-final.log`.

Test: `git diff --check` — PASS.

Changed files:

- `server/packs/electronics.py`, `server/packs/__init__.py`: guide, gates, growth reuse and pack registration.
- `server/agent.py`, `server/ws2.py`: deterministic turn ownership, recent memory, observed stops, pointing and mode selection.
- `server/family_note.py`: controlled electronics practice note.
- `server/test_ee_guide.py`: acceptance and safety regressions.
- `client-web/agent.js`, `client-web/turn.test.mjs`, `client-web/family-note.test.mjs`: Engineering startup and completion integration.
- `ios/AEyeCore/Sources/AEyeCore/Modes.swift`, `ios/AEyeCore/Sources/AEyeCore/GeminiLive.swift`, `ios/AEyeCore/Tests/AEyeCoreTests/ModesTests.swift`, `ios/AEye/App/Call/CallController.swift`: native mode URL and once-only startup; `ios/README.md`, `ios/AEye/SETUP.md`: availability notes.
- `scripts/ee_guide_rehearsal.py`, this report, `RESULT.md`: reproducible replay and handoff.

No commit, merge, push, deployment, physical-circuit validation or outbound note delivery was performed. Native sharing has no new UI here; the existing sink-style note flow is on the web.

Finished: Engineering guide and local rehearsal. Next: restore the existing vision fixture and rehearse on physical hardware. Suggested: GPT-6 / high.
