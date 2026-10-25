"""Synthetic two-call rehearsal through the actual /ws2 handler; scratch data only.

Run: python -m scripts.context_agent_rehearsal
No cloud, microphone, camera, or personal records are used.
"""
from datetime import datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from server.agent import Session
from server.context_agent import ContextAgent
from server.memory import Memories
from server.test_ws2 import app, send, receive
from server.test_agent import LLM


def rehearse(base, monkeypatch):
    monkeypatch.setenv('LOCAL_ONLY', '1')
    monkeypatch.setenv('STORE', 'local')
    monkeypatch.setenv('A_EYE_MEMORY_DIR', str(base))
    monkeypatch.setenv('CLOUD_BUDGET_PATH', str(base / 'budget.sqlite3'))
    monkeypatch.setenv('BOX_URL', 'http://127.0.0.1:9')
    monkeypatch.setenv('A_EYE_MEMORY_KEY', Fernet.generate_key().decode())
    application = app()
    class RehearsalTalker(LLM):
        async def stream(self, system, user, **kwargs):
            async for piece in super().stream(system, user):
                yield piece
    application.state.llm_v2 = RehearsalTalker()
    application.state.memories = Memories(base=base)
    store = application.state.memories.for_owner('local')
    store.save_settings(dict(consent=dict(person=True, caregiver=True), remembering=True))
    # Seed Friday before the most recent completed Saturday.
    today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    saturday = today - timedelta(days=(today.weekday() - 5) % 7 or 7)
    friday = saturday - timedelta(days=1)
    agent = ContextAgent(Session('seed'), store, store)
    plan = agent.ingest("I'm going to SF Saturday", now=friday.timestamp())
    assert plan
    with TestClient(application, base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        with client.websocket_connect('/ws2') as ws:
            send(ws, 'hello', pack='general', camera=False, private=True)
            assert receive(ws)['state'] == 'listening'
            opener = receive(ws)
            assert opener['type'] == 'say' and opener['text'] == 'How was the trip to SF?'
            send(ws, 'user_text', text="don't bring that up", final=True)
            while True:
                response = receive(ws)
                if response['type'] == 'say':
                    assert response['text'] == 'Okay, I deleted that follow-up.'
                    break
        deleted = not any(r.get('source') == 'plan' for r in store.records())
        # A distinct due plan verifies once-only across independent call objects.
        agent.ingest("I'm going to SF Saturday", now=friday.timestamp())
        with client.websocket_connect('/ws2') as ws:
            send(ws, 'hello', pack='general', camera=False, private=True)
            assert receive(ws)['state'] == 'listening'
            assert receive(ws)['text'] == opener['text']
        with client.websocket_connect('/ws2') as ws:
            send(ws, 'hello', pack='general', camera=False, private=True)
            assert receive(ws)['state'] == 'listening'
            send(ws, 'user_text', text='hello there', final=True)
            seen = []
            while True:
                msg = ws.receive_json()
                seen.append(msg)
                if msg['type'] == 'turn' and msg['stage'] in ('done', 'failed'):
                    assert msg['stage'] == 'done', 'rehearsal turn must complete'
                    break
            repeated = any(m.get('text') == opener['text'] for m in seen)
    assert deleted and not repeated
    return dict(result='PASS', opener=opener['text'], repeated=repeated, deleted=deleted,
                boundary='real ASGI WebSocket handler, synthetic talker, encrypted temporary store')


if __name__ == '__main__':
    with TemporaryDirectory(prefix='aeye-context-') as base, MonkeyPatch.context() as patch:
        print(json.dumps(rehearse(Path(base), patch)))
