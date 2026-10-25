# RESULT: System map for judges (pkg/system-map), 2026-10-25

New standalone page `/map.html`: an interactive three.js map of the A-Eye system (data flow, speed and cost per
call), driven by `client-web/map-data.json`. No app screen changed (agent.html, agent.js, agent.css untouched).

### Files changed

- `client-web/map.html`, `map.js`, `map.css`, `map-data.json`: the page and its data.
- `client-web/map-data.test.mjs`: data integrity (links resolve, building work marked, measured numbers, no dashes).
- `client-web/vendor/three/`: three.js 0.186.1 (MIT), core, module and OrbitControls, unmodified; see `VERSION`.
- `docs/results/system-map.md` and `docs/results/system-map/`: captures at 1536, 1280, 390, crops, frame times,
  contrast, capture scripts.

### Limits

Not tried on a real phone; motion seen only as stills; frame time measured only on the M5 Max (p95 16.7 ms).
Parts shelf, router time scope and saved-call recall are shown as building.

Test: `node --test client-web/map-data.test.mjs` - PASS (5 of 5)
Test: `.venv/bin/python -m pytest -q server/test_access.py` - PASS (28 passed)
