import asyncio
from types import SimpleNamespace

import pytest

from server.recent_memory import RecentMemory, source_for, answer


def scene(note, *labels):
    return dict(caption=note, objects=[dict(label=x) for x in labels], image_b64='never retain')


@pytest.mark.parametrize('match', ['call_started_wall', 'video_id'])
def test_past_search_hit_includes_matching_call_summary(monkeypatch, match):
    from server import rewind as rw

    summary = "colorful patterned tumbler with a blue and white design; That's a nice travel mug. " + 'x' * 600
    calls = [
        dict(started_wall=100, summary=summary, clips=[dict(video_id='mug-video')]),
        dict(started_wall=200, summary='Unrelated call with a wrench', clips=[]),
    ]
    monkeypatch.setattr(rw, 'kept_calls', lambda owner: calls if owner == 'fixture-owner' else [])

    async def search_kept(question):
        return [dict(t_s=3, **{match: 100 if match == 'call_started_wall' else 'mug-video'})]

    session = SimpleNamespace(
        recent_memory=RecentMemory(),
        rewind=SimpleNamespace(on=False, owner='fixture-owner', search_kept=search_kept),
    )
    result = asyncio.run(answer(session, 'What did I show you last call?'))
    assert result['found'] and result['source'] == 'rewind' and result['t_s'] == 3
    assert 'In that call: ' + summary[:600] + '.' in result['say']
    assert summary[:601] not in result['say']
    assert 'Unrelated' not in result['say']
    assert 'earlier call' in result['say'] or 'last call' in result['say'].lower()
    assert 'our call' not in result['say'] and 'this call' not in result['say']


def test_window_step_and_specific_time():
    log = RecentMemory(clock=lambda: 180, started=0)
    log.add(scene('Red wire beside multimeter', 'red wire', 'multimeter'), 60, 'Step 3: place wire')
    log.add(scene('Red wire on breadboard row 12', 'red wire', 'breadboard'), 120, 'Step 4: connect wire')
    log.add(scene('Soldering iron picked up', 'soldering iron'), 179)
    assert 'row 12' in log.find('where did I put the red wire a minute ago?')['say']
    assert 'Step 3' in log.find('what was step 3?')['say']
    assert 'Soldering iron' in log.find('what did I just do?')['say']
    assert log.find('where did I put the blue wire?') is None
    assert 'image_b64' not in repr(log.entries)
    log.prune(661)  # the RAM log keeps 10 minutes
    assert len(log.entries) == 2
    log.clear()
    assert not log.entries


def test_temporal_routes():
    for text, on, want in [
        ('what did I just do?', True, 'recent'),
        ('where did I put the wire a minute ago?', True, 'recent'),
        ('what was step 3?', False, 'recent'),
        ('what step was I just on?', True, 'recent'),
        ('what happened earlier in this call?', True, 'rewind'),
        ('what happened earlier in this call?', False, 'recent'),
        ('where was the resistor yesterday?', True, 'long-term'),
        ('what did I do last time?', False, 'long-term'),
        ('where was the wire 3 minutes ago?', True, 'recent'),
        ('where was the wire 6 minutes ago?', True, 'rewind'),
        ('where does this resistor go?', True, None),
    ]:
        assert source_for(text, on) == want


def test_start_of_call_selects_opening_scene_not_latest_or_transcript():
    log = RecentMemory(clock=lambda: 60, started=0)
    log.add(scene('A blue mug on the table', 'the object'), 1)
    log.add(scene('A red apple on the table', 'the object'), 25)
    log.note_transcript('You showed a wrench.', 'helper')
    hit = log.find('what did I show you at the start of this call?')
    assert hit and hit['t_s'] == 1 and 'mug' in hit['say'] and 'apple' not in hit['say']
    assert log.find('did you see my wrench earlier?') is None
    log.prune(602)
    assert log.find('what did I show you at the start of this call?') is None


def test_generic_opening_caption_does_not_inherit_live_mug_claim():
    log = RecentMemory(clock=lambda: 60, started=0)
    log.add(scene('An object on the table', 'the object'), 1)
    log.note_transcript('I see a blue mug.', 'helper')
    hit = log.find('what did I show you at the start of this call?')
    assert hit and 'object' in hit['say'] and 'mug' not in hit['say']
    assert log.find('did you see a mug earlier?') is None


def test_recent_never_calls_cloud_and_no_wrong_time_fallback():
    async def check():
        log = RecentMemory(clock=lambda: 100, started=0)
        log.add(scene('Resistor placed on breadboard row 12', 'resistor'), 99)
        session = SimpleNamespace(recent_memory=log, rewind=None)
        result = await answer(session, 'what did I just do?')
        assert result['source'] == 'recent' and 'row 12' in result['say']
        result = await answer(session, 'where was the resistor yesterday?')
        assert result['source'] == 'unavailable' and 'yesterday' in result['say']
    asyncio.run(check())


def test_rewind_age_filter_and_off_switch(monkeypatch):
    from server.rewind import Rewind, Clip

    class Client:
        async def search(self, index_id, query, video_ids, limit):
            assert video_ids == ['old']
            return [dict(video_id='new', start=0, end=4, rank=1),
                    dict(video_id='old', start=0, end=4, rank=2)]

    async def check():
        rewind = Rewind('fixture', client=Client(), clock=lambda: 100)
        rewind.set_on(True)
        rewind.clips = [Clip(10, 15, video_id='old', status='ready'),
                        Clip(85, 90, video_id='new', status='ready')]
        hits = await rewind.search('resistor', before_s=80)
        assert [h['video_id'] for h in hits] == ['old']
        rewind.set_on(False)
        log = RecentMemory(clock=lambda: 100, started=0)
        session = SimpleNamespace(recent_memory=log, rewind=rewind)
        async def forbidden(*args, **kwargs):
            raise AssertionError('cloud must not run')
        rewind.answer = forbidden
        result = await answer(session, 'where was the resistor 3 minutes ago?')
        assert result['source'] == 'unavailable'
        rewind.on = True
        monkeypatch.setenv('LOCAL_ONLY', '1')
        result = await answer(session, 'where was the resistor 3 minutes ago?')
        assert result['source'] == 'unavailable'
    asyncio.run(check())


def test_ws_recent_answer_without_brain_and_cleanup(monkeypatch):
    from fastapi.testclient import TestClient
    from server import ws2
    from server.test_ws2 import app, send, hello
    from server.test_pipeline import finish

    sessions = []
    original = ws2.Session
    def capture(*args, **kwargs):
        session = original(*args, **kwargs)
        sessions.append(session)
        return session
    monkeypatch.setattr(ws2, 'Session', capture)
    application = app()
    with TestClient(application) as client, client.websocket_connect('/ws2') as socket:
        hello(socket)
        assert sessions[0].recent_memory.entries
        send(socket, 'user_text', text='what did I just do?', final=True)
        messages = finish(socket)
        assert any(m['type'] == 'say' and 'scene note' in m['text'] for m in messages)
        assert not application.state.llm_v2.calls
        send(socket, 'hello', pack='general', camera=False)
        from server.test_pipeline import read
        read(socket)
        assert not sessions[0].recent_memory.entries
    assert all(not session.recent_memory.entries for session in sessions)


def test_fixture_sources_and_honest_fallback(tmp_path, monkeypatch):
    from scripts.recent_memory_bench import benchmark, fixture
    from server.privacy import set_call
    set_call(rewind=True)  # The fake recording path models an explicitly opted-in call.

    async def check():
        monkeypatch.delenv('LOCAL_ONLY', raising=False)
        report = await benchmark()
        assert report['right_source'] == report['answer_checks'] == 20
        assert report['latency']['recent']['max_ms'] < 1000
        session = fixture(tmp_path)
        async def unavailable(*args, **kwargs):
            return 'Indexing', None
        session.rewind.answer = unavailable
        result = await answer(session, 'Where was the resistor earlier in this call?')
        # Rewind has nothing yet: this call's own notes come before an earlier call.
        assert result['source'] == 'recent' and result['say'].startswith('From my notes of this call')
        session.recent_memory.entries.clear()
        result = await answer(session, 'Where was the resistor earlier in this call?')
        assert result['source'] == 'long-term'
        assert 'earlier call' in result['say'] and 'parts bin' in result['say']
        session.rewind.memory_writer.store.save_settings(dict(remembering=False))
        result = await answer(session, 'Where was the resistor yesterday?')
        assert result['source'] == 'unavailable'
    asyncio.run(check())


def test_step_instruction_not_claimed_as_completed_action():
    log = RecentMemory(clock=lambda: 100, started=0)
    log.note_step('Step 3: place resistor on row 12.')
    assert 'guide said' in log.find('what was step 3?')['say']
    assert log.find('what did I just do?') is None
    log.add(scene('Red wire on tray', 'red wire'), 100)
    assert log.entries[-1]['step'].startswith('Step 3:')


def test_live_transcripts_are_not_scene_evidence_and_steps_expire():
    now = [100]
    log = RecentMemory(clock=lambda: now[0], started=0)
    log.note_transcript('I placed the resistor.', 'user')
    assert log.find('what step was I just on?') is None
    log.note_transcript('Step 3: place resistor on row 12.', 'helper')
    assert 'guide said' in log.find('what step was I just on?')['say']
    assert log.find('what did I just do?') is None
    now[0] = 701
    assert log.find('what step was I just on?') is None
    assert not log.entries


def test_two_minutes_ago_plurals_and_synonyms():
    log = RecentMemory(clock=lambda: 130, started=0)
    log.add(scene('Wrench set on the towels', 'wrench'), 10)
    log.add(scene('Cup on the shelf', 'cup'), 100)
    assert 'towels' in log.find('where did I put the wrench two minutes ago?')['say']
    assert 'shelf' in log.find('where did I leave the mug?')['say']
    assert 'towels' in log.find('what did I do with the wrenches?')['say']
    assert log.find('where did I put the screwdriver a minute ago?') is None


def test_where_was_mug_a_minute_ago_uses_last_caption_not_current_desk():
    """Mug at t=0, desk without mug at t=40 s, "where was the mug a minute ago?" at t=70 s."""
    log = RecentMemory(clock=lambda: 70, started=0)
    log.add(scene('A travel mug on the desk next to the keyboard'), 0)
    log.add(scene('A wooden desk with a keyboard and monitor'), 40)
    hit = log.find('Where was the mug a minute ago?')
    assert hit and hit['found']
    assert 'on the desk next to the keyboard' in hit['say']
    assert '70' in hit['say'] or 'minute' in hit['say']
    assert log.find('Where was the screwdriver a minute ago?') is None

    async def check():
        session = SimpleNamespace(recent_memory=log, rewind=None, private=False)
        result = await answer(session, 'Where was the mug a minute ago?')
        assert result['found'] and 'on the desk next to the keyboard' in result['say']
        missed = await answer(session, 'Where was the screwdriver a minute ago?')
        assert not missed['found'] and "didn't see that in my notes" in missed['say']
        fresh = RecentMemory(clock=lambda: 70, started=0)
        fresh.add(scene('A travel mug in the current camera view'), 68)
        session.recent_memory = fresh
        now_cam = await answer(session, 'Where was the mug a minute ago?')
        assert not now_cam['found'] and "didn't see that in my notes" in now_cam['say']
    asyncio.run(check())


def test_last_week_reads_task_history_and_never_invents_one():
    from datetime import datetime, timedelta, timezone

    async def check(entries):
        log = RecentMemory(clock=lambda: 10, started=0)
        session = SimpleNamespace(recent_memory=log, rewind=None, growth=SimpleNamespace(entries=entries))
        return await answer(session, 'What did we fix last week?')
    five_days = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    result = asyncio.run(check([dict(task='sink', date=five_days, completed=True)]))
    assert result['source'] == 'history' and 'sink' in result['say'] and 'finished it' in result['say']
    result = asyncio.run(check([]))
    assert not result['found'] and "don't have a saved task from last week" in result['say']
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    assert not asyncio.run(check([dict(task='hinge', date=old, completed=True)]))['found']
