# boxsvc result

Implemented the GPU-box FastAPI service with background model initialization,
independent readiness flags and 503 responses, injectable engines, in-memory
media handling, streaming PCM16 conversion, and normalized detection boxes.

Files changed:
- `boxsvc/__init__.py`
- `boxsvc/app.py`
- `boxsvc/engines.py`
- `boxsvc/test_boxsvc.py`
- `boxsvc/run_box.ps1`
- `boxsvc/README.md`
- `pyproject.toml`: added only `"boxsvc"` to `testpaths`.
- `RESULT.md`

Test: .venv/bin/python -m pytest -q boxsvc - PASS (11 passed in 1.16s)
Test: .venv/bin/python -m pytest -q - PASS (288 passed in 5.17s)
Test: git diff --check - PASS (no whitespace errors)

Tests exercised real FastAPI routes through TestClient with fake engines:
health readiness, transcription and timing, 24-to-16 kHz resampling and signed
PCM16 bytes, streamed segment content and first-chunk logging, pixel-box
normalization, missing engines, startup library failures, sanitized invalid
inputs, and no disk writes or media/text logging during requests.

Live startup proof (uvicorn on `127.0.0.1:18090`):
```
INFO:     Application startup complete.
stt: model unavailable (ModuleNotFoundError)
tts: model unavailable (ModuleNotFoundError)
detect: model unavailable (ModuleNotFoundError)
ERROR:    [Errno 1] error while attempting to bind on address ('127.0.0.1', 18090): operation not permitted
```
The sandbox blocked the bind. The escalation attempt was rejected with
`approval request failed`; therefore the live HTTP check is BLOCKED, not passed.
The temporary process exited. No GPU box connection or deployment was made.

Limits / integrator verification:
- UNVERIFIED installed Kokoro API: `KPipeline(lang_code="a", device=device)`
  and `self.pipeline(text, voice=voice)` yielding `(_, _, audio)` at 24 kHz.
  Kokoro is not installed on this Mac, so installed-API inspection was unavailable.
- UNVERIFIED live faster-whisper calls: `WhisperModel(model, device=device,
  compute_type="float16")` on CUDA and `model.transcribe(audio,
  language=language, beam_size=1, vad_filter=False)`. CPU uses int8.
- UNVERIFIED live ultralytics calls: `YOLO(weights)` and
  `model.predict(source=image, imgsz=imgsz, conf=conf, device=device,
  half=device == "cuda", verbose=False, save=False)` and result tensor access.
- Model packages, CUDA execution, Windows PowerShell startup, GPU latency,
  concurrent model VRAM usage, and actual Kokoro segmentation need a box run.
- Startup may download model weights to library caches; request media is never
  saved. Initializations run sequentially in a background thread. An endpoint
  remains 503 until ready; a failed engine requires restart to retry.
- Standard-library linear interpolation avoids adding NumPy to the Mac's
  dependencies; live Whisper still uses its installed NumPy dependency.
- Stream failures after headers cannot become HTTP 503; clients must handle
  interrupted playback. Linear resampling is intentionally simple, with no
  antialias filter and at most one discarded output sample per segment.
- The required launcher binds all interfaces. Tailnet-only access requires the
  integrator's Tailscale-IP bind or firewall restriction, as documented.
- Files are unstaged; no staging, commit, push, or publication was attempted.
