# Price Tracker

Track prices for items you care about across multiple stores, see trend
graphs, and get emailed when a price drops below a threshold you set.

See [PLAN.md](PLAN.md) for the full design and build-order notes.

## Supported stores

All 7 stores from the spec are implemented, with real reliability
differences validated by actually running each adapter against the live
site (not just written and assumed to work):

| Store | Search | Scrape | Notes |
|---|---|---|---|
| lego.com | ✅ | ✅ | Cloudflare JS challenge; cleared by disabling the automation-controlled flag (see `scrape_utils.new_page`). |
| barnesandnoble.com | ✅ | ✅ | No bot protection encountered. Clean JSON-LD on product pages. |
| woot.com | ⚠️ | ✅ | No searchable catalog at all — see [app/adapters/woot.py](app/adapters/woot.py). "Search" scans today's deals for a keyword match, so it only surfaces something if it happens to be on sale right now (works well for opportunistic Switch 2 restocks, rarely for a specific LEGO set). |
| target.com | ✅ | ✅ | No bot protection, but soft-throttles rapid repeated identical queries (recovers after ~20s idle). Not expected to matter at the real scrape cadence. |
| bestbuy.com | ✅ | ✅ | `/product/*` pages are hard-blocked at the connection level (Akamai). `scrape()` works around this by re-querying search instead of visiting the product page. That search query is derived from the listing's URL slug (a natural-language product name), not the bare SKU — repeating the exact same numeric SKU query every scrape cycle turned out to get flagged and connection-reset too, confirmed by a real deployment failure. See [app/adapters/bestbuy.py](app/adapters/bestbuy.py). |
| walmart.com | ❌ | ❌ | PerimeterX blocks every request tested (search and product) with an interactive "Robot or human?" challenge, even with the same stealth measures that cleared other stores. Implemented and wired up in case a home-server residential IP fares better, but expect it to consistently fail — this was flagged from the start as the store least likely to work with free scraping. |
| amazon.com | ✅ | ✅ | Worked cleanly in initial testing; later requests in the same short test window got soft-throttled ("Sorry! Something went wrong!"), same pattern as Target/Best Buy. Product-page selectors are Amazon's standard long-lived IDs but weren't re-verified live after throttling kicked in — worth an eye the first time it runs for real. |

Everything is built around a `StoreAdapter` interface
([app/adapters/base.py](app/adapters/base.py)); each store's quirks and
what was actually confirmed live are documented in that adapter's own
file docstring — read those before touching selectors.

## Running it

1. Copy the env file and fill in SMTP details:
   ```bash
   cp .env.example .env
   ```

   For Gmail: enable 2-step verification on the account, then create an
   [app password](https://myaccount.google.com/apppasswords) and use that
   as `SMTP_PASS` (not your normal Gmail password).

2. Start it:
   ```bash
   docker compose up --build
   ```

3. Open http://localhost:8000

The `web` service serves the dashboard/API; the `worker` service runs the
background scheduler that re-scrapes every active listing on an interval
(`SCRAPE_INTERVAL_HOURS` in `.env`, default 6h) and sends an email the
first time a listing's price drops at or below the item's threshold.
SQLite data persists in `./data`.

## How tracking works

1. Add an item with a name and (optionally) a price threshold.
2. Search — the app queries every store adapter in parallel and shows
   candidate listings for you to review.
3. Confirm the listings that are actually the product you want; each
   confirmed listing is scraped on its own going forward.

This confirm-before-tracking step exists because automatically matching
one product across stores is unreliable — the app helps you find
candidates but you make the final call so you don't end up tracking the
wrong item.

You're not limited to the listings you add when first creating an item —
the item detail page has its own "Add a listing" search, so you can keep
attaching more stores (or edit the item's name/threshold, or delete it
entirely) at any time.

## Development (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
# in a second terminal, for the scheduler:
python worker.py
```

Note: the codebase uses Python 3.10+ syntax (`str | None`), so this needs
a 3.10+ interpreter locally — if your system Python is older, just run
everything through Docker instead (see above).

## Tests

```bash
docker compose build web
docker run --rm price-tracker-web pytest -v
```

Coverage: pure-function parsing logic (`scrape_utils.py`, and each
adapter's hand-written text/DOM heuristics — the parts most likely to
silently break when a store changes markup, tested against real sample
text captured from the live sites), the item/listing API with a fake
store adapter so no test hits the network, the threshold-notify dedup
logic in `scraping_service.py`, and the retention job.

Deliberately **not** covered: the actual `page.goto(...)` scraping against
live sites — that can only be verified by running against the real site
(which is what this project's development process did by hand; see
PLAN.md for what was validated and when). A live site changing its markup
won't be caught by this suite, only by actually running the app.

## Known limitations

- Scraping is inherently fragile: sites change markup and add bot
  protection. Walmart is expected to essentially never work with free
  scraping (see table above); a listing that fails to scrape shows its
  error on the item detail page rather than a stale price, for Walmart or
  any other store.
- Woot has no searchable catalog — see the table above.
- No auth — this is meant to run on a home network, not be
  internet-exposed. Put it behind your own VPN/reverse-auth if you expose
  it beyond your LAN.
