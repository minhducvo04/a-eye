# Fake vision service

Run `make vision` from the repository root to serve `vision.app:app` on port 8001.
Use `GET /health` and JSON `POST /identify`, `/locate`, `/verify` with the request
shapes in `contracts/examples.json`. Requests and successful responses are checked
with `contracts.validate`. Invalid JSON, contract violations and unsupported
scenario names return HTTP 422 with a short message that excludes input values.

`FAKE_SCENARIO` defaults to `ok`. The `X-Fake-Scenario` request header overrides
it for one request without changing other requests:

| Scenario | Behavior |
| --- | --- |
| `ok` | First identification candidate, canned location, passing verification |
| `wrong_header` | Verification fails at confidence 0.9 and names SYS_FAN1 |
| `blurry` | Location not found with blur; verification abstains at confidence 0.3 |
| `unknown_item` | Identification returns unknown at confidence 0.2 |

Other operations retain their default behavior in each scenario. POST results
include elapsed `ms` for parsing, request validation and backend work. `/health`
omits `ms` because the source-of-truth health contract forbids that property.
Error bodies use FastAPI's `detail` envelope; no vision error contract exists.

`fixtures.json` contains synthetic normalized `[x, y, w, h]` boxes for demo-b650.
Unknown boards or headers are not found. Only F_PANEL requests containing
`want_pins` receive the canned pin grid and `pin_ok: true`; this includes an empty
list. The grid is a full synthetic header grid, not a measurement of requested
pins. These coordinates are not suitable for guiding work on a real board.

`app.py` owns HTTP parsing, validation, scenario selection and timing. Its
`backend` object exposes `health()`, `identify(body, scenario)`,
`locate(body, scenario)` and `verify(body, scenario)`; replace that object to
integrate a real model. Backend POST methods return response fields without `ms`.
The fake ignores image contents and performs no decoding, storage, logging or
network calls. Verification deliberately succeeds by default even for unknown
boards; it is a demo stub, not a safety or physical-connection check.

Test with `.venv/bin/python -m pytest -q vision` (synthetic inputs only).
