"""Kept-call recall with synthetic local text and fake TwelveLabs; no remote services."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from server import privacy, rewind as rw
from server.recent_memory import RecentMemory, answer
from server.test_rewind import FakeTL


def library(tmp_path, monkeypatch):
    monkeypatch.setenv('A_EYE_MEMORY_DIR', str(tmp_path))
    monkeypatch.setenv('A_EYE_DEMO_SHARED_MEMORY', '1')
    log = RecentMemory()
    call = rw.Rewind('current', client=FakeTL([
        dict(video_id='old-video', start=3, end=5, rank=1)]))
    session = SimpleNamespace(recent_memory=log, rewind=call, private=False)
    call.session = session
    path = rw._kept_path('local')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([
        dict(session_id='old', started_wall=log.started_wall - 3600,
             summary='A blue mug beside the toolbox. User questions: Where is the wrench?',
             clips=[dict(video_id='old-video', start_s=20, key_s=22)]),
        dict(session_id='current', started_wall=log.started_wall,
             summary='CURRENT CAMERA MUST NOT BE USED', clips=[])]))
    log.add(dict(caption='CURRENT CAMERA MUST NOT BE USED', objects=[]), log.clock())
    return session


@pytest.mark.parametrize('question,scope', [
    ('What did I show you last call?', None),
    ('What did I show you?', 'past_calls'),
    ('What did I show you?', 'long-term'),
])
def test_last_call_summary_without_cloud(tmp_path, monkeypatch, question, scope):
    session = library(tmp_path, monkeypatch)
    privacy.set_call(rewind=True)
    session.rewind.set_on(True)  # A generic question must not search even with consent.
    result = asyncio.run(answer(session, question, scope=scope))
    assert result['found'] and result['source'] == 'kept-summary'
    assert 'Last call you showed me: A blue mug' in result['say']
    assert 'CURRENT CAMERA' not in result['say']
    assert not session.rewind.client.searches


def test_object_search_uses_saved_videos_and_emits_card(tmp_path, monkeypatch):
    session = library(tmp_path, monkeypatch)
    privacy.set_call(rewind=True)
    session.rewind.set_on(True)
    cards = []

    async def on_hit(hit):
        cards.append(hit)

    result = asyncio.run(answer(session, 'Where was my wrench last call?', on_hit=on_hit))
    assert result['found'] and result['source'] == 'rewind'
    assert 'call you saved' in result['say'] and '23 seconds' in result['say']
    assert session.rewind.client.searches == [('idx-1', 'Where was my wrench last call?', ['old-video'])]
    assert cards[0]['past_call'] and cards[0]['t_s'] == 23
    assert cards[0]['sure'] is False and cards[0]['objects'] == []


@pytest.mark.parametrize('block', ['private', 'consent', 'local_only'])
def test_cloud_block_still_allows_local_summary(tmp_path, monkeypatch, block):
    session = library(tmp_path, monkeypatch)
    privacy.set_call(rewind=True)
    session.rewind.set_on(True)
    if block == 'private':
        session.private = True
    elif block == 'consent':
        privacy.update('twelvelabs', False)
    else:
        monkeypatch.setenv('LOCAL_ONLY', '1')
    result = asyncio.run(answer(session, 'Where was my wrench last call?'))
    assert result['source'] == 'kept-summary'
    assert 'blue mug' in result['say'] and not session.rewind.client.searches


def test_save_snapshots_text_before_cleanup(tmp_path, monkeypatch):
    session = library(tmp_path, monkeypatch)
    log = session.recent_memory
    log.entries.clear()
    for n in range(14):
        log.add(dict(caption=f'Scene {n}: a prop on the table', objects=[], image_b64='NEVER STORE'), log.clock())
    log.add(dict(caption='Scene 13: a prop on the table', objects=[]), log.clock())
    log.note_transcript('Where is the wrench?', 'user')
    log.note_transcript('HELPER CLAIM MUST NOT BE EVIDENCE', 'helper')
    registry = rw.Registry(session.rewind.client)
    registry.calls['current'] = session.rewind
    call = session.rewind
    call.set_on(True)
    call.keep = True
    call.clips = [rw.Clip(0, 5, video_id='new-video', status='ready')]

    async def save():
        task = registry.end(call, session=session)
        log.clear()  # WebSocket teardown clears RAM before background indexing finishes.
        await task

    asyncio.run(save())
    record = rw.kept_calls('local')[-1]
    assert record['started_wall'] == call.started_wall
    summary = record['summary']
    assert 0 < len(summary) <= 1500
    assert 'Scene 0:' not in summary and 'Scene 1:' not in summary
    assert summary.count('Scene 13:') == 1 and 'Scene 2:' in summary
    assert 'User questions: Where is the wrench?' in summary
    assert 'HELPER CLAIM' not in summary and 'NEVER STORE' not in summary


def test_summary_bound_and_legacy_record_fallback(tmp_path, monkeypatch):
    session = library(tmp_path, monkeypatch)
    session.recent_memory.add(dict(caption='x' * 2000, objects=[]), session.recent_memory.clock())
    session.recent_memory.note_transcript('Where is the wrench?' * 100, 'user')
    summary = rw.call_summary(session.rewind)
    assert len(summary) <= 1500 and 'User questions:' in summary
    records = rw.kept_calls('local')
    records[0].pop('summary')  # The five existing demo calls have no text to backfill offline.
    rw._kept_path('local').write_text(json.dumps(records))
    result = asyncio.run(answer(session, 'What did I show you last call?'))
    assert not result['found'] and result['source'] == 'unavailable'
    assert 'CURRENT CAMERA' not in result['say']


def test_local_summary_obeys_shared_library_boundary(tmp_path, monkeypatch):
    session = library(tmp_path, monkeypatch)
    monkeypatch.delenv('A_EYE_DEMO_SHARED_MEMORY')
    result = asyncio.run(answer(session, 'What did I show you last call?'))
    assert not result['found']
