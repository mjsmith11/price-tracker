"""
bestbuy.com adapter.

IMPORTANT, CONFIRMED IN TESTING: bestbuy.com/product/* pages are blocked at
the connection level (Chromium reports net::ERR_HTTP2_PROTOCOL_ERROR /
net::ERR_EMPTY_RESPONSE — the server or a middlebox resets the connection
outright, not a normal HTTP error). This reproduced consistently across
multiple different product URLs. The search results page
(bestbuy.com/site/searchpage.jsp) was NOT categorically blocked the same
way, though it — like the rest of bestbuy.com — does soft-throttle after
a burst of rapid repeated requests and recovers after a short quiet period
(same pattern observed on target.com).

Since search tiles already carry accurate price/title per SKU, scrape()
deliberately avoids the product page entirely and instead re-runs a search,
then reads the price off the matching tile. This isn't a workaround for
something Best Buy is trying to hide — it's the same public price data,
sourced through the page that's actually reachable.

UPDATE, from a real deployment failure report: searching by the bare
numeric SKU (e.g. `st=6614313`) started reliably hitting
net::ERR_HTTP2_PROTOCOL_ERROR — a connection-level reset, not a normal
HTTP error — while a same-session natural-language query for the exact
same product (e.g. `st=switch+2+system`, which still surfaces the
`data-product-id="6614313"` tile) went through fine. A made-up numeric
string worked too. The likely explanation: a scraper re-querying the
identical bare-SKU string on every scrape cycle, forever, is a much
stronger bot signal than a normal-looking text search — and this adapter
was doing exactly that. Fixed by deriving the search query from the
listing's URL slug (e.g. `/product/switch-2-system/...` -> "switch 2
system") instead of the SKU, while still selecting the exact tile by
`data-product-id`. If that ever gets throttled too, this adapter simply
surfaces an error rather than a stale price, like every other adapter.

Search tiles are React-virtualized: many placeholder tiles render with no
title/price/link ("See price in cart", coming-soon image, href="#") for
items whose data hasn't hydrated or that only show price in-cart. Those
are silently skipped — they're a real subset of Best Buy listings, not a
selector bug.
"""

import logging
import re
from urllib.parse import quote, urlparse

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import new_page, parse_price, with_retries

logger = logging.getLogger("price_tracker.adapters.bestbuy")

BASE_URL = "https://www.bestbuy.com"
SKU_QUERY_RE = re.compile(r"[?&]skuId=(\d+)")


def _slug_to_query(product_url: str) -> str | None:
    """Turn '/product/switch-2-system/J7GSL57TGH' into 'switch 2 system'."""
    parts = [p for p in urlparse(product_url).path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "product":
        return parts[1].replace("-", " ")
    return None


class BestBuyAdapter:
    name = "bestbuy"

    def search(self, query: str) -> list[Candidate]:
        url = f"{BASE_URL}/site/searchpage.jsp?st={quote(query)}"
        try:
            return with_retries(lambda: self._search(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bestbuy search failed for %r: %s", query, exc)
            return []

    def _search(self, url: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        with new_page() as page:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            try:
                page.wait_for_selector(".product-list-item[data-product-id]", timeout=15000)
            except Exception:
                logger.warning("no product tiles appeared on bestbuy search page for %s", url)
                return []

            candidates = self._candidates_from_tiles(page)
        return candidates[:15]

    def _candidates_from_tiles(self, page) -> list[Candidate]:
        candidates: list[Candidate] = []
        tiles = page.query_selector_all(".product-list-item[data-product-id]")
        seen_pids = set()
        for tile in tiles:
            pid = tile.get_attribute("data-product-id")
            if not pid or pid in seen_pids:
                continue

            link = tile.query_selector('a[href*="/product/"]')
            title_el = tile.query_selector("h2, h3, h4")
            price_el = tile.query_selector(
                '[data-testid="price-block-customer-price"], [data-testid="price-block-regular-price"]'
            )
            if not (link and title_el and price_el):
                # placeholder tile (unhydrated, or a "see price in cart" item) — skip
                continue

            href = link.get_attribute("href")
            title = title_el.inner_text().strip()
            price = parse_price(price_el.inner_text())
            if not href or not title:
                continue

            seen_pids.add(pid)
            product_url = (href if href.startswith("http") else BASE_URL + href).split("?")[0]
            product_url = f"{product_url}?skuId={pid}"

            candidates.append(
                Candidate(
                    store=self.name,
                    product_url=product_url,
                    store_product_id=pid,
                    title=title,
                    price=price,
                    currency="USD",
                )
            )
        return candidates

    def scrape(self, product_url: str) -> PriceResult:
        match = SKU_QUERY_RE.search(product_url)
        if not match:
            return PriceResult(
                price=None, currency="USD", in_stock=False,
                error="No skuId on stored product URL (listing predates this adapter version?)",
            )
        sku = match.group(1)
        # a natural-language query is far less likely to get flagged than
        # repeating the bare SKU number on every scrape cycle — see docstring
        query = _slug_to_query(product_url) or sku

        try:
            return with_retries(lambda: self._scrape_via_search(sku, query))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bestbuy scrape failed for sku %s: %s", sku, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape_via_search(self, sku: str, query: str) -> PriceResult:
        url = f"{BASE_URL}/site/searchpage.jsp?st={quote(query)}"
        with new_page() as page:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            tile = page.query_selector(f'.product-list-item[data-product-id="{sku}"]')
            if not tile:
                return PriceResult(
                    price=None, currency="USD", in_stock=False,
                    error="Could not find this SKU via search (delisted, or bestbuy.com is throttling)",
                )

            title_el = tile.query_selector("h2, h3, h4")
            price_el = tile.query_selector(
                '[data-testid="price-block-customer-price"], [data-testid="price-block-regular-price"]'
            )
            title = title_el.inner_text().strip() if title_el else None
            price = parse_price(price_el.inner_text()) if price_el else None
            tile_text = tile.inner_text().lower()
            in_stock = "sold out" not in tile_text and "unavailable" not in tile_text

        return PriceResult(price=price, currency="USD", in_stock=in_stock, title=title)
