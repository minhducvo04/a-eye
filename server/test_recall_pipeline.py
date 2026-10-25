"""Recall pipeline: the two modes, no media file on the host, and status-poll backoff. Fakes only, no network."""
import asyncio
import builtins
import io
import shutil
import tempfile

import pytest

from server import rewind as rewind_mod
from server.rewind import Registry, recall_mode
from server.test_rewind import FakeTL, JPEG, fake_encoder


def call(registry, name, mode, keep=False):
    """A call with two finished clips (keyframes at 2 s and 9 s), fed through the real clip cutter."""
    rewind = registry.open(name, on=True)
    rewind.recall_mode = mode
    rewind.keep = keep
    clock = [0.0]
    rewind.clock = lambda: clock[0]
    rewind.started = 0.0
    t = 0.0
    while t <= 16.0:
        clock[0] = t
        rewind.add_frame(JPEG)
        if t in (2.0, 9.0):
            rewind.keyframe('change')
        t += 0.25
    return rewind, clock


async def end(registry, name):
    task = registry.end(name)
    if task:
        await task


def test_mode_from_query_then_env_then_live(monkeypatch):
    assert recall_mode() == 'live'
    monkeypatch.setenv('REWIND_MODE', 'at_save')
    assert recall_mode() == 'save' and recall_mode('on_the_fly') == 'live' and recall_mode('nonsense') == 'save'
    assert rewind_mod.Rewind('s').recall_mode == 'save'


def test_live_mode_uploads_each_clip_as_cut_and_is_searchable():
    registry = Registry(FakeTL([dict(video_id='vid-1', start=0, end=5, rank=1)]), encoder=fake_encoder)

    async def go():
        rewind, clock = call(registry, 'live', 'live')
        task = rewind.flush_soon()
        assert task is not None
        await task
        await asyncio.gather(*rewind.waits)
        return rewind

    rewind = asyncio.run(go())
    assert len(registry.client.uploads) >= 1 and rewind.clips[0].status == 'ready'
    hits = asyncio.run(rewind.search('screw'))
    assert hits and hits[0]['video_id'] == 'vid-1'


def test_follow_in_live_mode_uploads_without_waiting_for_a_minute():
    class S:
        camera = True
        frame = None

    async def go():
        rewind = rewind_mod.Rewind('s1', client=FakeTL(), encoder=fake_encoder)
        rewind.set_on(True)
        session = S()
        session.frame = dict(seq=1, jpeg_b64=JPEG)
        task = asyncio.create_task(rewind.follow(session))
        await asyncio.sleep(0.2)
        rewind.keyframe('change')
        rewind.clips[0].end_s = rewind.now_s()       # the clip is over; the still camera sends no new frame
        for _ in range(100):
            if rewind.clips[0].status == 'ready':
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, *rewind.waits, return_exceptions=True)
        return rewind

    rewind = asyncio.run(go())
    assert rewind.clips[0].status == 'ready' and len(rewind.client.uploads) == 1


def test_save_mode_holds_clips_in_memory_and_uploads_only_when_kept():
    registry = Registry(FakeTL(), encoder=fake_encoder)
    kept, _ = call(registry, 'kept', 'save', keep=True)
    assert kept.flush_soon() is None and kept.uploads_live() is False
    text, hit = asyncio.run(kept.answer('when did I plug in the fan?'))
    assert hit is None and 'save' in text and registry.client.uploads == []      # nothing left during the call
    assert all(c.frames for c in kept.clips)                                      # held in memory
    asyncio.run(end(registry, 'kept'))
    assert len(registry.client.uploads) == len(kept.clips) == 2
    assert all(c.status == 'ready' for c in kept.clips)


def test_save_mode_not_kept_discards_and_uploads_nothing():
    registry = Registry(FakeTL(), encoder=fake_encoder)
    gone, _ = call(registry, 'gone', 'save', keep=False)
    assert gone.clips
    asyncio.run(end(registry, 'gone'))
    assert registry.client.uploads == [] and registry.client.deleted == [] and gone.clips == []


def test_poll_backoff_counts_and_waits(monkeypatch):
    monkeypatch.setenv('REWIND_POLL_S', '2,4,8')
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(rewind_mod, '_sleep', fake_sleep)

    class Slow(FakeTL):
        polls = 0

        async def task(self, task_id):
            self.polls += 1
            return {'status': 'ready' if self.polls == 4 else 'indexing'}

    rewind = rewind_mod.Rewind('s', client=Slow(), encoder=fake_encoder)
    rewind.set_on(True)
    clip = rewind_mod.Clip(start_s=0, end_s=5, task_id='t1')
    assert asyncio.run(rewind.wait_ready(clip)) is True
    assert waits == [2, 4, 8, 8] and rewind.client.polls == 4      # no poll before the first wait
    waits.clear()
    clip = rewind_mod.Clip(start_s=0, end_s=5, task_id='t2')
    rewind.client = type('Never', (FakeTL,), {'task': lambda self, t: asyncio.sleep(0, {'status': 'indexing'})})()
    assert asyncio.run(rewind.wait_ready(clip, timeout=30)) is False and clip.status == 'failed'
    assert sum(waits) >= 30 and len(waits) == 5                     # 2+4+8+8+8: 5 polls, not 10 at 3 s


def test_default_backoff_polls_fewer_times_than_every_3_s(monkeypatch):
    monkeypatch.delenv('REWIND_POLL_S')
    delays = rewind_mod.poll_delays()
    # A clip ready 15 s after upload: old code polled at 0, 3, 6, 9, 12, 15 (6 polls); now 6, 9, 12, 15 (4).
    times, t = [], 0.0
    for d in delays:
        t += d
        times.append(t)
        if t >= 15:
            break
    assert times == [6, 9, 12, 15]


def _real_jpegs(n):
    from PIL import Image
    out = []
    for i in range(n):
        buffer = io.BytesIO()
        Image.new('RGB', (640, 480), (i * 20 % 255, 80, 160)).save(buffer, format='JPEG')
        out.append((i * 0.25, buffer.getvalue()))
    return out


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg not installed')
def test_no_media_file_is_written_on_the_host(monkeypatch, tmp_path_factory):
    """The real encoder plus a flush, with every Python file-creation path booby-trapped and a fresh temp dir."""
    tmp_path = tmp_path_factory.mktemp("no-disk")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    tempfile.tempdir = None
    real_open = builtins.open

    def no_write_open(file, mode='r', *args, **kwargs):
        if any(flag in mode for flag in 'wax+'):
            raise AssertionError(f'file opened for writing: {file}')
        return real_open(file, mode, *args, **kwargs)

    def trap(*args, **kwargs):
        raise AssertionError('temp file created')

    monkeypatch.setattr(builtins, 'open', no_write_open)
    monkeypatch.setattr(tempfile, 'mkstemp', trap)
    monkeypatch.setattr(tempfile, 'NamedTemporaryFile', trap)
    frames = _real_jpegs(20)
    video = rewind_mod.encode_mp4(frames)
    assert video[4:8] == b'ftyp' and len(video) > 1000            # a real MP4, from stdout
    client = FakeTL()
    rewind = rewind_mod.Rewind('s', client=client)                # default encoder: the real ffmpeg pipe
    rewind.set_on(True)
    rewind.clips.append(rewind_mod.Clip(start_s=0, end_s=5, frames=frames, status='pending'))
    asyncio.run(rewind.flush(wait=True))
    assert rewind.clips[0].status == 'ready' and client.uploads[0][1][4:8] == b'ftyp'
    assert list(tmp_path.iterdir()) == []                         # nothing landed in cwd or TMPDIR
    tempfile.tempdir = None
