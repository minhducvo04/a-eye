# Shopping helper — ready for lead review

Implemented in the working tree; no commit. `server/ws2.py` is unchanged.

A shopping question now bypasses the general talker/planner. The shopper acknowledges immediately while lookup runs, reads the product from the existing local vision scene (refreshing when it belongs to another frame), ranks offers in code, and speaks one recommendation plus at most two alternatives and one question. Private mode and the Claude switch block lookup before vision/source calls. The existing market sheet shows currency, delivery/pickup, links, and a highlighted recommendation; compatibility stays unverified.

Files: new `server/shopping.py` and `server/test_shopping.py`; small integration changes in `server/agent.py`, `server/llm.py`, `server/test_stream.py`, `client-web/agent.js`; additive schema/types/examples/changelog in `contracts/`; this report and an appended `RESULT.md` entry.

`OfferSource.search(product, location=None)` is asynchronous. `FixtureSource` is explicitly injected through `app.state.offer_source`, never a production fallback. Default `WebSearchSource` uses the existing Anthropic client and its [web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool), capped at two searches. No scraping or checkout. Model rows require a matching provider citation URL and price, contract validation, and HTTP(S) links; missing/invalid results never become guessed offers.

Ranking policy: price plus 3% of the cheapest price per waiting day; unknown delivery gets a 30-day ranking penalty without asserting an arrival date. Explicit urgency chooses fastest first. Only one currency is compared. Compatibility questions take priority for relevant categories; urgency is asked only for a material price/delivery tradeoff. Search has an eight-second timeout; local scene refresh has a two-second timeout.

## Verification

- Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest server/test_shopping.py server/test_agent.py server/test_stream.py server/test_ws2.py contracts/test_contracts.py -q` — PASS (110). Includes typed `/ws2`, synthetic frame, injected offers, final recommendation, and server audio chunks. Final ranking/context-only adjustment: `server/test_shopping.py -q` — PASS (7).
- Test: `make test-py PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` — 636 passed; four device setup errors because the sandbox prohibited binding localhost. Rerun `.../python -m pytest device/test_client.py -q` outside that sandbox — PASS (4). No assertion failures; two existing JWT test-key warnings. Full suite was run before the final acknowledgment/context adjustments, covered by the targeted reruns above.
- Test: `node --test client-web/` — PASS (132). `node --check client-web/agent.js` — PASS.
- Test: `/Users/minhducvo/Projects/kyra/.venv/bin/python /private/tmp/check_shopping_sheet.py` — PASS. Headless Chromium executed the repository's actual market rendering function with synthetic fixture data: store, price, delivery, link, recommendation border, unverified chip. Screenshot: `/private/tmp/shopping-sheet.png`. This is an isolated sheet check, not a full camera/microphone browser rehearsal.

## Limits for the reviewer

No paid/live cloud search, physical-device speech recognition, or real shopping latency was measured. The fixture proves transport and deterministic decisions, not retailer accuracy or natural voice quality. Product identification depends on local vision reading the brand/model; this implementation sends scene text only, no cloud crop. The search prompt abstains for unclear identity; citation checks do not independently prove every model-extracted stock/delivery field. Location is optional at the source interface; the turn does not infer location, so live pickup claims are suppressed without one. Follow-up answers still use the general conversation path unless they contain shopping intent. Prices are before tax, with known shipping; cross-currency comparisons and confirmed compatibility are intentionally unavailable.
