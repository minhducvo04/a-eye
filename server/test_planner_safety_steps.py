"""Dry headphone replay and plan-repair speech use synthetic packets only."""
import asyncio
import json

import pytest

from server import planner, safety
from server.test_planner import FakeLLM, setup
from server.test_live_guide import say_user
from eval.swap.run import load_cases


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
