# web-wait: listening waveform, wait card and scan sweep on the web call page

Port of iOS commit c39cb5d to `client-web/`. No protocol change; the web now uses the `turn` stages, `typical_ms`
and `detail` it already received, and the mic level voice.js already measured (it now also passes the raw RMS).

Files: `client-web/listen.js` (AudioLevel.swift port, 20 ms pooling, strip copy, bar layout), `client-web/wait.js`
(Wait.swift, CallState wait reduce, WaitCard copy), tests `listen.test.mjs` and `wait.test.mjs` (ports of
AudioLevelTests and WaitTests), `agent.html`/`agent.css`/`agent.js` wiring, `voice.js` (onLevel gets the raw RMS as
a second argument), `docs/ui-parity.md` rows, screenshots `docs/ui-parity/wait-web-*.png`.

Differences on purpose: see the three new rows in `docs/ui-parity.md`.

Limits: no iOS side-by-side of the wait state. The app builds for the iPhone 17 simulator and joins a call, but the
simulator has no mic (typed mode, so no strip) and the keyless server answers in under a second.

Test: node --test client-web/ - PASS (112 tests, 0 fail)
Test: make browser-smoke URL=http://127.0.0.1:8123 - PASS (14 of 16 runs; the 2 fails were a 30 s body inner_text
timeout under machine load, not reproduced in 12 later runs or with a long-task probe)
