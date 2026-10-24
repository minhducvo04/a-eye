"""Cancellable PCM16/16 kHz mono speech from the local GPU box."""
import asyncio
import os

from contracts import validate
from server.box_client import BoxClient
from voice.adapter import VoiceAdapter


class KokoroAdapter(VoiceAdapter):
    def __init__(self, client=None, **kwargs):
        super().__init__(**kwargs)
        self.box = BoxClient(client)
        self.tasks = {}

    def stop(self, utterance_id):
        task = self.tasks.get(utterance_id)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        return super().stop(utterance_id)

    async def say(self, utterance_id, text):
        validate('voice_say', dict(type='say', utterance_id=utterance_id, text=text))
        self._begin(utterance_id)
        self.tasks[utterance_id] = asyncio.current_task()
        try:
            async with self.box.client.stream('POST', self.box.url + '/tts', json=dict(
                    text=text, voice=os.environ.get('KOKORO_VOICE', 'af_heart')), timeout=5) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(2048):
                    if self._stopped(utterance_id):
                        return
                    if chunk:
                        yield chunk
            if not self._stopped(utterance_id):
                self._emit_spoken(utterance_id)
        finally:
            self.tasks.pop(utterance_id, None)
            self._t0.pop(utterance_id, None)
            self._stop.pop(utterance_id, None)

    async def aclose(self):
        await self.box.aclose()
