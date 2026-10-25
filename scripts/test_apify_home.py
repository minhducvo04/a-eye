"""Fake-transport parse of Apify home listings. No live scrape, token never printed."""
import json

import httpx
import pytest

from scripts import apify_home

TOKEN = 'test-token-not-real'


def _payload(keyword):
    return [
        {
            'name': f'Demo {keyword} kit',
            'url': 'https://www.amazon.com/dp/B0TESTHOME1',
            'brand': {'name': 'DemoBrand'},
            'asin': 'B0TESTHOME1',
        },
        {
            'title': f'{keyword} spare',
            'link': 'https://www.amazon.com/dp/B0TESTHOME2',
            'manufacturer': 'SpareCo',
        },
        {'name': 'missing url only'},
    ]


def test_fake_transport_parses_and_hides_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('APIFY_TOKEN', TOKEN)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content.decode())
        return httpx.Response(201, json=_payload(body['keyword']))

    out = tmp_path / 'home_products.jsonl'
    client = httpx.Client(transport=httpx.MockTransport(handler))
    items = apify_home.scrape(TOKEN, client=client)
    apify_home.write_jsonl(out, items)
    printed = capsys.readouterr()
    text = printed.out + printed.err + out.read_text()

    assert len(apify_home.KEYWORDS) == 20
    assert len(seen) == 20
    first = seen[0]
    body = json.loads(first.content.decode())
    assert str(first.url) == apify_home.ENDPOINT
    assert TOKEN not in str(first.url)
    assert first.headers['authorization'] == f'Bearer {TOKEN}'
    assert body == {
        'keyword': 'sink shutoff valve',
        'marketplaces': ['www.amazon.com'],
        'maxProductResults': 50,
    }
    assert TOKEN not in text
    assert all(set(row) == set(apify_home.FIELDS) for row in items)
    assert items[0]['name'] == 'Demo sink shutoff valve kit'
    assert items[0]['brand'] == 'DemoBrand'
    assert items[0]['category'] == 'plumbing'
    assert items[0]['url'] == 'https://www.amazon.com/dp/B0TESTHOME1'
    assert items[0]['keyword'] == 'sink shutoff valve'
    assert items[0]['id'] == apify_home._id({'asin': 'B0TESTHOME1'}, items[0]['url'])
    hinge = next(row for row in items if row['keyword'] == 'cabinet hinge concealed')
    assert hinge['category'] == 'hardware'
    breaker = next(row for row in items if row['keyword'] == 'circuit breaker finder')
    assert breaker['category'] == 'electrical'
    assert all('missing url' not in row['name'] for row in items)
    assert len(items) == 40
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert lines[0]['id'] == items[0]['id']
    assert TOKEN not in json.dumps(lines)


def test_dry_run_prints_plan_without_network(monkeypatch, capsys):
    monkeypatch.setenv('APIFY_TOKEN', TOKEN)
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(httpx, 'Client', lambda **kw: httpx.Client(transport=httpx.MockTransport(handler), **kw))
    assert apify_home.main(['--dry-run']) == 0
    output = capsys.readouterr().out
    plan = json.loads(output)
    assert called == []
    assert TOKEN not in output
    assert plan['actor'] == '2APbAvDfNDOWXbkWf'
    assert plan['url'] == apify_home.ENDPOINT
    assert len(plan['requests']) == 20
    assert plan['requests'][0]['body']['keyword'] == 'sink shutoff valve'
    assert plan['requests'][-1]['body']['keyword'] == 'p trap'
    assert 'Bearer from APIFY_TOKEN' in plan['auth']


def test_missing_token_refuses(monkeypatch):
    monkeypatch.delenv('APIFY_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='APIFY_TOKEN is not set'):
        apify_home.scrape(apify_home._token(), client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
