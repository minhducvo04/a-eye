"""Synthetic clip playback; HTTP is mocked and camera images are generated in RAM."""
import asyncio
import base64
import io
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from server import rewind as rw, rewind_tools
from server.test_rewind import FakeTL


def jpeg(value):
    out = io.BytesIO()
    Image.new('RGB', (640, 480), (value, 0, 0)).save(out, format='JPEG')
    return out.getvalue()


def current_call():
    call = rw.Rewind('current', client=FakeTL([dict(video_id='video', start=0, end=10, rank=1)]))
    call.set_on(True)
    call.index_id = 'index'
    call.clips = [rw.Clip(0, 10, key_s=5, video_id='video', status='ready',
                          frames=[(i / 4, jpeg(i * 5)) for i in range(41)])]
    return call


def test_this_call_card_has_small_ordered_frames_and_no_media_in_tool_result():
    call = current_call()
    result, cards = asyncio.run(rewind_tools.run_tool('search_past', {'query': 'keys'},
                                                     SimpleNamespace(rewind=call)))
    card = cards[0]
    assert card['type'] == 'rewind_hit' and card['t_s'] == 5
    assert len(card['frames_b64']) == 12 and 0 < card['fps'] <= 4
    colors = []
    for encoded in card['frames_b64']:
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as frame:
            assert frame.size == (320, 240)
            colors.append(frame.getpixel((0, 0))[0])
    assert colors == sorted(colors) and abs(colors[0] - 40) < 3 and abs(colors[-1] - 160) < 3
    assert not {'frames_b64', 'fps', 'frame_b64', 'clip_url'} & result.keys()


def test_past_call_retrieves_hls_with_video_relative_window(monkeypatch):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={'hls': {'video_url': 'https://media.invalid/clip.m3u8'}})

    call = rw.Rewind('current', client=rw.TwelveLabsClient(key='fake', transport=httpx.MockTransport(reply)))
    call.set_on(True)
    call.index_id = 'index'
    hit = dict(past_call=True, video_id='old-video', t_s=103, video_t_s=3, frame=None)
    fields = asyncio.run(rw.hit_media(call, hit))
    card = rw.hit_message(dict(sure=False, call_time_s=103, label='keys', box=None, alternatives=[], **fields))
    assert requests == ['/v1.3/indexes/index/videos/old-video']
    assert card['clip_url'] == 'https://media.invalid/clip.m3u8'
    assert (card['t_s'], card['start_s'], card['end_s']) == (103, 0, 6)


def test_past_call_timeout_keeps_existing_still(monkeypatch):
    call = current_call()
    cancelled = []

    async def slow(*args):
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.append(True)

    call.client.retrieve_video = slow
    wait_for = asyncio.wait_for

    async def fast_wait(awaitable, timeout):
        assert timeout == 2
        return await wait_for(awaitable, 0.01)

    monkeypatch.setattr(rw.asyncio, 'wait_for', fast_wait)
    fields = asyncio.run(rw.hit_media(call, dict(past_call=True, video_id='old-video', t_s=3,
                                               video_t_s=3, frame=jpeg(100))))
    assert fields['frame_b64'] and 'clip_url' not in fields and cancelled == [True]


@pytest.mark.parametrize('blocked', ['private', 'local_only', 'off'])
def test_video_retrieval_respects_privacy(monkeypatch, blocked):
    call = current_call()

    async def forbidden(*args):
        pytest.fail('retrieval must not run without cloud consent')

    call.client.retrieve_video = forbidden
    if blocked == 'private':
        call.private = True
    elif blocked == 'local_only':
        monkeypatch.setenv('LOCAL_ONLY', '1')
    else:
        call.set_on(False)
    fields = asyncio.run(rw.hit_media(call, dict(past_call=True, video_id='old-video', t_s=3, frame=None)))
    assert 'clip_url' not in fields


def test_live_memory_uses_clip_media_for_both_scopes(tmp_path, monkeypatch):
    from server import privacy
    from server.agent import Session
    from server.gemini_live import LiveBridge
    from server.test_past_calls import library

    async def trial():
        async def emit(*args):
            pass

        call = current_call()
        call.clock = lambda: call.started + 100
        session = Session('current')
        session.rewind = call
        privacy.set_call(rewind=True)
        bridge = LiveBridge(session, None, None, emit, emit)
        _, cards = await bridge._lookup_memory('Where were my keys?', scope='rewind')
        assert len(cards[0]['frames_b64']) == 12

        saved = library(tmp_path, monkeypatch)
        saved.rewind.set_on(True)

        async def retrieve(index, video):
            assert (index, video) == ('idx-1', 'old-video')
            return {'hls': {'video_url': 'https://media.invalid/saved.m3u8'}}

        saved.rewind.client.retrieve_video = retrieve
        session.rewind = saved.rewind
        _, cards = await bridge._lookup_memory('Where was my wrench last call?', scope='past_calls')
        assert cards[0]['clip_url'] == 'https://media.invalid/saved.m3u8'
        assert (cards[0]['t_s'], cards[0]['start_s'], cards[0]['end_s']) == (23, 0, 6)

    asyncio.run(trial())
