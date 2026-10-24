"""Keep tests hermetic: `make` exports .env, so clear runtime switches and keys before each test."""
import pytest

RUNTIME_ENV = [
    "VISION_BACKEND", "VISION_URL", "VISION_MODEL", "OLLAMA_URL", "FAKE_SCENARIO",
    "LLM_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "LOCAL_LLM_MODEL", "LOCAL_ONLY",
    "VOICE", "CARTESIA_API_KEY", "CARTESIA_VOICE_ID", "FAKE_TRANSCRIPT",
    "MARKET_SOURCE", "APIFY_TOKEN", "BRIGHTDATA_API_KEY", "BRIGHTDATA_ZONE",
    "BOX_URL", "YOLO_REFRESH", "STT_MODEL", "YOLO_WEIGHTS", "KOKORO_DIR",
]
# The GPU box is live on the tailnet now; point tests at a closed local port so nothing reaches it.
UNREACHABLE_BOX = "http://127.0.0.1:9"


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for name in RUNTIME_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOX_URL", UNREACHABLE_BOX)


# Some modules pick a backend at import time, so also clear the switches before any test module loads.
import os  # noqa: E402

for _name in RUNTIME_ENV:
    os.environ.pop(_name, None)
os.environ["BOX_URL"] = UNREACHABLE_BOX
