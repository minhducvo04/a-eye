"""The code-owned memory turn in the Live call, with synthetic provider packets only (no network, no Gemini)."""
import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from server import live_memory, privacy
from server.agent import Session
from server.gemini_live import LiveBridge, DOCUMENTED_MODEL


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(live_memory, 'DEBOUNCE', 0)
    monkeypatch.delenv('LIVE_MEMORY_GATE', raising=False)
    monkeypatch.delenv('ROUTER', raising=False)


def scene(note, *labels):
    return dict(caption=note, objects=[dict(label=x) for x in labels])


def bridge_for(clock=100, rewind=None):
    privacy.set_call({'google': True})
    emitted, fixed, wire = [], [], []

    async def emit(msg):
        emitted.append(msg)

    async def speak(text):
        fixed.append(text)

    async def send(raw):
        wire.append(json.loads(raw))
    session = Session('s')
    session.recent_memory.clock = lambda: clock
    session.recent_memory.started = 0
    session.rewind = rewind
    bridge = LiveBridge(session, None, None, emit, speak)
    bridge.active, bridge.model = True, DOCUMENTED_MODEL
    bridge.ws = SimpleNamespace(send=send)
    return bridge, emitted, fixed, wire


async def say_user(bridge, text, live_says='It is on the table right there.'):
    """One finished user utterance as Live's input transcription, then Live's own (held) reply and its end."""
    blob = dict(mimeType='audio/pcm;rate=24000', data=base64.b64encode(b'\x01\x00' * 9600).decode())
    await bridge.handle({'serverContent': {'inputTranscription': {'text': text}}})
    await bridge.handle({'serverContent': {'modelTurn': {'parts': [{'inlineData': blob}]},
                                           'outputTranscription': {'text': live_says}}})
    await bridge.handle({'serverContent': {'turnComplete': True}})
    if bridge.memory.task:
        await bridge.memory.task


def prompts(wire):
    return [m['clientContent']['turns'][0]['parts'][0]['text'] for m in wire
            if m.get('clientContent', {}).get('turnComplete') is True]


def played(emitted):
    return [m for m in emitted if m['type'] in ('audio', 'reply_delta', 'say')]


def test_seconds_question_holds_live_and_sends_one_evidence_turn(monkeypatch, capsys):
    async def trial():
        bridge, emitted, fixed, wire = bridge_for(clock=100)
        bridge.session.recent_memory.add(scene('Wrench set down on the towel', 'wrench', 'towel'), 92)
        lookups = []
        real = bridge._lookup_memory

        async def counted(question, scope=None):
            lookups.append(question)
            return await real(question, scope)
        bridge._lookup_memory = counted
        await say_user(bridge, 'What did I just do with the wrench?')
        assert lookups == ['What did I just do with the wrench?']
        # Live's own reply to the held turn (a current-frame guess) never reaches the client.
        assert not played(emitted)
        assert not fixed  # the RAM lookup is fast: no wait line
        [text] = prompts(wire)
        assert 'MEMORY v1' in text and 'towel' in text and 'not evidence of the past' in text
        assert not bridge.blocked  # Live may now speak its evidence answer
    asyncio.run(trial())
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"memory_turn"' in line]
    assert rows and rows[-1]['reason'] == {'scope': None, 'source': 'recent', 'found': True, 'via': 'regex',
                                           'filler': False, 'delivered': 'prompt_turn'}
    assert 'wrench' not in json.dumps(rows)  # fixed metadata only, no transcript text


def test_two_minutes_ago_reads_the_ten_minute_log():
    async def trial():
        bridge, emitted, fixed, wire = bridge_for(clock=130)
        bridge.session.recent_memory.add(scene('Wrench on the towel next to the sink', 'wrench'), 8)
        await say_user(bridge, 'Where did I put the wrench two minutes ago?')
        [text] = prompts(wire)
        assert 'towel' in text
    asyncio.run(trial())


def test_slow_lookup_says_the_wait_line_once_then_the_evidence(monkeypatch):
    monkeypatch.setattr(live_memory, 'FILLER_AFTER', .05)

    async def trial():
        bridge, emitted, fixed, wire = bridge_for(rewind=SimpleNamespace(on=True))
        privacy.set_call({'google': True, 'twelvelabs': True})

        async def slow(question, scope=None):
            await asyncio.sleep(.2)
            return dict(source='rewind', found=True, sure=True, say='At 0:05 in this call you picked it up.'), []
        bridge._lookup_memory = slow
        await say_user(bridge, 'Rewind: when did I first pick up the wrench?')
        assert fixed == [live_memory.FILLER]
        [text] = prompts(wire)
        assert '0:05' in text
    asyncio.run(trial())


def test_not_found_is_spoken_by_code_and_live_names_no_place():
    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        bridge.session.recent_memory.add(scene('Wrench on the towel', 'wrench'), 50)
        await say_user(bridge, 'Where did I put the screwdriver a minute ago?')
        assert not prompts(wire)  # Live gets no turn to invent "on the table"
        assert fixed and "can't confirm" in fixed[-1] and 'table' not in ' '.join(fixed)
        assert not played(emitted) and bridge.blocked
    asyncio.run(trial())


def test_lookup_timeout_gives_the_honest_line(monkeypatch):
    monkeypatch.setattr(live_memory, 'FILLER_AFTER', .02)
    monkeypatch.setattr(live_memory, 'TIMEOUT', .1)

    async def trial():
        bridge, emitted, fixed, wire = bridge_for()

        async def stuck(question, scope=None):
            await asyncio.sleep(5)
        bridge._lookup_memory = stuck
        await say_user(bridge, 'What did we fix last week?')
        assert fixed == [live_memory.FILLER, live_memory.TIMEOUT_LINE] and not prompts(wire)
    asyncio.run(trial())


def test_now_question_is_not_held():
    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        await say_user(bridge, 'What am I holding right now?', live_says='A wrench.')
        assert not prompts(wire) and bridge.memory.task is None
        assert any(m['type'] == 'audio' and m['pcm16_b64'] for m in emitted)
    asyncio.run(trial())


def test_safety_and_guide_win_over_memory():
    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        await say_user(bridge, 'where did I put the gas line wrench a minute ago')
        assert len(fixed) == 1 and 'gas' in fixed[0] and not prompts(wire)
        bridge._reset_reply()
        bridge.new_input_turn()
        fixed.clear()
        await say_user(bridge, 'my sink is dripping, what did I just do')
        await bridge.guide.task
        assert bridge.session.home_guide and bridge.memory.task is None
        assert all('MEMORY' not in text for text in prompts(wire))
    asyncio.run(trial())


def test_private_mode_and_gate_off_do_no_lookup(monkeypatch):
    async def trial(private):
        bridge, emitted, fixed, wire = bridge_for()
        bridge.session.private = private

        async def never(question, scope=None):
            raise AssertionError('no lookup')
        bridge._lookup_memory = never
        await say_user(bridge, 'What did I just do?')
        assert not prompts(wire) and bridge.memory.task is None
    asyncio.run(trial(True))
    monkeypatch.setenv('LIVE_MEMORY_GATE', '0')
    asyncio.run(trial(False))


def test_late_tool_answer_for_the_held_turn_is_dropped():
    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        bridge.session.recent_memory.add(scene('Mug on the shelf', 'mug'), 95)
        await bridge.handle({'serverContent': {'inputTranscription': {'text': 'What did I just do with the mug?'}}})
        # Live calls the tool for the held turn anyway; its answer must not be sent after the evidence turn.
        await bridge.handle({'toolCall': {'functionCalls': [
            dict(id='t1', name='recent_memory', args={'question': 'what did I just do with the mug'})]}})
        await bridge.handle({'serverContent': {'turnComplete': True}})
        await bridge.memory.task
        await asyncio.gather(*bridge.tool_tasks.values(), return_exceptions=True)
        assert len(prompts(wire)) == 1 and not any('toolResponse' in m for m in wire)
    asyncio.run(trial())


def test_router_scope_decides_without_time_words_and_vetoes_a_weak_match(monkeypatch):
    monkeypatch.setenv('ROUTER', 'on')
    seen = []

    async def trial(text, decision):
        async def fake(session, question):
            return decision
        monkeypatch.setattr(live_memory, 'scope_decision', fake)
        bridge, emitted, fixed, wire = bridge_for()

        async def lookup(question, scope=None):
            seen.append(scope)
            return dict(source='history', found=True, say='From your task history: on Monday you fixed the sink.'), []
        bridge._lookup_memory = lookup
        await say_user(bridge, text, live_says='Looks good.')
        return prompts(wire), emitted
    sent, _ = asyncio.run(trial('have we ever worked on this lamp together',
                                dict(scope='past_calls', scope_past=.97)))
    assert seen == ['long-term'] and 'Monday' in sent[0]
    # "did I put this in" sounds past but is a now check: the head says now, so Live's own answer plays.
    sent, emitted = asyncio.run(trial('did I put this in the right way', dict(scope='now', scope_past=.03)))
    assert seen == ['long-term'] and sent == [] and any(m['type'] == 'audio' for m in emitted)
    # Explicit time words with a sure "now" from the head: the early hold is released to Live.
    sent, emitted = asyncio.run(trial('what did I just do', dict(scope='now', scope_past=.01)))
    assert seen == ['long-term'] and sent == ['what did I just do']


def test_present_tense_checks_never_hold_without_the_router():
    async def trial():
        bridge, emitted, fixed, wire = bridge_for()
        await say_user(bridge, 'what did I do wrong here', live_says='The screw is crooked.')
        assert bridge.memory.task is None and not prompts(wire) and not fixed
    asyncio.run(trial())
