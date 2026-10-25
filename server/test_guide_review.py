"""Review reproductions: synthetic frames, local checker and fake Live transport only."""
import asyncio
import base64
from time import monotonic
from types import SimpleNamespace

import pytest

from server import agent, parts_shelf
from server.agent import Session
from server.packs.home import HomeGuide
from server.step_check import Checker, Verdict, RETRY_LINE
from server.test_live_guide import bridge_for, prompts, say_user
from server.test_step_check import photo


async def at_valve(monkeypatch):
    monkeypatch.setenv("HOME_TASKS", "1")
    app = SimpleNamespace(state=SimpleNamespace(presenter=True))
    bridge, emitted, fixed, wire = bridge_for(monkeypatch, app=app)
    for text in ('my sink is dripping', 'done', 'done'):
        bridge._reset_reply()
        await say_user(bridge, text)
    bridge._reset_reply()
    return bridge, emitted, fixed, wire


def test_later_transcription_does_not_cancel_valve_check(monkeypatch):
    async def trial():
        bridge, _, fixed, wire = await at_valve(monkeypatch)
        session = bridge.session
        session.checker_test_mode = True
        fixture = session.checker_test_verdict = ('closed', monotonic())
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def check(*args):
            calls.append(args)
            entered.set()
            await release.wait()
            return Verdict('closed', 1)

        monkeypatch.setattr(agent, 'check_water_off', check)
        await bridge.handle({'serverContent': {'inputTranscription': {'text': "it's off"}}})
        await entered.wait()
        first = bridge.guide.task
        await bridge.handle({'serverContent': {'inputTranscription': {'text': ' now'}}})
        release.set()
        await bridge.guide.task
        assert not first.cancelled() and len(calls) == 1
        assert calls[0][-1] is fixture and session.checker_test_verdict is None
        assert session.home_guide.index == 3 and not session.home_guide.water_off_passed
        assert not fixed and 'step 4 of 7' in prompts(wire)[-1]
    asyncio.run(trial())


def test_valve_check_waits_for_fresh_frame_and_preserves_capture_time(monkeypatch):
    async def trial():
        raw = photo()
        session = Session('fresh', frame={'seq': 1, 'jpeg_b64': base64.b64encode(raw).decode()},
                          frame_time=monotonic() - 1.49)
        checked = []

        class Method:
            async def classify(self, *args):
                await asyncio.sleep(.03)
                return Verdict('closed', 1)

        class RecordingChecker(Checker):
            async def check(self, frame, *args, captured_at=None):
                checked.append(captured_at)
                return await super().check(frame, *args, captured_at=captured_at)

        session.step_checker = RecordingChecker(Method())
        async def camera():
            await asyncio.sleep(.01)
            session.frame = dict(session.frame, seq=2)
            session.frame_time = monotonic()

        update = asyncio.create_task(camera())
        result = await agent.check_water_off(session, None)
        await update
        assert result.passed and checked == [session.frame_time]
        # The checker itself must reject old input and input that ages out during inference.
        assert not (await session.step_checker.check(raw, captured_at=monotonic() - 2)).passed
        assert not (await session.step_checker.check(raw, captured_at=monotonic() - 1.49)).passed
        # No camera update: waiting must be bounded and must not freshen an old timestamp.
        session.frame_time = monotonic() - 2
        assert not (await asyncio.wait_for(agent.check_water_off(session, None), 2)).passed
    asyncio.run(trial())


def test_next_requires_completion_intent_in_home_and_live(monkeypatch):
    monkeypatch.setenv("HOME_TASKS", "1")
    bridge, _, _, _ = bridge_for(monkeypatch)
    bridge.guide.kind = 'home'
    for text in ('the puddle is next to the cabinet', "I'm not done looking", 'not ready',
                 'what do I do next to the valve?'):
        guide = bridge.session.home_guide = HomeGuide(introduced=True)
        guide.reply(text)
        assert guide.index == 0, text
        assert not bridge.guide.claims(text), text
    for text in ('next step', "I'm done", 'done', 'ok next', "what's next", 'next',
                 'continue', 'ready', 'the water is off, next', 'USB unplugged, next'):
        guide = bridge.session.home_guide = HomeGuide(introduced=True)
        assert bridge.guide.claims(text), text
        guide.reply(text)
        assert guide.index == 1, text

    async def growing_transcript():
        bridge, _, _, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'my sink is dripping')
        bridge._reset_reply()
        await bridge.handle({'serverContent': {'inputTranscription': {'text': 'next'}}})
        await bridge.handle({'serverContent': {'inputTranscription': {'text': ' to the cabinet'}}})
        await bridge.handle({'serverContent': {'turnComplete': True}})
        await bridge.guide.task
        assert bridge.session.home_guide.index == 0
        assert 'step 1 of 7' in prompts(wire)[-1]
    asyncio.run(growing_transcript())


@pytest.mark.parametrize('text', ["I closed it", "it's closed", 'turned it off', 'shut it',
                                 'I shut the valve'])
def test_off_phrases_request_check_but_cannot_pass(monkeypatch, text):
    async def trial():
        bridge, _, fixed, wire = await at_valve(monkeypatch)
        before = len(prompts(wire))
        assert bridge.guide.claims(text)
        await bridge.guide.run(text)
        assert fixed == [RETRY_LINE] and len(prompts(wire)) == before
        assert bridge.session.home_guide.index == 2
        assert not bridge.session.home_guide.water_off_passed
    asyncio.run(trial())


def test_question_prompt_keeps_and_republishes_guide(monkeypatch):
    async def trial():
        bridge, _, _, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'help me with my tie')
        # Finish the spoken step and let the normal idle hook publish its background GUIDE.
        await bridge.handle({'serverContent': {'turnComplete': True}})
        before = len(wire)
        await bridge.guide.run('why is the wide end longer?')
        assert 'GUIDE v' in prompts(wire)[-1] and 'step 1 of 8' in prompts(wire)[-1]
        await bridge.handle({'serverContent': {'turnComplete': True}})
        background = [m for m in wire[before:] if m.get('clientContent', {}).get('turnComplete') is False]
        assert background and 'step 1 of 8' in background[-1]['clientContent']['turns'][0]['parts'][0]['text']
        assert bridge.session.tie_guide.index == 0
    asyncio.run(trial())


@pytest.mark.parametrize('passed', [True, False])
def test_hazard_during_check_prevents_prompt_or_retry(monkeypatch, passed):
    async def trial():
        bridge, _, fixed, wire = await at_valve(monkeypatch)
        before = len(prompts(wire))
        async def check(*args):
            await bridge.stop('Stop for the observed hazard.')
            return Verdict('closed', 1) if passed else Verdict()
        monkeypatch.setattr(agent, 'check_water_off', check)
        await bridge.guide.run("it's off")
        assert fixed == ['Stop for the observed hazard.']
        assert bridge.safety_stopped and len(prompts(wire)) == before
        assert bridge.session.home_guide.index == 2
        assert not bridge.session.home_guide.water_off_passed
    asyncio.run(trial())


def test_dialogue_cannot_warm_future_step_parts():
    # Isolate the card so NOTE_MAX cannot accidentally hide a bad match.
    shelf = parts_shelf.Shelf(parts_shelf.shelf().match('Blink upload'))
    text = "we'll swap the Blink upload in a minute"
    assert 'Blink upload' not in shelf.note('ee_led', 1, [text])
    assert 'Blink upload' in shelf.note('ee_led', 7, [text])
    assert 'Blink upload' in shelf.note(texts=[text])


@pytest.mark.parametrize('completed', [False, True])
def test_forget_recreates_and_republishes_first_step(monkeypatch, completed):
    async def trial():
        bridge, _, _, wire = bridge_for(monkeypatch)
        await say_user(bridge, 'help me with my tie')
        bridge._reset_reply()
        old = bridge.session.tie_guide
        old.index, old.completed = 3, completed
        bridge.guide.line = 'Old repair step'
        bridge.guide.note()
        assert bridge.guide.claims('forget my progress')
        await bridge.guide.run('forget my progress')
        guide = bridge.session.tie_guide
        assert guide is not old and guide.index == 0 and not guide.completed
        assert bridge.session.live_guide_note['step'] == 1
        assert 'step 1 of 8' in prompts(wire)[-1] and 'Old repair step' not in prompts(wire)[-1]
        await bridge.handle({'serverContent': {'turnComplete': True}})
        assert any(m.get('clientContent', {}).get('turnComplete') is False and
                   'step 1 of 8' in m['clientContent']['turns'][0]['parts'][0]['text'] for m in wire)
    asyncio.run(trial())
