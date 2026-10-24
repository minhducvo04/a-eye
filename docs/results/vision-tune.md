# vision-tune result

Implemented bounded single-label grounding while preserving 1280 px long-edge images and existing contracts.

Files changed:
- `vision/ollama.py`: fixed 4096 context, 30m model residency, token caps (60 grounding / 40 caption, identify, verify / 1 warm-up), shared HTTP client with 30m connection keep-alive, 8s chat and 2s health timeouts; sequential scene and locate calls capped at three and stopped before further calls after 1.5s; single-box and scene JSON salvage; response timing counters.
- `vision/app.py`: nonblocking daemon-thread warm-up through FastAPI lifespan for Ollama and auto, with one status/ms log line.
- `vision/probe_ollama.py`: `--bench N` runs exactly N synthetic single-label calls and prints per-call timings plus median/min/max wall, load, prompt evaluation and generation ms.
- `vision/test_tune.py`: offline MockTransport regressions for payloads, client reuse, query order/cap, fake-clock budget, locate target priority, warm-up startup behavior, malformed single boxes and benchmark timings.
- `vision/test_ollama.py`, `vision/test_scene.py`: adjusted expectations for intentional single-label payload/response changes; isolated fallback retry test from the new startup call.
- `vision/README.md`: updated behavior, probe usage and limitations.
- `RESULT.md`: this handoff.

Verification:
- New regression suite before implementation: 5 failed, confirming missing tuning behavior.
- Test: .venv/bin/python -m pytest -q vision - PASS (75 passed in 0.86s)
- Test: .venv/bin/python -m pytest -q - PASS (284 passed in 5.34s)
- Test: git diff --check - PASS (no whitespace errors)
- HTTP lifespan and response contracts exercised through FastAPI TestClient; all Ollama traffic uses MockTransport. No GPU/network run was attempted.

Limits and integrator action:
- Run `.venv/bin/python -m vision.probe_ollama --bench 5` on the real box. Offline tests establish behavior, not achieved GPU latency or grounding accuracy. The first sample may be cold; subsequent identical requests may benefit from prompt caching.
- The 1.5s budget stops starting further calls; it does not interrupt an in-flight request. HTTP timeouts apply per operation, not as a total deadline.
- Scene requests with queries return an empty caption. Without queries they return a caption and no boxes. The unchanged contract has no explicit caption flag, so caption plus boxes cannot be explicitly requested in one HTTP request.
- Warm-up never blocks startup; an immediate user request can still overlap loading. The daemon thread is not joined at shutdown.
- Concurrent LLM generation and different context settings from other callers remain outside this package. The orchestrator must schedule grounding separately from LLM generation, and other callers of the vision model must use context 4096.
- Existing auto-mode fake fallback behavior remains unchanged for connection failures/timeouts.
- Only owned files changed. No contracts, global settings or trust stores changed. Files left unstaged; no commit, push or publication.

Integrator real runs on the box from the Mac: probe --bench 5 (same image, prompt cached) median 406 ms [357 to 1748]. Fresh frame each call (the live case), one label, num_ctx 4096: 0.96 to 1.05 s wall (image prompt eval 0.62 s, generation 0.22 s for 36 tokens). Old multi-label prompt: 119 tokens, 0.75 s generation; cold load 2.2 s; switching num_ctx reloaded the model for 6.8 s. That explains the earlier 5 s.
