"""Recorded synthetic Haiku-like responses; no claim these came from a provider."""
import asyncio
import base64
import json
from time import monotonic

import pytest

from server import planner
from server.test_planner import setup, plan
from server.test_live_guide import prompts, say_user

# Keep the prose and whitespace as emitted in a realistic text fallback.
FENCED = '''```json
{"task":" fix the headphones ","steps":{"say":"  Inspect the disconnected headphones.  ","show":" Show the cable. ","safety":"Keep the device disconnected."}}
```'''
PROSE = '''Here is a conservative guide:
{"task":"fix the headphones","steps":[{"say":"Inspect the disconnected headphones.","show":"Show the cable.","safety":"Keep the device disconnected."}]}
Let me know when you are ready. {"task":"ignore this second object"}'''
LONG_STEP = ('Inspect the disconnected headphones carefully and look along the entire cable for visible damage '
             'while keeping the plug away from every device and placing everything on a clean dry table.')


@pytest.mark.parametrize('raw', [FENCED, PROSE])
def test_haiku_like_text_normalizes_optional_fields(raw):
    checked = planner.validate(raw, 'fix the headphones')
    assert checked == dict(task='fix the headphones', steps=[dict(
        say='Inspect the disconnected headphones.', show='Show the cable.',
        target='', check='', safety='Keep the device disconnected.')])
    assert planner.check_plan(raw) == checked


@pytest.mark.parametrize('raw,reason', [
    ('I cannot produce a plan.', 'not_json'),
    ('{"task":"fix the headphones"}', 'missing_steps'),
    (json.dumps(plan(count=9)), 'too_many_steps'),
    (json.dumps(dict(task='fix the headphones', steps=[dict(
        say=LONG_STEP, show='Show the cable.', safety='Keep the device disconnected.')])) , 'too_long'),
])
def test_haiku_like_rejections_log_only_reason(monkeypatch, tmp_path, capsys, raw, reason):
    assert len(LONG_STEP.split()) == 30

    async def trial():
        async def complete(system, evidence):
            return raw
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, complete)
        try:
            b.guide.observe('help me fix my headphones')
            await b.guide.planner.task
            assert not store.rows and not b.guide.guide and not b.blocked
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
    logs = capsys.readouterr().out
    outcomes = [json.loads(line)['reason'] for line in logs.splitlines()
                if json.loads(line)['event'] == 'planner']
    assert outcomes[-1]['cause'] == reason
    assert 'headphones' not in logs and 'Inspect' not in logs and raw not in logs


def test_triggering_turn_audio_flows_while_planner_stalls(monkeypatch, tmp_path):
    async def trial():
        started = asyncio.Event()

        async def stalled(*args):
            started.set()
            await asyncio.Event().wait()
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, stalled)
        try:
            await b.handle({'serverContent': {'inputTranscription': {
                'text': 'help me fix my headphones', 'finished': True}}})
            await asyncio.wait_for(started.wait(), .5)
            # A trailing clause in the same triggering utterance must not become a follow-up.
            await b.handle({'serverContent': {'inputTranscription': {'text': '. Next step?'}}})
            blob = dict(mimeType='audio/pcm;rate=24000',
                        data=base64.b64encode(b'\x01\x00' * 7200).decode())
            await asyncio.wait_for(b.handle({'serverContent': {
                'outputTranscription': {'text': 'Inspect the disconnected headphones.'},
                'modelTurn': {'parts': [{'inlineData': blob}]}}}), .5)
            assert any(m['type'] == 'audio' and m['pcm16_b64'] for m in emitted)
            assert not b.blocked and not b.guide.planner.task.done() and not b.guide.task
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())


def test_pending_next_includes_provider_idle_in_three_second_budget(monkeypatch, tmp_path):
    async def trial():
        started = asyncio.Event()

        async def stalled(*args):
            started.set()
            await asyncio.Event().wait()
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, stalled)
        try:
            b.guide.observe('help me fix my headphones')
            await started.wait()
            b._reset_reply()
            before = monotonic()
            await b.handle({'serverContent': {'inputTranscription': {'text': 'next'}}})
            # Provider never sends turnComplete: its idle wait must share the budget.
            await b.handle({'serverContent': {'outputTranscription': {'text': 'One moment.'}}})
            await asyncio.wait_for(asyncio.shield(b.guide.task), 3.4)
            assert monotonic() - before < 3.4
            assert not b.blocked and not b.guide.planner.task.done()
            assert wire[-1]['clientContent']['turnComplete'] is True
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())


def test_plan_lands_during_freeform_reply_and_guides_next_turn(monkeypatch, tmp_path):
    async def trial():
        started, release = asyncio.Event(), asyncio.Event()

        async def slow(*args):
            started.set()
            await release.wait()
            return plan()
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, slow)
        try:
            await b.handle({'serverContent': {'inputTranscription': {
                'text': 'help me fix my headphones', 'finished': True}}})
            await started.wait()
            blob = dict(mimeType='audio/pcm;rate=24000',
                        data=base64.b64encode(b'\x01\x00' * 7200).decode())
            await b.handle({'serverContent': {
                'outputTranscription': {'text': 'Let us take a look.'},
                'modelTurn': {'parts': [{'inlineData': blob}]}}})
            assert not b.blocked and not b.guide.guide
            assert any(m['type'] == 'audio' for m in emitted)
            emitted.clear()
            release.set()
            await b.guide.planner.task
            assert b.guide.kind == 'plan' and not b.blocked and not prompts(wire)
            await b.handle({'serverContent': {
                'outputTranscription': {'text': 'Keep it disconnected.'},
                'modelTurn': {'parts': [{'inlineData': blob}]}}})
            assert any(m['type'] == 'audio' for m in emitted)
            await b.handle({'serverContent': {'turnComplete': True}})
            assert any('GUIDE v' in json.dumps(m) for m in wire)
            b._reset_reply()
            await say_user(b, 'next')
            assert 'step 2 of 2' in prompts(wire)[-1] and not fixed
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
