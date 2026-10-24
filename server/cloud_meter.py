"""Per-call outgoing request evidence; no payloads or credentials are retained.

All HTTPX sends are metered centrally (including SDK retries and redirects), so adding
an HTTP provider cannot silently omit accounting. Conservatively includes other public
HTTP requests made by the call. Bytes are request bodies / WebSocket message payloads,
not responses, headers, TLS or IP overhead. Failed attempts still count as calls.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import ipaddress
import os
from threading import Lock
from urllib.parse import urlsplit

import httpx
from websockets.asyncio.client import ClientConnection

CURRENT = ContextVar('cloud_meter', default=None)
LOCAL_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    '127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
    '100.64.0.0/10', '169.254.0.0/16', '::1/128', 'fc00::/7', 'fe80::/10'))


def is_local(url):
    host = (urlsplit(str(url)).hostname or '').lower().rstrip('.')
    # These are explicitly operator-configured home services, not hosted-model URLs.
    home = {(urlsplit(os.environ.get(key, '')).hostname or '').lower().rstrip('.')
            for key in ('OLLAMA_URL', 'BOX_URL', 'VISION_URL', 'ROUTER_OLLAMA_URL')}
    if host and (host in home or host == 'localhost' or host.endswith(('.localhost', '.local', '.ts.net'))):
        return True
    try:
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return any(address in network for network in LOCAL_NETWORKS)
    except ValueError:
        return False  # unknown destinations are never silently treated as local


@dataclass
class Meter:
    calls: int = 0
    bytes: int = 0
    lock: Lock = field(default_factory=Lock, repr=False)

    def add(self, calls=0, size=0):
        with self.lock:
            self.calls += calls
            self.bytes += size

    def snapshot(self):
        with self.lock:
            return dict(cloud_ai_calls=self.calls, bytes_to_cloud=self.bytes)


def start():
    meter = Meter()
    CURRENT.set(meter)
    return meter


class SyncBody(httpx.SyncByteStream):
    def __init__(self, stream, meter):
        self.stream, self.meter = stream, meter

    def __iter__(self):
        for chunk in self.stream:
            self.meter.add(size=len(chunk))
            yield chunk

    def close(self):
        self.stream.close()


class AsyncBody(httpx.AsyncByteStream):
    def __init__(self, stream, meter):
        self.stream, self.meter = stream, meter

    async def __aiter__(self):
        async for chunk in self.stream:
            self.meter.add(size=len(chunk))
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


def _install(library):
    # One shared send boundary, below SDK retries and HTTP redirects, above transports.
    sync_body, async_body = SyncBody, AsyncBody
    if library is not httpx:
        sync_body = type('SyncBody2', (SyncBody, library.SyncByteStream), {})
        async_body = type('AsyncBody2', (AsyncBody, library.AsyncByteStream), {})
    for cls, body in ((library.Client, sync_body), (library.AsyncClient, async_body)):
        original = cls._send_single_request
        if getattr(original, '_cloud_meter', False):
            continue
        def wrap(original, body):
            def prepare(request):
                # Redirects may reuse a wrapped body, including a redirect back home.
                while isinstance(request.stream, (SyncBody, AsyncBody)):
                    request.stream = request.stream.stream
                meter = CURRENT.get()
                if meter is not None and not is_local(request.url):
                    meter.add(calls=1)
                    try:
                        meter.add(size=len(request.content))
                        return
                    except library.RequestNotRead:
                        pass
                    request.stream = body(request.stream, meter)
            if issubclass(body, AsyncBody):
                @wraps(original)
                async def send(self, request):
                    prepare(request)
                    return await original(self, request)
            else:
                @wraps(original)
                def send(self, request):
                    prepare(request)
                    return original(self, request)
            send._cloud_meter = True
            return send
        cls._send_single_request = wrap(original, body)


def _install_ws():
    original = ClientConnection.send
    if getattr(original, '_cloud_meter', False):
        return

    @wraps(original)
    async def send(self, message, *args, **kwargs):
        meter = CURRENT.get()
        uri = self.protocol.uri
        if meter is not None and not is_local(f'wss://[{uri.host}]:{uri.port}' if ':' in uri.host else f'wss://{uri.host}:{uri.port}'):
            meter.add(calls=1)
            def count(chunk):
                meter.add(size=len(chunk.encode('utf-8') if isinstance(chunk, str) else chunk))
                return chunk
            if isinstance(message, (str, bytes, bytearray, memoryview)):
                count(message)
            elif hasattr(message, '__aiter__'):
                async def chunks(source):
                    async for chunk in source:
                        yield count(chunk)
                message = chunks(message)
            else:
                message = map(count, message)
        return await original(self, message, *args, **kwargs)
    send._cloud_meter = True
    ClientConnection.send = send


_install(httpx)
try:
    import httpx2  # newer Anthropic SDK; older installations still use HTTPX
except ImportError:
    pass
else:
    _install(httpx2)
_install_ws()
