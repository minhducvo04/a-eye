"""Client tool protocol and live turn wiring, with no provider network calls."""
import asyncio
from copy import deepcopy
import json
import sys
from types import SimpleNamespace as NS

import pytest

from server import rewind_tools
from server.agent import Session, run_turn
from server.expert import ExpertDesk, OPUS
from server.llm import LLMClient
from server.test_agent import Vision


class Response:
    def __init__(self, text='', calls=()):
        self.text = text
        self.final = NS(stop_reason='tool_use' if calls else 'end_turn', content=list(calls), usage=None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @property
    def text_stream(self):
        async def stream():
            if self.text:
                yield self.text
        return stream()

    async def get_final_message(self):
        return self.final


def call(name='search_past', id='a'):
    return NS(type='tool_use', name=name, id=id, input={'query': 'PRIVATE QUERY'})


class Client:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return next(self.responses)


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'claude')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-only')
    monkeypatch.delenv('LOCAL_ONLY', raising=False)
    monkeypatch.delenv('ROUTER', raising=False)


@pytest.mark.parametrize('expert', [False, True])
def test_parallel_results_failure_followup_and_cache(expert):
    async def check():
        client = Client(Response('Checking. ', [call(), call('recap_call', 'b')]), Response('Found it.'))
        seen = []
        async def on_tool(name, args):
            seen.append(name)
            if name == 'recap_call':
                raise RuntimeError('PRIVATE QUERY')
            return {'say': 'Found it.'}
        llm = LLMClient(anthropic_client=client)
        if expert:
            result = await llm.expert('stable', 'question', model=OPUS, tools=rewind_tools.TOOLS, on_tool=on_tool)
            assert result['text'] == 'Found it.'
            assert {t['name'] for t in client.calls[0]['tools']} == {'search_past', 'recap_call', 'web_search'}
        else:
            assert ''.join([d async for d in llm.stream('stable', 'question', tools=rewind_tools.TOOLS,
                                                       on_tool=on_tool)]) == 'Checking. Found it.'
        assert seen == ['search_past', 'recap_call']
        first, second = client.calls
        assert first['system'] == second['system'] == [dict(type='text', text='stable', cache_control={'type': 'ephemeral'})]
        assert second['messages'][-2]['role'] == 'assistant'
        results = second['messages'][-1]
        assert results['role'] == 'user'
        assert [r['tool_use_id'] for r in results['content']] == ['a', 'b']
        assert results['content'][1]['is_error'] is True
        assert 'PRIVATE' not in results['content'][1]['content']
    asyncio.run(check())


@pytest.mark.parametrize('expert', [False, True])
def test_two_round_limit(expert):
    async def check():
        client = Client(*(Response(calls=[call(id=str(i))]) for i in range(3)))
        seen = []
        async def on_tool(*args):
            seen.append(args)
            return {'say': 'Found.'}
        llm = LLMClient(anthropic_client=client)
        if expert:
            await llm.expert('s', 'q', model=OPUS, tools=rewind_tools.TOOLS, on_tool=on_tool)
        else:
            _ = [d async for d in llm.stream('s', 'q', tools=rewind_tools.TOOLS, on_tool=on_tool)]
        assert len(seen) == 2 and len(client.calls) == 3
        assert client.calls[-1]['tool_choice'] == {'type': 'none'}
    asyncio.run(check())


@pytest.mark.parametrize('fail', [False, True])
def test_talker_first_line_cards_and_private_logs(monkeypatch, capsys, fail):
    async def check():
        order = []
        async def speak(msg):
            order.append(msg['text'])
            if False:
                yield
        async def tool(name, args, session, **kwargs):
            assert order == [rewind_tools.FIRST_LINE[name]]
            assert kwargs['vision'] is vision
            order.append('tool')
            if fail:
                raise RuntimeError('PRIVATE QUERY')
            return {'say': 'Found it.'}, [{'type': 'rewind_recap', 'steps': []}]
        monkeypatch.setattr(rewind_tools, 'run_tool', tool)
        client = Client(Response(calls=[call()]), Response('{"draw":[]}\nSAY: ' + (
            "I couldn't check the recording just now." if fail else 'Found it.')))
        s = Session('s', camera=False, speak=speak)
        s.rewind = NS(on=True, clips=[])
        vision = Vision()
        messages = await run_turn(s, 'PRIVATE QUERY', vision=vision, llm=LLMClient(anthropic_client=client))
        assert order[0] == rewind_tools.FIRST_LINE['search_past']
        assert any(m['type'] == 'rewind_recap' for m in messages) != fail
        assert client.calls[0]['tools'] == rewind_tools.TOOLS
        assert bool(client.calls[1]['messages'][-1]['content'][0].get('is_error')) == fail
    asyncio.run(check())
    logs = capsys.readouterr().out
    assert 'PRIVATE QUERY' not in logs
    rows = [json.loads(line) for line in logs.splitlines()]
    assert any(r['event'] == 'tool_call' and r['dependency'] == 'search_past' and
               r['ms'] >= 0 and r['reason']['ok'] is (not fail) for r in rows)


def test_off_has_no_tools():
    async def check():
        client = Client(Response('{"draw":[]}\nSAY: Hello.'))
        await run_turn(Session('s', camera=False), 'hi', vision=Vision(), llm=LLMClient(anthropic_client=client))
        assert 'tools' not in client.calls[0]
    asyncio.run(check())


def test_desk_rewind_and_web(monkeypatch):
    async def check():
        sent = []
        async def send(msg):
            sent.append(msg)
        async def tool(*args, **kw):
            return {'say': 'Found it.'}, [{'type': 'rewind_recap', 'steps': []}]
        monkeypatch.setattr(rewind_tools, 'run_tool', tool)
        s = Session('s', camera=False)
        s.rewind = NS(on=True, clips=[])
        client = Client(Response(calls=[call()]), Response('Found it.'))
        ExpertDesk().start(s, 'question', 'system', {'objects': []}, 0,
                           LLMClient(anthropic_client=client), send, 't')
        await s.expert_task
        assert {t['name'] for t in client.calls[0]['tools']} == {'search_past', 'recap_call', 'web_search'}
        assert any(m['type'] == 'rewind_recap' for m in sent)
        assert not any(m.get('text') in rewind_tools.FIRST_LINE.values() for m in sent)
    asyncio.run(check())


@pytest.mark.parametrize('label', ['past', 'expert', 'now', 'unsure', 'missing', 'raises'])
def test_router(monkeypatch, capsys, label):
    monkeypatch.setenv('ROUTER', 'on')
    async def aroute(text, recent):
        assert text == 'PRIVATE QUERY' and recent == ['earlier']
        if label == 'raises':
            raise RuntimeError(text)
        return {'label': label, 'confidence': .9}
    # The real interface: router.route.aroute (an async function).
    monkeypatch.setitem(sys.modules, 'router.route', None if label == 'missing' else NS(aroute=aroute))
    async def check():
        starts, calls = [], []
        async def tool(name, args, session, **kw):
            calls.append(name)
            return {'say': 'Found it.'}, []
        monkeypatch.setattr(rewind_tools, 'run_tool', tool)
        s = Session('s', camera=False, history=['earlier'], expert_start=lambda *args: starts.append(args))
        s.rewind = NS(on=True, clips=[])
        client = Client(Response('{"draw":[]}\nSAY: Normal answer.'))
        messages = await run_turn(s, 'PRIVATE QUERY', vision=Vision(), llm=LLMClient(anthropic_client=client))
        assert bool(starts) == (label == 'expert')
        assert calls == (['search_past'] if label == 'past' else [])
        assert bool(client.calls) == (label not in ('past', 'expert'))
        if label == 'past':
            assert [m['text'] for m in messages if m['type'] == 'say'] == [rewind_tools.FIRST_LINE['search_past'], 'Found it.']
    asyncio.run(check())
    rows = capsys.readouterr().out
    assert 'PRIVATE QUERY' not in rows
    assert rows.count('dependency_error') == int(label in ('missing', 'raises'))


@pytest.mark.parametrize('provider', ['local', 'canned'])
def test_non_claude_ignores_tools(monkeypatch, provider):
    import httpx
    monkeypatch.setenv('LLM_PROVIDER', provider)
    async def check():
        async def on_tool(*args):
            pytest.fail('Non-Claude provider invoked a tool')
        def handler(request):
            assert 'tools' not in json.loads(request.content)
            return httpx.Response(200, text=json.dumps({'message': {'content': 'Hello.'}, 'done': True}) + '\n')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            llm = LLMClient(anthropic_client=Client(), httpx_client=http)
            assert ''.join([d async for d in llm.stream('s', 'Hello.', tools=rewind_tools.TOOLS,
                                                       on_tool=on_tool)]) == 'Hello.'
    asyncio.run(check())


def test_router_off_and_safety_gate(monkeypatch):
    from server import packs
    def forbidden(*args):
        pytest.fail('Router should not run')
    monkeypatch.setitem(sys.modules, 'router.route', NS(aroute=forbidden))
    async def check():
        client = Client(Response('{"draw":[]}\nSAY: Hello.'))
        await run_turn(Session('s', camera=False), 'hello', vision=Vision(), llm=LLMClient(anthropic_client=client))
        monkeypatch.setenv('ROUTER', 'on')
        s = Session('s', pack=packs.get('pc_build'), camera=False)
        messages = await run_turn(s, 'help', vision=Vision(), llm=LLMClient(anthropic_client=Client()))
        assert 'power off' in next(m['text'] for m in messages if m['type'] == 'say').lower()
    asyncio.run(check())


def test_websocket_tool_turn(monkeypatch):
    from fastapi.testclient import TestClient
    from server import ws2, rewind
    from server.test_ws2 import app, send
    from server.test_pipeline import read, finish
    async def warm(app):
        pass
    async def tool(name, args, session, **kwargs):
        result = {'steps': [], 'skipped': [], 'say': 'Nothing was skipped.'}
        return result, [rewind.recap_message(result, kwargs['turn_id'])]
    monkeypatch.setattr(ws2, 'warm_brain', warm)
    monkeypatch.setattr(rewind_tools, 'run_tool', tool)
    monkeypatch.setenv('BRAIN_MODE', 'single')
    monkeypatch.setenv('A_EYE_MOCK', '0')
    monkeypatch.delenv('A_EYE_TOKEN', raising=False)
    application = app()
    fake = Client(Response(calls=[call('recap_call')]), Response('{"draw":[]}\nSAY: Nothing was skipped.'))
    application.state.llm_v2 = LLMClient(anthropic_client=fake)
    with TestClient(application) as client, client.websocket_connect('/ws2') as ws:
        send(ws, 'hello', pack='general', camera=False, rewind=True)
        read(ws)
        send(ws, 'user_text', text='Check my progress', final=True)
        messages = finish(ws)
        assert messages[-1]['stage'] == 'done'
        first = next(i for i, m in enumerate(messages) if m['type'] == 'say')
        card = next(i for i, m in enumerate(messages) if m['type'] == 'rewind_recap')
        assert messages[first]['text'] == rewind_tools.FIRST_LINE['recap_call']
        assert first < card
        assert [m['text'] for m in messages if m['type'] == 'say'][-1] == 'Nothing was skipped.'
        assert len(fake.calls) == 2


def test_router_hook_calls_aroute_and_sends_recaps_to_recap_call(monkeypatch):
    """The hook imported the router package instead of router.route.aroute, so every call fell back silently."""
    import asyncio
    import sys
    import types
    from server import routing
    calls = []

    async def aroute(text, recent):
        calls.append(text)
        return {'label': 'past', 'confidence': 0.9, 'ms': 43}

    module = types.ModuleType('router.route')
    module.aroute = aroute
    monkeypatch.setitem(sys.modules, 'router.route', module)
    session = types.SimpleNamespace(session_id='s', history=[])
    monkeypatch.setenv('ROUTER', 'on')
    assert asyncio.run(routing.route_turn(session, 'where did I put the screw?')) == 'past'
    assert calls == ['where did I put the screw?']
    monkeypatch.setenv('ROUTER', 'off')
    assert asyncio.run(routing.route_turn(session, 'x')) == 'unsure' and len(calls) == 1
    assert routing.past_tool('can you recap what I did so far?') == 'recap_call'
    assert routing.past_tool('when did I plug in the fan?') == 'search_past'
