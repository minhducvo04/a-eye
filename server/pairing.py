"""Process-local, single-use camera pairing. No media or credentials are logged."""
import asyncio
import hashlib
import json
import secrets
from time import monotonic

from anyio import CancelScope
from fastapi import WebSocketDisconnect
from jsonschema import ValidationError
from contracts import validate
from server.agent import message
from server.logs import event


class Registry:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.codes = {}
        self.retired = {}
        # "Remember this phone": the latest live call per verified Access identity (latest wins).
        self.owners = {}

    def drop(self, call):
        for ident, owned in list(self.owners.items()):
            if owned is call:
                del self.owners[ident]
        for code, entry in list(self.codes.items()):
            if entry[0] is call:
                self.retired[code] = entry[1]
                del self.codes[code]

    def issue(self, call):
        self.drop(call)
        # Expired entries remain until the next issue, allowing an explicit expired response.
        self.codes = {c: e for c, e in self.codes.items() if e[1] > self.clock()}
        self.retired = {c: expiry for c, expiry in self.retired.items() if expiry > self.clock()}
        available = [f'{n:04d}' for n in range(10000)
                     if f'{n:04d}' not in self.codes and f'{n:04d}' not in self.retired]
        if not available:
            raise ValueError('Pairing is busy. Try again shortly.')
        code = secrets.choice(available)
        self.codes[code] = (call, self.clock() + 300)
        event('pair_request', call.session.session_id)
        return message('pair', code=code, expires_in_s=300, path=f'/agent.html?pair={code}')

    def take(self, code):
        entry = self.codes.pop(code, None)
        if entry is None:
            return None, 'rejected'
        call, expiry = entry
        self.retired[code] = expiry
        if expiry <= self.clock():
            return None, 'expired'
        if call.closed or call.camera is not None:
            return None, 'rejected'
        return call, 'joined'


    def claim(self, call, ident):
        if ident:
            self.owners[ident] = call

    def take_remembered(self, ws):
        """A camera join without a code: only into the latest live call of the same verified Access identity.
        Returns (call, state, detail, retry_s); retry_s tells a remembered phone to wait and try again."""
        ident = verified_identity(ws)
        if not ident:
            event('pair_rejected', reason='no_access')
            return None, 'rejected', 'Sign in with your own account to use this phone without a code, or use a code.', None
        call = self.owners.get(ident)
        if call is None or call.closed:
            return None, 'rejected', 'Waiting for your next call.', 3
        if call.kicked:
            return None, 'rejected', 'Your call disconnected this phone. It joins your next call.', 3
        if call.camera is not None:
            return None, 'rejected', 'Your call already has a phone.', 3
        return call, 'joined', '', None


def verified_identity(ws):
    """'access:<hash>' for an Access email that server.auth verified on this socket, else ''. A shared token, an
    open server or an unverified cookie never counts."""
    email = getattr(getattr(ws, 'state', None), 'access_email', '')
    if not isinstance(email, str) or not email:
        return ''
    return 'access:' + hashlib.sha256(email.lower().encode()).hexdigest()[:16]


registry = Registry()


class Call:
    def __init__(self, session, send, switch, ident=''):
        self.session, self.send, self.switch = session, send, switch
        self.local_on = session.camera
        self.camera = None
        self.closed = False
        self.kicked = False  # the call disconnected its phone: no remembered rejoin into this call
        registry.claim(self, ident)
        # Phone mic: audio_in and barge_in from the camera socket, read by the call's own message loop.
        self.inbox = asyncio.Queue()

    async def status(self, state, source='camera'):
        fields = dict(state=state, camera_on=self.session.camera, source=source)
        if not self.closed:
            await self.send(message('pair_status', role='call', **fields))
        if self.camera:
            await self.camera.send_json(message('pair_status', role='camera', **fields))

    async def kick(self):
        """The call disconnects its phone. A remembered phone waits for the next call instead of rejoining."""
        self.kicked = True
        camera = self.camera
        if camera:
            event('pair_kicked', self.session.session_id)
            try:
                await camera.send_json(message('pair_status', state='left', role='camera',
                                               detail='Your call disconnected this phone.', retry_s=3))
                await camera.close()
            except (RuntimeError, WebSocketDisconnect):
                pass

    async def close(self):
        self.closed = True
        registry.drop(self)
        camera, self.camera = self.camera, None
        if camera:
            event('pair_left', self.session.session_id)
            try:
                await camera.send_json(message('pair_status', state='left', role='camera', detail='Call ended.', retry_s=3))
                await camera.close()
            except (RuntimeError, WebSocketDisconnect):
                pass


async def camera_socket(ws, hello):
    if 'pair_code' in hello:
        call, state = registry.take(hello['pair_code'])
        detail, retry = ('Code expired.' if state == 'expired' else 'Code unavailable. Request a new code.'), None
    else:
        call, state, detail, retry = registry.take_remembered(ws)
    if call is None:
        event('pair_rejected')
        await ws.send_json(message('pair_status', state=state, role='camera', detail=detail,
                                   **({'retry_s': retry} if retry else {})))
        await ws.close(code=4404)
        return
    call.camera = ws  # Reserve before the first await: only one camera can join.
    event('pair_joined', call.session.session_id)
    try:
        await call.switch(hello.get('camera', True), reset=True)
        if call.closed:
            return
        await call.status('joined')
        while True:
            try:
                incoming = await ws.receive_json()
                validate('client_message_v2', incoming)
                if (incoming['type'] not in ('frame', 'camera', 'audio_in', 'barge_in')
                        or incoming['session_id'] != hello['session_id']):
                    raise ValueError()
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
                await ws.send_json(message('error', code='bad_message',
                                           message='Camera sockets accept only frame, camera, audio_in and barge_in.'))
                continue
            if call.closed:
                break
            if incoming['type'] in ('audio_in', 'barge_in'):
                await call.inbox.put(dict(incoming, session_id=call.session.session_id))
            elif incoming['type'] == 'camera':
                await call.switch(incoming['on'])
                await call.status('camera')
            elif call.session.camera:
                frame = call.session.frame
                if frame is None or incoming['seq'] > frame['seq']:
                    call.session.frame = dict(incoming, session_id=call.session.session_id)
                    call.session.frame_time = monotonic()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if call.camera is ws:
            call.camera = None
            event('pair_left', call.session.session_id)
            if not call.closed:
                with CancelScope(shield=True):
                    await call.switch(call.local_on, reset=True)
                    await call.status('left', source='call')
