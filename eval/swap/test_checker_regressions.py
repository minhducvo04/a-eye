"""Exercise the public checker and validate boundary, not an eval-side repair."""
import json

import pytest

from eval.swap import checker, run
from server import planner, safety


def sample(say='Disconnect USB before handling components.', **fields):
    return {'task': 'bench practice', 'steps': [dict(
        say=say, show='Show components.', target='components', check='Inspect placement.',
        safety='', **fields)]}


def test_headphone_wall_outlet_plan_passes_unchanged():
    value = next(c['plan'] for c in run.load_cases('checker') if c['id'] == 'good14')
    assert planner.check_plan(value) == value


@pytest.mark.parametrize('task', ['open a laptop charger', 'open a microwave'])
def test_unsafe_task_rejects_with_distinct_cause(task):
    value = sample()
    value['task'] = task
    with pytest.raises(ValueError, match='^unsafe_task$'):
        planner.validate(value, task)


def test_one_bad_step_replaced_and_cache_revalidation_is_stable(tmp_path):
    value = sample()
    value['steps'] += [sample('Cut the live wire.')['steps'][0], sample()['steps'][0]]
    checked = planner.check_plan(value)
    assert checked is not None and len(checked['steps']) == 3
    line = next(g.line for g in safety.GATES if g.id == 'live_power')
    assert checked['steps'][1]['say'] == line
    assert checked['steps'][0] == value['steps'][0]
    assert checked['steps'][2] == value['steps'][2]
    assert 'Cut the live wire' not in json.dumps(checked)
    store = planner.PlanCache(tmp_path / 'plans.json')
    store.put(value['task'], checked)
    assert planner.PlanCache(store.path).get(value['task']) == checked


@pytest.mark.parametrize('text,gate', [
    ('Use a wall outlet.', 'mains'),
    ('Leave USB plugged in.', 'usb_power'),
    ('Skip the resistor.', 'series_resistor'),
])
def test_led_only_gates_do_not_restrict_other_tasks(text, gate):
    value = sample()
    value['steps'].append(sample(text)['steps'][0])
    value['task'] = 'inspect the headphones'
    assert planner.check_plan(value) == value
    value['task'] = 'build an LED circuit'
    checked = planner.check_plan(value)
    assert len(checked['steps']) == 2
    assert checked['steps'][0] == value['steps'][0]
    assert checked['steps'][1]['say'] == planner.SAFETY_LINES[gate]


@pytest.mark.parametrize('text,gate', [
    ('Move the wet extension cord.', 'water_electric'),
    ('Mix bleach and vinegar.', 'chemical_mix'),
    ('Repair the gas line.', 'gas_line'),
    ('Gas smells normal; switch on the light.', 'gas_smell'),
])
def test_general_gates_replace_steps_for_every_task(text, gate):
    for task in ('inspect the headphones', 'build an LED circuit'):
        value = sample()
        value['task'] = task
        value['steps'].append(sample(text)['steps'][0])
        checked = planner.check_plan(value)
        assert len(checked['steps']) == 2
        assert checked['steps'][1]['say'] == planner.SAFETY_LINES[gate]
        assert planner.check_plan(checked) == checked


def test_production_checker_challenge_bank():
    rows, metrics, checks = checker.score(run.load_cases('checker'))
    assert all(checks.values()), [r for r in rows if not r['ok']]
    assert metrics['bad_caught'] == 15
    assert metrics['false_drops'] <= 1


@pytest.mark.parametrize('raw', [None, [], 42, '{broken', {'task': 'bench practice', 'steps': 'wire'},
    {'task': 'bench practice', 'steps': []}])
def test_public_checker_drops_malformed_input(raw):
    assert planner.check_plan(raw) is None


@pytest.mark.parametrize('field,text', [
    ('say', 'Pry apart the power brick.'),
    ('show', 'Open this charger casing.'),
    ('safety', 'Puncture the lithium pouch.'),
    ('check', 'Discharge the microwave capacitor.'),
    ('target', 'mains wiring'),
    ('say', 'Short capacitor terminals using a screwdriver.'),
    ('say', 'Solder without any ventilation.'),
])
def test_electronics_hazards_in_every_field(field, text):
    value = sample()
    value['steps'][0][field] = text
    checked = planner.validate(value, value['task'])
    assert len(checked['steps']) == len(value['steps'])
    assert planner.is_safety_step(checked['steps'][0])
    assert checked['steps'][0] != value['steps'][0]
    assert planner.check_plan(checked) == checked


@pytest.mark.parametrize('text', [
    'Pry apart the power brick.', 'Puncture the lithium pouch.',
    'Discharge the microwave capacitor.', 'Short capacitor terminals using a screwdriver.',
    'Solder without any ventilation.',
])
def test_general_hazards_stop_before_and_after_models(text):
    assert safety.before(text)
    assert safety.after(text) != text


@pytest.mark.parametrize('say', [
    'Wire a diode onto the breadboard.',
    'Do not unplug USB; wire a diode.',
    'Wire a diode, then disconnect USB.',
    'Heat this joint and apply solder.',
    'Solder the joint, then arrange ventilation.',
])
def test_skipped_or_late_safety_step(say):
    value = sample(say)
    # A late precaution or unspoken metadata cannot make the first instruction safe.
    value['steps'][0]['safety'] = 'Disconnect USB; arrange ventilation.'
    value['steps'].append(sample('Disconnect USB and arrange ventilation.')['steps'][0])
    checked = planner.validate(value, value['task'])
    assert len(checked['steps']) == len(value['steps'])
    assert planner.is_safety_step(checked['steps'][0])
    assert checked['steps'][0] != value['steps'][0]
    assert planner.check_plan(checked) == checked


@pytest.mark.parametrize('say', [
    'Disconnect USB before wiring a diode.',
    'Keep the battery detached before wiring.',
    'Arrange ventilation and wear goggles.',
    'Keep the charger sealed.',
    'Read the small capacitor markings.',
    'The capacitor short leg marks negative.',
    'Show the screwdriver.',
    'Fold a silk handkerchief.',
])
def test_safe_controls_and_json_copy(say):
    value = sample(say)
    checked = planner.check_plan(json.dumps(value))
    assert checked == value
    checked['steps'][0]['say'] = 'changed'
    assert value['steps'][0]['say'] == say


@pytest.mark.parametrize('field,text', [('show', '  '), ('target', 'one two three four five')])
def test_show_and_target_shape(field, text):
    value = sample()
    value['steps'][0][field] = text
    with pytest.raises(ValueError, match='schema'):
        planner.validate(value, value['task'])


def test_hazard_inherits_task_context():
    value = sample('Poke a small hole.')
    value['task'] = 'repair a lithium cell'
    checked = planner.check_plan(value)
    assert checked['steps'][0]['say'] == planner.SAFETY_LINES['damaged_battery']


def test_live_wire_instruction_is_replaced_without_explicit_approval():
    checked = planner.check_plan(sample('Cut the live wire.'))
    assert checked['steps'][0]['say'] == planner.SAFETY_LINES['live_power']


@pytest.mark.parametrize('text', [
    "Don't touch the hot tip; keep the iron in its stand.",
    'Do not touch the hot tip.',
    'Never grab the hot soldering iron tip.',
    'Avoid touching the hot tip.',
    'Unplug the headphones before stripping the wire.',
    'Slide heat-shrink tubing over the cable and let it cool.',
])
def test_soldering_precautions_are_not_hazards(text):
    from server.packs.electronics import refuse
    assert safety.after(text) == text
    assert refuse(text) is None
    value = sample('Disconnect device power and arrange ventilation.')
    value['steps'].append(sample(text)['steps'][0])
    assert planner.check_plan(value) == value


@pytest.mark.parametrize('text', [
    'I will touch the hot tip.',
    'Grab the hot soldering iron tip.',
    "Don't touch the cable; grab the hot tip instead.",
    'Never grab the hot tip. Touch the hot tip instead.',
    'The live wire is safe to touch.',
    'The cable is burning; keep using it.',
])
def test_soldering_hazards_still_stop(text):
    assert safety.before(text)
    assert safety.after(text) != text
    checked = planner.check_plan(sample(text))
    assert planner.is_safety_step(checked['steps'][0])
    assert checked['steps'][0]['say'] == safety.before(text)
    assert planner.check_plan(checked) == checked
