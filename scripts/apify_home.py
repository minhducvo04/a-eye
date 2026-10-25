"""Scrape Amazon home-repair listings for Dad's parts shelf.

Runs Apify actor 2APbAvDfNDOWXbkWf (apify/e-commerce-scraping-tool) through the
documented synchronous dataset endpoint:

POST https://api.apify.com/v2/actors/{actorId}/run-sync-get-dataset-items
https://docs.apify.com/api/v2/actor-run-sync-get-dataset-items-post

Input per keyword matches the team's earlier runs:
{"keyword": "...", "marketplaces": ["www.amazon.com"], "maxProductResults": 50}

APIFY_TOKEN is read from the environment and never printed. Output JSON lines
hold only public product fields (id, name, category, brand, url, keyword).
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import httpx

ACTOR_ID = '2APbAvDfNDOWXbkWf'
MARKETPLACES = ['www.amazon.com']
MAX_PRODUCT_RESULTS = 50
ENDPOINT = f'https://api.apify.com/v2/actors/{ACTOR_ID}/run-sync-get-dataset-items'
ASIN_RE = re.compile(r'/dp/([A-Z0-9]{10})(?:[/?]|$)', re.I)
FIELDS = ('id', 'name', 'category', 'brand', 'url', 'keyword')

# keyword -> shelf category for sink, hinge, and breaker cards
KEYWORDS = (
    ('sink shutoff valve', 'plumbing'),
    ('angle stop valve 1/4 turn', 'plumbing'),
    ('faucet supply line braided', 'plumbing'),
    ('compression fitting 3/8', 'plumbing'),
    ('faucet cartridge', 'plumbing'),
    ('plumber tape PTFE', 'plumbing'),
    ('basin wrench', 'tools'),
    ('adjustable wrench 8 inch', 'tools'),
    ('bucket 5 gallon', 'tools'),
    ('flashlight headlamp', 'tools'),
    ('cabinet hinge concealed', 'hardware'),
    ('cabinet hinge screws', 'hardware'),
    ('phillips screwdriver #2', 'tools'),
    ('circuit breaker finder', 'electrical'),
    ('outlet tester', 'electrical'),
    ('non contact voltage tester', 'electrical'),
    ('towel microfiber', 'tools'),
    ('pipe thread sealant', 'plumbing'),
    ('faucet aerator', 'plumbing'),
    ('p trap', 'plumbing'),
)


def actor_body(keyword):
    return {
        'keyword': keyword,
        'marketplaces': list(MARKETPLACES),
        'maxProductResults': MAX_PRODUCT_RESULTS,
    }


def request_plan():
    """Public request plan for --dry-run. No token, no personal data."""
    return {
        'actor': ACTOR_ID,
        'method': 'POST',
        'url': ENDPOINT,
        'auth': 'Authorization Bearer from APIFY_TOKEN',
        'docs': 'https://docs.apify.com/api/v2/actor-run-sync-get-dataset-items-post',
        'requests': [{'keyword': keyword, 'body': actor_body(keyword)} for keyword, _ in KEYWORDS],
    }


def _token():
    token = os.environ.get('APIFY_TOKEN') or ''
    if not token:
        raise RuntimeError('APIFY_TOKEN is not set')
    return token


def _headers(token):
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def _rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('items', 'data', 'results'):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    return []


def _text(value):
    if isinstance(value, str):
        return ' '.join(value.split()).strip()
    return ''


def _brand(row):
    for key in ('brand', 'manufacturer', 'brandName'):
        value = row.get(key)
        text = _text(value)
        if text:
            return text
        if isinstance(value, dict):
            for inner in ('name', 'slogan'):
                text = _text(value.get(inner))
                if text:
                    return text
    extra = row.get('additionalProperties')
    if isinstance(extra, dict):
        return _brand({k: extra[k] for k in extra if k != 'additionalProperties'})
    return ''


def _url(row):
    return _text(row.get('url') or row.get('link') or row.get('productUrl'))


def _name(row):
    return _text(row.get('name') or row.get('title'))


def _asin(row, url):
    for key in ('asin', 'ASIN'):
        value = _text(row.get(key)).upper()
        if re.fullmatch(r'[A-Z0-9]{10}', value):
            return value
    extra = row.get('additionalProperties')
    if isinstance(extra, dict):
        value = _text(extra.get('asin') or extra.get('ASIN')).upper()
        if re.fullmatch(r'[A-Z0-9]{10}', value):
            return value
    found = ASIN_RE.search(url)
    return found.group(1).upper() if found else ''


def _id(row, url):
    seed = _asin(row, url) or url
    return hashlib.sha1(seed.encode()).hexdigest()[:20]


def map_item(row, keyword, category):
    if not isinstance(row, dict):
        return None
    name = _name(row)
    url = _url(row)
    if not name or not url:
        return None
    return {
        'id': _id(row, url),
        'name': name,
        'category': category,
        'brand': _brand(row),
        'url': url,
        'keyword': keyword,
    }


def fetch_keyword(keyword, category, token, client):
    response = client.post(ENDPOINT, headers=_headers(token), json=actor_body(keyword))
    response.raise_for_status()
    out = []
    for row in _rows(response.json()):
        item = map_item(row, keyword, category)
        if item is not None:
            out.append(item)
    return out


def scrape(token, client=None):
    own = client is None
    if own:
        client = httpx.Client(timeout=300)
    try:
        items = []
        for keyword, category in KEYWORDS:
            items.extend(fetch_keyword(keyword, category, token, client))
        return items
    finally:
        if own:
            client.close()


def write_jsonl(path, items):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('w', encoding='utf-8') as handle:
        for item in items:
            handle.write(json.dumps({key: item[key] for key in FIELDS}, ensure_ascii=False) + '\n')
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', help='JSON lines path (id, name, category, brand, url, keyword)')
    parser.add_argument('--dry-run', action='store_true', help='print the request plan; no network call')
    opts = parser.parse_args(argv)
    if opts.dry_run:
        print(json.dumps(request_plan(), indent=2))
        return 0
    if not opts.out:
        parser.error('--out is required unless --dry-run')
    items = scrape(_token())
    path = write_jsonl(opts.out, items)
    print(f'{len(items)} products written to {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
