"""Synthetic LLM and Live packets only; no provider, camera, or network calls."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from server import planner, privacy
from server.test_live_guide import bridge_for, details, prompts, say_user


@pytest.fixture(autouse=True)
def isolated_planner(monkeypatch, tmp_path):
    monkeypatch.delenv('PLANNER', raising=False)
    monkeypatch.delenv('PLANNER_MODEL', raising=False)
    monkeypatch.setenv('PLANNER_CACHE_PATH', str(tmp_path / 'default-plans.json'))
    monkeypatch.setattr(planner, '_CACHE', None)


def plan(task='fix the headphones', count=2):
    return dict(task=task, steps=[dict(say='Inspect the disconnected headphones.',
        show='Show the cable.', target='headphones', check='Look for a loose connector.',
        safety='Keep the device disconnected.') for _ in range(count)])


def solder_plan(task):
    return dict(task=task, steps=[
        dict(say='Disconnect device power and arrange ventilation.', show='Show the disconnected device and extractor.',
             target='device', check='Check that power is disconnected and ventilation is running.', safety='Wear eye protection.'),
        dict(say='Place the iron in its stand.', show='Show the stable iron stand.', target='iron stand',
             check='Check that the stand is stable.', safety='Keep fingers away from the hot tip.'),
        dict(say='Solder the disconnected wire joint.', show='Show the wire joint.', target='wire joint',
             check='Let the joint cool before inspecting it.', safety='Keep ventilation running.')])


class FakeLLM:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    async def __call__(self, system, evidence):
        self.calls.append((system, json.loads(evidence)))
        return ('Facts: check the connector without power.' if len(self.calls) % 2 else
                json.dumps(self.result or plan(self.calls[-1][1]['task'])))


def setup(monkeypatch, tmp_path, llm=None):
    bridge, emitted, fixed, wire = bridge_for(monkeypatch)
    fake = llm or FakeLLM()
    store = planner.PlanCache(tmp_path / 'plans.json')
    bridge.guide.planner = planner.BackgroundPlanner(bridge.guide, fake, store)
    points = []

    async def ground(*args, **kwargs):
        points.append((args[2], kwargs))
        return None
    monkeypatch.setattr('server.pointer.ground', ground)
    return bridge, emitted, fixed, wire, fake, store, points


@pytest.mark.parametrize('finished', [False, True])
@pytest.mark.parametrize('chunks', [
    ('dad The wire on my headphones broke near the plug. How do I fix it?',),
    ('dad the wire on my headphones broke near the plug. How do I fix it?   ',),
    ('Dad, the wire on my headphones broke near the plug. How do I fix it?',),
    ('dad', ' The wire on my', ' headphones broke', ' near the plug.', ' How do I', ' fix it?   '),
])
def test_real_live_repair_chunks_use_app_client_and_advance(monkeypatch, tmp_path, capsys, finished, chunks):
    from server import llm
    from server.app import create_app

    fake = FakeLLM()
    options, clients = [], []

    class Client:
        def is_closed(self):
            return False

        def with_options(self, **kwargs):
            options.append(kwargs)
            return self

        @property
        def messages(self):
            return self

        async def create(self, **kwargs):
            text = await fake(kwargs['system'][0]['text'], kwargs['messages'][0]['content'])
            return SimpleNamespace(content=[SimpleNamespace(type='text', text=text)], usage=None)

    def client():
        clients.append(Client())
        return clients[-1]

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic')
    monkeypatch.setattr(llm, '_ANTHROPIC', {})
    monkeypatch.setattr(llm.anthropic, 'AsyncAnthropic', client)

    async def trial():
        # Actual app and default planner: only the provider transport is fake.
        b, emitted, fixed, wire = bridge_for(monkeypatch, app=create_app())
        try:
            for chunk in chunks:
                await b.handle({'serverContent': {'inputTranscription': {'text': chunk}}})
                assert b.guide.planner.task is None and not fake.calls
            if finished:
                await b.handle({'serverContent': {'inputTranscription': {'finished': True}}})
            await b.handle({'serverContent': {'turnComplete': True}})
            assert b.guide.planner.task is not None, 'finished Live utterance must request a plan'
            await b.guide.planner.task
            assert len(fake.calls) == 2 and len(clients) == 1
            assert fake.calls[0][1]['question'] == ''.join(chunks)
            assert fake.calls[0][1]['task'] == 'fix the wire on the headphones near the plug'
            assert 'Guide: plan 1/2' in details(emitted)
            assert b.guide.kind == 'plan' and b.guide.guide.index == 0
            assert 'Step data:' in json.dumps(wire) and not fixed
            await say_user(b, 'Okay, what is the next step?')
            assert b.guide.guide.index == 1
            assert 'Guide: plan 2/2' in details(emitted)
            assert 'step 2 of 2' in prompts(wire)[-1] and len(fake.calls) == 2
            assert options == [dict(max_retries=0, timeout=planner.TIMEOUT)] * 2
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    outcomes = [e['reason']['result'] for e in events if e['event'] == 'planner']
    assert outcomes == ['started', 'valid', 'rejected']
    assert 'headphones' not in json.dumps(events)


@pytest.mark.parametrize('text,expected', [
    ('dad help me fix my headphones', 'fix the headphones'),
    ('Dad, can you teach me how to solder?', 'how to solder'),
    ('how do I solder a wire?   ', 'solder a wire'),
    ('what does a capacitor do', 'what a capacitor does'),
    ('Dad, what does a capacitor do?   ', 'what a capacitor does'),
    ('what is on the table', None),
    ('where was my wrench', None),
    ('hello dad', None),
    ('how are you?', None),
])
def test_live_intent_packets(monkeypatch, tmp_path, text, expected):
    async def trial():
        result = solder_plan(expected) if expected and 'solder' in expected else None
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, FakeLLM(result))
        try:
            await b.handle({'serverContent': {'inputTranscription': {'text': text, 'finished': True}}})
            await b.handle({'serverContent': {'turnComplete': True}})
            if expected:
                assert b.guide.planner.task is not None
                await b.guide.planner.task
                assert len(fake.calls) == 2
                assert b.guide.guide.task == expected and b.guide.guide.index == 0
                if result:
                    assert b.guide.guide.plan == result
                    assert planner.is_safety_step(planner.check_plan(plan(expected))['steps'][0])  # missing preparation stops the step
            else:
                assert b.guide.planner.task is None and not fake.calls and not store.rows
        finally:
            await b.memory.close()
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('boundary', ['finished', 'output', 'audio_output', 'output_before_tail',
                                     'streaming_output', 'early_finished', 'late_delta'])
def test_live_timed_transcription_plans_before_reply_ends(monkeypatch, tmp_path, capsys, boundary):
    from server.live_guide import OBSERVE_DEBOUNCE

    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        chunks = ('dad', ' The wire on my', ' headphones broke near', ' the plug. How do I fix it?')
        try:
            for index, chunk in enumerate(chunks):
                await b.handle({'serverContent': {'inputTranscription': {
                    'text': chunk, 'finished': boundary in ('early_finished', 'late_delta') and index == 0}}})
                # A provider may finish a segment before the rest of the utterance arrives.
                await asyncio.sleep(OBSERVE_DEBOUNCE + .05 if boundary == 'late_delta' and index == 0 else .01)
                if boundary == 'output_before_tail' and index == 2:
                    await b.handle({'serverContent': {'outputTranscription': {'text': 'Let us '}}})
            if boundary == 'finished':
                await b.handle({'serverContent': {'inputTranscription': {'finished': True}}})
            elif boundary == 'audio_output':
                await b.handle({'serverContent': {'modelTurn': {'parts': [{'inlineData': {
                    'mimeType': 'audio/pcm;rate=24000', 'data': 'AAA='}}]}}})
            else:
                await b.handle({'serverContent': {'outputTranscription': {'text': 'Let us inspect it.'}}})
            # The model's reply has started, but turnComplete has NOT arrived yet.
            for _ in range(20):
                await asyncio.sleep(.02)
                if boundary == 'streaming_output':
                    await b.handle({'serverContent': {'outputTranscription': {'text': ' More.'}}})
            assert b.guide.planner.task is not None, 'final input must plan before model turnComplete'
            await b.guide.planner.task
            assert len(fake.calls) == 2
            assert fake.calls[0][1]['question'] == ''.join(chunks)
            assert b.guide.guide.task == 'fix the wire on the headphones near the plug'
            assert b.guide.guide.index == 0
            await b.handle({'serverContent': {'turnComplete': True}})
            await say_user(b, 'Okay, what is the next step?')
            assert b.guide.guide.index == 1 and len(fake.calls) == 2
        finally:
            await b.memory.close()
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    reasons = [e['reason'] for e in events if e['event'] == 'planner']
    started = [r for r in reasons if r['result'] == 'started']
    assert len(started) == 1 and started[0]['chars'] == 67
    rejections = [r for r in reasons if r['result'] == 'rejected']
    assert len(rejections) == (2 if boundary == 'late_delta' else 1)
    if boundary == 'late_delta':
        assert rejections[0] == dict(result='rejected', cause='no_intent', chars=3)
    assert 'headphones' not in json.dumps(events)


@pytest.mark.parametrize('complete_before_tail', [False, True])
def test_live_interleaved_late_transcript_retries_and_next_waits(monkeypatch, tmp_path, capsys,
                                                               complete_before_tail):
    from server.live_guide import OBSERVE_DEBOUNCE, PLAN_WAIT

    async def trial():
        started, release = asyncio.Event(), asyncio.Event()
        fake = FakeLLM()

        async def slow(system, evidence):
            started.set()
            await release.wait()
            return await fake(system, evidence)

        b, emitted, fixed, wire, _, store, points = setup(monkeypatch, tmp_path, slow)
        text = 'dad The wire on my headphones broke near the plug. How do I fix it?'
        audio = {'modelTurn': {'parts': [{'inlineData': {
            'mimeType': 'audio/pcm;rate=24000', 'data': 'AAA='}}]}}
        try:
            await b.audio('AAA=', final=True)
            await b.handle({'serverContent': {'inputTranscription': {'text': text[:21]}}})
            await b.handle({'serverContent': audio})
            await b.handle({'serverContent': {'outputTranscription': {'text': 'Let us inspect it.'}}})
            # The actual reported rejection: first output is NOT the end of input.
            await asyncio.sleep(OBSERVE_DEBOUNCE + .05)
            assert not b.guide_observed and b.guide.planner.task is None
            await b.handle({'serverContent': {'inputTranscription': {'text': text[21:48]}}})
            await b.handle({'serverContent': audio})
            if complete_before_tail:
                await b.handle({'serverContent': {'turnComplete': True}})
            await b.handle({'serverContent': {'inputTranscription': {'text': text[48:]}}})
            await asyncio.wait_for(started.wait(), OBSERVE_DEBOUNCE + .5)
            pending = b.guide.planner.task
            assert b.guide_observed and not pending.done()
            if not complete_before_tail:
                await b.handle({'serverContent': {'turnComplete': True}})
            # A fresh mic utterance starts turn two, while the plan is still building.
            await b.audio('AAA=', final=True)
            emitted.clear()
            followup = asyncio.create_task(say_user(b, 'Okay, what is the next step?'))
            await asyncio.sleep(.02)
            assert b.blocked and not followup.done() and not prompts(wire)
            assert not any(m['type'] in ('audio', 'say', 'reply_delta') for m in emitted)
            release.set()
            await asyncio.wait_for(followup, PLAN_WAIT + .5)
            assert fake.calls[0][1]['question'] == text
            assert fake.calls[0][1]['task'] == 'fix the wire on the headphones near the plug'
            assert len(fake.calls) == 2 and b.guide.guide.index == 0
            assert 'step 1 of 2' in prompts(wire)[-1] and not fixed
        finally:
            await b.memory.close()
            await b.guide.close()
            await b.prefetch.close()

    asyncio.run(trial())
    reasons = [e['reason'] for line in capsys.readouterr().out.splitlines()
               if (e := json.loads(line))['event'] == 'planner']
    assert reasons[0] == dict(result='rejected', cause='no_intent', chars=21)
    assert [r['chars'] for r in reasons if r['result'] == 'started'] == [67]
    assert len([r for r in reasons if r['result'] == 'valid']) == 1
    assert 'headphones' not in json.dumps(reasons)


@pytest.mark.parametrize('action', ['stop', 'interrupted', 'close'])
def test_live_deferred_decision_cannot_outlive_turn(monkeypatch, tmp_path, action):
    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        try:
            await b.handle({'serverContent': {'inputTranscription': {
                'text': 'help me fix my headphones', 'finished': True}}})
            if action == 'stop':
                await b.stop('Stop and disconnect power.')
            elif action == 'interrupted':
                await b.handle({'serverContent': {'interrupted': True}})
                await b.handle({'serverContent': {'inputTranscription': {'text': 'hello dad'}, 'turnComplete': True}})
            else:
                await b.guide.close()
            await asyncio.sleep(.35)
            assert b.guide.planner.task is None and not fake.calls and not store.rows
        finally:
            await b.memory.close()
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('outcome', ['ready', 'debounce', 'timeout', 'invalid', 'safety'])
def test_live_next_waits_for_pending_plan(monkeypatch, tmp_path, outcome):
    async def trial():
        started, release = asyncio.Event(), asyncio.Event()
        fake = FakeLLM()

        async def slow(system, evidence):
            started.set()
            await release.wait()
            return '{}' if outcome == 'invalid' else await fake(system, evidence)

        b, emitted, fixed, wire, _, store, points = setup(monkeypatch, tmp_path, slow)
        if outcome == 'debounce':
            monkeypatch.setattr('server.live_guide.DEBOUNCE', .05)
        try:
            await b.handle({'serverContent': {'inputTranscription': {
                'text': 'dad The wire on my headphones broke near the plug. How do I fix it?',
                'finished': True}, 'turnComplete': True}})
            await asyncio.wait_for(started.wait(), .5)
            pending = b.guide.planner.task
            emitted.clear()
            followup = asyncio.create_task(say_user(b, 'Okay, what is the next step?'))
            await asyncio.sleep(.02)
            assert b.blocked and b.guide.task is not None
            assert not followup.done() and not prompts(wire)
            assert not any(m['type'] in ('audio', 'say', 'reply_delta') for m in emitted)
            if outcome == 'safety':
                await b.stop('Stop and disconnect power.')
            if outcome != 'timeout':
                release.set()
            await asyncio.wait_for(followup, 3.5)
            if outcome in ('ready', 'debounce'):
                assert b.guide.guide.index == 0
                assert 'step 1 of 2' in prompts(wire)[-1]
                assert plan()['steps'][0]['say'] in prompts(wire)[-1]
                assert len(fake.calls) == 2 and not b.blocked and not fixed
                b._reset_reply()
                await say_user(b, 'next')
                assert b.guide.guide.index == 1
            elif outcome == 'safety':
                assert b.safety_stopped and not prompts(wire)
            else:
                assert not b.guide.guide and not b.blocked
                assert 'Okay, what is the next step?' in prompts(wire)[-1]
                if outcome == 'timeout':
                    assert not pending.done()  # waiting must not cancel the background build
                    release.set()
                    await pending
                    assert b.guide.guide.index == 0
                    assert len(prompts(wire)) == 1  # no unsolicited second answer
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('during_hold', [False, True])
def test_pending_plan_completion_or_coded_replacement(monkeypatch, tmp_path, during_hold):
    async def trial():
        started, release = asyncio.Event(), asyncio.Event()
        fake = FakeLLM()

        async def slow(system, evidence):
            started.set()
            await release.wait()
            return await fake(system, evidence)

        b, emitted, fixed, wire, _, store, points = setup(monkeypatch, tmp_path, slow)
        try:
            await b.handle({'serverContent': {'inputTranscription': {
                'text': 'help me fix my headphones', 'finished': True}, 'turnComplete': True}})
            await started.wait()
            pending = b.guide.planner.task
            if during_hold:
                hold = b.hold

                async def finish_while_holding():
                    await hold()
                    release.set()
                    await pending
                monkeypatch.setattr(b, 'hold', finish_while_holding)
                await say_user(b, 'Okay, what is the next step?')
                assert b.guide.guide.index == 0 and 'step 1 of 2' in prompts(wire)[-1]
            else:
                await b.handle({'serverContent': {'inputTranscription': {'text': 'next'},
                                                  'turnComplete': True}})
                await asyncio.sleep(.02)
                waiting = b.guide.task
                assert not waiting.done()
                b._reset_reply()
                await say_user(b, 'help me with my tie')
                assert waiting.cancelled() and pending.cancelled()
                assert b.guide.kind == 'tie' and b.guide.guide.index == 0
                assert 'step 1 of 8' in prompts(wire)[-1] and len(prompts(wire)) == 1
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())


@pytest.mark.parametrize('text,expected', [
    ('help me fix my headphones', 'fix the headphones'),
    ('how do I solder a wire?', 'solder a wire'),
    ('teach me what a capacitor does', 'what a capacitor does'),
    ('Dad, help me fold a paper airplane', 'fold a paper airplane'),
    ('Dad, the wire on my headphones broke near the plug. How do I fix it?',
     'fix the wire on the headphones near the plug'),
    ('My headphones are broken. How can I repair them?', None),  # unresolved form: no guess
    ('My wall outlet is broken. How do I fix it?', None),
    ('My headphones for Alex broke. How do I fix it?', None),
    ('can you teach me how to sew a button?', 'how to sew a button'),
    ('hello dad', None), ('how are you?', None), ('what is this?', None),
    ('help me find where the wire is now', None),
    ("help me understand what I'm holding", None),
    ('teach me what this is', None), ('help me find the screwdriver', None),
    ('help me remember how I fixed my headphones yesterday', None),
    ('how did I solder this wire?', None), ('what did we build last time?', None),
    ('help me make an LED blink', None), ('help me read resistor bands', None),
    ('help me with my tie', None), ('help me repair the sink', None),
    ('help me fix a wall outlet', None),
    ('help me troubleshoot a radio', 'troubleshoot a radio'),
    ('help me fix headphones for Alex', None),
])
def test_task_intent(text, expected):
    assert planner.task_request(text) == expected


@pytest.mark.parametrize('text,outcomes', [
    ('hello Dad', [{'result': 'rejected', 'cause': 'no_intent'}]),
    ('help me fix my headphones', [{'result': 'started'}, {'result': 'no_client'}]),
])
def test_live_planner_diagnostics_without_client(monkeypatch, capsys, text, outcomes):
    from server import llm

    def forbidden():
        pytest.fail('missing credentials must not construct a provider client')
    monkeypatch.setattr(llm, '_shared_anthropic', forbidden)

    async def trial():
        b, emitted, fixed, wire = bridge_for(monkeypatch)
        try:
            await b.handle({'serverContent': {'inputTranscription': {'text': text, 'finished': True}}})
            await b.handle({'serverContent': {'turnComplete': True}})
            if b.guide.planner.task:
                await b.guide.planner.task
            assert b.guide.kind is None and not b.blocked and not wire and not fixed
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    reasons = [e['reason'] for e in events if e['event'] == 'planner']
    assert [{k: v for k, v in r.items() if k not in ('task_hash', 'chars')} for r in reasons] == outcomes
    assert all(r['chars'] == len(text) for r in reasons)
    assert 'headphones' not in json.dumps(events) and 'hello Dad' not in json.dumps(events)


@pytest.mark.parametrize('change', [
    lambda p: p.update(extra='ignored'),
    lambda p: p.update(steps=[]),
    lambda p: p.update(steps=p['steps'] * 5),
    lambda p: p['steps'][0].update(say='word ' * 25),
    lambda p: p['steps'][0].update(target=['headphones']),
    lambda p: p.update(task='another task'),
])
def test_schema_reject(change):
    value = plan()
    change(value)
    with pytest.raises(ValueError):
        planner.validate(value, 'fix the headphones')


@pytest.mark.parametrize('field,text', [
    ('say', 'Hold the hot soldering iron tip.'),
    ('show', 'Open the electrical panel.'),
    ('safety', 'Keep cooking with smoking oil.'),
    ('say', 'Fix the leaking sink.'),
])
def test_unsafe_any_field_replaces_step(field, text):
    value = plan()
    value['steps'][0][field] = text
    checked = planner.validate(value, value['task'])
    assert len(checked['steps']) == len(value['steps'])
    assert planner.is_safety_step(checked['steps'][0])
    assert checked['steps'][1] == value['steps'][1]
    assert planner.validate(plan(), value['task']) == plan()


def test_live_immediate_answer_idle_publish_advance_and_good_cache(monkeypatch, tmp_path):
    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        b.session.scene = {'caption': 'A synthetic headphone cable.', 'objects': [], 'image': 'NEVER SEND'}
        b.session.frame = {'jpeg_b64': 'NEVER SEND'}
        b.session.camera = True
        await b.handle({'serverContent': {'inputTranscription': {'text': 'help me fix my headphones'}}})
        assert b.guide.planner.task is None  # no partial-triggered spending
        await b.handle({'serverContent': {'inputTranscription': {'text': '', 'finished': True},
                                         'outputTranscription': {'text': 'Disconnect the headphones first.'}}})
        # Some provider versions omit finished; turnComplete is the reliable fallback.
        await b.handle({'serverContent': {'turnComplete': True}})
        await b.guide.planner.task
        await asyncio.sleep(0)
        assert b.guide.kind == 'plan' and not b.blocked and not fixed
        assert len(fake.calls) == 2
        assert fake.calls[0][1]['scene'] == 'A synthetic headphone cable.'
        assert 'NEVER SEND' not in json.dumps(fake.calls)
        assert any(m.get('text') == 'Disconnect the headphones first.' for m in emitted)
        assert 'Guide: plan 1/2' in details(emitted)
        assert not prompts(wire)  # initial planning never asks a second voice to speak
        background = [m for m in wire if m.get('clientContent', {}).get('turnComplete') is False]
        assert background and 'Step data:' in json.dumps(background)
        assert points and points[0][1]['witness'] is True
        assert not b.guide.claims('the cable is next to the headphones')
        await say_user(b, 'next')
        assert b.guide.guide.index == 1 and 'step 2 of 2' in prompts(wire)[-1]
        b._reset_reply()
        await say_user(b, 'done')
        assert b.guide.guide.completed and store.rows['fix the headphones']['good']
        saved = json.loads(store.path.read_text())
        assert set(saved['fix the headphones']) == {'plan', 'good'}
        assert 'synthetic headphone cable' not in store.path.read_text()
        assert 'help me' not in store.path.read_text()
        b._reset_reply()
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert b.guide.guide.index == 0 and not b.guide.guide.completed and len(fake.calls) == 2
        await b.guide.close()
    asyncio.run(trial())


def test_finished_flag_starts_without_waiting_for_reply(monkeypatch, tmp_path):
    async def trial():
        started, release = asyncio.Event(), asyncio.Event()

        async def slow(system, evidence):
            started.set()
            await release.wait()
            return '{}'
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, slow)
        await b.handle({'serverContent': {'inputTranscription': {
            'text': 'help me fix my headphones', 'finished': True}}})
        await asyncio.wait_for(started.wait(), .5)
        assert not b.blocked and not b.guide.guide
        await b.handle({'serverContent': {'outputTranscription': {'text': 'Disconnect it first.'}}})
        assert any(m.get('text') == 'Disconnect it first.' for m in emitted)
        await b.guide.close()
    asyncio.run(trial())


def test_coded_wins_and_cancels_pending_plan(monkeypatch, tmp_path):
    async def trial():
        started = asyncio.Event()

        async def slow(*args):
            started.set()
            await asyncio.Event().wait()
        b, *rest = setup(monkeypatch, tmp_path, slow)
        b.guide.observe('help me fix my headphones')
        await started.wait()
        pending = b.guide.planner.task
        await say_user(b, 'help me with my tie')
        assert b.guide.kind == 'tie' and pending.cancelled()
        b.guide.observe('teach me what a capacitor does')
        assert b.guide.planner.task is pending
        await b.guide.close()
    asyncio.run(trial())


def test_cache_hit_revalidated_and_no_model(monkeypatch, tmp_path):
    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        store.put('fix the headphones', plan(), good=True)
        b.guide.planner.store = planner.PlanCache(store.path)  # reload durable cache
        b.generating = True
        b.guide.observe('Help me fix MY headphones!')
        await b.guide.planner.task
        assert b.guide.kind == 'plan' and not fake.calls and not wire
        b.generating = False
        await b.publish_guide()
        assert wire and not fixed
        await b.guide.close()
    asyncio.run(trial())


def test_timeout_falls_back_and_never_retries_same_task(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(planner, 'TIMEOUT', .01)

    async def trial():
        calls = []

        async def slow(*args):
            calls.append(args)
            await asyncio.Event().wait()
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, slow)
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        b.guide.observe('help me fix my headphones')
        assert len(calls) == 1 and not b.guide.guide and not b.blocked and not fixed
        assert not store.path.exists()
        await b.guide.close()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    events = [e for e in events if e['event'] == 'planner']
    assert [e['reason']['result'] for e in events] == ['started', 'timeout']
    assert 'headphones' not in json.dumps(events)


@pytest.mark.parametrize('mode', ['off', 'private', 'local', 'consent'])
def test_disabled_no_calls_or_cache(monkeypatch, tmp_path, mode):
    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        if mode == 'off':
            monkeypatch.setenv('PLANNER', '0')
        elif mode == 'private':
            b.session.private = True
        elif mode == 'local':
            monkeypatch.setenv('LOCAL_ONLY', '1')
        else:
            privacy.update('claude', False)
        b.guide.observe('help me fix my headphones')
        assert b.guide.planner.task is None and not fake.calls and not store.path.exists()
    asyncio.run(trial())


def test_revoked_consent_between_calls(monkeypatch, tmp_path):
    async def trial():
        calls = []

        async def revoke(*args):
            calls.append(args)
            privacy.update('claude', False)
            return 'Facts'
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, revoke)
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert len(calls) == 1 and not store.rows and not b.guide.guide
    asyncio.run(trial())


def test_bad_step_replaced_before_install_and_cache(monkeypatch, tmp_path, capsys):
    async def trial():
        bad = plan()
        bad['steps'][1]['check'] = 'Grab the hot soldering iron tip.'
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, FakeLLM(bad))
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert len(fake.calls) == 2 and b.guide.guide and not b.blocked
        checked = b.guide.guide.plan
        assert len(checked['steps']) == 2 and checked['steps'][0] == bad['steps'][0]
        assert checked['steps'][1]['say'] == planner.SAFETY_LINES['hot_tool']
        assert checked['steps'][1]['check'] == ''
        assert planner.PlanCache(store.path).get(bad['task']) == checked
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(e['event'] == 'planner' and e['reason']['result'] == 'valid' for e in events)
    assert 'Grab' not in json.dumps(events) and 'headphones' not in json.dumps(events)


@pytest.mark.parametrize('task,gate', [
    ('open a laptop charger', 'open_power_supply'),
    ('open a microwave', 'open_microwave'),
])
def test_unsafe_task_logs_cause_without_model_or_cache(monkeypatch, tmp_path, capsys, task, gate):
    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        assert b.guide.planner.observe('help me ' + task) is False
        assert not fake.calls and not store.rows and not b.guide.guide
        # Exercise the post-model boundary too, independently of the intent gate.
        b.guide.planner.complete = FakeLLM(plan(task))
        b.guide.planner.request = task
        await b.guide.planner.build(task, 'synthetic request')
        assert not store.rows and not b.guide.guide
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    rejected = [e['reason'] for e in events if e['event'] == 'planner' and e['reason']['result'] == 'rejected']
    assert len(rejected) == 2
    assert all(r['cause'] == 'unsafe_task' and r['gate'] == gate for r in rejected)
    assert task not in json.dumps(events)


def test_cache_rechecks_home_scope(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME_TASKS', '1')
    store = planner.PlanCache(tmp_path / 'plans.json')
    value = plan('adjust a hinge')
    store.put(value['task'], value)
    assert store.get(value['task'])
    monkeypatch.delenv('HOME_TASKS')
    assert store.get(value['task']) is None
    assert not planner.PlanCache(store.path).rows


def test_failed_new_task_releases_previous_plan(monkeypatch, tmp_path):
    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert b.guide.claims('next')

        async def bad(*args):
            return 'invalid json'
        b.guide.planner.complete = bad
        b.guide.observe('teach me what a capacitor does')
        await b.guide.planner.task
        assert not b.guide.guide and not b.guide.claims('next')
        await b.publish_guide()
        assert 'no active guide' in json.dumps(wire[-1])
        await b.guide.close()
    asyncio.run(trial())


def test_personal_plan_rejected():
    value = plan()
    value['steps'][0]['show'] = 'Read the serial number 12345678.'
    with pytest.raises(ValueError, match='personal'):
        planner.validate(value, value['task'])


def test_second_call_shares_total_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(planner, 'TIMEOUT', .04)

    async def trial():
        calls = []

        async def slow(system, evidence):
            calls.append(system)
            await asyncio.sleep(.025)
            return 'Facts' if len(calls) == 1 else json.dumps(plan())
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, slow)
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert len(calls) == 2 and not b.guide.guide and not store.rows and not b.blocked
    asyncio.run(trial())


@pytest.mark.parametrize('model', [None, 'fixture-model'])
def test_sdk_two_calls_text_only_retries_off(monkeypatch, tmp_path, model):
    from server import llm
    calls, options = [], []

    class Client:
        def with_options(self, **kwargs):
            options.append(kwargs)
            return self

        @property
        def messages(self):
            return self

        async def create(self, **kwargs):
            calls.append(kwargs)
            block = (SimpleNamespace(type='text', text='Facts') if len(calls) == 1 else
                     SimpleNamespace(type='tool_use', name='submit_plan', input=plan()))
            return SimpleNamespace(content=[block], usage=None)

    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic')
        if model:
            monkeypatch.setenv('PLANNER_MODEL', model)
        monkeypatch.setattr(llm, '_shared_anthropic', lambda: Client())
        b.guide.planner.complete = planner.claude
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert b.guide.kind == 'plan' and len(calls) == 2
        assert all(c['model'] == (model or 'claude-haiku-5-5')
                   and isinstance(c['messages'][0]['content'], str) for c in calls)
        assert all(o == dict(max_retries=0, timeout=12) for o in options)
        assert 'tools' not in calls[0]
        assert calls[1]['tool_choice'] == {'type': 'tool', 'name': 'submit_plan'}
        assert [t['name'] for t in calls[1]['tools']] == ['submit_plan']
        from jsonschema import validate
        validate(plan(), calls[1]['tools'][0]['input_schema'])
        await b.guide.close()
    asyncio.run(trial())


def test_recorded_headphone_repair_installs_and_reloads(monkeypatch, tmp_path):
    cases = Path(__file__).resolve().parents[1] / 'eval/cases/checker_good_plans.jsonl'
    value = next(row['plan'] for line in cases.read_text().splitlines()
                 if (row := json.loads(line))['id'] == 'good13')
    assert len(value['steps']) == 8
    assert planner.check_plan(value) == value
    request = 'dad The wire on my headphones broke near the plug. How do I fix it?'
    value['task'] = planner.task_request(request)

    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, FakeLLM(value))
        try:
            await b.handle({'serverContent': {'inputTranscription': {
                'text': request, 'finished': True}, 'turnComplete': True}})
            await b.guide.planner.task
            assert b.guide.guide.plan == value and b.guide.kind == 'plan'
            assert planner.PlanCache(store.path).get(value['task']) == value
            for index in range(1, 8):
                b._reset_reply()
                await say_user(b, 'next')
                assert b.guide.guide.index == index
            assert len(fake.calls) == 2 and not fixed
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
