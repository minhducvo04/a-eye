# A-eye dev targets. Run from the repo root (or a worktree root).
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
SERVER_PORT ?= 8000
VISION_PORT ?= 8001

.PHONY: setup test test-py test-web vision server dev smoke

setup:            ## create .venv and install Python deps
	uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

test: test-py test-web   ## every module's tests

test-py:
	$(PY) -m pytest -q

test-web:
	@if ls client-web/*.test.mjs >/dev/null 2>&1; then node --test client-web/; else echo "no client-web tests yet"; fi

vision:           ## fake vision service on :8001 (canned boxes)
	$(PY) -m uvicorn vision.app:app --host 0.0.0.0 --port $(VISION_PORT)

server:           ## orchestrator on :8000, serves client-web at /
	VISION_URL=http://127.0.0.1:$(VISION_PORT) $(PY) -m uvicorn server.app:app --host 0.0.0.0 --port $(SERVER_PORT)

dev:              ## vision + server together; open http://localhost:8000
	$(MAKE) vision & $(MAKE) server; kill %1

smoke:            ## end to end: photo -> server -> fake vision -> box + step
	$(PY) scripts/smoke.py
