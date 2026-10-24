"""WebSocket orchestrator; each connection owns one in-memory session."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles


class NoCacheStatic(StaticFiles):
    """Client modules must always be revalidated. Seen live: after an update the browser mixed cached and new ES
    modules of the call page (some 304, some 200), which can break imports and leave buttons dead."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers['Cache-Control'] = 'no-cache'
        return response
from fastapi.responses import JSONResponse
from server.auth import authorized, accept_socket, mint_owner, warn_unconfigured
from server.logs import event, protect_transport_logs
from server import api, mock, rewind_api, proof_wall, cloud_meter
from jsonschema import ValidationError

from contracts import validate
from market.search import search
from server import ws2
from server.expert import check_local_model
from server.routing import warm_router
from server.boards import load_board
from server.brain_local import make_llm
from server.steps import Session, error
from server.vision_client import VisionClient, VisionUnavailable

CLIENT_WEB = Path(__file__).resolve().parents[1] / 'client-web'


def create_app(vision=None, clock=None, static_dir=CLIENT_WEB, llm=None):
    @asynccontextmanager
    async def lifespan(app):
        protect_transport_logs()
        warn_unconfigured()
        warmup = None if app.state.mock else asyncio.create_task(ws2.warm_brain(app))
        if not app.state.mock:
            # Off the event loop: warn once at startup if the local expert model tag is missing on the box.
            asyncio.get_running_loop().run_in_executor(None, check_local_model)
            asyncio.get_running_loop().run_in_executor(None, warm_router)
        try:
            yield
        finally:
            if warmup:
                warmup.cancel()
                await asyncio.gather(warmup, return_exceptions=True)

    app = FastAPI(lifespan=lifespan)
    app.state.vision = vision if vision is not None else VisionClient()
    app.state.llm = llm if llm is not None else make_llm()
    app.state.llm_v2 = app.state.llm
    app.state.mock = os.environ.get('A_EYE_MOCK') == '1'
    if os.environ.get('REWIND_FAKE_TL') == '1':
        # Rehearsals: Rewind runs end to end with an in-process TwelveLabs stand-in (nothing uploaded).
        from server.rewind_fake import FakeTwelveLabs
        app.state.rewind_client = FakeTwelveLabs()
    app.state.status_cache = None
    app.state.status_lock = asyncio.Lock()
    if app.state.mock:
        mock.install(app)
        app.add_middleware(mock.FirstSceneBarrier)

    @app.middleware('http')
    async def authenticate(request, call_next):
        if request.url.path.startswith('/api/') and not authorized(request):
            event('auth_rejected', level='warning')
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        session_id = request.query_params.get('session_id')
        call = (rewind_api.registry(request.app).get(session_id, rewind_api.identity(request))
                if session_id else None)
        token = cloud_meter.CURRENT.set(getattr(call, 'cloud_meter', None))
        try:
            return await call_next(request)
        finally:
            cloud_meter.CURRENT.reset(token)

    now = clock if clock is not None else lambda: int(time.time() * 1000)

    @app.get('/health')
    async def health():
        return {'ok': True}

    @app.post('/api/call-owner')
    async def call_owner(request: Request):
        # Access users keep their verified identity. Only token callers need a call capability.
        owner = mint_owner() if getattr(request.state, 'token_owner', '') else ''
        return JSONResponse({'owner': owner}, headers={'Cache-Control': 'no-store'})

    @app.websocket('/ws')
    async def websocket(ws: WebSocket):
        if not await accept_socket(ws):
            return
        session = None

        async def send(messages):
            for message in messages:
                validate('server_message', message)
                await ws.send_json(message)

        try:
            while True:
                try:
                    incoming = await ws.receive_json()
                    validate('client_message', incoming)
                except (json.JSONDecodeError, ValidationError, KeyError):
                    await send([error('bad_message', 'Invalid client message.')])
                    continue
                if incoming['type'] == 'hello':
                    board_id = incoming.get('board_id', 'demo-b650')
                    try:
                        board = load_board(board_id)
                    except (OSError, ValueError, ValidationError):
                        await send([error('bad_message', 'Unknown or invalid board.')])
                        continue
                    event('hello', incoming['session_id'])
                    session = Session(incoming['session_id'], board_id, board)
                    await send(session.start())
                    continue
                if session is None or incoming['session_id'] != session.session_id:
                    await send([error('bad_message', 'Send hello with the matching session first.')])
                    continue
                messages, request = session.handle(incoming, now())
                await send(messages)
                while request:
                    operation, payload = request
                    if operation == 'market':
                        try:
                            result = await asyncio.to_thread(search, payload)
                            validate('market_response', result)
                        except Exception:
                            await send([error('internal', 'Market is unavailable. Try again.')])
                            break
                        top = next((item for item in result['items']
                                    if item['compat']['status'] == 'fits'), None)
                        text = (f"Cheapest that fits: {top['title']}, ${top['price_usd']:.2f} "
                                f"at {top['retailer']}." if top else
                                'I found nothing that I can confirm fits.')
                        await send([dict(v=1, type='market_results', result=result), session.say(text)])
                        break
                    if operation == 'text':
                        text = 'Please check the manual page for this step.'
                        try:
                            result = await asyncio.to_thread(app.state.llm.complete, **payload)
                            if (result.provider != 'canned' and isinstance(result.text, str)
                                    and result.text.strip()):
                                text = result.text
                        except Exception:
                            # Provider and response-shape failures must not close the socket.
                            pass
                        await send([session.say(text)])
                        break
                    try:
                        result = await app.state.vision.call(operation, payload)
                    except VisionUnavailable:
                        await send(session.vision_failed())
                        break
                    messages, request = session.accept(operation, result, now())
                    await send(messages)
        except WebSocketDisconnect:
            pass

    app.include_router(ws2.router)
    app.include_router(api.router)
    app.include_router(proof_wall.router)
    app.include_router(rewind_api.router)
    # Routes must precede the catch-all static mount. The client package owns this directory.
    if Path(static_dir).is_dir():
        app.mount('/', NoCacheStatic(directory=static_dir, html=True, check_dir=False), name='client')
    return app


app = create_app()
