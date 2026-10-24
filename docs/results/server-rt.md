# server-rt result

Implemented shared app-level GPU priority scheduling, server STT, Kokoro TTS and auto selection, background local-brain warm-up, and opt-in YOLO re-anchoring.

Changed files:
- `server/ws2.py`: priority gate shared across sockets; at most two pack-default scene queries; asynchronous in-memory STT with latest-turn cancellation, one fallback error, and audio barge-in; optional three-request YOLO loop with 320 px JPEGs and scene-ID matching; task/client cleanup.
- `server/box_client.py`: reusable HTTP client for STT and detection, five-second timeouts.
- `voice/kokoro.py`: keep-alive PCM16 streaming, stop/task cancellation and response cleanup.
- `voice/adapter.py`: default `VOICE=auto`, Kokoro health cache for 60 seconds, then keyed Cartesia, then Fake; serialized health checks.
- `server/app.py`: lifespan background warm-up and shutdown cancellation only.
- `server/test_rt.py`, `voice/test_kokoro.py`: 11 new fake-backed tests covering scheduling, STT and fallback, barge-in, streaming/cancellation, auto order/cache, YOLO concurrency/matching/downscaling, and startup.
- `RESULT.md`: this handoff.

Verification:
Test: .venv/bin/python -m pytest -q server voice - PASS (123 passed in 5.32s)
Test: .venv/bin/python -m pytest -q - PASS (288 passed in 5.62s)
Test: git diff --check - PASS (no whitespace errors)

The first scheduling regression failed before implementation because GPUGate did not exist. Tests execute the real FastAPI WebSocket route and HTTP serialization with synthetic audio/images and fake providers. No live GPU performance or boxsvc interoperability claim is made.

Limits:
- GPU scheduling is per app/server process. Other processes or GPU clients are outside this gate. Conservatively, the gate covers the entire turn, including TTS drain and shopper work, so scene refresh can pause beyond the brain stream itself.
- Scene refresh uses the first two pack-default queries. The approximate 0.7-second target depends on the vision host and network; no new latency benchmark was run.
- Audio is memory-only, capped at 60 seconds per utterance. After STT failure the socket switches to browser STT mode; the client must act on the specified fallback error.
- Auto health probing is synchronous for API compatibility; the WebSocket runs adapter selection in a worker thread. Health probes time out after one second and are cached by box URL.
- Optional YOLO (`YOLO_REFRESH=1`) uses label-word matching and nearest box centers, keeps scene IDs, drops older detection results, and silently tolerates detection failures. The browser remains the fast tracker.
- Warm-up is one local Ollama request with a five-second timeout, shared GPU gate, and no startup wait. A cold load taking longer may not finish within that timeout.

Only owned files changed. Contracts, boxsvc, global settings and trust stores were not edited. Files are left unstaged; no commit, push or publish was performed.
