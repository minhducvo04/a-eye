"""Account boundaries with synthetic RSA tokens, real routes and temporary storage."""
import io
import time
import zipfile

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from server.app import create_app
from server import memory

ORIGIN = 'https://testserver'


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv('SESSION_SECRET', 'synthetic-session-secret-' * 3)
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'synthetic-client')
    monkeypatch.setenv('A_EYE_MEMORY_DIR', str(tmp_path / 'memory'))
    monkeypatch.setenv('A_EYE_MOCK', '1')
    app = create_app()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    from server import accounts
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update(kid='google-test', alg='RS256', use='sig')
    monkeypatch.setattr(accounts, 'google_keys', accounts.GoogleKeys(fetcher=lambda url: {'keys': [jwk]}))
    return app, key


def login(client, key, sub='alice', **overrides):
    config = client.get('/auth/config').json()
    claims = dict(sub=sub, iss='https://accounts.google.com', aud='synthetic-client',
                  iat=int(time.time()), exp=int(time.time()) + 300, nonce=config['nonce'])
    claims.update(overrides)
    encoded = jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'google-test'})
    return client.post('/auth/google', json={'credential': encoded},
                       headers={'origin': ORIGIN, 'x-aeye-csrf': config['nonce']})


def guest(client):
    nonce = client.get('/auth/config').json()['nonce']
    return client.post('/auth/guest', headers={'origin': ORIGIN, 'x-aeye-csrf': nonce})


@pytest.mark.parametrize('change', [{'iss': 'https://evil.test'}, {'aud': 'other'},
                                  {'exp': 1}, {'sub': ''}, {'nonce': 'wrong'}])
def test_google_claims_and_valid_control(setup, change):
    app, key = setup
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, key, **change).status_code == 401
        response = login(client, key)
        assert response.status_code == 200
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'Max-Age=2592000' in cookie
        first = client.get('/api/me').json()['owner']
        assert login(client, key, email='changed@example.test').status_code == 200
        assert client.get('/api/me').json()['owner'] == first


def test_forged_signature_cookie_and_csrf_refused(setup):
    app, key = setup
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, attacker).status_code == 401
        assert client.post('/auth/guest').status_code == 403
        assert login(client, key).status_code == 200
        assert client.delete('/api/me', headers={'origin': 'https://evil.test'}).status_code == 403
        assert client.post('/api/memory/tag', json={'name': 'bad'},
                           headers={'origin': 'https://evil.test'}).status_code == 403
        client.cookies.clear()
        forged = jwt.encode({'sub': 'alice', 'exp': time.time() + 1000}, 'x' * 32, algorithm='HS256')
        client.cookies.set('aeye_session', forged)
        assert client.get('/api/me').status_code == 401
        assert client.get('/api/memory/settings').status_code == 401


def test_guest_expires_and_deletes_without_return_visit(setup):
    app, _ = setup
    with TestClient(app, base_url=ORIGIN) as client:
        response = guest(client)
        assert response.status_code == 200
        assert 'Max-Age=86400' in response.headers['set-cookie']
        owner = client.get('/api/me').json()['owner']
        store = memory.memories(app).for_owner(owner)
        store.set_tag('guest keys')
        from server import accounts
        db = accounts.database(app)
        db.clock = lambda: time.time() + 86401
        client.portal.call(accounts.reap, app)
        assert not store.dir.exists()
        assert client.get('/api/me').status_code == 401


def test_own_view_export_delete_and_other_user_isolation(setup):
    app, key = setup
    from server.growth import for_owner
    from server.rewind import registry
    from server.family_note import Store
    with TestClient(app, base_url=ORIGIN) as alice, TestClient(app, base_url=ORIGIN) as bob:
        assert login(alice, key).status_code == 200
        assert login(bob, key, sub='bob').status_code == 200
        owner = alice.get('/api/me').json()['owner']
        other = bob.get('/api/me').json()['owner']
        mine = memory.memories(app).for_owner(owner)
        theirs = memory.memories(app).for_owner(other)
        mine.set_tag('alice keys')
        theirs.set_tag('bob keys')
        mine._write_json('reference.json', {'synthetic': True})
        for_owner(app, owner).start('alarm')
        registry(app).open('alice-call', owner=owner)
        registry(app).open('bob-call', owner=other)
        family = app.state.family_notes = Store()
        family.contacts[owner + ':alice-call'] = {'contact': {'name': 'Alice contact'}}
        family.links['secret'] = {'owner': owner + ':alice-call'}
        assert 'alice keys' not in bob.get('/api/me', params={'owner': owner}).text
        assert 'alice keys' in alice.get('/api/me').text
        exported = bob.get('/api/me/export', params={'owner': owner})
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert 'manifest.json' in archive.namelist()
            personal = archive.read('my-data.json').decode()
            assert 'bob keys' in personal and 'alice keys' not in personal
        app.state.limits.turns[('owner', owner)] = __import__('collections').deque([time.monotonic()] * 40)
        assert alice.get('/api/me/export').status_code == 200
        old_cookie = alice.cookies.get('aeye_session')
        response = alice.delete('/api/me', headers={'origin': ORIGIN})
        assert response.status_code == 200
        assert not mine.dir.exists() and theirs.dir.exists()
        assert owner not in app.state.growth_logs
        assert 'alice-call' not in registry(app).calls and 'bob-call' in registry(app).calls
        assert not family.links and owner + ':alice-call' not in family.contacts
        alice.cookies.set('aeye_session', old_cookie)
        assert alice.get('/api/me').status_code == 401
        assert bob.get('/api/me').status_code == 200


def test_guest_small_quota_and_data_stays_available(setup):
    app, _ = setup
    with TestClient(app, base_url=ORIGIN) as client:
        assert guest(client).status_code == 200
        codes = [client.post('/api/memory/tag', json={'name': 'keys'},
                             headers={'origin': ORIGIN}).status_code for _ in range(12)]
        assert 200 in codes and 429 in codes
        assert client.get('/api/me').status_code == 200
        assert client.get('/api/me/export').status_code == 200
        assert client.delete('/api/me', headers={'origin': ORIGIN}).status_code == 200


def test_delete_stops_live_socket_and_revokes_inflight_writers(setup):
    from starlette.websockets import WebSocketDisconnect
    app, key = setup
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, key).status_code == 200
        owner = client.get('/api/me').json()['owner']
        store = memory.memories(app).for_owner(owner)
        with client.websocket_connect('wss://testserver/ws', headers={'origin': ORIGIN}) as ws:
            assert client.delete('/api/me', headers={'origin': ORIGIN}).status_code == 200
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        with pytest.raises(PermissionError):
            store.append({'note': 'late write'})
        assert not store.dir.exists()


def test_cloud_delete_failure_keeps_only_retry_manifest_then_cleans(setup):
    from server import accounts
    app, key = setup
    class Cloud:
        fail = True
        async def delete_video(self, index_id, video_id, force=False):
            assert force
            if self.fail:
                raise RuntimeError('synthetic outage')
    cloud = app.state.rewind_client = Cloud()
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, key).status_code == 200
        owner = client.get('/api/me').json()['owner']
        store = memory.memories(app).for_owner(owner)
        store.set_tag('secret keys')
        store.add_video('index', 'video')
        response = client.delete('/api/me', headers={'origin': ORIGIN})
        assert response.status_code == 202 and response.json()['cloud_pending'] == 1
        assert {p.name for p in store.dir.iterdir()} == {'owner.json', 'videos.json'}
        assert login(client, key).status_code == 409
        cloud.fail = False
        client.portal.call(accounts.reap, app)
        assert not store.dir.exists()
        assert login(client, key).status_code == 200


def test_guest_quota_survives_database_reopen_and_expiry_on_restart(setup):
    from server import accounts
    app, _ = setup
    with TestClient(app, base_url=ORIGIN) as client:
        assert guest(client).status_code == 200
        owner = client.get('/api/me').json()['owner']
        db = accounts.database(app)
        for _ in range(100):
            assert db.guest_turn(owner)
        reopened = accounts.Database(db.path)
        assert not reopened.guest_turn(owner)
        store = memory.memories(app).for_owner(owner)
        store.set_tag('old guest')
        reopened.clock = lambda: time.time() + 86401
        app.state.accounts = reopened
        client.portal.call(accounts.reap, app)
        assert not store.dir.exists()


def test_export_filters_actual_call_metadata_and_private_calls(setup):
    import json
    from types import SimpleNamespace
    from server.rewind import registry
    app, key = setup
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, key).status_code == 200
        owner = client.get('/api/me').json()['owner']
        for name, who, private in [('mine', owner, False), ('private', owner, True), ('other', 'google:other', False)]:
            call = registry(app).open(name, owner=who)
            call.session = SimpleNamespace(private=private)
        archive = zipfile.ZipFile(io.BytesIO(client.get('/api/me/export').content))
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['counts']['call'] == 1
        assert manifest['excluded_private_calls'] == 1
        assert b'google:other' not in archive.read('my-data.json')


def test_signin_keys_and_data_remain_free_after_budget_limit(setup, monkeypatch):
    import httpx
    from server import cloud_meter
    app, key = setup
    monkeypatch.setenv('DAILY_CLOUD_CAP_USD', '0')
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as network:
        assert network.get('https://www.googleapis.com/oauth2/v3/certs').status_code == 200
        with pytest.raises(cloud_meter.CloudCapReached):
            network.get('https://www.googleapis.com/some-other-service')
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, key).status_code == 200
        assert client.get('/api/me').status_code == 200
        assert client.get('/api/me/export').status_code == 200
        assert client.delete('/api/me', headers={'origin': ORIGIN}).status_code == 200


def test_local_only_keeps_guest_but_refuses_google(setup, monkeypatch):
    app, key = setup
    monkeypatch.setenv('LOCAL_ONLY', '1')
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/auth/config').json()['google_client_id'] == ''
        assert login(client, key).status_code == 503
        assert guest(client).status_code == 200
