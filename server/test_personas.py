import json

import pytest
from fastapi.testclient import TestClient

from contracts import validate
from server import personas
from server.agent import Session
from server.app import create_app
from server.test_agent import LLM, Vision, run


def test_registry_and_classic_prompt():
    rows = personas.list_personas()
    assert {row['id'] for row in rows} >= {'strict-dad', 'funny-dad', 'chill-dad'}
    for row in rows:
        llm = LLM()
        run(Session('fixture', persona=row), llm, 'help', Vision())
        assert personas.style_block(row) in llm.calls[0][0]
        assert 'STYLE ONLY' in personas.style_block(row)
    assert personas.get() == personas.get('chill-dad')
    with pytest.raises(ValueError):
        personas.get('../../unknown')


def test_drop_in_registry_and_invalid_fields(tmp_path):
    row = dict(personas.get(), id='new-dad', display_name='New dad')
    path = tmp_path / 'new-dad.json'
    path.write_text(json.dumps(row))
    assert personas.list_personas(tmp_path) == [row]
    row['safety'] = 'off'
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        personas.list_personas(tmp_path)


def test_api_and_optional_hello(monkeypatch):
    monkeypatch.delenv('ENABLE_EXTRA_MODES', raising=False)
    monkeypatch.delenv('SHOPPING', raising=False)
    with TestClient(create_app(llm=LLM(), vision=Vision())) as client:
        assert len(client.get('/api/personas').json()['personas']) >= 3
        assert client.get('/api/features').json() == {'extra_modes': False, 'shopping': False}
        assert client.post('/api/market', json={'v': 1, 'category': 'ram', 'owned_parts': []}).status_code == 403
        monkeypatch.setenv('ENABLE_EXTRA_MODES', '1')
        monkeypatch.setenv('SHOPPING', '1')
        assert client.get('/api/features').json() == {'extra_modes': True, 'shopping': True}
    hello = dict(v=2, type='hello', session_id='fixture', pack='home')
    validate('client_message_v2', hello)
    validate('client_message_v2', dict(hello, persona='funny-dad'))


def test_hello_selects_persona_and_tts_and_rejects_unknown():
    from server.test_ws2 import app, send, receive
    from voice.adapter import VoiceAdapter
    class Voice(VoiceAdapter):
        async def say(self, utterance_id, text):
            yield b'\x00\x00'
    voice = Voice()
    application = app(voice=voice)
    with TestClient(application) as client, client.websocket_connect('/ws2') as ws:
        send(ws, 'hello', pack='general', tts='server', camera=False, persona='funny-dad')
        assert receive(ws)['state'] == 'listening'
        assert voice.voice == personas.get('funny-dad')['tts_voice']
        send(ws, 'hello', pack='general', persona='unknown-dad')
        assert receive(ws)['code'] == 'bad_message'
        send(ws, 'user_text', text='help', final=True)
        for _ in range(10):
            if receive(ws)['type'] == 'say':
                break
        assert personas.style_block(personas.get('funny-dad')) in application.state.llm_v2.calls[0][0]


def test_disabled_shopping_ignores_model_category(monkeypatch):
    monkeypatch.delenv('SHOPPING', raising=False)
    def unexpected(*args):
        raise AssertionError('Shopping must not run')
    monkeypatch.setattr('server.agent.search', unexpected)
    llm = LLM(json.dumps(dict(agent='helper', say='Here it is.', draw=[], market_category='ram')))
    messages = run(llm=llm)
    assert not any(m['type'] == 'market_results' for m in messages)
