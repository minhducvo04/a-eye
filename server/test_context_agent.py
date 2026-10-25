"""Synthetic context, encrypted plans, and real call-boundary regressions."""
from datetime import datetime, timedelta
from time import monotonic

import pytest
from cryptography.fernet import Fernet

from server import privacy
from server.agent import Session
from server.context_agent import ContextAgent, extract_plan, rank
from server.growth import GrowthLog
from server.memory import Cipher, Store


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.delenv('LOCAL_ONLY', raising=False)
    token = privacy.SWITCHES.set(None)
    private = privacy.PRIVATE.set(False)
    store = Store('test', base=tmp_path, cipher=Cipher(Fernet.generate_key()))
    store.claim('test-owner')
    store.save_settings(dict(consent=dict(person=True, caregiver=True), remembering=True))
    session = Session('context-test')
    session.growth = GrowthLog(store)
    agent = ContextAgent(session, store, store)
    session.context_agent = agent
    yield agent
    privacy.SWITCHES.reset(token)
    privacy.PRIVATE.reset(private)


def test_ranking_prefers_relevance_then_recency():
    rows = [dict(source='memory', text='keys in drawer', t=80),
            dict(source='camera', text='a red cup', t=100),
            dict(source='places', text='keys in bowl', t=90)]
    assert [r['text'] for r in rank(rows, 'where are my keys?', 100)] == [
        'keys in bowl', 'keys in drawer', 'a red cup']


def test_all_stores_short_context_and_expiry(context):
    s, store = context.session, context.store
    s.scene = dict(caption='keys on the workbench', objects=[])
    s.frame = dict(seq=1)
    s.scene_seq = 1
    s.frame_time = monotonic()
    s.recent_memory.add(dict(caption='keys beside the screwdriver', objects=[]), monotonic())
    s.recent_memory.add(dict(caption='expired note', objects=[]), monotonic() - 130)
    store.place('keys', ['workshop', 'drawer'])
    store.append(dict(id='note', t=store.clock(), note='keys have a blue tag'))
    run = s.growth.start('find keys')
    s.growth.update(run, completed=True, hints=2)
    block = context.gather('keys', provider='local')
    assert context.sources == ['camera', 'memory', 'places', 'growth']
    assert all(word in block for word in ('workbench', 'screwdriver', 'drawer', 'blue tag', 'hints'))
    assert 'expired note' not in block
    assert len(block) <= 1800
    s.camera = False
    assert 'workbench' not in context.gather('keys', provider='local')


def test_plan_encrypted_once_after_date_and_recent(context):
    now = datetime(2026, 10, 23, 12).timestamp()
    plan = context.ingest("I'm going to SF Saturday", now=now)
    assert plan['note'] == "I'm going to SF Saturday"
    assert datetime.fromtimestamp(plan['followup_at']).date().isoformat() == '2026-10-25'
    assert b'going to SF' not in context.plans._path('log.jsonl').read_bytes()
    assert not context.followup(provider='local', now=plan['followup_at'] - 1)
    assert context.followup(provider='local', now=plan['followup_at']) == 'How was the trip to SF?'
    second = ContextAgent(context.session, context.store, context.plans)
    assert not second.followup(provider='local', now=plan['followup_at'] + 1)
    context.ingest("I'm going to LA tomorrow", now=now)
    assert not second.followup(provider='local', now=now + 12 * 86400)


def test_private_and_switches_do_not_consume_plan(context):
    plan = context.ingest("I'm going to SF tomorrow", now=datetime(2026, 10, 20).timestamp())
    now = plan['followup_at'] + 1
    privacy.set_call({'google': True, 'claude': True}, private=True)
    assert not context.gather('SF', provider='google', now=now)
    assert not context.followup(provider='google', now=now)
    privacy.set_call({'google': False, 'claude': False})
    assert not context.followup(provider='claude', now=now)
    assert not context.followup(provider='google', now=now)
    privacy.set_call({'google': True})
    assert context.followup(provider='google', now=now) == 'How was the trip to SF?'


def test_delete_followup_and_no_plaintext_or_optout_write(context, tmp_path):
    plan = context.ingest("I'm going to SF tomorrow", now=datetime(2026, 10, 20).timestamp())
    assert context.followup(provider='local', now=plan['followup_at'])
    assert context.dismiss("don't bring that up")
    assert not any(r.get('source') == 'plan' for r in context.plans.records())
    assert 'SF' not in context.gather('SF', provider='local')
    context.plans = Store('plain', base=tmp_path, cipher=Cipher(''))
    assert context.ingest("I'm going to SF tomorrow") is None
    assert not context.plans.dir.exists()
    context.store.save_settings(dict(consent={}, remembering=False))
    assert not context.gather('SF', provider='local')
    assert context.ingest("I'm going to SF tomorrow") is None


@pytest.mark.parametrize('text', ['She is going to SF tomorrow', 'I went to SF yesterday',
                                 'Maybe I will go to SF', "I'm not going to SF Saturday"])
def test_only_explicit_own_future_plans(text):
    assert extract_plan(text, datetime(2026, 10, 23, 12).timestamp()) is None


def test_classic_prompt_receives_context(context):
    from server.test_agent import LLM, Vision, run
    context.store.append(dict(id='note', t=context.store.clock(), note='blue toolbox for the trip'))
    llm = LLM()
    run(context.session, llm, 'help with the toolbox', Vision())
    assert 'blue toolbox' in llm.calls[0][0]


def test_live_optional_context_tool_and_own_plan(context):
    import asyncio
    import json
    from server.gemini_live import LiveBridge
    async def trial():
        privacy.set_call({'google': True})
        context.store.append(dict(id='note', t=context.store.clock(), note='blue toolbox for the trip'))
        wire, emitted = [], []
        class Socket:
            async def send(self, raw):
                wire.append(json.loads(raw))
        async def send(msg):
            emitted.append(msg)
        bridge = LiveBridge(context.session, None, None, send, send)
        bridge.ws, bridge.active, bridge.model = Socket(), True, 'fixture'
        await bridge.audio('AAA=', final=True)
        assert 'audio' in wire[0]['realtimeInput']
        assert not any('clientContent' in item for item in wire)
        result = await bridge.tool(dict(name='gather_context', args={'question': 'toolbox'}))
        assert 'blue toolbox' in result
        assert context.sources == ['memory']
        await bridge.handle({'serverContent': {'inputTranscription': {'text': "I'm going to SF tomorrow"},
                                               'turnComplete': True}})
        plans = [r for r in context.plans.records() if r.get('source') == 'plan']
        assert len(plans) == 1 and plans[0]['note'] == "I'm going to SF tomorrow"
        await bridge.handle({'serverContent': {'outputTranscription': {'text': "I'm going to LA tomorrow"},
                                               'turnComplete': True}})
        assert len([r for r in context.plans.records() if r.get('source') == 'plan']) == 1
        privacy.update('google', False)
        with pytest.raises(PermissionError):
            await bridge.tool(dict(name='gather_context', args={'question': 'toolbox'}))
    asyncio.run(trial())


def test_followup_claim_is_atomic_and_retention_uses_plan_date(context):
    from concurrent.futures import ThreadPoolExecutor
    now = context.store.clock()
    past = now - 20 * 86400
    date = datetime.fromtimestamp(now - 2 * 86400).date().isoformat()
    plan = context.ingest(f'I will visit SF {date}', now=past)
    context.store.purge_old()
    assert any(r['id'] == plan['id'] for r in context.plans.records())
    agents = [ContextAgent(context.session, context.store, context.plans) for _ in range(2)]
    with ThreadPoolExecutor(2) as executor:
        outputs = list(executor.map(lambda agent: agent.followup(provider='local', now=now), agents))
    assert len([line for line in outputs if line]) == 1


def test_rehearsal_starts_call_and_deletes(tmp_path, monkeypatch):
    from scripts.context_agent_rehearsal import rehearse
    result = rehearse(tmp_path, monkeypatch)
    assert result['opener'] == 'How was the trip to SF?'
    assert result['repeated'] is False
    assert result['deleted'] is True
