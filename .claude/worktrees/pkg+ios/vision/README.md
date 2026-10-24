# Fake vision service

Run `make vision` from the repository root to serve `vision.app:app` on port 8001.
Use `GET /health` and JSON `POST /identify`, `/locate`, `/verify`, `/scene` with the request
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
`locate(body, scenario)`, `verify(body, scenario)` and `scene(body, scenario)`; replace that object to
integrate a real model. Backend POST methods return response fields without `ms`.
The fake ignores image contents and performs no decoding, storage, logging or
network calls. Verification deliberately succeeds by default even for unknown
boards; it is a demo stub, not a safety or physical-connection check.

Test with `.venv/bin/python -m pytest -q vision` (synthetic inputs only).

## Ollama on the team PC

Choose the backend before starting the service:

```sh
VISION_BACKEND=ollama make vision
VISION_BACKEND=auto make vision
```

`VISION_BACKEND` defaults to `fake`. `ollama` uses the PC directly; `auto` retries
Ollama on every request and uses fake demo responses on connection errors or
timeouts. A failed health request returns `fake: true, models: ["fake"]`; the
reason is logged only as `ollama unreachable, using fake`. No extra reason field
is added to health. HTTP errors and malformed model answers do not trigger demo
fallback. Auto mode inherits the fake backend's canned passing verdicts, so its
results are for demos, not physical connection assurance.

`OLLAMA_URL` defaults to `http://100.93.176.7:11434`; `VISION_MODEL` defaults to
`qwen2.5vl:7b-q4_K_M`. Chat requests use a 20-second HTTP timeout; each health GET
uses 2 seconds. `/health` checks `/api/tags` for availability and `/api/ps` for
residency. It reports `gpu`, `partial`, `cpu`, or `not_loaded`; `ok` is false when
the configured model is absent from tags. This exposes CPU fallback after reboot.
These are httpx operation timeouts, not a total wall-clock deadline.

Images are decoded and resized in memory with Pillow: the longer side is exactly
1280 pixels, preserving aspect ratio to the nearest pixel. Returned pixel corners
are normalized against that resized image, clipped, and converted to `[x,y,w,h]`.
No frames are saved or logged. The model uses temperature zero and no Ollama
`format` option; fenced JSON and trailing prose are accepted. Measured warm calls
were roughly 1.4 seconds at 640x480 and 3 seconds at 1280x960; this backend always
sends the resized image, and the first call can include model loading.

Locate searches all board-table silkscreen labels in one call and returns text
boxes, never connector or pin grids. Header names and silkscreen aliases match
case-insensitively with underscores and whitespace ignored. Exact matches get
0.7 confidence; a unique best SequenceMatcher ratio of at least 0.8 gets 0.5.
These scores are heuristics, not calibrated probabilities. Ambiguous fuzzy
matches are omitted. Unknown boards/headers and invalid boxes yield not found.

Identify is limited to the supplied candidates and caps confidence at 0.85.
Verify requires a boolean `plugged` and an exact board-label match to pass. Its
confidence is always 0.75, below the 0.8 green gate: the VLM alone must never
produce a green tick. Unparseable verification abstains at 0.3. The fake scenario
argument is ignored by Ollama. Blur, glare and connector seating are not
independently measured here; downstream freshness/confidence gates still apply.

Run the synthetic-only real-PC probe from the repo root:

```sh
.venv/bin/python -m vision.probe_ollama
```

It draws CPU_FAN, SYS_FAN1 and F_PANEL on a dark green image in memory, prints
health first, then CPU_FAN text-box IoU and latency. It uses Ollama directly so an
unreachable PC cannot produce a misleading fake success. The integrator must run
this on a machine with PC access; mocked tests do not establish GPU accuracy.
`OllamaBackend(client=...)` or `OllamaBackend(transport=httpx.MockTransport(...))`
allows offline testing. Callers supplying a client retain ownership of it.

## General scene grounding

`POST /scene` accepts `image_b64`, optional `queries` (up to eight strings), and
optional `max_objects` (1–20, default 8). It returns a short `caption`, `objects`
with consecutive `o1`, `o2`, … IDs, normalized `[x,y,w,h]` boxes and confidence,
plus `source` and measured `ms`. The object cap applies even if more queries
were supplied. Query matches precede other salient objects.

Fake scenes use query labels verbatim at fixed spread-out positions, then canned
motherboard, fan cable and table objects within the cap. The `blurry` scenario
returns no objects and caption `too blurry to see`; other scenarios use the
normal canned scene. These objects do not describe the submitted image.

Ollama scenes use one chat call and the same 1280-pixel resize and fenced-JSON
parser as locate. The prompt asks for visible query matches first, labelled with
the exact query text, followed by other salient objects. Code orders matches by
query order, enforces the cap, clips boxes to the image and drops zero-area or
invalid boxes. Labels match queries with case, whitespace and underscores
ignored. Query matches receive 0.7 confidence and other objects 0.5: these are
heuristics, not calibrated scores. If the model paraphrases a query label, it is
treated as an ordinary object. Unparseable answers return an empty scene with
`Could not describe the frame.`; invalid object rows are omitted. Ollama ignores
fake scenarios and does not independently detect blur. Auto mode falls back to
fake on connection errors and timeouts, as with the other endpoints.

Run the additional synthetic scene probe on the real PC:

```sh
.venv/bin/python -m vision.probe_ollama --scene
```

It draws labelled red, blue and green shapes in memory, queries `red square`, and
prints health, caption, objects and milliseconds without printing or saving the
image. Offline tests exercise the HTTP boundary and mocked Ollama transport;
they do not establish real-model grounding accuracy.
