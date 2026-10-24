"""In-process voice adapter: TTS chunks out, transcripts and barge-in events in."""
from __future__ import annotations

import os
import time
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any

from contracts import validate

SAMPLE_RATE = 16000


class VoiceAdapter:
    """Base adapter. Orchestrator calls these methods in process."""

    def __init__(self, on_event: Callable[[dict], None] | None = None) -> None:
        self.on_event = on_event
        self.last_event: dict | None = None
        self._t0: dict[str, float] = {}
        self._stop: dict[str, bool] = {}

    def _begin(self, utterance_id: str) -> None:
        self._t0[utterance_id] = time.monotonic()
        self._stop[utterance_id] = False

    def _stopped(self, utterance_id: str) -> bool:
        return bool(self._stop.get(utterance_id))

    def _elapsed_ms(self, utterance_id: str) -> int:
        t0 = self._t0.get(utterance_id)
        if t0 is None:
            return 0
        return max(0, int((time.monotonic() - t0) * 1000))

    def _emit(self, event: dict) -> dict:
        self.last_event = event
        if self.on_event is not None:
            self.on_event(event)
        return event

    def _emit_spoken(self, utterance_id: str) -> dict:
        event = {"type": "spoken", "utterance_id": utterance_id}
        validate("voice_spoken", event)
        return self._emit(event)

    async def say(self, utterance_id: str, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError

    def stop(self, utterance_id: str) -> dict:
        """Stop TTS for this utterance. Returns a voice_barge_in event."""
        self._stop[utterance_id] = True
        event = {
            "type": "barge_in",
            "utterance_id": utterance_id,
            "at_ms": self._elapsed_ms(utterance_id),
        }
        validate("voice_barge_in", event)
        return self._emit(event)

    async def transcribe(self, pcm16: bytes) -> dict:
        raise NotImplementedError


_health_cache = {}
_health_lock = threading.Lock()


def _kokoro_available():
    with _health_lock:
        return _check_kokoro()


def _check_kokoro():
    # make_adapter is synchronous; socket callers run it in a worker thread.
    import httpx
    from server.box_client import box_url
    url = box_url()
    cached = _health_cache.get(url)
    if cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    try:
        with httpx.Client(timeout=1) as client:
            response = client.get(url + '/health')
            response.raise_for_status()
            available = response.json().get('tts') is True
    except Exception:
        available = False
    _health_cache[url] = (time.monotonic(), available)
    return available


def make_adapter(**kwargs: Any) -> VoiceAdapter:
    """Prefer local Kokoro, then configured Cartesia, then browser speech."""
    mode = os.environ.get('VOICE', 'auto')
    if mode == 'kokoro' or (mode == 'auto' and _kokoro_available()):
        from voice.kokoro import KokoroAdapter
        return KokoroAdapter(**kwargs)
    if mode in ('auto', 'cartesia') and os.environ.get('CARTESIA_API_KEY'):
        from voice.cartesia import CartesiaAdapter
        return CartesiaAdapter(**kwargs)
    from voice.fake import FakeAdapter
    return FakeAdapter(**kwargs)
