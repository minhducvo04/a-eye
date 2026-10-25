# Gemini vision — lead reviewer handoff

Status: backend implemented in the working tree; **not integration-ready**. No commit made.

## Blocking contract decision

`AGENTS.md` says: “Never change a contract inside a feature branch ‘to make it fit’.”
The existing `v2_hello.cloud` schema has `additionalProperties: false` and permits only Claude,
Cartesia and TwelveLabs. A Google setting cannot travel through the current validated hello.
The requested exception was put to the owner; no answer has arrived yet.

`docs/results/gemini-contract-ui.patch` is a concrete, unapplied patch adding the optional Google
boolean to schema/types/examples and adding the browser switch, persisted preference, hello value,
and disclosure. `git apply --check` passes. Google defaults off. Existing protocol version stays 2.
Apply only after the contract exception is granted, then run contract and browser integration checks.
The scene source is optional, so Gemini omits it and needs no scene-response schema change.

## Implemented

- `vision/gemini.py`: HTTPS inline-image Gemini adapter, environment-only key, no redirects,
  four-second HTTP timeout, no retries, in-memory JPEG downscale to maximum 1280 pixels.
  Native `box_2d` coordinates `[y_min,x_min,y_max,x_max]` / 1000 become normalized xywh.
  Invalid/nonfinite/out-of-range/empty boxes are rejected. Query labels must match.
  No salvaged or guessed malformed output. Failed requests produce `unsure` and no scene objects.
- `vision/app.py`: `gemini` and `cloud_fallback` modes. Service requests default to cloud denied;
  explicit `X-Aeye-Private: 0` and `X-Aeye-Google: 1` are required, and LOCAL_ONLY still wins.
  The trusted internal service reports outgoing calls/bytes in response headers.
- `server/cloud_vision.py`, `server/vision_client.py`, `server/ws2.py`: cloud requests execute with
  the caller's privacy/meter context, in worker threads. Cloud fallback tries Ollama first;
  only timeout/connect errors permit Gemini. The local GPU gate is released before Gemini.
  Direct Gemini bypasses the GPU reservation. Remote vision calls forward consent and import meters.
- `server/privacy.py`: Google defaults off and requires explicit per-call consent. Private and
  LOCAL_ONLY are hard vetoes at the send boundary.
- `vision/ollama.py`: configurable timeout and optional grounding retry, preserving old defaults;
  cloud fallback uses four seconds and one local grounding attempt.
- `scripts/gemini_vision_check.py`: the existing 16 public-image cases and IoU >= .3 scoring;
  reports per-case hits/latencies and total hits, failures, median and interpolated p95. No outputs
  or images are written. Missing key prints exactly `not configured`, exit 2.
- `.env.example`: blank placeholders for GEMINI_API_KEY and GEMINI_VISION_MODEL.
- `vision/test_gemini.py`: tests written before implementation, including Private/Google-off/LOCAL_ONLY,
  positive meter control, resizing, native box conversion, failed requests, service consent,
  fallback error classification, orchestrator context/meter propagation, and GPU gate behavior.

## Model reference

Default: `gemini-3.8-flash`. Verified against Google's current
[image understanding guide](https://ai.google.dev/gemini-api/docs/image-understanding), which uses
that exact identifier. The [2.5 Flash model page](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)
now directs new projects to 3.8 Flash or 3.5 Flash-Lite. GEMINI_VISION_MODEL overrides the default.
No claim of measured Gemini accuracy or availability is made without a configured API run.

## Operation and limits

Set VISION_BACKEND=gemini or cloud_fallback on **both server and vision processes** for matching
routing/gate behavior. Set the Gemini key on the server for the direct orchestrator route (and on
vision if using that service directly). After contract integration, explicitly enable Google in
Settings. Missing consent always abstains; existing browser clients cannot opt in yet.

A four-second timeout is per HTTP request, not a strict entire-operation deadline. Fallback can
include a local attempt plus a cloud attempt. Ollama caption/grounding remain separate requests.
HTTPX connect/read/write timeouts are not a strict wall-clock deadline for a trickling peer.
Model boxes receive heuristic .7 confidence; pin-level and green connection claims are not made.
Gemini verification deliberately abstains because one cloud image is not independent safety proof.
The vision service is an existing trusted internal boundary, not a new public endpoint.

## Validation

Fail-before evidence: `vision/test_gemini.py` initially failed collection with
`ModuleNotFoundError: No module named 'vision.gemini'`.

The first targeted run reported 121 passed / 1 failed because the sandbox denied a loopback bind.
The same suite with loopback permission passed 127 tests. Final summaries are recorded below.

Live benchmark command: `$HOME/Projects/a-eye/.venv/bin/python scripts/gemini_vision_check.py`
Result: `not configured`, exit 2. No Gemini key was available in the process; no `.env` was read,
no live image was uploaded, and no Gemini latency/accuracy result is claimed.

Final targeted command:
`$HOME/Projects/a-eye/.venv/bin/python -m pytest -q vision/ server/test_ws2.py server/test_ws.py server/test_cloud_meter.py voice/test_home_first.py`

Summary: **150 passed in 15.05s**. Loopback permission granted for the existing real socket test.
The `voice/test_home_first.py` assertion was updated to include Google-off and the Google disclosure.

Browser command: `node --test client-web/`
Summary: **tests 151; pass 151; fail 0; cancelled 0; skipped 0; todo 0**.
This verifies the current browser tree, not the unapplied Google UI patch.

`git diff --check`: PASS. `git apply --check docs/results/gemini-contract-ui.patch`: PASS.
The proposed Google hello example was independently validated in memory against the proposed schema.

The first full-suite run was **1 failed, 968 passed, 2 warnings**: the existing provider-defaults
assertion needed Google added. An intermediate rerun was interrupted after 102 passes to include
both the defaults and disclosure-provider assertion fixes. Final full-suite result follows.
