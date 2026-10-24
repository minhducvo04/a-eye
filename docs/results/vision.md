# Vision package result

Implemented the deterministic fake HTTP API on branch `pkg/vision`.

Files changed:
- `vision/app.py`: FastAPI routes, contract validation, request scenario override and timing.
- `vision/fake.py`: replaceable fake backend with four demo scenarios.
- `vision/fixtures.json`: synthetic demo-b650 header boxes and F_PANEL grid.
- `vision/test_vision.py`: TestClient coverage of endpoints, scenarios, contracts and private error responses.
- `vision/README.md`: usage, backend seam and limitations.
- `RESULT.md`: verification evidence and handoff.

Test: .venv/bin/python -m pytest -q vision - PASS (33 passed, 1 warning in 0.45s)
Test: .venv/bin/python -m pytest -q - PASS (74 passed, 1 warning in 0.42s)

The tests exercised the actual ASGI routes through FastAPI TestClient with synthetic
input strings. Before implementation, the vision test command failed collection
because `vision.app` did not exist. Both final runs emitted the installed
Starlette/httpx TestClient deprecation warning; no dependencies were changed.

Limits:
- The health contract forbids `ms`, so health returns exactly ok/models/fake.
  POST success bodies include measured `ms`. HTTP errors use the short `detail` envelope.
- All detections, pin geometry and verdicts are canned, not physical measurements.
  Default verify accepts even unknown boards. Only locate checks fixture membership.
- Only demo-b650 has fixtures. F_PANEL supplies its full synthetic grid whenever
  want_pins is present; no real grid fitting occurs.
- Images are neither decoded nor persisted, logged or sent to any external service.
- Verification covers the ASGI boundary, not a separate network server or GPU model.
- Contracts and other packages are unchanged. Nothing was pushed or published.
