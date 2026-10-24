# pipe-server result

Implemented immediate final-input acknowledgement; received/transcribing/thinking/backup/speaking and exactly one terminal stage per socket turn; shared turn IDs through STT, reply deltas, speech and metrics; process-wide median of the last five received-to-first-say samples.

Brain providers have a first-token deadline (`BRAIN_FIRST_TOKEN_S`, default 3.5 seconds). Timeout closes the stalled stream and advances through the configured Claude/local/canned order. Partial-stream errors fail the turn. Canned v2 replies use a valid speech header and never echo the JSON prompt.

Speech-only reply deltas coalesce at 80 ms intervals. Camera-off drops cached images/scenes, cancels refresh work and disables drawings. Camera-on accepts new frames again. Scene refresh requires a new frame sequence and respects brain reservations; turns discard grounding when the latest frame has aged beyond three seconds.

Stage events use the existing JSON logger: `turn_received`, `turn_transcribing`, `turn_thinking`, `turn_backup`, `turn_speaking`, `turn_done`, `turn_failed`, `turn_cancelled`. Their `ms` is elapsed time from received, so thinking/first-say/completion timings are available without logging transcripts. Existing metrics remain intact.

## Changed files

- `server/ws2.py`: acknowledgement, lifecycle, STT handling, provider backup notification, camera and scene scheduling.
- `server/agent.py`: turn stages and median, frame-age checks, camera-off prompt/drawing guard, coalesced deltas, safety-reply server audio.
- `server/llm.py`: first-token timeout and safe v2 canned response.
- `server/mock.py`: camera-off voice-only reply.
- `server/test_pipeline.py`: new network-free acceptance regressions through the real ASGI WebSocket route and injected dependencies.
- `server/test_agent.py`, `server/test_stream.py`, `server/test_ws2.py`: expected additive messages.
- `server/test_latency.py`: refresh-priority test now supplies a new frame instead of expecting a same-frame rescan.
- `RESULT.md`: this handoff.

## Verification

Initial regressions failed for missing acknowledgement and same-frame rescan. The completed checks cover stage order, empty STT, same-ID Claude-to-local and local-to-canned timeout fallback, cancellation and failure, delta ordering/coalescing, camera off/resume, stale frames, median, private logs and safety-reply audio. Existing GPU exclusion tests pass.

Test: .venv/bin/python -m pytest -q - PASS (358 passed in 10.02s)
Test: git diff --check - PASS (no whitespace errors)

## Limits

- Verified with synthetic dependencies and actual in-process ASGI WebSocket sessions; no live GPU/provider latency claim.
- Frame age uses server receipt monotonic time, avoiding client clock skew.
- `typical_ms` is omitted until the process has a first-say sample; turns without speech supply no sample.
- The deadline covers first token only; existing provider transport timeouts handle later stalls.
- Canned fallback is a successful offline reply; thrown turn/provider errors produce `failed`.
- Contracts, logger/API files, global settings and trust stores were not edited. Files remain unstaged; no commit, push or publication.
