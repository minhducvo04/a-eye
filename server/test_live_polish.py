"""Offline regressions for the live-call weakness fixes."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from server import context_agent, personas, privacy
from server.agent import Session
from server.gemini_live import LiveBridge, live_setup
from server.test_live_streaming import audio_content


def bridge():
    privacy.set_call({'google': True})
    emitted, fixed, wire = [], [], []
    async def emit(msg):
        emitted.append(msg)
    async def speak(line):
        fixed.append(line)
    async def send(raw):
        wire.append(json.loads(raw))
    b = LiveBridge(Session('polish', camera=False), None, None, emit, speak)
    b.ws, b.active, b.model = SimpleNamespace(send=send), True, 'fake'
    return b, emitted, fixed, wire


def test_live_setup_omits_catchphrases_and_bounds_visual_claims():
    for persona in personas.list_personas():
        style = personas.style_block(persona, live=True)
        text = live_setup('fake', style)['systemInstruction']['parts'][0]['text']
        assert 'catchphrase' not in text.lower()
        assert all(phrase not in text for phrase in persona['voice_style']['catchphrases'])
        assert 'at most once' in text and 'next concrete step' in text
        assert 'clearly visible' in text and 'two different frames' in text
        assert 'No small talk about objects' in text
        assert 'ordinary visual questions' in text
        assert 'catchphrases' in personas.style_block(persona)


@pytest.mark.parametrize('filler', ['…', '...', '  !? —  ', '\n'])
def test_silent_filler_never_opens_caption_or_audio_turn(filler):
    async def trial():
        b, emitted, fixed, _ = bridge()
        await b.handle({'serverContent': {'outputTranscription': {'text': filler}, 'turnComplete': True}})
        assert not emitted and not fixed
        await b.handle(audio_content('A blue cup.', turnComplete=True))
        assert [m['text'] for m in emitted if m['type'] == 'say'] == ['A blue cup.']
        assert any(m['type'] == 'audio' and m['pcm16_b64'] for m in emitted)
    asyncio.run(trial())


def test_audio_before_transcript_has_no_placeholder_caption():
    async def trial():
        b, emitted, _, _ = bridge()
        await b.handle(audio_content())
        await b.handle(audio_content())
        assert not emitted  # No placeholder, and no PCM for a late caption to cancel.
        await b.handle({'serverContent': {'outputTranscription': {'text': 'A blue cup.'}, 'turnComplete': True}})
        captions = [m for m in emitted if m['type'] == 'say']
        assert [m['text'] for m in captions] == ['A blue cup.']
        first_audio = next(m for m in emitted if m['type'] == 'audio' and m['pcm16_b64'])
        assert emitted.index(captions[0]) < emitted.index(first_audio)
        assert {m['utterance_id'] for m in emitted if m['type'] == 'audio'} == {captions[0]['utterance_id']}
    asyncio.run(trial())


@pytest.mark.parametrize('direct', [False, True])
def test_background_stop_waits_for_mic_final_but_input_hazard_is_instant(monkeypatch, direct):
    monkeypatch.setenv('LIVE_CONTEXT_ENABLED', '1')
    monkeypatch.setattr(context_agent.LiveContextBuilder, 'start', lambda self: None)
    async def assess(session, evidence):
        return {'context': 'A smoking charger.', 'hazard': 'smoking charger'}
    monkeypatch.setattr(context_agent, 'assess_live_context', assess)
    async def trial():
        b, _, fixed, _ = bridge()
        b.start_context()
        await b.audio('AAA=')
        await b.context_builder.build()
        assert not fixed and not b.safety_stopped
        if direct:
            text = 'Can I touch the hot soldering iron tip?'
            line = b.stop_line(text)
            assert line
            await b.handle({'serverContent': {'inputTranscription': {'text': text}}})
            assert fixed == [line] and b.audio_input_open
        else:
            # Provider completion does not mean the son has finished speaking.
            await b.handle({'serverContent': {'turnComplete': True}})
            assert not fixed
            await b.audio('', final=True)
            assert fixed == [b.stop_line('smoking charger')]
            await b.context_builder.build()
            assert len(fixed) == 1
        await b.close_context()
    asyncio.run(trial())


@pytest.mark.parametrize('question', ['What is on the table?', 'What is that valve?', 'Do you see the sink?'])
def test_visual_questions_pass_scope_but_home_repair_is_refused(question):
    from server.task_scope import SCOPE_LINE, refuse_home
    assert refuse_home(question) is None
    assert refuse_home('Help me fix the sink') == SCOPE_LINE
    assert refuse_home('Remove this faucet.') == SCOPE_LINE
    assert refuse_home('Turn that valve clockwise.') == SCOPE_LINE
    async def trial():
        b, emitted, fixed, wire = bridge()
        assert await b.text(question)
        assert wire[-1]['realtimeInput']['text'] == question
        await b.handle(audio_content('A blue cup.', turnComplete=True))
        assert not fixed
        assert any(m['type'] == 'audio' and m['pcm16_b64'] for m in emitted)
        await b.text('Help me fix the sink')
        assert fixed == [SCOPE_LINE]
    asyncio.run(trial())
