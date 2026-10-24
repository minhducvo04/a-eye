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
    probes = []
    async def outbound():
        probes.append(True)
        return dict(online=False, checked_at_ms=1)
    monkeypatch.setattr(proof_wall, 'outbound_check', outbound)
    client = TestClient(create_app(), client=('192.168.1.5', 1234))
    assert client.get('/api/proof').status_code == 401
    assert client.get('/api/proof?token=wrong').status_code == 401
    assert probes == []
    response = client.get('/api/proof', headers={'Authorization': 'Bearer fixture-token'})
    assert response.json() == dict(pictures_saved=1, online=False, checked_at_ms=1)
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


def test_outbound_check_uses_server_connection_and_expires(monkeypatch):
    from server import proof_wall
    monkeypatch.setattr(proof_wall, '_network', None)
    async def trial():
        class Writer:
            def close(self):
                pass
            async def wait_closed(self):
                pass
        calls = []
        async def online(host, port):
            calls.append((host, port))
            return None, Writer()
        monkeypatch.setattr(asyncio, 'open_connection', online)
        assert (await proof_wall.outbound_check())['online'] is True
        assert (await proof_wall.outbound_check())['online'] is True
        assert len(calls) == 1
        monkeypatch.setattr(proof_wall, '_network', None)
        async def offline(*args):
            raise OSError('offline')
        monkeypatch.setattr(asyncio, 'open_connection', offline)
        assert (await proof_wall.outbound_check())['online'] is False
    asyncio.run(trial())
