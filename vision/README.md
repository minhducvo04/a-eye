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
`qwen2.5vl:7b-q4_K_M`. Chat requests use an 8-second HTTP timeout; each health GET
uses 2 seconds. `/health` checks `/api/tags` for availability and `/api/ps` for
residency. It reports `gpu`, `partial`, `cpu`, or `not_loaded`; `ok` is false when
the configured model is absent from tags. This exposes CPU fallback after reboot.
These are httpx operation timeouts, not a total wall-clock deadline.

Images are decoded and resized in memory with Pillow: the longer side is exactly
1280 pixels, preserving aspect ratio to the nearest pixel. Returned pixel corners
are normalized against that resized image, clipped, and converted to `[x,y,w,h]`.
No frames are saved or logged. Every generation uses temperature 0, `num_ctx: 4096`
and `keep_alive: "30m"`. Token caps are 60 for boxes, 40 for captions,
identification and verification, and 1 for warm-up. One shared `httpx.Client`
reuses connections (keep-alive expiry 30 minutes), including health requests.
Fenced JSON, trailing prose and broken closing brackets on labelled boxes are
accepted; invalid/empty boxes are still discarded.

At startup, Ollama and auto backends send a synthetic 1280×960 warm-up in a daemon
thread. Startup and shutdown do not wait for it; one status/timing line is logged.
A user request arriving immediately can still encounter cold loading. Warm-up
failure does not switch the configured backend or prevent later retries.

Locate requests the target silkscreen first, then at most two other board-table
labels, one per call in table order. It stops starting calls after 1.5 seconds.
It returns text boxes, never connector or pin grids. Header names and silkscreen
aliases match case-insensitively with underscores and whitespace ignored. Exact
matches get 0.7 confidence; a unique best SequenceMatcher ratio of at least 0.8
gets 0.5. These scores are heuristics, not calibrated probabilities. Ambiguous
fuzzy matches are omitted. Unknown boards/headers and invalid boxes yield not found.

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
were supplied. Ollama processes only the first three queries, in order.

Fake scenes use query labels verbatim at fixed spread-out positions, then canned
motherboard, fan cable and table objects within the cap. The `blurry` scenario
returns no objects and caption `too blurry to see`; other scenarios use the
normal canned scene. These objects do not describe the submitted image.

Ollama scenes send one label per call, sequentially, at 1280 pixels long edge.
Only matching query labels are returned, with heuristic confidence 0.7 and
consecutive IDs. No extra salient objects are requested. Further calls stop once
1.5 seconds have elapsed or `max_objects` is reached; a call already in flight
can exceed this budget, up to the HTTP operation timeout. Empty or malformed
answers contribute no boxes. Partial results survive budget exhaustion.

With queries, `caption` is an empty string. Without queries, one short caption
call returns no boxes (or `Could not describe the frame.` on parse failure).
The unchanged request contract has no explicit caption flag; omit queries to
request a caption. Fake scene behavior remains unchanged. Auto mode still falls
back on connection errors/timeouts. Ollama does not independently detect blur.

Run the additional synthetic scene probe on the real PC:

```sh
.venv/bin/python -m vision.probe_ollama --scene
```

It draws labelled red, blue and green shapes in memory, queries `red square`, and
prints health, caption, objects and milliseconds without printing or saving the
image. Offline tests exercise the HTTP boundary and mocked Ollama transport;
they do not establish real-model grounding accuracy.

## Latency breakdown

```sh
.venv/bin/python -m vision.probe_ollama --bench 5
```

Runs exactly N single-label scene requests against synthetic shapes using the
same client. Prints each wall time and Ollama's `load_duration`,
`prompt_eval_duration`, and `eval_duration` converted from nanoseconds to ms,
then median/min/max for each. Missing counters are reported as unavailable.
The first request is included and may be cold. Repeated identical synthetic
requests can benefit from prompt caching; this is a diagnostic, not an uncached
accuracy or production-latency benchmark. It never saves or prints the image.

See `docs/pc-benchmarks.md` for measured GPU results. The integrator must run this
probe on the real box; offline tests cannot establish the speedup. Scheduling
LLM speech generation outside grounding calls belongs to the orchestrator and
cannot be enforced in this package. Other callers sharing this model must also
keep `num_ctx` at 4096 to avoid reloads.
