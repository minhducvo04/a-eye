# Growth flow integration — lead review

Historical verification below; product copy has been updated. Current guidance, sharing gates, growth measurements and limits are in [grow.md](grow.md).

Implemented in the working tree on 2026-10-24; **not committed or merged**. Read
`AGENTS.md`, `CLAUDE.md`, and the home-fix, step-check, family-note and proof-wall
handoffs before implementation. The integrated presenter browser flow and all
five local-service rehearsals passed. Real-photo checker evaluation remains open.

## What is connected

- Added `home` to the v2 contract enum, TypeScript union and example. The existing
  home pack is now reachable from the Sink selector. Exact spoken/typed `sink`
  also switches a general call into the deterministic home guide; the one-word
  STT filter accepts it. Home turns bypass the model router and Rewind routing.
- The guide speaks one step per turn. The explicit presenter launcher attaches
  a read-only text fixture: `Tuesday: shutoff valve under the left cabinet`.
  It does not enable remembering, frame storage or crop writes.
- Existing real checker wiring remains in use for normal calls. Missing, open,
  unsure, stale or failed checks cannot advance plumbing. A pass authorizes only
  the current turn. The outlet hook invokes the existing coded stop, discards any
  armed simulated pass, and requires another check before continuing.
- Finishing the sink guide opens “Want to show someone?” only when a contact has been added.
  Completion is not auto-attested: the user still selects what actually happened.
  Read-before-send, consent, text-only delivery links and reply reading remain
  enforced. Closed-set spoken `send` now tolerates terminal STT punctuation;
  `Zend` and extra words are still rejected.
- Small UI additions use the existing style: Sink in the ring, presenter controls,
  a persistent TEST MODE warning, a simulated valve-card label, and the existing
  Pictures saved / Pictures sent / Cloud AI calls counters.

## Presenter-only checker mode

Normal `server.app:app` does not mount `/api/dad-demo`; no browser query flag,
storage value or normal hello message enables simulated checks. The separate
launcher explicitly calls `create_app(presenter=True)`, which requires
`LOCAL_ONLY=1`. Its controls additionally require an owned Private home session,
a real loopback peer, no proxy headers, and the existing API authentication and
same-origin write checks.

Every session starts OFF, including reconnects. Enable the checkbox explicitly;
the orange **TEST MODE · simulated valve, no repair proof** warning stays visible.
`Test pass + next` supplies a single-use verdict with a 15-second expiry. Turning
mode off clears any pass. The valve card says **Simulated pass, not a water-off
check**. The outlet button injects `water near the outlet` into the normal coded
safety path. No real outlet detection is claimed by this hook.

## Run it

From this worktree, using installed Python dependencies and reachable configured
home TTS/STT services:

```sh
$HOME/Projects/a-eye/.venv/bin/python scripts/dad_flow_rehearsal.py
```

This starts and stops its own loopback server, runs five fresh Private calls with
camera and Rewind off, and removes its temporary text-memory directory. It forces
real home adapters (`A_EYE_MOCK=0`) and disables the router. Audio is held only in
RAM. No actual family contact is used: delivery and reply use Fixture Friend locally.

For the presenter UI, keep the usual `A_EYE_TOKEN` configured and authenticate the
browser normally (never paste the token into logs or receipts):

```sh
$HOME/Projects/a-eye/.venv/bin/python scripts/dad_flow_rehearsal.py --serve --port 8047
```

Open the printed loopback URL, select Private, then Sink. Keep the camera off for
the fixture demonstration. Say/type `next` for recall and shutoff, demonstrate
the blocked check, enable TEST MODE, then use `Test pass + next`. The outlet-stop
button demonstrates the stop and invalidation. Finish with fresh test passes,
confirm only the fixture activity in Want to show someone?, read the note, and say `send`.
Open the resulting fixture delivery link locally to reply.

The integrated browser check expects that presenter server and the same token in
its environment; it uses synthetic devices and blocks other browser origins:

```sh
python scripts/dad_flow_browser_smoke.py http://127.0.0.1:8047
```

Use a Python environment with Playwright and installed Chromium for that command.
The verified run used the existing cached Playwright interpreter. A temporary
runner generated an ephemeral token for both processes and shut each server down.

## Verification receipts

Full Python and Node suites were run directly, matching the Makefile targets
without loading `.env`. The shared server virtualenv is used below.

| Check | Result | Retained evidence |
| --- | --- | --- |
| `python -m pytest -q` | **848 passed, 2 warnings in 69.19s (0:01:09)** | `/private/tmp/dad-full-python-final.log` |
| `node --test client-web/` | **150 tests, 150 pass, 0 fail, 0 skipped** | `/private/tmp/dad-full-node-verified.log` |
| `python scripts/browser_smoke.py <local mock server>` | **BROWSER SMOKE PASS**; frames_sent 2, problems [] | `/private/tmp/dad-browser-smoke-final.log` |
| `VISION_BACKEND=fake python scripts/smoke.py` | **SMOKE PASS**; SAFETY → IDENTIFY → LOCATE → GUIDE → AWAIT; target_overlays 1 | `/private/tmp/dad-smoke.log` |
| `python scripts/dad_flow_rehearsal.py` | **GROWTH FLOW REHEARSAL: 5/5 PASS, 0/5 FAIL; checker TEST MODE; no real-photo claim** | `/private/tmp/dad-rehearsal-final.log` |
| `python scripts/dad_flow_browser_smoke.py <local presenter server>` | **GROWTH FLOW BROWSER: PASS; sink through reply; native note/reply speech completed; TEST MODE visible; all three counters 0** | `/private/tmp/dad-integrated-browser-final.log`; `/private/tmp/dad-flow-browser.png` |

The two Python warnings come from existing short HMAC keys in JWT test fixtures.
After the full Python run, the presenter proxy check was switched to the shared
`auth.proxied` guard. Final focused checks passed: `server/test_dad_flow.py`,
`server/test_ws2.py`, `server/test_family_note.py` — **33 passed in 0.99s**; then
`server/test_dad_flow.py server/test_home_pack.py server/test_home_safety.py
contracts/` — **109 passed in 0.67s**, retained in
`/private/tmp/dad-final-targeted.log`. The final Node run includes the client fixes.

The screenshot was visually inspected: Private, TEST MODE, simulated valve card,
Want to show someone? and all three zero counters are visible. Browser note/reply speech
completion callbacks passed. The browser sends by button; actual spoken `Send.`
through home STT is covered separately by all five server rehearsals.

### Per-step median latency

Milliseconds, five samples per available metric. Answer means final text received;
complete means turn/audio generation completed, **not speaker playback duration**.
Note/reply read timings are real home TTS synthesis in the scripted rehearsal.

| Step | First audio | Answer | Complete |
| --- | ---: | ---: | ---: |
| Select sink | 430 | 3 | 1374 |
| Recall fixture | 498 | 3 | 873 |
| Shutoff instruction | 279 | 3 | 420 |
| Normal check blocked | 248 | 4 | 422 |
| Open test verdict blocked | 324 | 4 | 451 |
| Test checker pass | 401 | 4 | 783 |
| Outlet coded stop | 293 | 4 | 707 |
| Post-hazard check blocked | 283 | 4 | 394 |
| Hand-snug step | 382 | 5 | 737 |
| Tap step | 353 | 4 | 675 |
| Dry check step | 356 | 4 | 848 |
| Want to show someone? | 375 | 5 | 479 |
| Note read | 476 | — | 1170 |
| Spoken send via home STT | — | — | 998 |
| Fixture reply arrived | — | — | 2 |
| Reply read | 185 | — | 351 |

Every trial asserted Pictures saved 0, Pictures sent 0, Cloud AI calls 0 and
Bytes to cloud 0. The seed location was also asserted absent from the sent note.

## Failures found and fixed

Initial rehearsals exposed inappropriate HTTP headers copied into the WebSocket
handshake, a presenter event missing required `at_ms`, and one-word STT output
`Send.` being rejected. One synthetic voice produced `Zend.`; it remains rejected,
and the fixture now uses a voice that the real home STT recognizes. Browser runs
caught an invalid `text` command source and misuse of the JSON API helper. Client
regressions now exercise the actual Sink selection, presenter GET/POST shapes,
visible warning and unattested completion. An unauthenticated smoke run failed
with 401s; authenticated reruns passed without weakening authentication.

## Scope and lead review

- Review the additive v2 contract registration with schema, types and example
  together. The assignment explicitly requested this integration; no contract
  version bump or unrelated schema relaxation was made.
- Real-photo valve precision/recall, real reach detection, physical microphone/
  speaker/device behavior and an actual remote recipient remain **unverified**.
  The simulated checks do not clear the real-photo evaluation hold.
- Normal mode remains fail-closed and cannot enable presenter mode. No real
  footage, photo fixture, audio file, secret, external family message or cloud AI
  request was needed for these proofs. Home services were used over the existing
  configured home network.
- All work is uncommitted. No deployment, push, merge or service configuration
  change was made. Temporary local demo servers were stopped.

Finished: Growth flow integration and demo verification. Next: lead review and real-photo checker evaluation. Suggested: GPT-6.1 / high.
