# vision-scene result

Implemented POST /scene with contract validation, scenario selection and timing.
Fake, Ollama and Auto backends support query-first objects, sequential IDs and
the requested object cap. Ollama uses one chat call, resized-image pixel boxes,
clipping and zero-area rejection. Added a synthetic --scene probe.

Files changed:
- vision/app.py
- vision/fake.py
- vision/ollama.py
- vision/probe_ollama.py
- vision/test_scene.py
- vision/README.md
- RESULT.md

Validation used synthetic inputs only, with the real FastAPI boundary exercised
through TestClient and Ollama HTTP mocked. The new tests first failed (10 failed)
before implementation because the route, backend methods and flag were absent.

Test: .venv/bin/python -m pytest -q vision - PASS (67 passed in 0.65s)
Test: .venv/bin/python -m pytest -q - PASS (237 passed in 1.48s)
Test: git diff --check - PASS (no whitespace errors)

Limits: no network or real GPU/model call was made. The integrator must run
`.venv/bin/python -m vision.probe_ollama --scene` on the PC to check real grounding.
Confidence is heuristic (0.7 for query labels, 0.5 otherwise), not calibrated.
The prompt requests verbatim query labels; paraphrases are treated as other
objects. Ollama does not independently assess blur. Fake results are canned demo
data, including when Auto falls back. The object cap wins when queries exceed it.

Contracts and other packages are unchanged. Files are left unstaged; no commit,
push, publication, global settings or trust-store changes were made.

Integrator: live Qwen output had broken JSON (box closed with "}"); added salvage_scene regex fallback + test. Real run on PC GPU: 3 objects grounded, 5.2 s at 1280 px (over the 1 s budget; image size to tune from docs/pc-benchmarks.md).
