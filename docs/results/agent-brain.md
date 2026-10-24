# agent-brain result

Implemented the independent `/ws2` agent with general, PC-build, cooking and assembly packs, grounded drawing, JSON fallback, in-memory conversation history, fixture-compatible shopping, newest-turn cancellation and cancellable server speech.

Changed files:
- `server/packs/__init__.py`, `general.py`, `pc_build.py`, `cooking.py`, `assemble.py`: pack dataclass, registry, prompts and refusal rules.
- `server/agent.py`: session state, validated turns, target resolution, shopper and bounded history.
- `server/ws2.py`: router, injectable 25-second scene HTTP client, socket validation, frame retention, cancellation and PCM16 streaming.
- `server/app.py`: router import and registration before the static mount only.
- `server/test_agent.py`, `server/test_ws2.py`: offline acceptance tests with synthetic frames and injected vision, model and voice doubles.
- `RESULT.md`: handoff and exact verification results.

Validation:
Test: .venv/bin/python -m pytest -q server - PASS (70 passed in 0.91s)
Test: .venv/bin/python -m pytest -q - PASS (244 passed in 1.35s)
Test: git diff --check - PASS (no whitespace errors)

The server run includes the existing `/ws` full-flow smoke test. New tests exercise real FastAPI WebSocket connections, drawing coordinates, fallback and unknown targets, refusal and power gates, shopper compatibility, history bounds, scene failure reporting, latest-frame retention, replacement-turn cancellation, TTS interruption, final audio chunks and fake-adapter silence. HTTP requests use httpx MockTransport; no external network or real camera/audio input was used.

Integration:
- Optional app-state injections: `vision_v2` with async `call(operation, payload)`, `llm_v2` with blocking `complete(system, user)`, and `voice_factory_v2` returning a voice adapter.
- Hello acknowledges with helper listening. Browser TTS is the default. Power confirmation must be true; false revokes confirmation.
- Outgoing wire types are `say`, `draw`, `audio`, etc., with `v: 2`, as required by the v2 schema definitions.
- Contracts and `server/steps.py` are unchanged. No dependency additions, staging, commits, pushes or publishing.

Limits:
- Cooking and assembly are prompt-only stubs. General refusals use deterministic phrase matching, not a comprehensive semantic safety classifier.
- `brain_turn` cannot express arbitrary freehand points. A target-based path draws the object's rectangular outline. Centers and path edges are clamped to normalized frame bounds.
- No frame means no scene HTTP request and an empty scene; missing/failed vision still permits text replies. Vision unavailability is reported at most once per connection session.
- Cancelling a turn suppresses its later output but cannot terminate an already-running blocking model or market call in `asyncio.to_thread`.
- Speech uses one-chunk lookahead to flag the final chunk. Live Cartesia, live vision and live model providers were not exercised. Shopping defaults to the existing fixture provider; provider failures produce the unconfirmed-fit spoken fallback.
- v2 scene objects have no pin-verification, blur or glare metadata, so the original v1 specialized verification gates remain in `/ws`; v2 pins are visual center markers, not electrical pin verification.
