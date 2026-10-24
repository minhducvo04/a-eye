"""WebSocket orchestrator; each connection owns one in-memory session."""
import asyncio
import json
from pathlib import Path
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from jsonschema import ValidationError

from contracts import validate
from market.search import search
from server.boards import load_board
from server.llm import LLMClient
from server.steps import Session, error
from server.vision_client import VisionClient, VisionUnavailable

CLIENT_WEB = Path(__file__).resolve().parents[1] / 'client-web'


def create_app(vision=None, clock=None, static_dir=CLIENT_WEB, llm=None):
    app = FastAPI()
    app.state.vision = vision if vision is not None else VisionClient()
    app.state.llm = llm if llm is not None else LLMClient()
    now = clock if clock is not None else lambda: int(time.time() * 1000)

    @app.get('/health')
    async def health():
        return {'ok': True}

    @app.websocket('/ws')
    async def websocket(ws: WebSocket):
        await ws.accept()
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

    # Routes must precede the catch-all static mount. The client package owns this directory.
    if Path(static_dir).is_dir():
        app.mount('/', StaticFiles(directory=static_dir, html=True, check_dir=False), name='client')
    return app


app = create_app()
