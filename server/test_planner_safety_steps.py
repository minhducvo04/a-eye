"""Dry headphone replay and plan-repair speech use synthetic packets only."""
import asyncio
import json

import pytest

from server import planner, safety
from server.test_planner import FakeLLM, setup
from server.test_live_guide import say_user
from eval.swap.run import load_cases


@pytest.mark.parametrize('precaution', [
    'Make sure the headphones are not plugged into any device before handling the wire.',
    'Unplug the headphones if plugged into a phone before handling the wire.',
    'Turn the power off before handling the wire.',
    'Let the soldering iron cool before touching the hot tip.',
])
def test_round12_precaution_through_live_plan_and_context(monkeypatch, tmp_path, capsys, precaution):
    from server import context_agent

    async def trial():
        value = next(c['plan'] for c in load_cases('checker') if c['id'] == 'good14')
        value['task'] = 'fix the wire on the headphones near the plug'
        value['steps'][0]['say'] = precaution
        value['steps'][0]['safety'] = ''
        # Six-step synthetic reconstruction, not a captured provider response.
        value['steps'] = value['steps'][:6]
        b, emitted, fixed, wire, _, _, _ = setup(monkeypatch, tmp_path, FakeLLM(value))

        async def assess(*args):
            return dict(hazard='', context='The current plan step says: ' + precaution)

        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        b.start_context()
        builder = b.context_builder
        # Exercise the actual builder callbacks without its periodic worker.
        await builder.close()
        try:
            await b.handle({'serverContent': {'inputTranscription': {'text':
                'dad The wire on my headphones broke near the plug. How do I fix it?', 'finished': True}}})
            await b.handle({'serverContent': {'outputTranscription': {'text':
                'We can definitely take a look at that, but first, can you show me the broken wire on the headphones?'},
                'turnComplete': True}})
            await b.guide.planner.task
            assert b.guide.kind == 'plan' and len(b.guide.guide.plan['steps']) == 6
            await builder.build()
            assert not b.safety_stopped and not fixed
            await b.handle({'serverContent': {'outputTranscription': {'text': precaution}, 'turnComplete': True}})
            assert not b.safety_stopped and not fixed
            assert not any(m.get('detail') == 'Stopped by code' for m in emitted)
            b._reset_reply()
            await say_user(b, 'next')
            assert b.guide.guide.index == 1 and not fixed
            await b.handle({'serverContent': {'inputTranscription': {'text': 'The wire is still live.'}}})
            assert b.safety_stopped and fixed == [next(g.line for g in safety.GATES if g.id == 'live_power')]
        finally:
            await b.guide.close()
            await b.prefetch.close()
            await b.close_context()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    stops = [e['reason'] for e in events if e['event'] == 'live_stop']
    assert stops == [{'gate': 'live_power', 'source': 'question'}]
    assert precaution not in json.dumps(events) and 'headphones' not in json.dumps(events)


@pytest.mark.parametrize('source', ['question', 'output', 'plan_step', 'context', 'guide'])
def test_live_stop_logs_gate_and_source_only(monkeypatch, capsys, source):
    from server.test_live_guide import bridge_for

    async def trial():
        b, _, fixed, _ = bridge_for(monkeypatch)
        line = b.stop_line('The wire is still live.')
        if source in ('question', 'output'):
            field = 'inputTranscription' if source == 'question' else 'outputTranscription'
            await b.handle({'serverContent': {field: {'text': 'The wire is still live.'}}})
        elif source == 'context':
            from server import context_agent

            async def assess(*args):
                return dict(hazard='The wire is still live.', context='Pause the task.')

            monkeypatch.setattr(context_agent, 'assess_live_context', assess)
            b.start_context()
            await b.context_builder.close()
            await b.context_builder.build()
            await b.close_context()
        else:
            await b.stop(line, source=source)
        await b.stop(line, source=source)
        assert fixed == [line]
        await b.guide.close()
        await b.prefetch.close()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(events) == 1 and events[0]['event'] == 'live_stop'
    assert events[0]['reason'] == {'gate': 'live_power', 'source': source}
    assert 'wire' not in json.dumps(events)


@pytest.mark.parametrize('text', [
    'Unplug the headphones if plugged into a phone before handling the wire. The wire is still live.',
    'Unplug the headphones if plugged into a phone and work on the wire while plugged in.',
    'Do not unplug the headphones if plugged into a phone before handling the wire.',
    'Never try to unplug the headphones if plugged into a phone before handling the wire.',
    'Do not let the soldering iron cool before touching the hot tip.',
    'Let the soldering iron cool before touching the hot tip; grab the hot iron.',
    'Turn the power off before handling the wire. There is water by the outlet.',
])
def test_precaution_does_not_hide_real_hazard(monkeypatch, text):
    from server.test_live_guide import bridge_for
    b, _, _, _ = bridge_for(monkeypatch)
    assert b.stop_line(text, output=True) in safety.LINES


@pytest.mark.parametrize('text', [
    'Inspect the headphone cord near the plug.',
    'Check for sound leakage near the laptop.',
    'Keep water in the cup. Inspect the charger.',
    'Inspect the charger. Wipe up the spill.',
    'Inspect the charger.\nThe cloth is wet.',
])
def test_water_gate_requires_explicit_water_in_same_sentence(text):
    gate = next(g for g in safety.GATES if g.id == 'water_electric')
    assert not gate.ask.search(text)
    assert safety.before(text) is None
    assert safety.violation(text) is None


@pytest.mark.parametrize('text', [
    'Water is next to the plug.', 'The cord is wet.', 'A spill is next to the outlet.',
    'The charger is in a puddle.', 'A drip is falling onto the power strip.',
])
def test_actual_water_electric_reports_still_stop(text):
    assert safety.before(text) == next(g.line for g in safety.GATES if g.id == 'water_electric')


@pytest.mark.parametrize('legacy', [False, True])
def test_headphone_replaced_step_speaks_without_latching_stop(monkeypatch, tmp_path, capsys, legacy):
    async def trial():
        value = next(c['plan'] for c in load_cases('checker') if c['id'] == 'good14')
        value['task'] = 'fix the headphones'
        # Reproduce the round-7 replacement path, including an already cached fixed line.
        hazard = 'Move the wet extension cord.'
        if legacy:
            line = next(g.line for g in safety.GATES if g.id == 'water_electric')
            value['steps'][1] = planner.safety_step(line)
        else:
            value['steps'][1]['check'] = hazard
        b, emitted, fixed, wire, fake, store, points = setup(monkeypatch, tmp_path, FakeLLM(value))
        try:
            b.guide.observe('help me fix my headphones')
            await b.guide.planner.task
            checked = b.guide.guide.plan
            assert planner.PlanCache(store.path).get(value['task']) == checked
            assert checked['steps'][1]['say'] not in safety.LINES
            for index in range(2):
                if index:
                    b._reset_reply()
                    await say_user(b, 'next')
                await b.handle({'serverContent': {'outputTranscription': {
                    'text': checked['steps'][index]['say']}, 'turnComplete': True}})
                assert not b.safety_stopped and not b.blocked and not fixed
            assert not any(m.get('detail') == 'Stopped by code' for m in emitted)
            await b.handle({'serverContent': {'inputTranscription': {
                'text': 'There is water beside the outlet.', 'finished': True}}})
            assert b.safety_stopped and fixed == [next(g.line for g in safety.GATES if g.id == 'water_electric')]
        finally:
            await b.guide.close()
            await b.prefetch.close()
    asyncio.run(trial())
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(e['event'] == 'planner_step_replaced' and e['reason']['gate'] == 'water_electric'
               and e['reason']['step'] == 2 for e in events)
    assert 'headphones' not in json.dumps(events) and 'Move the wet' not in json.dumps(events)


@pytest.mark.parametrize('gate,line', planner.SAFETY_LINES.items())
def test_every_plan_precaution_passes_live_output_gate(monkeypatch, gate, line):
    from server.test_live_guide import bridge_for
    b, _, _, _ = bridge_for(monkeypatch)
    assert line not in safety.LINES
    assert b.stop_line(line, output=True) is None, gate


def test_headphone_plan_does_not_pair_water_across_fields():
    value = next(c['plan'] for c in load_cases('checker') if c['id'] == 'good14')
    value['steps'][2]['check'] = 'Put the water cup on a separate table.'
    assert planner.check_plan(value) == value
