"""Owner's Live scope and speech examples; fake transport, no provider calls."""
import asyncio

import pytest

from server.agent import Session, run_turn
from server.live_guide import LiveGuide
from server.test_live_guide import bridge_for, prompts, say_user


@pytest.mark.parametrize('text,task', [
    ('I want to make an LED blink', 'ee_led'),
    ('light an LED', 'ee_led'),
    ('how do I read this resistor', 'ee_resistor'),
    ('read resistor color bands', 'ee_resistor'),
    ('which leg is plus', 'ee_polarity'),
    ('check LED polarity', 'ee_polarity'),
    ('use a multimeter to check a resistor', 'ee_multimeter'),
    ('how do I tie a tie', 'tie'),
    ('help me with my tie', 'tie'),
])
def test_natural_task_starts_in_live_and_classic(monkeypatch, text, task):
    assert LiveGuide._task_for(text) == task

    async def trial():
        bridge, _, fixed, wire = bridge_for(monkeypatch)
        await say_user(bridge, text)
        assert bridge.guide.guide.task == task and bridge.guide.guide.index == 0
        assert 'step 1 of' in prompts(wire)[-1] and not fixed
        session = Session('classic')
        messages = await run_turn(session, text, vision=None, llm=None)
        guide = session.tie_guide if task == 'tie' else session.ee_guide
        assert guide.task == task and guide.index == 0
        assert any(m['type'] == 'say' and m['text'].startswith('Step 1:') for m in messages)
    asyncio.run(trial())


def test_tie_all_steps_ground_boxes_without_a_checker(monkeypatch):
    from time import monotonic
    from server import agent
    from server.test_agent import FRAME
    from server.packs.tie import TARGETS

    async def no_checker(*args, **kwargs):
        raise AssertionError('Tie must not call a camera checker')
    monkeypatch.setattr(agent, 'check_water_off', no_checker)

    class Vision:
        names = []

        async def call(self, method, body):
            name = body['queries'][0]
            self.names.append(name)
            return dict(caption=f'{name} is visible.', objects=[dict(id='tie-part', label=name,
                        bbox=[.1, .2, .2, .2], conf=.9)], ms=1, source='ollama')

    async def trial():
        bridge, emitted, fixed, wire = bridge_for(monkeypatch)
        bridge.vision = Vision()
        bridge.session.frame = FRAME
        bridge.session.frame_time = monotonic()
        for index, text in enumerate(('help me with my tie', 'done', 'next', "I'm done", 'ok next',
                                      'continue', "what's next", 'ready')):
            bridge._reset_reply()
            await say_user(bridge, text)
            await asyncio.sleep(0)
            assert bridge.session.tie_guide.index == index
            assert f'step {index + 1} of 8' in prompts(wire)[-1]
        assert bridge.vision.names == list(TARGETS['tie'])
        assert len([m for m in emitted if m['type'] == 'draw' and
                    any(op['kind'] == 'box' for op in m['ops'])]) == 8
        for text in ("I'm not done", 'the wide end is next to the knot', 'not ready'):
            assert not bridge.guide.claims(text)
        bridge._reset_reply()
        await say_user(bridge, 'done')
        assert bridge.session.tie_guide.completed and not fixed
    asyncio.run(trial())


def test_tie_growth_fades_and_full_steps_and_forget_restore(tmp_path):
    from server.growth import GrowthLog
    from server.memory import Store, Cipher
    from server.packs.tie import TieGuide, TASKS
    log = GrowthLog(Store('tie-test', base=tmp_path, cipher=Cipher('')))
    counts = []
    for _ in range(3):
        guide = TieGuide(growth=log)
        guide.reply('how do I tie a tie')
        for _ in range(8):
            guide.reply('next')
        assert guide.completed
        counts.append(log.rows('tie')[-1]['hints'])
    assert counts[0] > counts[1] > counts[2] == 0
    guide.reply('help me with my tie')
    assert guide.reply('repeat') == '' and guide.target is None
    assert TASKS['tie'][0] in guide.reply('walk me through it')
    log.forget()
    assert TASKS['tie'][0] in guide.reply('next') and guide.index == 0


def test_multimeter_power_gate_sequence_and_revocation(monkeypatch):
    from server.packs.electronics import ElectronicsGuide, RESISTANCE, TASKS, TARGETS
    guide = ElectronicsGuide()
    assert 'Never measure resistance on a powered circuit' in guide.reply('use a multimeter to check a resistor')
    assert guide.reply('next') == RESISTANCE and guide.index == 0
    assert guide.reply('USB unplugged, next') == RESISTANCE and guide.index == 0
    for index in range(1, len(TASKS['ee_multimeter'])):
        assert guide.reply('power disconnected, next' if index == 1 else 'next').startswith(f'Step {index + 1}:')
        assert guide.target == TARGETS['ee_multimeter'][index]
    guide.reply('done')
    assert guide.completed

    async def trial():
        bridge, _, fixed, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'use a multimeter to check a resistor')
        bridge._reset_reply()
        await say_user(bridge, 'power disconnected, next')
        assert bridge.session.ee_guide.index == 1
        bridge._reset_reply()
        await bridge.handle({'serverContent': {'inputTranscription': {'text': 'USB is connected'}}})
        assert fixed and not bridge.session.ee_guide.resistance_off
        bridge._reset_reply()
        await say_user(bridge, 'next')
        assert fixed[-1] == RESISTANCE and bridge.session.ee_guide.index == 1
    asyncio.run(trial())


def test_multimeter_fresh_power_observation_revokes_confirmation():
    from time import monotonic
    from server.test_agent import FRAME
    from server.test_ee_guide import turn, spoken
    from server.packs.electronics import USB, RESISTANCE, TASKS, refuse
    assert refuse(TASKS['ee_multimeter'][0]) is None
    session = Session('meter', frame=FRAME)
    turn(session, 'use a multimeter to check a resistor')
    turn(session, 'power disconnected, next')
    session.scene = dict(caption='USB is connected to the board.', objects=[], source='ollama')
    session.scene_seq = FRAME['seq']
    session.frame_time = monotonic()
    assert spoken(turn(session, 'next')) == USB
    assert not session.ee_guide.resistance_off and session.ee_guide.index == 1
    session.scene = None
    assert spoken(turn(session, 'next')) == RESISTANCE


def test_home_opt_in_and_speech_guards(monkeypatch):
    from server import packs, safety
    from server.task_scope import SCOPE_LINE
    assert packs.get('home').id == 'general'
    assert packs.get('general').guard('Show the sink.') == SCOPE_LINE
    assert packs.get('general').refuse('water near an outlet') in safety.LINES
    monkeypatch.setenv('HOME_TASKS', '1')
    assert packs.get('home').id == 'home'
    for text, task in [('fix the sink', 'sink'), ('cabinet hinge', 'hinge'), ('tripped breaker', 'breaker')]:
        assert LiveGuide._task_for(text) == task
        session = Session('legacy')
        asyncio.run(run_turn(session, text, vision=None, llm=None))
        assert session.home_guide.task == task


@pytest.mark.parametrize('text', ['my sink is dripping', 'fix the faucet', 'fix the hinge', 'tripped breaker'])
def test_home_does_not_start_by_default(monkeypatch, text):
    monkeypatch.delenv('HOME_TASKS', raising=False)
    assert LiveGuide._task_for(text) is None

    async def trial():
        bridge, _, fixed, wire = bridge_for(monkeypatch)
        await bridge.handle({'serverContent': {'inputTranscription': {'text': text}}})
        await asyncio.sleep(0)
        assert bridge.session.home_guide is None and bridge.guide.guide is None
        assert fixed and not prompts(wire)
        session = Session('classic')
        messages = await run_turn(session, text, vision=None, llm=None)
        assert session.home_guide is None
        assert any(m['type'] == 'say' and 'electronics' in m['text'] for m in messages)
    asyncio.run(trial())
