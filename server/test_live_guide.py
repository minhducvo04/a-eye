import pytest
"""The coded step guide inside the Live call, with synthetic provider packets only (no network)."""
import asyncio
import base64
import json
from time import monotonic
from types import SimpleNamespace

from server import live_guide, privacy
from server.agent import Session
from server.gemini_live import LiveBridge, DOCUMENTED_MODEL
from server.packs.home import HINTS, TASKS
from server.safety import WATER_OFF_LINE
from server.step_check import RETRY_LINE



@pytest.fixture(autouse=True)
def _guide_ui(monkeypatch):
    monkeypatch.setenv('LIVE_GUIDE_UI', '1')


def test_new_screens_stay_off_by_default(monkeypatch):
    from server.live_guide import ui_detail
    monkeypatch.delenv('LIVE_GUIDE_UI')
    assert ui_detail('Valve: unsure') == 'Guide: unsure' and ui_detail('Home: complete') == 'Guide: complete'

def bridge_for(monkeypatch, app=None, growth=None):
    monkeypatch.setattr(live_guide, 'DEBOUNCE', 0)
    privacy.set_call({'google': True})
    emitted, fixed, wire = [], [], []

    async def emit(msg):
        emitted.append(msg)

    async def speak(text):
        fixed.append(text)

    async def send(raw):
        wire.append(json.loads(raw))
    session = Session('s')
    session.growth = growth
    bridge = LiveBridge(session, None, app, emit, speak)
    bridge.active, bridge.model = True, DOCUMENTED_MODEL
    bridge.ws = SimpleNamespace(send=send)
    return bridge, emitted, fixed, wire


async def say_user(bridge, text):
    """One finished user utterance, as Live's input transcription, then the held provider turn ends."""
    blob = dict(mimeType='audio/pcm;rate=24000', data=base64.b64encode(b'\x01\x00' * 4800).decode())
    await bridge.handle({'serverContent': {'inputTranscription': {'text': text}}})
    # Live's own reply to the turn code owns: never forwarded.
    await bridge.handle({'serverContent': {'modelTurn': {'parts': [{'inlineData': blob}]},
                                           'outputTranscription': {'text': 'Great, the next step is'}}})
    await bridge.handle({'serverContent': {'turnComplete': True}})
    await bridge.guide.task


def prompts(wire):
    return [m['clientContent']['turns'][0]['parts'][0]['text'] for m in wire
            if m.get('clientContent', {}).get('turnComplete') is True]


def details(emitted):
    return [m.get('detail') for m in emitted if m['type'] == 'turn' and m.get('detail')]


def test_sink_starts_in_live_and_live_reply_is_held(monkeypatch):
    async def trial():
        bridge, emitted, fixed, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'my sink is dripping')
        guide = bridge.session.home_guide
        assert guide and guide.task == 'sink' and guide.index == 0 and guide.introduced
        assert bridge.session.pack.id == 'general'
        text = prompts(wire)[-1]
        assert 'step 1 of 7' in text and TASKS['sink'][0] in text and 'do not skip ahead' in text
        assert 'Guide: sink 1/7' in details(emitted) and 'Home: sink' not in details(emitted)
        assert not any(m['type'] in ('audio', 'say', 'reply_delta') for m in emitted)
        assert not fixed
        # An ordinary question about the sink is Live's to answer.
        assert not bridge.guide.claims('what is under the sink?')
    asyncio.run(trial())


def test_shutoff_step_never_advances_on_words_without_the_valve_check(monkeypatch):
    async def trial():
        bridge, emitted, fixed, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'my sink is dripping')
        await say_user(bridge, 'done')
        bridge._reset_reply()
        await say_user(bridge, 'done')
        guide = bridge.session.home_guide
        assert guide.index == 2 and 'step 3 of 7' in prompts(wire)[-1]
        sent = len(prompts(wire))
        bridge._reset_reply()
        await say_user(bridge, "it's off")
        # No camera, no checker: missing is not passed. Fixed retry line, no step given by Live.
        assert guide.index == 2 and fixed == [RETRY_LINE] and len(prompts(wire)) == sent
        assert 'Valve: unsure' in details(emitted) and guide.water_off_passed is False
        # The latched stop unlatches on the next input, as for any stop.
        bridge._reset_reply()
        await say_user(bridge, 'next')
        assert guide.index == 2 and fixed == [RETRY_LINE, RETRY_LINE]
    asyncio.run(trial())


def test_shutoff_step_advances_with_a_valve_pass(monkeypatch):
    async def trial():
        app = SimpleNamespace(state=SimpleNamespace(presenter=True))
        bridge, emitted, fixed, wire = bridge_for(monkeypatch, app=app)
        session = bridge.session
        for text in ('my sink is dripping', 'done', 'done'):
            bridge._reset_reply()
            await say_user(bridge, text)
        session.checker_test_mode = True
        session.checker_test_verdict = ('closed', monotonic())
        bridge._reset_reply()
        await say_user(bridge, "it's off")
        guide = session.home_guide
        assert guide.index == 3 and not fixed and guide.water_off_passed is False
        assert 'step 4 of 7' in prompts(wire)[-1] and TASKS['sink'][3] in prompts(wire)[-1]
        assert 'Valve: test closed' in details(emitted)
        # The pass is consumed: the next "done" needs a fresh check.
        bridge._reset_reply()
        await say_user(bridge, 'done')
        assert guide.index == 3 and fixed == [RETRY_LINE]
        assert WATER_OFF_LINE not in fixed
    asyncio.run(trial())


def test_guide_block_published_only_while_idle(monkeypatch):
    async def trial():
        bridge, emitted, fixed, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'my sink is dripping')
        bridge.guide.version += 1  # a step change not yet carried by a prompt
        bridge._reset_reply()
        bridge.generating = True
        await bridge.publish_guide()
        assert not [m for m in wire if m.get('clientContent', {}).get('turnComplete') is False]
        bridge.generating = False
        await bridge.publish_guide()
        background = [m for m in wire if m.get('clientContent', {}).get('turnComplete') is False]
        assert len(background) == 1 and 'GUIDE v' in background[0]['clientContent']['turns'][0]['parts'][0]['text']
        await bridge.publish_guide()  # unchanged: not re-sent
        assert len([m for m in wire if m.get('clientContent', {}).get('turnComplete') is False]) == 1
    asyncio.run(trial())


def test_hints_fade_and_walk_me_through_it_restores_steps(monkeypatch):
    async def trial():
        growth = SimpleNamespace(level=lambda task: 2, epoch=0, start=lambda task: 'run',
                                 update=lambda *a, **k: True, comparison=lambda task, run: '')
        bridge, emitted, fixed, wire = bridge_for(monkeypatch, growth=growth)
        await say_user(bridge, 'my sink is dripping')
        assert HINTS['sink'][0] in prompts(wire)[-1] and TASKS['sink'][0] not in prompts(wire)[-1]
        bridge._reset_reply()
        await say_user(bridge, 'walk me through it')
        assert TASKS['sink'][0] in prompts(wire)[-1]
    asyncio.run(trial())


def test_hazard_in_a_guide_turn_gets_the_fixed_line(monkeypatch):
    async def trial():
        bridge, emitted, fixed, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'my sink is dripping')
        bridge._reset_reply()
        await bridge.handle({'serverContent': {'inputTranscription': {'text': 'water near the outlet, done'}}})
        await asyncio.sleep(0)
        assert fixed and 'electrician' in fixed[0]
        assert bridge.session.home_guide.index == 0 and bridge.session.home_guide.water_off_passed is False
    asyncio.run(trial())
