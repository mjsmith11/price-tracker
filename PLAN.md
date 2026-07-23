# Price Tracker — Implementation Plan

## Decisions locked in
- **Item entry:** Auto-find across stores, *search-assisted*. You type a product query (name / set number / model), the app searches each supported store, shows candidate listings with current price, and you confirm the correct one per store. Confirmed listings are then tracked by their stable URL/product-id.
- **Price source:** Free self-scraping only (no paid APIs). Amazon & Walmart are aggressively anti-bot and will be best-effort — expect occasional gaps and per-store maintenance.
- **Notifications:** Email via free SMTP (e.g. Gmail app password). Sends when a store price falls below the per-item threshold.
- **Stack:** Python — FastAPI + APScheduler, Playwright for scraping, SQLite, lightweight frontend. One `docker compose` stack for the home server.

## Architecture

```
┌─────────────────────────────────────────────────┐
│ docker compose                                    │
│                                                   │
│  ┌────────────┐   ┌──────────────┐   ┌─────────┐ │
│  │  web (API  │   │  scheduler   │   │ SQLite  │ │
│  │  + UI)     │◄──┤ APScheduler  │──►│ volume  │ │
│  │  FastAPI   │   │ scrape jobs  │   │         │ │
│  └────────────┘   └──────┬───────┘   └─────────┘ │
│                          │                        │
│                   ┌──────▼───────┐                │
│                   │ Playwright   │                │
│                   │ (headless    │                │
│                   │  chromium)   │                │
│                   └──────────────┘                │
│                          │ SMTP (email alerts)    │
└──────────────────────────┼────────────────────────┘
                           ▼  your inbox
```

Single Python image, two compose services sharing the code: `web` (FastAPI serving API + UI) and `worker` (APScheduler running scrape/notify jobs). SQLite on a mounted volume keeps it dependency-light; can swap to Postgres later.

## Data model (SQLite)
- **items** — id, name, notes, threshold_price, currency, created_at
- **listings** — id, item_id (FK), store, product_url, store_product_id, title, confirmed (bool), active, last_seen_at
- **price_points** — id, listing_id (FK), price, in_stock, currency, scraped_at
- **notifications** — id, listing_id (FK), price_point_id, threshold, sent_at, channel  (dedup: don't re-alert for the same low-price streak)

## Store adapters (the core abstraction)
A `StoreAdapter` interface each store implements:
```python
class StoreAdapter(Protocol):
    name: str
    def search(self, query: str) -> list[Candidate]: ...      # for auto-find
    def scrape(self, url_or_id: str) -> PriceResult: ...       # for tracking
```
Adapters, roughly easiest → hardest to keep working:
1. **lego.com** — clean structured data (JSON-LD / Next.js data). Easiest.
2. **Barnes & Noble** — JSON-LD, moderate.
3. **Woot** — has a semi-public API-ish JSON; moderate.
4. **Target** — RedSky internal JSON endpoints; moderate but changes.
5. **Best Buy** — JSON-LD + HTML; moderate, some bot checks.
6. **Walmart** — heavy bot protection (PerimeterX). Best-effort, Playwright + stealth.
7. **Amazon** — heaviest bot protection + frequent captchas. Best-effort, most likely to break.

Shared scraping toolkit: Playwright headless chromium, randomized user-agent/headers, polite per-store rate limiting + jitter, retry/backoff, and a `parse_price()` helper. Each adapter prefers structured data (JSON-LD) over CSS selectors for resilience. Adapters degrade gracefully — a failure records an error status, never crashes the run.

## Backend (FastAPI)
- `POST /api/items` — create item (name, threshold)
- `GET /api/search?q=` — run search across all store adapters, return candidates for confirmation
- `POST /api/items/{id}/listings` — confirm a candidate → start tracking
- `DELETE /api/listings/{id}` and `DELETE /api/items/{id}`
- `GET /api/items` / `GET /api/items/{id}` — items + latest prices
- `GET /api/items/{id}/history?store=` — price_points for the trend graph
- `POST /api/items/{id}/refresh` — manual re-scrape

## Scheduler (APScheduler in worker)
- Periodic scrape job per active listing (default every 6h, configurable, staggered/jittered to avoid hammering stores).
- After each new price_point: if `price <= threshold` and not already in an active alert streak → send email + record notification (dedup).
- Cleanup/retention job (optional): prune very old price_points.

## Frontend
Lightweight — server-rendered templates (Jinja) + a bit of JS, or a small React SPA. Pages:
- **Dashboard:** list of tracked items, current best price per item, threshold status, quick add.
- **Add item flow:** enter query → pick store candidates → confirm → set threshold.
- **Item detail:** multi-line price-trend chart (one line per store) using Chart.js, threshold line, per-store current price & stock, remove buttons.

## Notifications (email)
- Config via env: SMTP host/port/user/pass, from/to. Documented Gmail app-password setup.
- Email includes item name, store, new price, threshold, and a link to the listing.
- Dedup so one dip doesn't spam every scrape cycle; re-arm once price goes back above threshold.

## Deployment
- `Dockerfile` (Python + Playwright browsers baked in).
- `docker-compose.yml`: `web` + `worker`, shared volume for SQLite, `.env` for SMTP + settings, restart policy for the home server.
- `.env.example` and a README with setup + the "email sends must be free" Gmail notes.

## Build order (milestones)
1. **Scaffold** — repo layout, FastAPI app, SQLite models, docker compose that boots.
2. **One end-to-end store** — implement lego.com adapter (search + scrape), manual add-by-confirm, store a price_point.
3. **Dashboard + chart** — list items, item detail with trend graph.
4. **Scheduler + email alerts** — periodic scraping, threshold notifications with dedup.
5. **Remaining adapters** — B&N, Woot, Target, Best Buy, then best-effort Walmart & Amazon.
6. **Polish** — retention, error surfacing in UI (per-store "last scrape failed"), README/docs.

## Known risks / honest caveats
- **Amazon & Walmart** will be the flaky ones; treat their data as best-effort and surface scrape failures in the UI rather than pretending prices are current.
- **Auto-find matching** can still surface wrong candidates — the confirmation step is what keeps tracking accurate; there's no reliable fully-blind cross-store match.
- Scrapers break when sites change markup; the JSON-LD-first approach and per-adapter isolation limit the blast radius. Budget for occasional maintenance.
- Legal/ToS: this is personal-use scraping at a polite rate. Keep request volume low and respectful.

## Milestones 1–2: build status (validated against live sites)
lego.com's search page turned out to be Cloudflare-challenge-protected too (not
just Amazon/Walmart as assumed) — plain headless Chromium got served an
interstitial. Fix: launch Chromium with `--disable-blink-features=AutomationControlled`
and patch `navigator.webdriver` via an init script (`app/scrape_utils.py:new_page`).
That's applied to every adapter by default, since it costs nothing when a site
*isn't* checking for it. Validated live: search returns real product tiles
(title, price, set number) and scrape pulls live JSON-LD price data.

Also: `python:3.12-slim`'s current tag resolves to Debian trixie, and
Playwright's `--with-deps` installer doesn't yet have package fallbacks for
it (fails on `ttf-unifont`/`ttf-ubuntu-font-family`). Switched the Dockerfile
base to `mcr.microsoft.com/playwright/python:v1.49.0-jammy`, which ships
matching browsers + OS deps preinstalled — more robust across host
architectures too.

Full flow verified end-to-end via `docker compose up`: create item → search
lego.com → confirm listing → price scraped and stored → chart renders →
below-threshold item correctly attempts an email notification (only failed
locally because `.env` has placeholder SMTP credentials).

## Milestone 5: build status (validated against live sites)
All 6 remaining adapters (Barnes & Noble, Woot, Target, Best Buy, Walmart,
Amazon) are implemented and registered. Reliability turned out to sort
differently than the original "easy/moderate/best-effort" ranking assumed
— see the table in [README.md](README.md) for the current per-store status;
the short version:

- **Reliable, no bot protection encountered:** Barnes & Noble, Target,
  Amazon (initially — see below). All three server-render prices; B&N and
  (mostly) Amazon have clean structured data, Target needed a DOM text
  heuristic since its component library doesn't tag title/price semantically.
- **Reliable but needed a workaround:** Best Buy's `/product/*` pages are
  hard-blocked at the connection level (Akamai resets the connection —
  `net::ERR_HTTP2_PROTOCOL_ERROR`), while its search page isn't. `scrape()`
  routes around this entirely by re-querying search for the listing's SKU
  instead of ever loading the product page.
- **Soft-throttling under repeated requests:** Target and Amazon both
  tolerated occasional requests fine but started failing after several
  rapid identical queries in a short test window, recovering after a short
  idle period. Not expected to bite at the real scrape cadence (hours
  apart, paced between listings) — worth knowing if search/scrape
  suddenly goes quiet during heavy testing.
- **Not really a searchable catalog:** Woot has no search endpoint at all
  (confirmed: `/search` 404s, no search UI). Its "search" scans the
  current all-deals page for a keyword match — genuinely useful for
  opportunistic Switch 2 restocks (Woot does carry it), much less so for
  a specific LEGO set.
- **Hard-blocked, as expected:** Walmart's PerimeterX challenge blocked
  every single request tested — search and product pages alike — with no
  variation. This was flagged from the start as the store most likely to
  fail under a free-scraping-only approach, and testing confirmed it.
  Implemented anyway since a home-server residential IP might fare better
  than this sandbox's IP, but don't expect it to work.

One correction to the original plan: lego.com and Barnes & Noble were
ranked "easiest," Target/Best Buy "moderate," but in practice Best Buy's
product-page block was harder to work around than anything except
Walmart. The store-by-store difficulty is genuinely hard to predict from
outside — what mattered in the end was testing each one live rather than
trusting the a priori ranking.

## Milestone 6: build status
- **Retention job**: `app/retention.py` deletes price points older than
  `PRICE_HISTORY_RETENTION_DAYS` (default 730), run daily by the worker's
  scheduler. Default is deliberately generous — the app's whole point is
  long-term trend history — this is a safety valve, not routine cleanup.
  Verified directly: seeded an 800-day-old and a 5-day-old price point,
  confirmed only the old one got pruned.
- **Dashboard error surfacing**: item-detail already showed per-listing
  `last_error`; the dashboard list only distinguished "has a price" vs.
  "no data yet," which made a *failing* scrape look identical to a
  never-scraped item. Now: if every listing on an item has failed with no
  successful price yet, the card shows "⚠ scrape failing" in red instead
  of the ambiguous "no data yet"; if the current best price came from an
  earlier successful scrape but the most recent attempt failed, it's
  shown with a "⚠ last check failed, price may be stale" hint (hover for
  the actual error). Verified with a screenshot against a real failing
  listing.
