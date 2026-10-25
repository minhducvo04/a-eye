"""No network, macOS speech, credentials, or real media required."""
import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from scripts import live_acceptance as acceptance


class FakeSocket:
    def __init__(self, events=(), clock=None):
        self.events = iter(events)
        self.sent = []
        self.clock = clock

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = dict(next(self.events))
        except StopIteration:
            raise StopAsyncIteration
        if self.clock is not None:
            self.clock[0] = event.pop('t')
        return json.dumps(event)


def say(text, uid='reply', **extra):
    return dict(type='say', text=text, utterance_id=uid, **extra)


def audio(uid='reply', **extra):
    return dict(dict(type='audio', utterance_id=uid, pcm16_b64='AQACAA=='), **extra)


def detail(text):
    return dict(type='turn', detail=text)


def judge(flow, batches):
    """Exercise actual JSON socket decoding/redaction before checking the flow."""
    raw, turns = [], []
    for index, batch in enumerate(batches):
        start = 20 * index
        first = len(raw)
        raw += [dict(event, t=event.get('t', start + 3 + i * .01)) for i, event in enumerate(batch)]
        turns.append(dict(start=start, speech_end=start + 2, final_sent=start + 2.6,
                          end=start + 14, event_start=first, event_end=len(raw)))
    clock = [0]
    call = acceptance.Call(FakeSocket(raw, clock), 'fixture', {}, clock=lambda: clock[0])
    asyncio.run(call.read())
    return acceptance.evaluate(flow, turns, call.events, ['mug', 'cup'])


VALID = {
    'ask': [[say('There is a blue mug on the table.'), audio()]],
    'box': [[dict(type='draw', ops=[dict(kind='box', bbox=[.2, .3, .4, .5])])]],
    'hazard': [[detail('Stopped by code'), say(acceptance.HOT, uid='fixed'), audio(uid='fixed')]],
    'sink': [[detail('Guide: sink 1/7')], [detail('Guide: sink 2/7')],
             [detail('Guide: sink 3/7')], [detail('Guide: unsure'), say(acceptance.RETRY)]],
    'water': [[detail('Guide: sink 1/7')], [say('Okay, the water is on your left.')]],
    'memory': [[say('A blue mug.')], [say('An apple.')], [say('You showed me a blue mug at the start.')],
               [say("No, I didn't see a wrench earlier.")]],
    'parts': [[say('Find the LED and breadboard.')], [say('Use a 220 ohm resistor.')]],
    'private': [[detail('Brain: local / qwen'), say('A blue mug.')]],
}


@pytest.mark.parametrize('flow', acceptance.EXPECTED)
def test_all_flows_accept_observed_success(flow):
    reasons, _ = judge(flow, VALID[flow])
    assert reasons == []


@pytest.mark.parametrize('flow', acceptance.EXPECTED)
def test_all_flows_reject_silence(flow):
    reasons, _ = judge(flow, [[] for _ in VALID[flow]])
    assert reasons


def test_ask_uses_speech_end_not_final_and_requires_answer_audio():
    reasons, latency = judge('ask', [[say('A mug.'), audio(t=4.1)]])
    assert latency == pytest.approx([2.1])
    assert 'No spoken reply within 2 s' in reasons
    assert judge('ask', [[say('A mug.'), audio(uid='unrelated')]])[0]
    assert judge('ask', [[say('A wrench.'), audio()]])[0]
    assert judge('ask', [[say('A mug.'), audio(pcm16_b64='')]])[0]
    assert not judge('ask', [[say('A mug.'), audio(t=4)]])[0]


@pytest.mark.parametrize('event', [
    dict(type='draw', t=6.01, ops=[dict(kind='box', bbox=[.2, .2, .3, .3])]),
    dict(type='draw', ops=[dict(kind='arrow', bbox=[.2, .2, .3, .3])]),
    dict(type='draw', ops=[dict(kind='box', bbox=[.2, .2, 0, .3])]),
    dict(type='draw', ops=[dict(kind='box', bbox=[.8, .8, .3, .3])]),
])
def test_box_rejects_late_or_invalid_draw(event):
    assert judge('box', [[event]])[0]


def test_hazard_allows_only_fixed_voice_after_stop_including_late_audio():
    batch = VALID['hazard'][0]
    assert judge('hazard', [batch + [audio(uid='gemini', t=13)]])[0]
    assert judge('hazard', [batch + [detail('Brain: Google / gemini')]])[0]
    assert judge('hazard', [[say(acceptance.HOT)]])[0]
    assert judge('hazard', [[detail('Stopped by code'), say('Be careful')]])[0]
    # Existing model audio before a stop does not count as post-stop leakage.
    assert not judge('hazard', [[audio(uid='gemini', t=2.5)] + batch])[0]


def test_sink_rejects_skips_and_false_claim_of_shutoff():
    assert judge('sink', [VALID['sink'][1], VALID['sink'][0], *VALID['sink'][2:]])[0]
    assert judge('sink', [*VALID['sink'][:3], [detail('Guide: sink 4/7'), say(acceptance.RETRY)]])[0]
    assert judge('sink', [*VALID['sink'][:3], [say('Water is off, go ahead.')]])[0]


def test_water_cannot_pass_without_guide_or_with_stop():
    assert judge('water', [[], VALID['water'][1]])[0]
    assert judge('water', [VALID['water'][0], [detail('Stopped by code'), say('Okay')]])[0]
    assert judge('water', [VALID['water'][0], [say('…')]])[0]


@pytest.mark.parametrize('recall,wrench', [
    ('You showed an apple.', "No, I didn't see a wrench."),
    ("I can't remember a mug.", "No wrench was shown."),
    ('You showed a mug.', 'Yes, I saw your wrench.'),
    ('You showed a mug.', 'No, I saw your wrench on the table.'),
    ('You showed a mug.', 'I am checking.'),
])
def test_memory_rejects_wrong_object_uncertainty_and_invented_wrench(recall, wrench):
    assert judge('memory', [*VALID['memory'][:2], [say(recall)], [say(wrench)]])[0]


def test_parts_checks_second_turn_not_led_setup():
    assert judge('parts', [[say('Find a 220 ohm resistor.')], [say('Try 10 ohms.')]])[0]
    assert not judge('parts', [[], [say('Two hundred and twenty ohms.')]])[0]


@pytest.mark.parametrize('provider', ['Google / gemini', 'Claude / sonnet', 'OpenAI / gpt', 'unknown'])
def test_private_rejects_nonlocal_brain(provider):
    assert judge('private', [[detail('Brain: ' + provider), say('A mug.')]])[0]


def test_private_requires_grounded_timely_answer_not_availability_filler():
    assert judge('private', [[say('The brain is unavailable. Please try again.')]])[0]
    assert judge('private', [[say('A blue mug.', t=6.1)]])[0]
    assert not judge('private', [[detail('Local camera note'), say('A blue mug.', t=5.9)]])[0]


def test_server_failure_invalidates_otherwise_passing_turn():
    assert judge('ask', [VALID['ask'][0] + [dict(type='error', code='internal')]])[0]
    assert judge('ask', [VALID['ask'][0] + [dict(type='turn', stage='failed')]])[0]


def test_wire_audio_pacing_and_final_match_probe():
    clock = [0.0]
    async def sleep(seconds):
        clock[0] += seconds
    socket = FakeSocket()
    call = acceptance.Call(socket, 'test', {}, clock=lambda: clock[0], sleep=sleep)
    pcm = b'\1\0' * 4000  # .25 seconds, last chunk is .05 not .2 seconds.
    asyncio.run(call.ask('question', pcm, 4))
    messages = socket.sent
    assert [m['seq'] for m in messages] == list(range(1, 7))
    assert all(m['sample_rate'] == 16000 and m['session_id'] == 'test' for m in messages)
    assert b''.join(base64.b64decode(m['pcm16_b64']) for m in messages[:2]) == pcm
    assert all(base64.b64decode(m['pcm16_b64']) == b'\0' * 6400 for m in messages[2:5])
    assert messages[-1]['final'] and not messages[-1]['pcm16_b64']
    assert call.turns[0]['speech_end'] == pytest.approx(.25)
    assert call.turns[0]['final_sent'] == pytest.approx(.85)
    assert call.turns[0]['end'] == pytest.approx(4.25)


@pytest.mark.parametrize('flow', acceptance.EXPECTED)
def test_complete_runner_with_fake_socket(flow, monkeypatch):
    """Run the real flow orchestration, speech sender, reader and evaluator together."""
    real_sleep = asyncio.sleep
    clock = [0.0]

    class RespondingSocket(FakeSocket):
        def __init__(self):
            super().__init__()
            self.queue = asyncio.Queue()
            self.turn = 0
            self.closed = False

        async def send(self, raw):
            await super().send(raw)
            msg = json.loads(raw)
            if msg['type'] == 'audio_in' and msg['final']:
                for event in VALID[flow][self.turn]:
                    self.queue.put_nowait(json.dumps(event))
                self.turn += 1

        async def __anext__(self):
            return await self.queue.get()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

    async def fast_sleep(seconds):
        await real_sleep(0)  # Drain events available at the beginning of the wait.
        clock[0] += seconds
        await real_sleep(0)

    class FastCall(acceptance.Call):
        def __init__(self, *args):
            super().__init__(*args, clock=lambda: clock[0], sleep=fast_sleep)

        async def feed_frames(self):
            # Avoid a simulated periodic timer advancing the speech clock.
            await self.send('frame', seq=1, ts_ms=0, **self.frames['a'])
            await asyncio.Future()

    socket = RespondingSocket()
    monkeypatch.setattr(acceptance, 'connect', lambda *args, **kwargs: socket)
    monkeypatch.setattr(acceptance, 'Call', FastCall)
    args = SimpleNamespace(url=acceptance.DEFAULT_URL, rewind=True, object_a=['mug', 'cup'],
                           warm=0, pre=0, observe=4)
    speech = {text: b'\1\0' * 100 for text, _ in acceptance.plan(flow, 'mug')}
    result = asyncio.run(acceptance.run_flow(flow, args, acceptance.load_frames(), speech, 1))
    assert result['passed'], result['reasons']
    assert socket.closed and socket.turn == len(VALID[flow])
    assert socket.sent[0]['type'] == 'hello'
    assert result['events'] and all('t' in e and 'pcm16_b64' not in e for e in result['events'])


def test_private_and_recall_configuration_match_client():
    private = acceptance.hello('private', private=True, rewind=True)
    assert private['private'] and private['stt'] == private['tts'] == 'server'
    assert 'cloud' not in private and 'rewind' not in private
    assert acceptance.call_url(acceptance.DEFAULT_URL, private=True) == 'ws://127.0.0.1:8000/ws2'
    recall = acceptance.hello('recall', rewind=True)
    assert recall['rewind'] and recall['cloud']['twelvelabs']
    assert 'rewind_mode=live' in acceptance.call_url(acceptance.DEFAULT_URL, rewind=True)


@pytest.mark.parametrize('url', ['ws://example.com/ws2', 'https://localhost/ws2', 'ws://user:pass@localhost/ws2'])
def test_runner_cannot_connect_to_remote_host(url):
    with pytest.raises(acceptance.argparse.ArgumentTypeError):
        acceptance.local_url(url)


def test_media_and_credentials_do_not_enter_timeline():
    clean = acceptance.safe_message(dict(type='audio', pcm16_b64='AQACAA==',
        nested=dict(frame_b64='private image', token='private key'), url='private url', message='private error'))
    assert clean == dict(type='audio', audio_bytes=4, nested={})


def test_cost_is_unknown_without_server_dollars():
    assert acceptance.cost([dict(type='metrics', cloud_ai_calls=5)]) is None
    assert acceptance.cost([dict(type='meter', estimated_usd=.1), dict(type='meter', estimated_usd=.2)]) == .2


def test_reports_and_exit_rule_do_not_hide_missing_audio(tmp_path):
    args = SimpleNamespace(output=tmp_path, repeat=2, rewind=False, frames=None,
                           object_a=['mug'], object_b=['apple'], warm=6, pre=3, observe=12)
    runs = [dict(flow='ask', repeat=1, passed=True, expected=acceptance.EXPECTED['ask'], reasons=[],
                 first_audio_s=[1.2], total_s=10, estimated_usd=None, turns=[], events=[]),
            dict(flow='ask', repeat=2, passed=False, expected=acceptance.EXPECTED['ask'], reasons=['silent'],
                 first_audio_s=[None], total_s=11, estimated_usd=None, turns=[], events=[])]
    assert acceptance.write_report(runs, args) == 0  # One passing repeat meets the requested exit rule.
    report = json.loads(next(tmp_path.glob('*.json')).read_text())
    row = report['summary'][0]
    assert row['passed'] == 1 and row['repeats'] == 2
    assert row['mean_audio_s'] == 1.2 and row['audio_samples'] == 1 and row['total_s'] == 21
    assert 'not measured' in next(tmp_path.glob('*.md')).read_text()
    runs[0]['passed'] = False
    assert acceptance.write_report(runs, args) == 1


def test_setup_failure_writes_all_failed_report_without_connecting(tmp_path, monkeypatch):
    def unavailable(*args):
        raise FileNotFoundError('secret body must not be logged')
    monkeypatch.setattr(acceptance, 'synthesize', unavailable)
    assert asyncio.run(acceptance.main(['--repeat', '1', '--output', str(tmp_path)])) == 1
    report = next(tmp_path.glob('*.json')).read_text()
    assert 'secret body' not in report
    assert len(json.loads(report)['runs']) == 8


def test_generated_frames_are_small_distinct_jpegs():
    frames = acceptance.load_frames()
    assert frames['a']['jpeg_b64'] != frames['b']['jpeg_b64']
    for frame in frames.values():
        assert frame['w'] == 640 and frame['h'] == 480
        assert base64.b64decode(frame['jpeg_b64']).startswith(b'\xff\xd8')


def test_make_acceptance_skips_secret_include(tmp_path):
    # A sentinel include in a scratch copy proves make never opens the secret file.
    # No actual .env file is read or created.
    import subprocess
    content = (acceptance.ROOT / 'Makefile').read_text().replace('-include .env', '-include forbidden-include.mk')
    (tmp_path / 'Makefile').write_text(content)
    (tmp_path / 'forbidden-include.mk').write_text('$(error secret include was evaluated)\n')
    for goals in (['acceptance'], ['acceptance', 'test-py']):
        result = subprocess.run(['make', '-n', *goals, 'PY=python3'], cwd=tmp_path,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert 'scripts/live_acceptance.py' in result.stdout
    (tmp_path / 'forbidden-include.mk').write_text('')
    default = subprocess.run(['make', '-n'], cwd=tmp_path, capture_output=True, text=True)
    assert default.returncode == 0 and 'uv venv' in default.stdout
    assert 'live_acceptance.py' not in default.stdout
