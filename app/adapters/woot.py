"""
woot.com adapter.

IMPORTANT LIMITATION: Woot has no searchable catalog. It's a flash-deal
site with a small, constantly-rotating set of items (roughly one deal per
category per day) — there is no `/search` endpoint (confirmed: it 404s),
and the homepage has no search box. search() works by scanning the current
"All Deals" page (https://www.woot.com/alldeals) and keyword-matching
titles, so it will only surface a result if something matching the query
happens to be on sale *right now*. That's a real fit for opportunistic
items like a Nintendo Switch 2 restock (which does show up on Woot), much
less so for a specific LEGO set, which may simply never appear.

Once a listing is confirmed, scrape() itself is reliable: each offer page
embeds a small `var offerItems = [...]` JSON blob (Woot's own react-app
state, not schema.org) with exact sale price and an
`offerAvailableQuantity` that goes to 0 when a deal sells out.
"""

import json
import logging
import re

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import new_page, parse_price, with_retries

logger = logging.getLogger("price_tracker.adapters.woot")

ALL_DEALS_URL = "https://www.woot.com/alldeals"

# tile price text renders as separate text nodes, e.g. "$\n449\n00\n(NEW) Nintendo Switch 2"
TILE_PRICE_RE = re.compile(r"\$\s*([\d,]+)(?:\s*\n\s*(\d{2}))?")
OFFER_ITEMS_RE = re.compile(r"var offerItems = (\[.*?\]);", re.DOTALL)
AVAILABLE_QTY_RE = re.compile(r"var offerAvailableQuantity = (\d+);")


class WootAdapter:
    name = "woot"

    def search(self, query: str) -> list[Candidate]:
        try:
            return with_retries(lambda: self._search(query))
        except Exception as exc:  # noqa: BLE001
            logger.warning("woot search failed for %r: %s", query, exc)
            return []

    def _search(self, query: str) -> list[Candidate]:
        query_words = {w.lower() for w in query.split() if len(w) > 2}
        candidates: list[Candidate] = []

        with new_page() as page:
            page.goto(ALL_DEALS_URL, timeout=20000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector('a[data-test-ui="offerItem"]', timeout=15000)
            except Exception:
                logger.warning("no deal tiles appeared on woot all-deals page")
                return []

            tiles = page.query_selector_all('a[data-test-ui="offerItem"]')
            seen_urls = set()
            for tile in tiles:
                title_el = tile.query_selector('[data-test-ui="offerItemTitle"]')
                href = tile.get_attribute("href")
                if not title_el or not href:
                    continue
                title = title_el.inner_text().strip()
                if not title:
                    continue

                title_words = {w.lower().strip(".,()") for w in title.split()}
                if not (query_words & title_words) and query.lower() not in title.lower():
                    continue

                product_url = href.split("?")[0]
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)

                price = self._price_from_tile(tile.inner_text())
                candidates.append(
                    Candidate(
                        store=self.name,
                        product_url=product_url,
                        store_product_id=product_url.rstrip("/").split("/")[-1],
                        title=title,
                        price=price,
                        currency="USD",
                    )
                )
        return candidates[:15]

    @staticmethod
    def _price_from_tile(text: str) -> float | None:
        match = TILE_PRICE_RE.search(text)
        if not match:
            return None
        dollars = match.group(1).replace(",", "")
        cents = match.group(2) or "00"
        return parse_price(f"{dollars}.{cents}")

    def scrape(self, product_url: str) -> PriceResult:
        try:
            return with_retries(lambda: self._scrape(product_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("woot scrape failed for %s: %s", product_url, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape(self, product_url: str) -> PriceResult:
        with new_page() as page:
            page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            html = page.content()
            title = page.title()

        match = OFFER_ITEMS_RE.search(html)
        if not match:
            return PriceResult(
                price=None, currency="USD", in_stock=False,
                error="Could not find offer data on page (deal may have expired)",
            )

        try:
            items = json.loads(match.group(1))
        except json.JSONDecodeError:
            return PriceResult(price=None, currency="USD", in_stock=False, error="Malformed offer JSON")

        if not items:
            return PriceResult(price=None, currency="USD", in_stock=False, error="No offer items on page")

        price = parse_price(items[0].get("SalePrice"))

        qty_match = AVAILABLE_QTY_RE.search(html)
        in_stock = int(qty_match.group(1)) > 0 if qty_match else True

        return PriceResult(price=price, currency="USD", in_stock=in_stock, title=title)
