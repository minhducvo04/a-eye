# market

Compatibility checks and price search for RAM (and a small SSD rule set). Fixture offers are the default. Apify and Bright Data are thin clients and were not called live.

## Files

- `market/compat.py` — deterministic `check()`
- `market/search.py` — `search()` and `load_offers()`
- `market/apify.py` — synchronous actor run, dataset items mapped to offers
- `market/brightdata.py` — Web Unlocker / SERP request mapped to offers
- `market/fixtures/ram_offers.json` — 10 invented listings
- `market/test_compat.py`
- `market/test_search.py`
- `market/README.md`
- `RESULT.md`

## Limitations

- Apify endpoint is the documented synchronous dataset call: `POST https://api.apify.com/v2/actors/{actorId}/run-sync-get-dataset-items` (https://docs.apify.com/api/v2/actor-run-sync-get-dataset-items-post). Auth is a Bearer token.
- Actor id is **UNVERIFIED**. The default is `UNVERIFIED~shopping-scraper`. Override with `APIFY_ACTOR_ID`. No store actor was checked against live data.
- Actor input `{"query", "category"}` is **UNVERIFIED**.
- Apify field mapping is **UNVERIFIED**: `title`/`name`, `price`/`price_usd`/`extracted_price`, `url`/`link`, `retailer`/`seller`/`store`, optional `specs`. Rows without a numeric price are dropped.
- Bright Data endpoint is the documented request API: `POST https://api.brightdata.com/request` with `zone`, `url`, `format: raw`, `data_format: parsed_light` (https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website and https://docs.brightdata.com/products/serp-api/introduction). The target URL is a Google search with `brd_json=1`.
- Bright Data field mapping is **UNVERIFIED**. Docs show both `organic[].link`/`title` and `results[].url`/`title`. Documented organic rows do not include a price, so rows without a numeric price are dropped. Specs are taken only from an explicit `specs` object.
- A missing `buffered` flag is treated as not buffered when `ecc` is false. A missing `ecc` flag is `unverified`. A hard rule failure is `no` even if another field is missing.
- CPU specs are not checked. RAM and SSD rules use the owned board only.
- Other part categories stay `unverified` (`category rules not written yet`).
- No live network call was made. Tests use `httpx.MockTransport`.

## Tests

Full suite also passed: `.venv/bin/python -m pytest -q` — 71 passed in 0.14s.

Test: .venv/bin/python -m pytest -q market - PASS (30 passed in 0.12s)
