"""Review regressions: synthetic bytes and fake/MockTransport providers only."""
import asyncio
import inspect
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from server import privacy, rewind as rw, safety
from server.test_rewind import FakeTL, fake_encoder


@pytest.fixture(autouse=True)
def consent(monkeypatch, tmp_path):
    privacy.set_call(rewind=True)
    monkeypatch.setenv('A_EYE_MEMORY_DIR', str(tmp_path))


def clip(status='pending', video_id=None):
    return rw.Clip(0, 5, frames=[(0, b'synthetic')], status=status, video_id=video_id)


async def toggle(rewind, on):
    result = rewind.set_on(on)
    if inspect.isawaitable(result):
        await result


class Client(FakeTL):
    async def delete_video(self, index_id, video_id, force=False):
        assert force
        self.deleted.append((index_id, video_id))


def test_water_location_is_not_running_supply():
    for text in ('The water is on the left', 'The water is on the stove',
                 'The water is on the floor', 'Where is the water?'):
        assert safety.before(text) is None
        assert safety.after(text, 'Where is the water?') == text
    for text in ('The water is still on; loosen the sink fitting',
                 'The water is running; remove the valve', 'The water is not off yet'):
        assert safety.before(text) == safety.WATER_OFF_LINE
        assert safety.after(text) == safety.WATER_OFF_LINE
    assert safety.plumbing_stop(False) == safety.WATER_OFF_LINE
    assert safety.plumbing_stop(None) == safety.WATER_OFF_LINE
    assert safety.plumbing_stop(True) is None


def test_psu_connection_question_is_not_live_wire_work():
    for text in ('Is the PSU plugged in?', 'Is the power supply plugged in?'):
        assert safety.before(text) is None
    for text in ('Can I touch this live wire?', 'Replace the outlet without turning the breaker off',
                 'The PSU power is still on; touch the wires'):
        assert safety.before(text) in safety.LINES


def test_water_electric_includes_demo_devices():
    for device in ('PSU', 'power supply', 'charger', 'power strip', 'computer', 'laptop'):
        assert safety.before(f'I spilled water on the {device}.') in safety.LINES
        assert safety.before(f'The {device} is wet.') in safety.LINES
        assert safety.before(f'Where is the {device}?') is None


def test_repeat_hello_and_stale_socket_cleanup_preserve_call():
    from server.test_ws2 import app, send
    application = app()
    application.state.rewind = registry = rw.Registry(Client(), encoder=fake_encoder)

    def listening(ws):
        while ws.receive_json().get('state') != 'listening':
            pass

    with TestClient(application) as client, client.websocket_connect('/ws2') as ws:
        send(ws, 'hello', pack='general', camera=False, rewind=True)
        listening(ws)
        original = registry.get('s')
        original.index_id = 'idx'
        original.clips = [clip('ready', 'saved')]
        send(ws, 'hello', pack='general', camera=False, rewind=True)
        listening(ws)
        assert registry.get('s') is original
        assert original.clips[0].video_id == 'saved'
        assert not registry.client.deleted

    async def stale_close():
        old = registry.open('reconnect', on=True)
        first_session = SimpleNamespace()
        old.session = first_session
        resumed = registry.open('reconnect', on=True)
        resumed.session = SimpleNamespace()
        resumed.clips = [clip('ready', 'resumed-video')]
        assert resumed is old
        assert registry.end(old, session=first_session) is None
        assert not resumed.ended and resumed.clips[0].video_id == 'resumed-video'
        registry.calls.pop('reconnect')
        new = registry.open('reconnect', on=True)
        new.clips = [clip('ready', 'new-video')]
        registry.end(old)
        await asyncio.gather(*registry.background)
        assert new.clips[0].video_id == 'new-video'
    asyncio.run(stale_close())


@pytest.mark.parametrize('boundary', ['index', 'upload'])
def test_off_during_flush_keeps_uploaded_id_for_deletion(boundary):
    async def go():
        entered, release = asyncio.Event(), asyncio.Event()

        class Racing(Client):
            async def ensure_index(self, name=None):
                if boundary == 'index':
                    entered.set()
                    await release.wait()
                return 'idx'

            async def upload(self, *args):
                if boundary == 'upload':
                    entered.set()
                    await release.wait()
                return await super().upload(*args)

        registry = rw.Registry(Racing(), encoder=fake_encoder)
        rewind = registry.open('race', on=True)
        rewind.clips = [clip()]
        uploading = asyncio.create_task(rewind.flush())
        await entered.wait()
        stopping = asyncio.create_task(toggle(rewind, False))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(uploading, stopping)
        cleanup = registry.end(rewind)
        if cleanup is not None:
            await cleanup
        assert len(rewind.client.uploads) == len(rewind.client.deleted)
        assert len(rewind.client.uploads) == (1 if boundary == 'upload' else 0)
        assert all(c.video_id is None and not c.frames for c in rewind.clips)
    asyncio.run(go())


def test_forget_deletes_even_with_private_mode_and_spend_cap(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request.method)
        return httpx.Response(204)

    rewind = rw.Rewind('forget', client=rw.TwelveLabsClient(key='synthetic', transport=httpx.MockTransport(handler)))
    rewind.index_id = 'idx'
    rewind.clips = [clip('ready', 'video')]
    privacy.PRIVATE.set(True)
    monkeypatch.setattr(privacy, 'server_local_only', lambda: True)
    result = asyncio.run(rewind.forget())
    assert requests == ['DELETE'] and result['failed'] == 0
    assert not rewind.clips


def test_anonymous_kept_calls_never_cross_call_boundary(monkeypatch):
    stored = [{'session_id': 'a', 'clips': [{'video_id': 'a-video', 'start_s': 0}]}]
    monkeypatch.setattr(rw, 'kept_calls', lambda owner: stored if owner in ('local', 'access:alice') else [])
    client = Client([dict(video_id='a-video', start=0, end=5, rank=1)])
    registry = rw.Registry(client)
    call = registry.open('b', on=True, owner='local')
    assert asyncio.run(call.search_kept('screw')) == []
    assert client.searches == []
    alice = registry.open('alice-call', on=True, owner='access:alice')
    assert asyncio.run(alice.search_kept('screw'))[0]['video_id'] == 'a-video'
    bob = registry.open('bob-call', on=True, owner='access:bob')
    assert asyncio.run(bob.search_kept('screw')) == []


def test_recap_never_reuploads_deleted_frames():
    rewind = rw.Rewind('recap', client=Client(), encoder=fake_encoder)
    rewind.set_on(True)
    rewind.clips = [clip('deleted')]
    result = asyncio.run(rw.recap(rewind))
    assert result['steps'] == [] and rewind.client.analyzed is None

    async def forget_during_encode():
        entered, release = threading.Event(), threading.Event()

        def encode(frames):
            entered.set()
            assert release.wait(2)
            return b'mp4'

        rewind.index_id = 'idx'
        rewind.clips = [clip('ready', 'video')]
        recapping = asyncio.create_task(rw.recap(rewind, encoder=encode))
        assert await asyncio.to_thread(entered.wait, 2)
        try:
            await rewind.forget()
        finally:
            release.set()
        result = await recapping
        assert result['steps'] == [] and rewind.client.analyzed is None
        assert rewind.client.deleted == [('idx', 'video')]
    asyncio.run(forget_during_encode())


def test_http_recap_flush_search_honor_call_switch():
    from server.test_ws2 import app, send
    application = app()
    application.state.rewind = registry = rw.Registry(Client(), encoder=fake_encoder)
    with TestClient(application) as client, client.websocket_connect('/ws2') as ws:
        send(ws, 'hello', pack='general', camera=False, rewind=True)
        while ws.receive_json().get('state') != 'listening':
            pass
        call = registry.get('s')
        call.index_id = 'idx'
        call.clips = [clip('ready', 'video')]
        send(ws, 'rewind', on=False)
        while ws.receive_json().get('type') != 'rewind_state':
            pass
        call.clips.append(clip())  # queued work must also be refused when off
        for route in ('flush', 'search', 'recap'):
            response = client.post('/api/rewind/' + route, json={'session_id': 's', 'query': 'screw'})
            assert response.status_code == 200
        assert not call.client.uploads and not call.client.searches and call.client.analyzed is None
    privacy.SWITCHES.set(None)
    assert not privacy.twelvelabs_allowed()


def test_transient_poll_errors_retry_before_failure():
    class Transient(Client):
        polls = 0

        async def task(self, task_id):
            self.polls += 1
            if self.polls <= 2:
                raise httpx.ReadTimeout('synthetic timeout')
            return {'status': 'ready'}

    rewind = rw.Rewind('poll', client=Transient())
    rewind.set_on(True)
    pending = clip('indexing', 'video')
    pending.task_id = 'task'
    assert asyncio.run(rewind.wait_ready(pending)) is True
    assert pending.status == 'ready' and rewind.client.polls == 3

    class Broken(Client):
        polls = 0

        async def task(self, task_id):
            self.polls += 1
            raise httpx.ConnectError('synthetic disconnect')

    rewind.client = Broken()
    assert asyncio.run(rewind.wait_ready(pending)) is False
    assert pending.status == 'failed' and rewind.client.polls == 4  # initial attempt plus three retries
