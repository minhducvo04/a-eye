"""Read-only judge evidence. Authentication is the shared /api middleware."""
import asyncio
import os
from pathlib import Path
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/proof')
DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic', '.avif', '.tif', '.tiff'}
_network = None
_lock = asyncio.Lock()


def picture_count(root=None):
    """Count image-named files (including encrypted crops); never open their contents or follow links."""
    count = 0
    def denied(error):
        raise error
    for directory, _, files in os.walk(root or DATA_DIR, onerror=denied, followlinks=False):
        for name in files:
            path = Path(directory) / name
            if path.suffix.lower() in IMAGE_SUFFIXES and not path.is_symlink() and path.is_file():
                count += 1
    return count


async def outbound_check():
    """A bounded TCP handshake only: no HTTP request, credentials, prompt, image or audio."""
    global _network
    async with _lock:
        if _network and time.monotonic() - _network[0] < 10:
            return _network[1]
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection('1.1.1.1', 443), 1)
            writer.close()
            await writer.wait_closed()
            online = True
        except (OSError, TimeoutError):
            online = False
        result = dict(online=online, checked_at_ms=int(time.time() * 1000))
        _network = (time.monotonic(), result)
        return result


@router.get('')
async def status():
    try:
        count = await asyncio.to_thread(picture_count)
    except OSError:
        count = None  # unreadable is unknown, never a reassuring zero
    return JSONResponse(dict(pictures_saved=count, **await outbound_check()),
                        headers={'Cache-Control': 'no-store'})
