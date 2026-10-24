# Turn latency package

Changed files: `server/agent.py`, `server/ws2.py`, `server/test_stream.py`, `server/test_rt.py`, `server/test_latency.py`, `RESULT.md`.

- Parse the first balanced header object without waiting for a newline; recover the live malformed SAY field and normalize nested draw items, type/kind, roles, empty text and invalid from_target IDs. Filter speech at the shared emission boundary. Shopping fallback remains intact.
- Wake scene refresh on the first audio/interim-text input when the cache is older than 500 ms. Reserve the session against new refreshes from final input through brain completion, including STT. Brain streams bypass an already running scene call, while new scene calls remain blocked during brain streaming. Cached scenes are used immediately; no-cache waits stop after 300 ms without cancelling the refresh.
- Flush the first clause at a comma, semicolon or sentence end after four words and enqueue TTS immediately. Later speech retains sentence splitting. Prompt requests a short first clause.
- For server STT, `first_audio_ms` and `turn_ms` start at receipt of the final audio input, before transcription and cancellation work. Other turns retain their existing timing origin. No schema fields added; STT time is included in those totals, not separately reported or repurposed into `track_ms`. `vlm_ms` measures only the cold-cache wait.

Verification: all seven initial live-format/chunk-boundary and first-clause regression cases failed before implementation. Final tests exercise character-at-a-time and whole-response parsing, safe fallback text, immediate TTS while generation is paused, a one-second scene request with cached brain start within 50 ms, audio and interim-text refresh triggers, refresh exclusion through final-input/brain processing, cold-cache bounds, cancellation and schema-valid messages. Socket tests use the real FastAPI WebSocket lifecycle with fake providers and no network.

Test: .venv/bin/python -m pytest -q server - PASS (111 passed in 5.67s)
Test: .venv/bin/python -m pytest -q - PASS (321 passed in 6.75s)
Test: git diff --check - PASS (no whitespace errors)

Limits: the real GPU stack was not called, so the 1.5 s end-to-speech-to-sound budget is not yet measured for this patch. An existing scene call can overlap the brain and contend for GPU time; it is not remotely cancelled. Cached scenes can be old and retain their source sequence. The model still emits a drawing header before speech. An immediately emitted first clause cannot know whether more tokens will follow: if it is the entire response, its say message retains final=false; turn metrics and TTS final audio still complete normally. The existing audio adapter forwarding retains its one-chunk lookahead. No raw media or secrets recorded; contracts and unowned files unchanged. Changes left unstaged; no push or publication.
