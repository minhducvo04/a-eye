"""Text reasoning with code-enforced cloud guards and offline fallback.

Images must be base64 board crops, never full camera frames. The cloud limit
is 400,000 encoded bytes across the request; size cannot prove crop provenance.
No prompts, images, credentials or provider exceptions are logged here.
"""
import base64
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
import os
import re
from time import perf_counter

import anthropic
import httpx


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    ms: float


class LLMClient:
    def __init__(self, anthropic_client=None, httpx_client=None):
        # Injected clients remain caller-owned. Never store the API key.
        self._anthropic_client = anthropic_client
        self._httpx_client = httpx_client

    def complete(self, system: str, user: str, *, max_tokens: int = 1024,
                 images: list[str] | None = None) -> LLMResult:
        started = perf_counter()
        provider = os.environ.get('LLM_PROVIDER', 'auto')
        cloud_allowed = os.environ.get('LOCAL_ONLY') != '1'
        if images:
            cloud_allowed = cloud_allowed and sum(len(item.encode('utf-8')) for item in images) <= 400000
        use_claude = provider == 'claude' or (
            provider == 'auto' and bool(os.environ.get('ANTHROPIC_API_KEY')))

        def result(text, name, model):
            return LLMResult(text, name, model, (perf_counter() - started) * 1000)

        if use_claude and cloud_allowed:
            model = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5-5')
            try:
                if self._anthropic_client is not None:
                    response = self._claude(self._anthropic_client, model, system, user, max_tokens, images)
                else:
                    with anthropic.Anthropic() as client:
                        response = self._claude(client, model, system, user, max_tokens, images)
                if response.stop_reason != 'refusal':
                    text = '\n'.join(block.text for block in response.content if block.type == 'text')
                    if text.strip():
                        return result(text, 'claude', model)
            except anthropic.RateLimitError:
                pass
            except anthropic.APIConnectionError:
                pass
            except anthropic.APIStatusError:
                pass
            except Exception:
                # Also contain SDK/configuration/response-shape failures.
                pass

        if provider in ('auto', 'claude', 'local'):
            model = os.environ.get('LOCAL_LLM_MODEL', 'gemma4:12b-it-q4_K_M')
            try:
                message = {'role': 'user', 'content': user}
                if images:
                    message['images'] = images
                payload = {'model': model, 'stream': False, 'think': False,
                           'options': {'num_predict': max_tokens},
                           'messages': [{'role': 'system', 'content': system}, message]}
                url = os.environ.get('OLLAMA_URL', 'http://100.93.176.7:11434').rstrip('/') + '/api/chat'
                if self._httpx_client is not None:
                    response = self._httpx_client.post(url, json=payload, timeout=20)
                else:
                    with httpx.Client(timeout=20) as client:
                        response = client.post(url, json=payload, timeout=20)
                response.raise_for_status()
                text = response.json()['message']['content']
                if isinstance(text, str) and text.strip():
                    return result(text, 'local', model)
            except Exception:
                pass

        text = re.split(r'(?<=[.!?])\s+', user.strip(), maxsplit=1)[0] or 'OK.'
        return result(text, 'canned', 'canned')

    async def stream(self, system: str, user: str, *, max_tokens: int = 512):
        """Cancellable text stream; fall back only before committing provider text."""
        provider = os.environ.get('LLM_PROVIDER', 'auto')
        use_claude = provider == 'claude' or (
            provider == 'auto' and bool(os.environ.get('ANTHROPIC_API_KEY')))
        emitted = False
        if use_claude and os.environ.get('LOCAL_ONLY') != '1':
            try:
                async with AsyncExitStack() as stack:
                    client = self._anthropic_client
                    if client is None:
                        client = await stack.enter_async_context(anthropic.AsyncAnthropic())
                    async with client.messages.stream(
                        model=os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5-5'),
                        max_tokens=max_tokens, system=system,
                        messages=[{'role': 'user', 'content': user}],
                    ) as response:
                        async for delta in response.text_stream:
                            if delta:
                                emitted = True
                                yield delta
                if emitted:
                    return
            except Exception:
                if emitted:
                    return
        if provider in ('auto', 'claude', 'local'):
            try:
                async with AsyncExitStack() as stack:
                    client = self._httpx_client
                    if client is None:
                        client = await stack.enter_async_context(httpx.AsyncClient(timeout=20))
                    payload = dict(model=os.environ.get('LOCAL_LLM_MODEL', 'gemma4:12b-it-q4_K_M'),
                                   stream=True, think=False, options={'num_predict': max_tokens},
                                   messages=[{'role': 'system', 'content': system},
                                             {'role': 'user', 'content': user}])
                    url = os.environ.get('OLLAMA_URL', 'http://100.93.176.7:11434').rstrip('/') + '/api/chat'
                    async with client.stream('POST', url, json=payload, timeout=20) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            chunk = json.loads(line)
                            if 'error' in chunk:
                                raise ValueError('Local stream failed')
                            delta = chunk.get('message', {}).get('content', '')
                            if isinstance(delta, str) and delta:
                                emitted = True
                                yield delta
                            if chunk.get('done'):
                                break
                if emitted:
                    return
            except Exception:
                if emitted:
                    return
        yield re.split(r'(?<=[.!?])\s+', user.strip(), maxsplit=1)[0] or 'OK.'

    @staticmethod
    def _claude(client, model, system, user, max_tokens, images):
        content = user
        if images:
            content = []
            for data in images:
                header = base64.b64decode(data[:16])
                media_type = 'image/jpeg'
                if header.startswith(b'\x89PNG'):
                    media_type = 'image/png'
                elif header.startswith(b'GIF8'):
                    media_type = 'image/gif'
                elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
                    media_type = 'image/webp'
                content.append({'type': 'image', 'source': {
                    'type': 'base64', 'media_type': media_type, 'data': data}})
            content.append({'type': 'text', 'text': user})
        return client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                      messages=[{'role': 'user', 'content': content}])
