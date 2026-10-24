# vision-route result

Implemented environment-selected grounding, caption and fallback models. Grounding
now defaults to qwen3.5:9b-q4_K_M; captions and fallback default to
qwen2.5vl:7b-q4_K_M. BOX_FORMATS drives prompts and parsing for pixel, normalized
x,y and Gemma 26b y,x corners. Each failed query retries once, using the fallback
model's format. Health lists ground and caption models and ground GPU residency.
Restored the lost ollama.py implementation and added support for `caption: true`
with queries: grounding runs first, then the caption model fills the caption.

Changed files:
- vision/ollama.py: routing, native formats, fallback, think:false and health.
- vision/probe_ollama.py: --model, per-run and aggregate IoU, actual model used.
- vision/test_route.py: offline MockTransport routing, coordinate, fallback,
  health, clamp and benchmark acceptance tests; caption-with-queries HTTP regression.
- vision/test_ollama.py, vision/test_scene.py, vision/test_tune.py: explicitly
  select the pixel model for existing pixel fixtures; update health and retry counts.
- vision/README.md: configuration, retry behavior and benchmark commands.
- RESULT.md: this handoff.

Test: .venv/bin/python -m pytest -q vision - PASS (94 passed in 1.29s)
Test: .venv/bin/python -m pytest -q - PASS (387 passed in 10.15s)
Test: .venv/bin/python -m vision.probe_ollama --help - PASS (--bench N and --model MODEL exposed)
Test: git diff --check - PASS (no whitespace errors)

Fail-before proof on this restart: `.venv/bin/python -m pytest -q vision/test_route.py`
produced 18 failed, 1 passed in 0.54s, including the new caption-with-queries test.
The restored implementation passed both required suites on their first runs.

Limits: no live GPU/network benchmark was run. All image tests use synthetic
in-memory frames and offline transport. The integrator must compare both models
on the real box with the documented --bench commands; mocked IoU is not accuracy
or latency evidence. Fallback can exceed the 1.5-second new-label budget and
adds another HTTP attempt. Probe wall time includes fallback; Ollama duration
counters describe the last attempt, and the printed model identifies that attempt.
Identify/verify and startup warm-up use the ground model; only caption requests
use the caption model. Auto mode retains existing demo fallback behavior after
both real box attempts fail with connection errors/timeouts.

Contracts, app boundary, fake backend, global settings and trust stores were not
changed. Files are unstaged; no git add, commit, push or publishing was attempted.

Integrator real run on the box (synthetic label image, same image 5 runs): qwen3.5:9b IoU 0.954, 505 ms median wall; qwen2.5vl:7b IoU 0.919, 349 ms. The 16-case benchmark (docs/backend-benchmarks.md) is the accuracy evidence: 15/16 vs 12/16.
