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

    analyzed = None

    async def analyze(self, mp4, prompt, schema=None, model=None, max_tokens=800):
        self.analyzed = (mp4, prompt, schema)
        return json.dumps({'steps': [{'t': 5.0, 'text': 'Plugged in the CPU fan cable'},
                                     {'t': 0.1, 'text': 'Installed the CPU'}],
                           'skipped': ['install the RAM', 'juggle the case']}), {'output_tokens': 40}

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
    assert clip.status == 'ready' and clip.video_id == 'vid-1' and len(clip.frames) in (6, 7)
    assert any(f[0] == clip.key_s for f in clip.frames)   # the change frame itself is kept
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
    assert text == "I'm not sure I saw it. Maybe about 20 seconds in or right at the start of the call. Here's my best guess."
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
    from server.rewind import fmt_offset
    assert [fmt_offset(s) for s in (2, 42, 60, 130)] == [
        'right at the start of the call', 'about 42 seconds in', 'about 1 minute in', 'about 2 minutes 10 seconds in']


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


def test_voice_path_through_ws2():
    """Typed "when did I ..." over /ws2: Rewind state with the notice, then a spoken answer and the hit frame."""
    from contracts import validate
    from server.app import create_app
    from server.test_agent import FRAME, LLM, Vision

    app = create_app(static_dir='/nonexistent')
    app.state.vision_v2 = Vision()
    app.state.llm_v2 = LLM()
    app.state.rewind = Registry(FakeTL([dict(video_id='vid-1', start=0, end=4, rank=1)]), encoder=fake_encoder)

    def until(ws, kind):
        while True:
            msg = ws.receive_json()
            validate('server_message_v2', msg)
            if msg['type'] == kind:
                return msg

    with TestClient(app) as client, client.websocket_connect('/ws2') as ws:
        ws.send_json(dict(v=2, type='hello', session_id='s', pack='general', rewind=True))
        state = until(ws, 'rewind_state')
        assert state['on'] and 'TwelveLabs' in state['notice']
        ws.send_json(FRAME)
        until(ws, 'track')                                  # first keyframe scanned: a clip is open
        rewind = app.state.rewind.get('s')
        assert rewind.clips and rewind.clips[0].frames
        rewind.clips[0].status = 'pending'
        assert client.post('/api/rewind/flush', json={'session_id': 's'}).json()['uploaded'] == 1
        for _ in range(100):
            if rewind.clips[0].status == 'ready':
                break
            import time
            time.sleep(0.02)
        ws.send_json(dict(v=2, type='user_text', session_id='s', text='Where did I put the screw?', final=True))
        hit = until(ws, 'rewind_hit')
        said = until(ws, 'say')
        assert hit['sure'] and hit['objects'][0]['label'] == 'screw' and hit['frame_b64']
        assert said['text'].startswith('That was ') and said['final']
        assert until(ws, 'turn')['stage'] in ('speaking', 'done')
        ws.send_json(dict(v=2, type='rewind', session_id='s', on=False))
        assert until(ws, 'rewind_state')['on'] is False


def test_follow_samples_any_frame_source():
    """A paired phone camera writes session.frame directly; Rewind samples it the same way."""
    class S:
        camera = True
        frame = None

    async def go():
        rewind = Rewind('s1', client=FakeTL(), encoder=fake_encoder)
        rewind.set_on(True)
        session = S()
        task = asyncio.create_task(rewind.follow(session, every=999))
        session.frame = dict(seq=1, jpeg_b64=JPEG)
        await asyncio.sleep(0.3)                          # sampling is capped at 4 frames per second
        session.frame = dict(seq=2, jpeg_b64=JPEG)
        await asyncio.sleep(0.3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return len(rewind.ring)

    assert asyncio.run(go()) == 2



def test_recap_orders_steps_maps_times_and_filters_skipped():
    from server.rewind import recap
    rewind = ready_rewind([])                                # clips at 1..6 s and 18..23 s, 6 kept frames each
    result = asyncio.run(recap(rewind, mode='pc_build', encoder=lambda frames, path: len(frames) * 0.5))
    mp4, prompt, schema = rewind.client.analyzed
    assert 'install the RAM' in prompt and 'never describe or identify people' in prompt and schema
    assert [s['text'] for s in result['steps']] == ['Installed the CPU', 'Plugged in the CPU fan cable']
    assert result['steps'][0]['t_s'] < 7 <= 18 <= result['steps'][1]['t_s']     # t mapped back to call time
    assert result['skipped'] == ['install the RAM']           # free text from the model is dropped
    assert result['frames'] in range(12, 15)


def test_recap_uses_only_uploaded_clips():
    from server.rewind import recap
    rewind, clock = make([])
    rewind.set_on(True)
    feed(rewind, clock, 0, 12, keyframes=[3])                # finished but never uploaded
    result = asyncio.run(recap(rewind, mode='cooking'))
    assert result['steps'] == [] and rewind.client.analyzed is None and 'Nothing to recap' in result['note']


def test_tool_interface():
    from server import rewind_tools
    rows = [dict(video_id='vid-2', start=0, end=5, rank=1), dict(video_id='vid-1', start=0, end=5, rank=2)]

    class Session:
        session_id = 's1'
        pack = type('P', (), {'id': 'pc_build'})()

    session = Session()
    assert rewind_tools.tools_for(session) == []
    session.rewind = ready_rewind(rows)
    names = [t['name'] for t in rewind_tools.tools_for(session)]
    assert names == ['search_past', 'recap_call']
    assert all(set(t) == {'name', 'description', 'input_schema'} for t in rewind_tools.TOOLS)
    fan = dict(id='o1', label='CPU fan', bbox=[0.4, 0.3, 0.2, 0.2], conf=0.8)
    result, cards = asyncio.run(rewind_tools.run_tool('search_past', {'query': 'plug in the CPU fan'}, session,
                                                      vision=FakeVision([fan]), turn_id='t1'))
    assert {k: result[k] for k in ('sure', 'call_time_s', 'label', 'box', 'clip_id', 'alternatives')} == dict(
        sure=True, call_time_s=20.0, label='CPU fan', box=[0.4, 0.3, 0.2, 0.2], clip_id='vid-2', alternatives=[3.0])
    json.dumps(result)                                        # JSON-safe tool_result, no image bytes
    assert 'frame_b64' not in result and cards[0]['type'] == 'rewind_hit' and cards[0]['turn_id'] == 't1'
    session.rewind.encoder = lambda frames, path: len(frames) * 0.5
    result, cards = asyncio.run(rewind_tools.run_tool('recap_call', {}, session, turn_id='t2'))
    assert result['skipped'] == ['install the RAM'] and result['say'].startswith("Here's what you did: Installed")
    assert cards[0]['type'] == 'rewind_recap'


def test_recap_route_and_typed_recap_over_ws2():
    from contracts import validate
    from server.app import create_app
    from server.test_agent import FRAME, LLM, Vision

    app = create_app(static_dir='/nonexistent')
    app.state.vision_v2 = Vision()
    app.state.llm_v2 = LLM()
    app.state.rewind = Registry(FakeTL([]), encoder=fake_encoder)

    def until(ws, kind):
        while True:
            msg = ws.receive_json()
            validate('server_message_v2', msg)
            if msg['type'] == kind:
                return msg

    with TestClient(app) as client:
        assert client.post('/api/rewind/recap', json={'session_id': 'nope'}).status_code == 404
        with client.websocket_connect('/ws2') as ws:
            ws.send_json(dict(v=2, type='hello', session_id='s', pack='pc_build', rewind=True))
            until(ws, 'rewind_state')
            ws.send_json(dict(v=2, type='confirm', session_id='s', what='power_off', value=True))
            ws.send_json(FRAME)
            until(ws, 'track')
            rewind = app.state.rewind.get('s')
            rewind.clips[0].status = 'pending'
            ws.send_json(dict(v=2, type='user_text', session_id='s', text='Recap please, did I skip anything?',
                              final=True))
            first = until(ws, 'say')
            card = until(ws, 'rewind_recap')
            last = until(ws, 'say')
            assert first['text'] == 'Let me look back over the call.' and not first['final']
            assert card['skipped'] == ['install the RAM'] and last['final']
        body = client.post('/api/rewind/recap', json={'session_id': 's'}).json()
        assert body['mode'] == 'pc_build' and body['steps'][0]['text'] == 'Installed the CPU'
