# A-eye dev targets. Run from the repo root (or a worktree root).
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
SERVER_PORT ?= 8000
VISION_PORT ?= 8001
# Vision backend: fake (canned), ollama (PC GPU), auto (ollama, fake when the PC is unreachable)
VISION_BACKEND ?= auto

# Load local keys from .env (gitignored) into every recipe. Values are never printed.
-include .env
export

.PHONY: setup test test-py test-web vision server dev smoke phone

setup:            ## create .venv and install Python deps
	uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

test: test-py test-web   ## every module's tests

test-py:
	$(PY) -m pytest -q

test-web:
	@if ls client-web/*.test.mjs >/dev/null 2>&1; then node --test client-web/; else echo "no client-web tests yet"; fi

vision:           ## vision service on :8001 (VISION_BACKEND=fake|ollama|auto)
	VISION_BACKEND=$(VISION_BACKEND) $(PY) -m uvicorn vision.app:app --host 0.0.0.0 --port $(VISION_PORT)

server:           ## orchestrator on :8000, serves client-web at / (v1) and /agent.html (v2)
	VISION_URL=http://127.0.0.1:$(VISION_PORT) $(PY) -m uvicorn server.app:app --host 0.0.0.0 --port $(SERVER_PORT)

dev:              ## vision + server together; open http://localhost:8000/agent.html
	$(MAKE) vision & $(MAKE) server; kill %1

phone:            ## print the HTTPS command for iPhone testing (Safari needs HTTPS for camera and mic)
	@echo "Run this yourself (it changes Tailscale settings on this Mac):"
	@echo "  tailscale serve --bg $(SERVER_PORT)"
	@echo "Then open https://<this-mac>.<tailnet>.ts.net/agent.html on the phone (same tailnet)."
	@echo "Stop it with: tailscale serve reset"

smoke:            ## end to end: photo -> server -> fake vision -> box + step
	VISION_BACKEND=fake $(PY) scripts/smoke.py
