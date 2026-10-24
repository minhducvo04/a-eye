"""Rewind HTTP routes under /api (token-checked by the app middleware). The TwelveLabs key stays server-side."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.rewind import NOTICE, registry

router = APIRouter(prefix='/api/rewind')


def public(hit):
    return {k: hit[k] for k in ('t_s', 'start_s', 'end_s', 'rank') if k in hit}


@router.get('/status')
async def status(request: Request, session_id: str = ''):
    rewind = registry(request.app).for_question(session_id or None)
    return dict(rewind.status() if rewind else dict(on=False, clips=0, ready=0, indexing=0, pending=0),
                notice=NOTICE)


async def body(request):
    try:
        value = await request.json()
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


@router.post('/search')
async def search(request: Request):
    value = await body(request)
    query = value.get('query') if value else None
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        return JSONResponse({'error': 'invalid_body'}, status_code=422)
    rewind = registry(request.app).for_question(value.get('session_id'))
    if rewind is None:
        return {'hits': []}
    try:
        hits = await rewind.search(query.strip())
    except Exception:
        return JSONResponse({'error': 'dependency_unavailable'}, status_code=503)
    return {'hits': [public(h) for h in hits]}


@router.post('/flush')
async def flush(request: Request):
    value = await body(request)
    rewind = registry(request.app).get(value.get('session_id')) if value else None
    if rewind is None:
        return JSONResponse({'error': 'unknown_session'}, status_code=404)
    try:
        sent = await rewind.flush()
    except Exception:
        return JSONResponse({'error': 'dependency_unavailable'}, status_code=503)
    return dict(rewind.status(), uploaded=len(sent))
