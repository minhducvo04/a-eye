"""End-call retention is indexing only, using synthetic clips and fake TwelveLabs."""
import asyncio
from types import SimpleNamespace

import pytest

from server import rewind as rw, rewind_api
from server.test_rewind import FakeTL, fake_encoder


@pytest.mark.parametrize("already_indexing", [False, True])
def test_kept_call_reports_ready_only_after_all_indexing_and_recording(monkeypatch, tmp_path, already_indexing):
    monkeypatch.setattr(rw, '_kept_path', lambda owner: tmp_path / 'kept.json')
    monkeypatch.setattr(rewind_api, 'identity', lambda request: 'alice')

    async def run():
        released = asyncio.Event()
        polling = asyncio.Event()

        class TL(FakeTL):
            async def task(self, task_id):
                polling.set()
                await released.wait()
                return {'status': 'ready'}

        async def sleep(_):
            await asyncio.sleep(0)

        monkeypatch.setattr(rw, '_sleep', sleep)
        client = TL()
        registry = rw.Registry(client, encoder=fake_encoder)
        call = registry.open('saved', on=True, owner='alice')
        call.keep = True
        call.clips = [rw.Clip(0, 5, frames=[(0, b'synthetic')], status='pending')]
        if already_indexing:
            await call.flush()  # live indexing, with no pending clips left at hang-up
            await polling.wait()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rewind=registry)))
        monkeypatch.setattr(rewind_api, 'registry', lambda app: registry)
        task = registry.end(call)
        await polling.wait()
        assert (await rewind_api.status(request, 'saved'))['save_status'] == 'saving'
        assert client.analyzed is None
        released.set()
        await task
        assert (await rewind_api.status(request, 'saved'))['save_status'] == 'saved'
        assert rw.kept_calls('alice')[0]['clips'][0]['video_id'] == 'vid-1'
        assert client.analyzed is None
        assert (await rewind_api.status(request, 'unknown'))['save_status'] is None

    asyncio.run(run())


def test_not_kept_off_and_failed_calls_never_report_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(rw, '_kept_path', lambda owner: tmp_path / 'kept.json')

    async def run():
        for on, keep, clip_status in [(True, False, 'pending'), (False, True, 'pending'),
                                       (True, True, 'failed'), (True, True, None)]:
            client = FakeTL()
            registry = rw.Registry(client, encoder=fake_encoder)
            call = registry.open('s', on=on, owner='alice')
            call.keep = keep
            if clip_status:
                call.clips = [rw.Clip(0, 5, frames=[(0, b'synthetic')], status=clip_status)]
            task = registry.end(call)
            if task:
                await task
            assert call.save_status() != 'saved'
            if not on or not keep:
                assert call.save_status() is None
            assert client.analyzed is None
    asyncio.run(run())
