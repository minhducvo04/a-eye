"""Synthetic LLM and Live packets only; no provider, camera, or network calls."""
import asyncio
import json
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
def test_real_live_repair_chunks_use_app_client_and_advance(monkeypatch, tmp_path, capsys, finished):
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
            for chunk in ('Dad, the wire on my', ' headphones broke', ' near the plug.',
                          ' How do I', ' fix it?'):
                await b.handle({'serverContent': {'inputTranscription': {'text': chunk}}})
                assert b.guide.planner.task is None and not fake.calls
            if finished:
                await b.handle({'serverContent': {'inputTranscription': {'finished': True}}})
            await b.handle({'serverContent': {'turnComplete': True}})
            assert b.guide.planner.task is not None, 'finished Live utterance must request a plan'
            await b.guide.planner.task
            assert len(fake.calls) == 2 and len(clients) == 1
            assert fake.calls[0][1]['question'] == (
                'Dad, the wire on my headphones broke near the plug. How do I fix it?')
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
    assert [{k: v for k, v in r.items() if k != 'task_hash'} for r in reasons] == outcomes
    assert 'headphones' not in json.dumps(events) and 'hello Dad' not in json.dumps(events)


@pytest.mark.parametrize('change', [
    lambda p: p.update(extra='ignored'),
    lambda p: p.update(steps=[]),
    lambda p: p.update(steps=p['steps'] * 5),
    lambda p: p['steps'][0].update(say='word ' * 25),
    lambda p: p['steps'][0].update(target=['headphones']),
    lambda p: p['steps'][0].pop('check'),
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
    ('target', 'wall outlet'),
    ('check', 'The resistor is not in series.'),
    ('safety', 'Keep cooking with smoking oil.'),
    ('say', 'Fix the leaking sink.'),
])
def test_unsafe_any_field_reject(field, text):
    value = plan()
    value['steps'][0][field] = text
    with pytest.raises(ValueError, match='unsafe'):
        planner.validate(value, value['task'])
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


def test_bad_plan_falls_back_without_cache_or_speech(monkeypatch, tmp_path, capsys):
    async def trial():
        bad = plan()
        bad['steps'][1]['check'] = 'Grab the hot soldering iron tip.'
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, FakeLLM(bad))
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert len(fake.calls) == 2 and not b.guide.guide and not b.blocked
        assert not store.rows and not store.path.exists() and not wire and not fixed and not points
    asyncio.run(trial())
    assert '"result":"rejected","cause":"unsafe"' in capsys.readouterr().out


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


def test_sdk_two_calls_text_only_retries_off(monkeypatch, tmp_path):
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
            text = 'Facts' if len(calls) == 1 else json.dumps(plan())
            return SimpleNamespace(content=[SimpleNamespace(type='text', text=text)], usage=None)

    async def trial():
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path)
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic')
        monkeypatch.setenv('PLANNER_MODEL', 'fixture-model')
        monkeypatch.setattr(llm, '_shared_anthropic', lambda: Client())
        b.guide.planner.complete = planner.claude
        b.guide.observe('help me fix my headphones')
        await b.guide.planner.task
        assert b.guide.kind == 'plan' and len(calls) == 2
        assert all(c['model'] == 'fixture-model' and isinstance(c['messages'][0]['content'], str) for c in calls)
        assert all(o == dict(max_retries=0, timeout=12) for o in options)
        await b.guide.close()
    asyncio.run(trial())
