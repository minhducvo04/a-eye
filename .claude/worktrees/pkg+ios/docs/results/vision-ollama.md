# vision-ollama result

Implemented the Ollama backend and per-request automatic fake fallback. Only
owned files changed; contracts and dependencies are unchanged.

Files changed:
- `vision/ollama.py`: injectable httpx client/transport, environment configuration,
  in-memory 1280-long-side JPEG resizing, fenced/prose JSON parsing, board-table
  label matching, clipped normalized boxes, closed-set identification, capped
  verification confidence, GPU residency health and connection/timeout fallback.
- `vision/app.py`: environment-based backend selection only; default remains fake.
- `vision/probe_ollama.py`: synthetic board CLI printing health, label IoU and ms.
- `vision/test_ollama.py`: 24 mocked tests covering the new backend, HTTP fallback
  and recovery, portrait/landscape resizing, aliases, probe output and contracts.
- `vision/README.md`: configuration, confidence rules, fallback behavior and probe.
- `RESULT.md`: this handoff and observed checks.

Test: .venv/bin/python -m pytest -q vision - PASS (57 passed in 0.66s)
Test: .venv/bin/python -m pytest -q - PASS (191 passed in 0.96s)
Test: git diff --check - PASS (no output)

The first acceptance-test run failed because `vision.ollama` did not yet exist.
The probe test initially used exact floating-point equality; it now uses an
approximate comparison. The final commands above ran after that correction.
All HTTP calls in tests used MockTransport; existing fake HTTP tests stayed green.

Limitations and integration handoff:
- No real-PC request was attempted: network access is unavailable for this task.
  The integrator must run `.venv/bin/python -m vision.probe_ollama` from the repo
  root with PC access and retain its health/IoU/ms output. GPU accuracy and warm
  latency are not verified by these tests. The supplied measured latency is
  documented as prior evidence, not a measurement from this run.
- Locate produces silkscreen text boxes, never pins. Confidence is heuristic:
  exact matches 0.7; unique fuzzy matches with similarity >= 0.8 get 0.5.
- Verify confidence is 0.75 and cannot clear the server's 0.8 green gate. There is
  no independent blur/glare, pin alignment or seating measurement in this backend.
- Auto mode uses existing fake demo answers on connection errors and timeouts,
  including fake passing verification. Health retries the PC and reports fake
  when that health request falls back. HTTP errors do not trigger fallback.
- HTTP timeouts are 20 seconds for chat and 2 seconds per health GET, using httpx
  operation timeout semantics rather than a total request deadline.
- Only the existing demo board table is present; real boards need hand-checked
  tables supplied by their owner.

Files are left unstaged. No commit, push, publication, network install, global
settings change, or trust-store change was performed.

Integrator real run (probe_ollama, synthetic labels, PC GPU): CPU_FAN found, IoU 0.787, 1845 ms warm (6377 ms cold), health gpu=gpu.
