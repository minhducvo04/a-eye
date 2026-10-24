# Keyframes result

Implemented change-triggered scene scans and per-session rolling caption memory.

## Changed files

- `server/keyframes.py`: Pillow grayscale signatures, mean absolute difference, configurable keyframe gate, and eight-entry scene memory. Gate comparisons use the last selected scan, not the immediately preceding frame.
- `server/ws2.py`: only scene-loop behavior and required imports changed. Signature work runs in a worker thread. Scans remain serialized, respect camera-off and brain reservations, and honor speech refresh requests after the heartbeat. Logs include reason, cumulative scans/skips, sequence and VLM wall time; session IDs remain hashed.
- `server/agent.py`: session scene state, one shared prompt sentence, and memory in the brain user message. Voice implementation unchanged.
- `server/test_keyframes.py`: synthetic jitter/cuts, gate timing and overrides, 60-second feed, memory merge/limit/ages, brain input, camera-off, speech refresh and pack-reset checks.
- `server/test_agent.py`, `server/test_ws2.py`: shared synthetic frame is now a real Pillow JPEG; corresponding payload assertion updated.
- `server/test_stream.py`, `server/test_rt.py`, `server/test_latency.py`: existing scheduling checks use explicit keyframe heartbeat/min-gap settings instead of the retired scene interval.
- `scripts/keyframe_bench.py`: 300 synthetic frames over 60 seconds through `/ws2`; prints scan count per minute, summed VLM wall time, and exact reasons when supplied the server stdout log.
- `RESULT.md`: this handoff.

## Evidence

The real scene loop, with a fake clock and fake vision, consumed 300 synthetic frames representing 60 seconds at 5 fps: 6 scans and 294 skips. Reasons: first, heartbeat, change, heartbeat, change, heartbeat. This is three scene selections plus three heartbeats, versus the supplied fixed-1-fps baseline of 60 calls/minute. It does not measure GPU time or model accuracy.

Memory keeps the newest eight distinct consecutive captions, merges a repeated newest caption with updated labels/time, and calculates rounded ages from the scanned frame's arrival time. Only the newest entry is marked `now`; camera-off or stale input marks none current. A new hello creates empty memory, verified through the socket with a pack change.

Test: .venv/bin/python -m pytest -q server - PASS (153 passed in 12.09s)
Test: .venv/bin/python -m pytest -q - PASS (375 passed in 13.16s)
Test: .venv/bin/python scripts/keyframe_bench.py --help - PASS (CLI loads and lists options)
Test: git diff --check - PASS (no whitespace errors)

## Limits and integration

- No network benchmark was run here. Against each running old/new server, run `.venv/bin/python scripts/keyframe_bench.py --url ws://127.0.0.1:8000/ws2 --log /path/to/server.jsonl`. The log must capture server stdout. The script filters new log rows by the benchmark's hashed session ID. Old servers without `scene_scan` reasons report `unknown`; no reasons are inferred.
- The clip takes 60 seconds plus a default 26-second final-scan drain. `--drain-s` can shorten that wait for fast/fake vision. Avoid unrelated GPU load when comparing runs. VLM milliseconds are wall time, not GPU busy time.
- The unchanged `v2_metrics` schema forbids extra properties and has no count/reason fields. Socket scan metrics therefore retain `seq` and `vlm_ms` only; counts and reasons are in `scene_scan` logs. `track_ms` is not repurposed. The shared logger allowlist also excludes these fields, so the scene loop emits a fixed metadata-only JSON event with the standard timestamp, level and hashed session fields.
- Scans count attempted calls; skips count newest frames examined but not scanned, not frames overwritten while a dependency is busy. Failed/cancelled scans are logged but do not create memory entries. Regular heartbeats require arriving frames; speech-start refresh can re-scan the cached frame after the heartbeat.
- Contracts, other packages, global settings and trust stores were not edited. No push or publication. Files are left unstaged for the integrator.

Integrator, after rebase on 8422591, real box (scripts/keyframe_bench.py, 60 s synthetic three-scene clip, 5 fps): before (main 8422591, fixed loop) 53 scans/min, 61.0 s of vision time per minute; after 6 scans/min (first 1, change 2, heartbeat 3), 11.1 s per minute (each scan now captions plus grounds with qwen3.5). make browser-smoke PASS on the branch.
