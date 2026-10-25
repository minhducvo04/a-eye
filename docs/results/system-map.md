# A-Eye system map: submission bundle

Interactive 3D map of the A-Eye system for judges, served at `/map.html` next to the app. Data flow, speed and cost
per call, all driven by one JSON file. Branch `pkg/system-map`; the commit sha is in the git log of that branch (this
file is part of that commit).

## Numbers round (team numbers sheet, 2026-10-25)

1. Scale panel filled from the sheet: per-user caps, what breaks first at 10 / 100 / 1,000 / 100,000 users, monthly
   cost per active user, with the provider source links in the panel footnote (`1280-scale.png`, `390-scale.png`).
2. Every flow now has Path, Data that leaves, Latency, Cost and How long it runs. On desktop the flow opens a panel;
   on a phone the bottom card has a "Path, cost, runtime" button (`1280-flow-hazard.png`, `390-flow-guest.png`).
3. Nodes carry list price (estimate) next to our meter: Gemini $0.016 to $0.025 / min list vs $0.10 meter; Haiku notes
   $0.003 / min list vs $0.15 meter; Rewind busy minute $0.033 list. Router 45.7 ms p50, recent-memory and saved-call
   lookups (fixtures), Guest / local first audio 1630 ms, Rewind flush 0 at 11 to 20 s marked estimate, all as the
   sheet marks them. The headline cost chip now reads "(meter)".
4. Step guide lists the coded multimeter (6 steps) and four-in-hand tie (8 steps) from `server/packs/` on main;
   soldering stays gate-only. The sheet's pre-refocus home-repair section was not used, and its card count (39) is
   superseded by main's 20 electronics cards.

## Product focus round (owner, 2026-10-25)

1. Electronics plus a tie: the headline, step guide and parts shelf now follow the dad guiding his son. The step guide
   panel lists the coded tasks on main (Arduino LED build 7 steps, resistor bands 2, LED polarity 2) and marks
   multimeter, soldering and tying a tie as having no coded steps yet. The valve checker panel and its line are gone;
   the GPU node is Captions. Hazard examples are the hot soldering iron and live USB (`server/safety.py`,
   `server/packs/electronics.py`). Parts shelf: 20 electronics cards, 11 linked to products (`data/kb/cards.json`),
   from the 10,001-listing Apify scrape.
2. "Guest / local" flow replaces Private mode: camera to server, router, local grounding, Whisper / local brain /
   Kokoro and back, $0 cloud. The Privacy switches panel shows what stays on our machines and what goes to the cloud
   in a normal call (`1280-privacy-panel.png`, `390-privacy-panel.png`, `1280-flow-guest.png`).
3. Scale panel (header button) with placeholder rows marked "numbers coming" (`1280-scale.png`, `390-scale.png`).
4. A test fails if sink, faucet, valve, plumbing, hinge or breaker appear in the map data, page or script. Panels now
   open below the header controls on desktop.

## Polish round (after SIGN-OFF WITH NOTES, 8 of 10, on b035759)

1. Ambient pulse heads 1.6x the first build (2.4 vs 1.5), thin tails that fade out over the last 10% of each line, so
   nothing smears into a node; the flow packet keeps the full fix-round strength.
2. The fit keeps a band for the legend and its footnote, and includes the zone captions, so in Speed mode Saved
   calls and MEMORY sit clear of the footnote (`1280-speed.png`).
3. At 390 in Cost mode only non-zero values show; $0 local parts show their name, with the footnote "Name only = $0
   (local). Tap a part to see its zone." Selecting a part shows its zone's values (`390-cost.png`,
   `390-cost-selected.png`).
4. Now merged on main and shown as working: parts shelf (39 guide cards linked to scraped product rows, parts note in
   Live context), the router time-scope head and saved-call recall. Time scope: 86% on an independent 300-question set
   with 0 "now" questions held by mistake (coordinator's figure; not in a tracked file), and 96 of 100 with 0 of 20
   "now" held in `router/results/scope_heldout_eval.json`; about 45 ms on CPU (route() median 45.7 ms, commit 7d3ee3f).
   The "building" legend entry is gone because nothing is building now.

## Fix round 1 (after the Media lead FIX on 00c2283)

1. Headline strip under the title: one sentence on what A-Eye does and three chips, voice in 0.6 to 1.1 s, hazard
   stop in 86 ms, ~$1.40 per 2.5 min call (est.). Chips open the matching node. Data in `map-data.json` `headline`.
2. Light: pulse heads about 2.4x bigger (2.8 vs 1.5 world units at the source) with 30-point tails (was 18); the
   camera to server and server to Gemini lines carry 9 pulses each (was 5); landing glow 1.1x halo growth (was 0.45).
   "Ask a question" plays once on a bare load, then the map returns to all flows; not under reduced motion.
3. Composition: the camera fit now projects every node and fits them inside the area below the header strip and
   above the legend; Router, Context builder, Step guide, Safety gates and Privacy switches moved apart.
4. Facts: Recent memory speed is "not measured"; Rewind and Gemini edge costs carry "(est.)".
5. Labels try below, above, right and left before giving up; node labels are never dropped (edge labels may be).
   Chart axes are padded, the unit sits after the last tick, and range captions have a dark halo over mark lines.
6. Phone: flow chips wrap to two rows; the header has a dark scrim so the title is never covered; when a panel opens
   the tagline, chips and flows fold away and the selected node is centred between header and sheet. Flow text moves
   to a bottom card. Index values use the mode colour.

## What it is

- `client-web/map.html`, `map.js`, `map.css`, `map-data.json`; three.js 0.186.1 vendored under
  `client-web/vendor/three/` (MIT, unmodified, source in `vendor/three/VERSION`). No CDN, no remote font or image.
- Real-time three.js scene: orbit, zoom, pan, hover tooltip, click a node or a line for a side panel (bottom sheet
  on phones). Glowing comet pulses travel along curved lines; nodes flash when a pulse lands (additive glow sprites
  and a fresnel rim instead of a post-process bloom pass, so it stays light on phones).
- Label switch: Name (white), Speed (cyan), Cost (amber). Each mode has its own text colour; edges show a label only
  when they carry a value for that mode, so the map stays uncluttered. Overlapping labels are hidden by priority
  (still reachable by hover, click and Index).
- Five flow buttons (Ask a question, Find an object, Hazard stop, Rewind, Private mode) dim everything else and send
  one bright packet hop by hop with a one-line explanation.
- Panels carry "something to look at": measured-time range charts (Gemini, Safety, Grounding, Rewind), router vs
  Haiku vs regex bars (from `router/results/heldout_eval.json`), a memory timeline of where answers about the past come
  from, knowledge cards (Saved calls, Step guide), privacy switches with jump links, and the parts shelf as a
  10,001-point cloud (one point per listing; positions decorative).
- Index button: list twin of the map with shared selection, works with motion off.
- A building item would be drawn dashed/wireframe and labelled "building"; none is building after the polish round.
- URL state for demos and captures: `?mode=speed|cost`, `?select=<node or edge id>`, `?flow=<id>`, `?panel=index`.
- To add a branch later: add a node, edge or flow in `map-data.json`; `client-web/map-data.test.mjs` checks that
  every reference resolves.

## Numbers shown (sources)

| Item | Shown | Source |
|---|---|---|
| End of speech to first voice | 0.6 to 1.1 s | real Live calls tonight, synthetic speech (brief) |
| Box after object named | 1.8 to 2.3 s | same |
| Hazard stop line | 86 ms after speech, Gemini muted | same |
| Router lanes | p50 43 ms, p90 49.5 ms, 96 of 100 held-out | `router/results/heldout_eval.json` |
| Router time scope | 86% of 300 independent, 0 "now" held; 96 of 100 held-out; about 45 ms on CPU | coordinator; `router/results/scope_heldout_eval.json`; commit 7d3ee3f |
| Haiku as router (comparison only) | 97 of 100, p50 803 ms | same file |
| Rewind searchable | about 35 to 40 s; flush now 15 s, not re-measured | brief; code default `REWIND_FLUSH_S` 60 |
| Context builder | every ~4 s; speed per note not measured | `server/context_agent.py` (`interval=4`) |
| Gemini Live cost | ~$0.10 / min, estimate | `GEMINI_LIVE_USD_PER_MINUTE` default, `server/gemini_live.py` |
| Claude cost | $5 / $25 / $0.5 per M input / output / cache read, budget weights | `server/cloud_meter.py` defaults |
| TwelveLabs cost | $0.10 / request default, $0.01 demo override, estimate | `server/cloud_meter.py` |
| One 2.5 min Live call with Rewind | about $1.40 on the meter (overcounts status polls) | brief |
| Local models | $0 | |

Everything else says "not measured".

## Captures (`docs/results/system-map/`)

Headless Chromium 1248 (Playwright) on the real GPU: `ANGLE Metal Renderer: Apple M5 Max`.

| Width | Files |
|---|---|
| 1536 | `1536-name.png` (no rail open, `?still=1`), `1536-reduced.png` (prefers-reduced-motion emulated, no autoplay) |
| 1280 | `1280-name.png` (`?still=1`), `1280-autoplay.png` (bare load, Ask a question playing), `1280-speed.png`, `1280-cost.png`, `1280-router-panel.png`, `1280-safety-panel.png`, `1280-memory-panel.png`, `1280-saved-panel.png`, `1280-flow-hazard.png`, `1280-index.png`, `1280-click-gemini.png` (real mouse click on the node) |
| 390 | `390-name.png`, `390-autoplay.png`, `390-speed.png`, `390-cost.png`, `390-index.png`, `390-router-panel.png` (bottom sheet), all at 2x |
| Crops (2x) | `crop-server-pulses.png`, `crop-gemini.png`, `crop-parts-cloud.png`, `crop-controls.png`, `crop-hover-router.png` (real hover), `crop-look-gemini.png`, `crop-look-safety.png`, `crop-look-rewind.png`, `crop-look-guide.png`, `crop-look-privacy.png` |

Recipe: `python -m http.server 8471 --bind 127.0.0.1` inside `client-web`, then `shoot.py <outdir>`, `crop.py <outdir>`,
`contrast.py <outdir>` from this folder (set `PW_CHROMIUM` if the Playwright browser build differs).

## Measured

| Metric | Result |
|---|---|
| Frame time | p95 16.7 to 16.8 ms, p50 16.7 ms in all captures (about 127 frames each, after 30 warm-up frames; vsync bound at 60 Hz). `frames.json` |
| Label contrast, from pixels | brightest text vs chip median per visible label (chips now 0.9 opaque): worst 9.0:1 (1280 cost), 11.9:1 (1280 speed), 15.0:1 (1536 name), 11.8:1 (390 cost); zone captions worst 6.6:1. `contrast.json` |
| Token contrast, computed | muted #a3afc2 9.1:1 on canvas, 7.2:1 on a bright chip (#1a2232); danger #ff6b78 7.4:1 / 5.8:1; speed 13.8:1; cost 14.4:1 |
| Assets | page code 79.7 KB raw (html 1.8, js 37.9, css 12.4, json 27.6); three.js 829.8 KB raw (core 415.8, module 392.8, OrbitControls 21.1), 199.7 KB gzip |
| Served by the app | `create_app()` static mount returns 200 for map.html, map.js, map-data.json and all three vendor files (TestClient, isolated budget file, LOCAL_ONLY=1) |
| Tests | `node --test client-web/map-data.test.mjs`: 5 pass; `server/test_access.py`: 28 pass |

Drive recipe and Doctor line: N/A (Kyra tools; this is the A-Eye repo).

## Not verified

- Real phone or touch device; 390 is a viewport emulation. Pinch zoom and one-finger orbit not exercised.
- Motion only seen as stills and frame timings; reduced motion checked by emulation in a still, not watched.
- Frame time on a weaker GPU (phone, integrated laptop); only the M5 Max was measured.
- Dimmed labels (opacity 0.16 when something else is selected) are context only and fall below 4.5:1 by design.
- Autoplay seen only as a mid-flow still; the return to all flows after one pass was not watched.
- Bright comets on the main path were judged in stills only; could read as too strong in motion.
- Not loaded through the live server on :8000 (not restarted, as asked); the static mount was checked with TestClient.
- No Media lead sign-off yet.
