"""Rewind with a fake TwelveLabs client and a fake vision host. No network, no ffmpeg."""
import asyncio
import base64
import json
import os

import httpx
from fastapi.testclient import TestClient

from server.rewind import (Registry, Rewind, TwelveLabsClient, is_rewind_question, query_from, target_from)

JPEG = base64.b64encode(b'\xff\xd8fake\xff\xd9').decode()


class FakeTL:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.uploads = []
        self.searches = []

    async def ensure_index(self):
        return 'idx-1'

    async def upload(self, index_id, path, metadata):
        assert os.path.exists(path)
        self.uploads.append((index_id, path, metadata))
        n = len(self.uploads)
        return f'task-{n}', f'vid-{n}'

    async def task(self, task_id):
        return {'status': 'ready'}

    async def search(self, index_id, query, video_ids=None, limit=5):
        self.searches.append((index_id, query, list(video_ids or [])))
        return [r for r in self.rows if not video_ids or r['video_id'] in video_ids]


class FakeVision:
    def __init__(self, objects):
        self.objects = objects
        self.calls = []

    async def call(self, operation, payload):
        self.calls.append((operation, payload))
        return dict(caption='', objects=self.objects, ms=1)


def fake_encoder(frames, path):
    with open(path, 'wb') as handle:
        handle.write(b'mp4')


def make(rows=None):
    clock = [0.0]
    rewind = Rewind('s1', client=FakeTL(rows), clock=lambda: clock[0], encoder=fake_encoder)
    return rewind, clock


def feed(rewind, clock, start, end, keyframes=()):
    t = start
    while t <= end + 1e-9:
        clock[0] = t
        rewind.add_frame(JPEG)
        if any(abs(t - k) < 1e-9 for k in keyframes):
            rewind.keyframe('change')
        t = round(t + 0.25, 2)


def test_off_by_default_keeps_nothing():
    rewind, clock = make()
    feed(rewind, clock, 0, 5, keyframes=[1])
    assert rewind.on is False and not rewind.ring and not rewind.clips
    text, hit = asyncio.run(rewind.answer('when did I plug in the CPU fan?'))
    assert 'Rewind is off' in text and hit is None


def test_clip_has_preroll_extends_and_closes():
    rewind, clock = make()
    rewind.set_on(True)
    feed(rewind, clock, 0, 17, keyframes=[5, 6, 15])
    first, second = rewind.clips
    assert (first.start_s, first.key_s, first.end_s) == (3.0, 5.0, 9.0)   # 2 s before, extended by the 6 s change
    assert first.frames[0][0] == 3.0 and first.frames[-1][0] == 9.0
    assert first.status == 'pending' and second.status == 'open'
    assert rewind.keyframe('heartbeat') is None            # only real changes cut clips


def test_flush_uploads_deletes_temp_and_thins_frames():
    rewind, clock = make()
    rewind.set_on(True)
    feed(rewind, clock, 0, 12, keyframes=[3])
    asyncio.run(rewind.flush(wait=True))
    clip = rewind.clips[0]
    _, path, metadata = rewind.client.uploads[0]
    assert not os.path.exists(path)                        # no video stays on disk
    assert clip.status == 'ready' and clip.video_id == 'vid-1' and len(clip.frames) == 6
    assert metadata['start_s'] == 1.0 and metadata['end_s'] == 6.0
    assert rewind.status() == dict(on=True, clips=1, ready=1, indexing=0, pending=0)


def test_turning_off_drops_unsent_clips():
    rewind, clock = make()
    rewind.set_on(True)
    feed(rewind, clock, 0, 12, keyframes=[3])
    rewind.set_on(False)
    asyncio.run(rewind.flush(wait=True))
    assert rewind.clips == [] and rewind.client.uploads == []


def ready_rewind(rows):
    rewind, clock = make(rows)
    rewind.set_on(True)
    feed(rewind, clock, 0, 30, keyframes=[3, 20])
    rewind.close()
    asyncio.run(rewind.flush(wait=True))
    return rewind


def test_search_maps_clip_time_to_call_time():
    rows = [dict(video_id='vid-2', start=0, end=5, rank=1), dict(video_id='vid-1', start=3, end=5, rank=2),
            dict(video_id='other-call', start=0, end=4, rank=3)]
    rewind = ready_rewind(rows)
    hits = asyncio.run(rewind.search('a red ball'))
    assert [(h['t_s'], h['start_s'], h['end_s']) for h in hits] == [(20.0, 18.0, 23.0), (4.0, 4.0, 6.0)]
    assert rewind.client.searches[0][2] == ['vid-1', 'vid-2']   # only this call's videos


def test_answer_claims_only_what_local_vision_confirms():
    rows = [dict(video_id='vid-2', start=0, end=5, rank=1), dict(video_id='vid-1', start=0, end=5, rank=2)]
    rewind = ready_rewind(rows)
    fan = dict(id='o1', label='CPU fan', bbox=[0.4, 0.3, 0.2, 0.2], conf=0.8)
    vision = FakeVision([fan])
    text, hit = asyncio.run(rewind.answer('When did I plug in the CPU fan?', vision=vision))
    assert text == "That was about 20 seconds in. Here's the clip."
    assert hit['sure'] and hit['objects'] == [fan] and hit['frame']
    assert vision.calls[0][1]['queries'] == ['CPU fan']

    text, hit = asyncio.run(rewind.answer('When did I plug in the CPU fan?',
                                          vision=FakeVision([dict(fan, label='RAM stick')])))
    assert text == "I'm not sure I saw it. Maybe about 20 seconds in or 3 seconds in. Here's my best guess."
    assert hit['sure'] is False and hit['alternatives'] == [3.0]


def test_answer_without_hits_or_while_indexing():
    rewind = ready_rewind([])
    assert asyncio.run(rewind.answer('where did I put the screw?'))[0] == "I didn't find that moment in this call."
    rewind, clock = make([])
    rewind.set_on(True)
    feed(rewind, clock, 0, 12, keyframes=[3])
    rewind.clips[0].status = 'indexing'
    rewind.clips[0].video_id = 'vid-x'
    assert 'still indexing' in asyncio.run(rewind.answer('where did I put the screw?'))[0]


def test_question_and_query_words():
    assert is_rewind_question('When did I plug in the CPU fan?')
    assert is_rewind_question('where did I put the screw')
    assert not is_rewind_question('which header does the CPU fan go in?')
    assert query_from('When did I plug in the CPU fan?') == 'plug in the CPU fan'
    assert target_from('plug in the CPU fan') == 'CPU fan'


def test_registry_falls_back_to_last_call_with_clips():
    registry = Registry(FakeTL())
    old = registry.open('a', on=True, encoder=fake_encoder)
    old.clips.append(object())
    current = registry.open('b')
    assert registry.for_question('b') is old
    current.clips.append(object())
    assert registry.for_question('b') is current


def test_http_client_creates_index_and_searches_with_filter(monkeypatch):
    monkeypatch.setenv('TWELVELABS_API_KEY', 'tlk_test')
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers['x-api-key'] == 'tlk_test'
        if request.method == 'GET' and request.url.path.endswith('/indexes'):
            return httpx.Response(200, json={'data': [{'_id': 'x', 'index_name': 'My Index (Default)'}]})
        if request.url.path.endswith('/indexes'):
            body = json.loads(request.content)
            assert body['index_name'] == 'a-eye-rewind' and body['models'][0]['model_name'] == 'marengo3.0'
            return httpx.Response(201, json={'_id': 'new'})
        return httpx.Response(200, json={'data': [dict(video_id='v', start=1, end=2, rank=1)]})

    client = TwelveLabsClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(client.ensure_index()) == 'new'
    rows = asyncio.run(client.search('new', 'a red ball', video_ids=['v']))
    assert rows[0]['video_id'] == 'v'
    form = seen[-1].content.decode()
    assert 'name="query_text"' in form and '{"id": ["v"]}' in form and 'name="search_options"' in form


def test_http_client_needs_key(monkeypatch):
    monkeypatch.delenv('TWELVELABS_API_KEY', raising=False)
    try:
        asyncio.run(TwelveLabsClient().ensure_index())
    except RuntimeError as exc:
        assert 'not set' in str(exc)
    else:
        raise AssertionError('missing key must fail')


def test_routes(monkeypatch):
    from server.app import create_app
    app = create_app(static_dir='/nonexistent')
    registry = Registry(FakeTL([dict(video_id='vid-1', start=0, end=5, rank=1)]))
    app.state.rewind = registry
    with TestClient(app) as client:
        assert client.get('/api/rewind/status').json()['on'] is False
        assert client.post('/api/rewind/search', json={'query': ''}).status_code == 422
        assert client.post('/api/rewind/flush', json={'session_id': 'nope'}).status_code == 404
        clock = [0.0]
        rewind = registry.open('s1', on=True, clock=lambda: clock[0], encoder=fake_encoder)
        clock[0] = 10.0
        rewind.add_frame(JPEG)
        rewind.keyframe('first')
        rewind.close()
        assert client.post('/api/rewind/flush', json={'session_id': 's1'}).json()['uploaded'] == 1
        asyncio.run(rewind.wait_ready(rewind.clips[0]))
        hits = client.post('/api/rewind/search', json={'query': 'red ball', 'session_id': 's1'}).json()['hits']
        assert hits == [dict(t_s=10.0, start_s=8.0, end_s=13.0, rank=1)]
        status = client.get('/api/rewind/status', params={'session_id': 's1'}).json()
        assert status['ready'] == 1 and 'TwelveLabs' in status['notice']
