import asyncio

import httpx
from fastapi.testclient import TestClient

from server import privacy
from server.agent import Session, run_turn
from server.test_agent import LLM, Vision


def test_private_expert_answers_locally_without_handoff():
    async def trial():
        token = privacy.PRIVATE.set(True)
        try:
            llm = LLM('SAY: Here is the local answer.')
            def handoff(*args):
                raise AssertionError('Private turn must not enter the expert desk')
            session = Session('proof', camera=False, expert_start=handoff)
            messages = await run_turn(session, 'Explain this difficult problem', vision=Vision(),
                                      llm=llm, route='expert')
            spoken = ' '.join(m['text'] for m in messages if m['type'] == 'say')
            assert llm.calls
            assert 'local' in spoken.lower() and 'Private' in spoken
            assert 'Here is the local answer.' in spoken
        finally:
            privacy.PRIVATE.reset(token)
    asyncio.run(trial())


def test_readonly_count_and_auth(tmp_path, monkeypatch):
    from server import proof_wall
    from server.app import create_app
    (tmp_path / 'crop.JPG').write_bytes(b'fixture')
    (tmp_path / 'note.txt').write_text('fixture')
    (tmp_path / 'link.png').symlink_to(tmp_path / 'crop.JPG')
    monkeypatch.setattr(proof_wall, 'DATA_DIR', tmp_path)
    monkeypatch.setenv('A_EYE_TOKEN', 'fixture-token')
    client = TestClient(create_app(), client=('192.168.1.5', 1234))
    assert client.get('/api/proof').status_code == 401
    assert client.get('/api/proof?token=wrong').status_code == 401
    response = client.get('/api/proof', headers={'Authorization': 'Bearer fixture-token'})
    assert response.json() == dict(pictures_saved=1, cloud_ai_calls=None, bytes_to_cloud=None)
    assert response.headers['cache-control'] == 'no-store'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['crop.JPG', 'link.png', 'note.txt']


def test_safety_proof_and_actual_local_model(monkeypatch):
    from contracts import validate
    from server.llm import LLMClient
    async def trial():
        private = privacy.PRIVATE.set(True)
        try:
            calls = []
            def transport(request):
                calls.append(request.url.host)
                return httpx.Response(200, text='{"message":{"content":"SAY: Fixture answer."},"done":true}\n')
            monkeypatch.setenv('OLLAMA_URL', 'http://127.0.0.1:11434')
            async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
                llm = LLMClient(httpx_client=http)
                messages = await run_turn(Session('s', camera=False), 'Hello', llm=llm, vision=Vision())
                assert calls == ['127.0.0.1']
                assert any(m.get('detail', '').startswith('Brain: local / ') for m in messages)
                calls.clear()
                messages = await run_turn(Session('s', camera=False), 'My power strip is smoking',
                                          llm=llm, vision=Vision())
                assert calls == []
                assert any(m.get('detail') == 'Stopped by code' for m in messages)
                for message in messages:
                    validate('server_message_v2', message)
        finally:
            privacy.PRIVATE.reset(private)
    asyncio.run(trial())


def test_private_and_cloud_turn_counters(monkeypatch):
    from server import cloud_meter
    from server.brain_openai_compat import OpenAICompatBrain
    for key, value in dict(LOCAL_ONLY='0', OLLAMA_URL='http://127.0.0.1:11434',
                           OPENAI_COMPAT_BASE_URL='https://model.example/v1',
                           OPENAI_COMPAT_API_KEY='fixture', OPENAI_COMPAT_TALKER_MODEL='fixture').items():
        monkeypatch.setenv(key, value)

    async def trial():
        def respond(request):
            if request.url.host == '127.0.0.1':
                return httpx.Response(200, text='{"message":{"content":"SAY: Hello."},"done":true}\n')
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"SAY: Hello."}}]}\n\ndata: [DONE]\n\n')
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            for private in (True, False):
                privacy.set_call(private=private)
                meter = cloud_meter.start()
                messages = await run_turn(Session('counter', camera=False), 'Hello',
                                          llm=OpenAICompatBrain(httpx_client=client), vision=Vision())
                assert any(m['type'] == 'say' for m in messages)
                assert meter.calls == (0 if private else 1)
                assert (meter.bytes == 0) if private else (meter.bytes > 0)
    asyncio.run(trial())


def test_call_proof_owner_and_repeated_hello(tmp_path, monkeypatch):
    from server import rewind
    from server.app import create_app
    from server.auth import mint_owner
    monkeypatch.setenv('A_EYE_TOKEN', 'fixture-token')
    monkeypatch.setenv('A_EYE_MOCK', '1')
    monkeypatch.setenv('A_EYE_MEMORY_DIR', str(tmp_path))
    app = create_app()
    headers = {'Authorization': 'Bearer fixture-token', 'X-Aeye-Owner': mint_owner()}
    with TestClient(app, headers=headers) as client:
        with client.websocket_connect('/ws2', headers=headers) as ws:
            hello = dict(v=2, type='hello', session_id='owned', pack='general', camera=False, tts='browser')
            ws.send_json(hello)
            while ws.receive_json().get('type') != 'agent_state':
                pass
            call = rewind.registry(app).calls['owned']
            call.cloud_meter.add(calls=2, size=123)
            expected = dict(cloud_ai_calls=2, bytes_to_cloud=123)
            def counters(response):
                return {k: response.json()[k] for k in expected}
            assert counters(client.get('/api/proof?session_id=owned')) == expected
            other = dict(headers, **{'X-Aeye-Owner': mint_owner()})
            assert counters(client.get('/api/proof?session_id=owned', headers=other)) == dict.fromkeys(expected)
            ws.send_json(dict(hello, private=True))
            while ws.receive_json().get('type') != 'agent_state':
                pass
            assert counters(client.get('/api/proof?session_id=owned')) == expected
