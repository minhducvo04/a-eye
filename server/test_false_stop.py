"""Replay synthetic Live packets through the real gates; no provider calls."""
import asyncio
import base64

import pytest

from server.test_live_guide import bridge_for

QUESTION = ('dad', ' The wire on my headphones broke', ' near the plug.', ' How do I fix it?')
REPLY = ("We'll need to cut off the damaged part,", ' strip the wires,',
         ' and solder them to a new plug.')


async def transcript(bridge, field, chunks):
    for chunk in chunks:
        await bridge.handle({'serverContent': {field: {'text': chunk}}})


@pytest.mark.parametrize('tail', [
    '', ' Unplug the headphones before stripping the wire.',
    ' Slide heat shrink tubing over the wire.',
    ' Use the hot soldering iron to join the wires.',
    " Don't touch the hot tip; keep the iron in its stand.",
])
def test_headphone_repair_stream(monkeypatch, tail):
    async def trial():
        b, emitted, fixed, _ = bridge_for(monkeypatch)
        try:
            await transcript(b, 'inputTranscription', QUESTION)
            await transcript(b, 'outputTranscription', (*REPLY, tail))
            await b.handle({'serverContent': {'turnComplete': True}})
            assert not fixed
            assert not b.safety_stopped
            assert any(m['type'] == 'say' and m['text'] == ''.join(REPLY) + tail for m in emitted)
        finally:
            b.ws = None
            await b.close()
    asyncio.run(trial())


@pytest.mark.parametrize('chunks', [
    ('I will touch', ' the hot tip.'),
    ('I will work on', ' live mains.'),
    ('I will rewire this', ' while plugged into the wall.'),
])
@pytest.mark.parametrize('field', ['inputTranscription', 'outputTranscription'])
def test_real_hazards_still_stop(monkeypatch, chunks, field):
    async def trial():
        b, emitted, fixed, _ = bridge_for(monkeypatch)
        try:
            await transcript(b, field, chunks)
            assert b.safety_stopped and b.blocked and len(fixed) == 1
            assert not any(m['type'] == 'audio' for m in emitted)
        finally:
            b.ws = None
            await b.close()
    asyncio.run(trial())


@pytest.mark.parametrize('boundary', ['none', 'interrupted', 'complete'])
def test_voice_reply_after_output_stop(monkeypatch, boundary):
    async def trial():
        b, emitted, fixed, _ = bridge_for(monkeypatch)
        try:
            await transcript(b, 'inputTranscription', QUESTION)
            await transcript(b, 'outputTranscription', ('Touch the hot tip.',))
            assert b.safety_stopped and len(fixed) == 1
            emitted.clear()
            if boundary == 'interrupted':
                await b.handle({'serverContent': {'interrupted': True}})
            await transcript(b, 'outputTranscription', ('Stale provider speech.',))
            if boundary == 'complete':
                await b.handle({'serverContent': {'turnComplete': True}})
            assert b.safety_stopped and not any(m['type'] in ('say', 'audio', 'reply_delta') for m in emitted)
            await transcript(b, 'inputTranscription', ('What colour', ' is the cable?'))
            await b.handle({'serverContent': {
                'outputTranscription': {'text': 'The cable is blue.'},
                'modelTurn': {'parts': [{'inlineData': {
                    'mimeType': 'audio/pcm;rate=24000',
                    'data': base64.b64encode(b'\x00\x00' * 6000).decode()}}]}}})
            await b.handle({'serverContent': {'turnComplete': True}})
            assert not b.safety_stopped and len(fixed) == 1
            assert any(m['type'] == 'audio' for m in emitted)
            assert any(m['type'] == 'say' and m['text'] == 'The cable is blue.' for m in emitted)
        finally:
            b.ws = None
            await b.close()
    asyncio.run(trial())


def test_background_repair_summary(monkeypatch):
    from server import context_agent

    async def trial():
        b, _, fixed, _ = bridge_for(monkeypatch)
        published = []

        async def assess(*args):
            return dict(hazard='', context='Live is explaining wire repair using a hot soldering iron.')

        async def publish(block):
            published.append(block)
            return True

        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        builder = context_agent.LiveContextBuilder(b.session, publish, b.stop, b.stop_line)
        try:
            await transcript(b, 'inputTranscription', QUESTION)
            await transcript(b, 'outputTranscription', REPLY)
            await builder.build()
            assert not fixed and published
        finally:
            b.ws = None
            await b.close()
    asyncio.run(trial())
