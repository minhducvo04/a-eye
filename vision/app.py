"""Vision HTTP boundary: contract validation and timing around a backend."""
import json
import os
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from jsonschema import ValidationError

from contracts import validate
from vision.fake import FakeBackend, SCENARIOS


app = FastAPI(title="A-eye fake vision")
def select_backend(ollama=None):
    mode = os.environ.get("VISION_BACKEND", "fake")
    if mode == "fake":
        return FakeBackend()
    if mode not in {"ollama", "auto"}:
        raise ValueError("VISION_BACKEND must be fake, ollama, or auto")
    from vision.ollama import AutoBackend, OllamaBackend
    real = ollama if ollama is not None else OllamaBackend()
    return AutoBackend(real, FakeBackend()) if mode == "auto" else real


backend = select_backend()


async def run(request, operation):
    started = perf_counter()
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="Invalid JSON body") from None
    try:
        validate(operation + "_request", body)
    except ValidationError:
        # ValidationError text can contain image data. Never echo or log it.
        raise HTTPException(status_code=422, detail="Invalid " + operation + " request") from None
    scenario = request.headers.get("X-Fake-Scenario", os.environ.get("FAKE_SCENARIO", "ok"))
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=422, detail="Invalid fake scenario")
    result = getattr(backend, operation)(body, scenario)
    result["ms"] = (perf_counter() - started) * 1000
    validate(operation + "_response", result)
    return result


@app.get("/health")
def health():
    result = backend.health()
    # health_response disallows ms; keep the contract unchanged.
    validate("health_response", result)
    return result


@app.post("/identify")
async def identify(request: Request):
    return await run(request, "identify")


@app.post("/locate")
async def locate(request: Request):
    return await run(request, "locate")


@app.post("/verify")
async def verify(request: Request):
    return await run(request, "verify")
