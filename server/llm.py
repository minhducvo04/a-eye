"""Text reasoning with code-enforced cloud guards and offline fallback.

Images must be base64 board crops, never full camera frames. The cloud limit
is 400,000 encoded bytes across the request; size cannot prove crop provenance.
No prompts, images, credentials or provider exceptions are logged here.
"""
import asyncio
from contextvars import ContextVar
import base64
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
import os
import re
from time import perf_counter

import anthropic
import httpx


# Benchmarks (docs/pc-benchmarks.md): qwen3.5:9b with think off, about 125 tok/s, 7.3 GB, sits next to the VLM.
LOCAL_DEFAULT = 'qwen3.5:9b-q4_K_M'
_CLIENTS = {}
TURN_USAGE = ContextVar('turn_usage', default=None)


def cached_system(text):
    return [{'type': 'text', 'text': text, 'cache_control': {'type': 'ephemeral'}}]


def usage_counts(message):
    usage = getattr(message, 'usage', None)
    return dict(input_tokens=getattr(usage, 'input_tokens', 0) or 0,
                output_tokens=getattr(usage, 'output_tokens', 0) or 0,
                cache_read_tokens=getattr(usage, 'cache_read_input_tokens', 0) or 0,
                cache_creation_tokens=getattr(usage, 'cache_creation_input_tokens', 0) or 0,
                web_searches=getattr(getattr(usage, 'server_tool_use', None), 'web_search_requests', 0) or 0)



def _shared_async_client():
    """One keep-alive connection pool per event loop: a new connection to the box costs about 340 ms vs 100 ms."""
    import asyncio
    loop = asyncio.get_running_loop()
    client = _CLIENTS.get(id(loop))
    if client is None or client.is_closed:
        client = _CLIENTS[id(loop)] = httpx.AsyncClient(timeout=20)
    return client


def turn_model():
    """Realtime talker model. ANTHROPIC_TURN_MODEL overrides; ANTHROPIC_MODEL stays the planner/complete() model."""
    return os.environ.get('ANTHROPIC_TURN_MODEL', 'claude-haiku-5-5')


def fast_options(model):
    """Lowest-latency settings per model: thinking off where the model allows it, low effort."""
    if model.startswith('claude-haiku-5'):
        return dict(thinking={'type': 'disabled'}, output_config={'effort': 'low'})
    if model.startswith('claude-sonnet-5-5'):
        return dict(thinking={'type': 'between_tools'}, output_config={'effort': 'low'})
    if model.startswith('claude-opus-5-5'):
        return dict(output_config={'effort': 'low'})
    return {}


_ANTHROPIC = {}


def _shared_anthropic():
    """One warm TLS pool per event loop; a fresh client per turn pays the handshake on the voice path."""
    loop = asyncio.get_running_loop()
    client = _ANTHROPIC.get(id(loop))
    if client is None or client.is_closed():
        client = _ANTHROPIC[id(loop)] = anthropic.AsyncAnthropic()
    return client



def _content(user, images):
    """Text, or image crops (JPEG base64) followed by the text."""
    if not images:
        return user
    return [{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': data}}
            for data in images] + [{'type': 'text', 'text': user}]

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
            model = os.environ.get('LOCAL_LLM_MODEL', LOCAL_DEFAULT)
            try:
                message = {'role': 'user', 'content': user}
                if images:
                    message['images'] = images
                payload = {'model': model, 'stream': False, 'think': False,
                           'options': {'num_predict': max_tokens, 'num_ctx': 4096}, 'keep_alive': '30m',
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

    async def stream(self, system: str, user: str, *, max_tokens: int = 512, on_backup=None, model=None,
                     images: list[str] | None = None):
        """Cancellable text stream; fall back only before committing provider text.

        Voice turns default to the Haiku-class talker with thinking off (docs/voice-options.md).
        """
        provider = os.environ.get('LLM_PROVIDER', 'auto')
        use_claude = provider == 'claude' or (
            provider == 'auto' and bool(os.environ.get('ANTHROPIC_API_KEY')))
        emitted = False
        timeout = float(os.environ.get('BRAIN_FIRST_TOKEN_S', '3.5'))
        if images and sum(len(item.encode('utf-8')) for item in images) > 400000:
            images = None  # too large to be a crop: never send it to the cloud
        if use_claude and os.environ.get('LOCAL_ONLY') != '1':
            try:
                async with asyncio.timeout(timeout) as deadline, AsyncExitStack() as stack:
                    client = self._anthropic_client or _shared_anthropic()
                    name = model or turn_model()
                    async with client.messages.stream(
                        model=name, max_tokens=max_tokens, system=cached_system(system),
                        messages=[{'role': 'user', 'content': _content(user, images)}], **fast_options(name),
                    ) as response:
                        async for delta in response.text_stream:
                            if delta:
                                deadline.reschedule(None)
                                emitted = True
                                yield delta
                        if hasattr(response, 'get_final_message'):
                            final = await response.get_final_message()
                            counts = TURN_USAGE.get()
                            if counts is not None:
                                counts.append(usage_counts(final))
                if emitted:
                    return
            except Exception as exc:
                if emitted:
                    raise
                if isinstance(exc, TimeoutError) and on_backup:
                    await on_backup()
        if provider in ('auto', 'claude', 'local'):
            try:
                async with asyncio.timeout(timeout) as deadline, AsyncExitStack() as stack:
                    client = self._httpx_client or _shared_async_client()
                    payload = dict(model=os.environ.get('LOCAL_LLM_MODEL', LOCAL_DEFAULT),
                                   stream=True, think=False, options={'num_predict': max_tokens, 'num_ctx': 4096}, keep_alive='30m',
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
                                deadline.reschedule(None)
                                emitted = True
                                yield delta
                            if chunk.get('done'):
                                break
                if emitted:
                    return
            except Exception as exc:
                if emitted:
                    raise
                if isinstance(exc, TimeoutError) and on_backup:
                    await on_backup()
        try:
            json.loads(user)
        except ValueError:
            yield re.split(r'(?<=[.!?])\s+', user.strip(), maxsplit=1)[0] or 'OK.'
        else:
            yield '{"agent":"helper","draw":[]}\nSAY: The brain is unavailable. Please try again.'

    async def expert(self, system, user, *, model, images=None):
        from server.expert import OPUS, FABLE, LOCAL, cost
        started = perf_counter()
        first = None
        if os.environ.get('LOCAL_ONLY') == '1' or not os.environ.get('ANTHROPIC_API_KEY'):
            model = LOCAL
        counts = usage_counts(None)
        search_errors = 0
        if model == LOCAL:
            client = self._httpx_client or _shared_async_client()
            payload = dict(model=LOCAL, stream=True, think=False,
                           messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}])
            url = os.environ.get('OLLAMA_URL', 'http://100.93.176.7:11434').rstrip('/') + '/api/chat'
            text = ''
            async with client.stream('POST', url, json=payload, timeout=None) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if 'error' in chunk:
                        raise ValueError('Local expert failed')
                    delta = chunk.get('message', {}).get('content', '')
                    if delta and first is None:
                        first = (perf_counter() - started) * 1000
                    text += delta
                    if chunk.get('done'):
                        counts.update(input_tokens=chunk.get('prompt_eval_count', 0),
                                      output_tokens=chunk.get('eval_count', 0))
                        break
        else:
            if images and sum(len(item.encode()) for item in images) > 400000:
                images = None
            client = self._anthropic_client or _shared_anthropic()
            use_tools = True
            retried_tool = retried_model = False
            while True:
                try:
                    options = dict(model=model, max_tokens=2048, system=cached_system(system),
                                   messages=[{'role': 'user', 'content': _content(user, images)}],
                                   output_config={'effort': 'high' if model == FABLE else 'medium'})
                    if use_tools:
                        options.update(tools=[{'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 3}],
                                       tool_choice={'type': 'auto'})
                    text = ''
                    async with client.messages.stream(**options) as response:
                        async for delta in response.text_stream:
                            if delta and first is None:
                                first = (perf_counter() - started) * 1000
                            text += delta
                        final = await response.get_final_message()
                    counts = usage_counts(final)
                    if final.stop_reason == 'refusal':
                        text = "I can't help with that request."
                    else:
                        for block in final.content:
                            if getattr(block, 'type', '') == 'web_search_tool_result':
                                content = getattr(block, 'content', None)
                                if getattr(content, 'type', '') == 'web_search_tool_result_error' or (
                                        isinstance(content, dict) and content.get('type') == 'web_search_tool_result_error'):
                                    search_errors += 1
                    break
                except anthropic.APIStatusError as exc:
                    if exc.status_code != 400 or model != FABLE:
                        raise
                    # Provider diagnostics select retries only; never log them.
                    if use_tools and not retried_tool and ('web_search' in str(exc) or 'tool type' in str(exc)):
                        use_tools = False
                        retried_tool = True
                    elif not retried_model:
                        model = OPUS
                        use_tools = True
                        retried_model = True
                    else:
                        raise
        return dict(text=text or 'I could not reach a conclusion.', metrics=dict(
            model=model, first_token_ms=first, total_ms=(perf_counter() - started) * 1000,
            **counts, web_search_errors=search_errors, cost_usd=cost(model, counts),
            search_cost='UNVERIFIED', search_cost_excluded=True))

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
