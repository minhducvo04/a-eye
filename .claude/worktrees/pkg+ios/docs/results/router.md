# Router package result

Changed files:
- `server/llm.py`: synchronous reasoning router, injectable clients, Claude/local/canned fallback, cloud privacy guards, and result timing across all attempts.
- `server/llm_probe.py`: executable CLI printing provider, model, elapsed milliseconds, and text.
- `server/test_llm.py`: 20 offline cases using a fake Anthropic client and httpx MockTransport.
- `RESULT.md`: verification and handoff notes.

Test: .venv/bin/python -m pytest -q server/test_llm.py - PASS (20 passed in 1.34s)
Test: .venv/bin/python -m pytest -q - PASS (187 passed in 1.34s)

The initial targeted run failed with `ModuleNotFoundError: No module named 'server.llm'` before implementation.

Offline CLI proof:
```text
$ env LLM_PROVIDER=canned .venv/bin/python -m server.llm_probe 'Where does the CPU fan connect?'
provider=canned model=canned ms=0.0
Where does the CPU fan connect?
```

Limits and integrator handoff:
- No network calls were attempted. The integrator must run `.venv/bin/python -m server.llm_probe "<question>"` with the intended provider environment for live API proof; confirm the printed provider to distinguish a live answer from fallback.
- The cloud size limit is conservatively 400,000 UTF-8 bytes across all base64 images in a request. Size alone cannot identify full camera frames: callers must provide only board crops. LOCAL_ONLY=1 blocks all Claude requests.
- Image inputs are bare base64 strings; PNG, GIF, and WebP signatures are recognized, with JPEG as the default. Data URLs are not supported.
- Canned output repeats the first sentence (or OK. for blank input); it is an availability fallback, not a model-generated explanation or a safety/compatibility verdict. Existing orchestrator gates still apply.
- SDK retries use Anthropic defaults; the local request uses a 20-second httpx timeout. No overall deadline is imposed across attempts.
- Unknown provider values fall directly to canned. Empty or malformed provider responses also fall back.
- Injected clients remain caller-owned; internally created clients are closed after use. The router logs no payloads or exceptions and does not store the API key.
- No contracts or other package files changed. Files are unstaged; no staging, commit, push, or publication was attempted.

Integrator: added think:false for Ollama (warm probe 2.5 s vs 5.5 s). Real run: provider=local model=gemma4:12b-it-q4_K_M ms=2464. Claude path untested (no key yet).
