# stream-turn result

Implemented session background scene refresh, async brain streaming, anchored drawing before speech,
numbered sentence parts, ordered cancellable server audio, and turn/frame metrics. Contracts unchanged.

Files changed:
- server/ws2.py: serial newest-frame refresh governed by SCENE_INTERVAL_MS (default 1000), track and frame
  metrics, scene lifecycle cleanup, turn cancellation, and streaming audio adapter.
- server/agent.py: fresh scene cache, bounded initial wait, streamed header/speech parsing, draw anchors,
  sentence queue, one audio worker per turn (including shopper speech), timing metrics and cancellation guard.
- server/llm.py: async Claude SDK text_stream, Ollama NDJSON, and canned fallback; complete unchanged.
- server/test_agent.py, server/test_ws2.py, server/test_llm.py: updated stream/cache tests and provider fallback checks.
- server/test_stream.py: fake-only acceptance tests for draw/say order, parts/final, contract validation,
  cached/stale/cold scenes, serial interval/latest-frame refresh, track messages, ordered audio, streaming
  before completion and cancellation under 200 ms with no subsequent messages.
- RESULT.md: this handoff.

Verification on the final code:
Test: .venv/bin/python -m pytest -q server - PASS (85 passed in 4.37s)
Test: .venv/bin/python -m pytest -q - PASS (272 passed in 5.08s)
Test: git diff --check - PASS (no whitespace errors)

The server tests exercise the actual ASGI WebSocket route using TestClient and the HTTP scene boundary
using MockTransport. Streaming acceptance tests use synthetic data and fake providers, with no network.
Cancellation test requires stream/audio closure within 200 ms and observes another 210 ms without messages.
The initial-scene timeout test measures a real three-second wait; the refresh remains alive afterward.

Limits:
- Real Claude/Ollama/Cartesia/GPU latency was not benchmarked. The 1.5-second first-sound and one-second
  vision budgets are unverified. Serial scheduling cannot shorten a five-second provider inference.
- With no scene, the explicitly requested initial wait can consume three seconds. Stale scenes are excluded
  without waiting; fresh scene age is measured from response receipt, and draws retain the source frame seq.
- Exactly one nonempty final speech part requires retaining the most recent complete sentence until more
  spoken text or EOF arrives. Other completed sentences are emitted during generation, not after completion.
- Provider fallback applies before any text has been emitted. A failure after partial output ends that
  stream rather than appending a second provider's unrelated header/speech to committed text.
- Browser playback latency is not observable here. first_audio_ms measures the first emitted server audio
  message and is omitted when no server audio is emitted. Existing audio chunk lookahead is retained.
- Refusal/power-gate and confirmation speech keep their existing non-streamed messages. Shopper responses
  retain compatibility/search behavior and now share the turn's ordered audio queue.
- The existing parse_turn helper is retained, although streamed turns no longer call it.

Only owned files changed. No frames/audio persisted, contracts modified, settings changed, commits, pushes,
or publication performed. Files are left unstaged for review; git add was not attempted.
