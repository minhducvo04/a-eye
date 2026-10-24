"""Local memory HTTP routes under /api/memory (behind the /api auth check). Bound to the caller's identity."""
from time import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server import memory as mem
from server.rewind import identity, registry

router = APIRouter(prefix='/api/memory')


async def body(request):
    try:
        value = await request.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def own_store(request, memory_id, create=False):
    """The caller's own memory, or None (unknown and other callers' ids look the same)."""
    try:
        store = mem.memories(request.app).store(memory_id or '')
    except ValueError:
        return None
    owner = store.owner()
    if owner is None:
        return store if create else None
    return store if owner == identity(request) else None


def card(result):
    import base64
    out = {k: v for k, v in result.items() if k not in ('crop', 'live_scene')}
    if result.get('crop'):
        out['crop_b64'] = base64.b64encode(result['crop']).decode()
    return out


@router.post('/attach')
async def attach(request: Request):
    """Start or stop writing this call's scans into a person's memory (off by default)."""
    value = await body(request)
    session_id, memory_id = value.get('session_id'), value.get('memory_id')
    rewind = registry(request.app).get(session_id, identity(request)) if session_id else None
    if rewind is None:
        return JSONResponse({'error': 'unknown_session'}, status_code=404)
    memories = mem.memories(request.app)
    if not value.get('on', True):
        memories.detach(session_id)
        rewind.memory_writer = None
        return {'on': False}
    try:
        store, writer = memories.attach(session_id, memory_id or '', identity(request))
    except ValueError:
        return JSONResponse({'error': 'invalid_memory_id'}, status_code=422)
    except PermissionError:
        return JSONResponse({'error': 'unknown_memory'}, status_code=404)
    rewind.memory_writer = writer
    # Rewind cloud for this person goes to their own index, and Forget can find the videos.
    if not any(c.video_id for c in rewind.clips):
        rewind.index_name, rewind.index_id = f'a-eye-{store.id}', None
    rewind.on_upload = store.add_video
    return dict(mem.status(store), on=True)


@router.get('/status')
async def status(request: Request, memory_id: str = ''):
    store = own_store(request, memory_id)
    if store is None:
        return dict(memory_id=memory_id, count=0, crops=0, bytes=0, encrypted=mem.Cipher().encrypted,
                    retention_days=mem.retention_days(), tags=[])
    return mem.status(store)


@router.post('/find')
async def find(request: Request):
    value = await body(request)
    query = value.get('query')
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        return JSONResponse({'error': 'invalid_body'}, status_code=422)
    store = own_store(request, value.get('memory_id'))
    if store is None:
        return dict(found=False, count=0, say="I don't have a memory for you yet.")
    rewind = registry(request.app).get(value.get('session_id'), identity(request)) if value.get('session_id') else None
    session = getattr(rewind, 'session', None)
    memories = mem.memories(request.app)
    return card(await mem.find(store, query, embedder=memories.embedder,
                               scene=getattr(session, 'scene', None)))


@router.post('/tag')
async def tag(request: Request):
    """Caregiver tag: an object ("blue pill box") or a place ("key bowl"), with an optional home place."""
    value = await body(request)
    store = own_store(request, value.get('memory_id'), create=True)
    if store is None:
        return JSONResponse({'error': 'unknown_memory'}, status_code=404)
    store.claim(identity(request))
    try:
        saved = store.set_tag(value.get('name'), value.get('label'), value.get('home'), value.get('kind', 'object'))
    except ValueError:
        return JSONResponse({'error': 'invalid_body'}, status_code=422)
    return dict(tag=saved, **mem.status(store))


@router.post('/forget')
async def forget(request: Request):
    """Real deletion: scope item (with item), today, or everything; TwelveLabs videos for the person go too."""
    value = await body(request)
    store = own_store(request, value.get('memory_id'))
    if store is None:
        return JSONResponse({'error': 'unknown_memory'}, status_code=404)
    scope = value.get('scope')
    cloud = (0, 0)
    if scope == 'item' and isinstance(value.get('item'), str) and value['item'].strip():
        deleted = store.forget_item(value['item'])
    elif scope == 'today':
        from datetime import datetime
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cloud = await mem.delete_cloud(store, since=since)
        deleted = store.forget_since(since)
    elif scope == 'everything':
        cloud = await mem.delete_cloud(store)
        deleted = store.forget_all()
    else:
        return JSONResponse({'error': 'invalid_body'}, status_code=422)
    out = dict(mem.status(store), deleted=deleted, cloud_deleted=cloud[0], cloud_failed=cloud[1])
    if scope == 'item':
        out['count_item'] = store.count(value['item'])
    return out
