"""
amazon.com adapter — expect intermittent failures; harden further once
running against a real home-server IP over time.

Search worked cleanly in testing (real tiles, real prices) on the first
request, but a handful of repeated test queries in a short window got a
generic "Sorry! Something went wrong!" page — the same soft-throttle
pattern seen on target.com and bestbuy.com, not a hard per-request block.
Product pages weren't re-verified live after that throttling kicked in
mid-session; their selectors below (#productTitle, #corePrice_feature_div)
are Amazon's long-standing, widely-documented IDs, but treat them as
slightly less battle-tested here than the other adapters until they've
run for real.

Search tiles: `[data-component-type="s-search-result"]` with a `data-asin`
attribute — the ASIN is Amazon's stable product ID, so product_url is
built directly as amazon.com/dp/{asin} rather than parsed from the tile's
href (which carries long, volatile tracking query params and isn't always
present in a consistent place across sponsored vs. organic tile layouts).
Title is *not* the tile's `<h2>` — as of the current layout that only
holds the brand name (e.g. "Zylvoxia"); the actual descriptive title is
the next non-empty line of the tile's rendered text.
"""

import logging
from urllib.parse import quote

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import new_page, parse_price, with_retries

logger = logging.getLogger("price_tracker.adapters.amazon")

BASE_URL = "https://www.amazon.com"


class AmazonAdapter:
    name = "amazon"

    def search(self, query: str) -> list[Candidate]:
        url = f"{BASE_URL}/s?k={quote(query)}"
        try:
            return with_retries(lambda: self._search(url), attempts=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("amazon search failed for %r: %s", query, exc)
            return []

    def _search(self, url: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        with new_page() as page:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            try:
                page.wait_for_selector('[data-component-type="s-search-result"]', timeout=15000)
            except Exception:
                logger.warning(
                    "no results appeared on amazon search page for %s "
                    "(bot check or throttling; title was %r)", url, page.title()
                )
                return []

            tiles = page.query_selector_all('[data-component-type="s-search-result"]')
            seen_asins = set()
            for tile in tiles:
                asin = tile.get_attribute("data-asin")
                if not asin or asin in seen_asins:
                    continue

                lines = [line for line in tile.inner_text().split("\n") if line.strip()]
                if len(lines) < 2:
                    continue
                title = lines[1]

                price_el = tile.query_selector(".a-price .a-offscreen")
                price = parse_price(price_el.inner_text()) if price_el else None

                seen_asins.add(asin)
                candidates.append(
                    Candidate(
                        store=self.name,
                        product_url=f"{BASE_URL}/dp/{asin}",
                        store_product_id=asin,
                        title=title,
                        price=price,
                        currency="USD",
                    )
                )
        return candidates[:15]

    def scrape(self, product_url: str) -> PriceResult:
        try:
            return with_retries(lambda: self._scrape(product_url), attempts=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("amazon scrape failed for %s: %s", product_url, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape(self, product_url: str) -> PriceResult:
        with new_page() as page:
            page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            title_el = page.query_selector("#productTitle")
            if not title_el:
                return PriceResult(
                    price=None, currency="USD", in_stock=False,
                    error=f"Could not load product page (title was {page.title()!r} — likely a bot check)",
                )
            title = title_el.inner_text().strip()

            price_el = page.query_selector(
                "#corePrice_feature_div .a-offscreen, #corePriceDisplay_desktop_feature_div .a-offscreen, "
                "#priceblock_ourprice, #priceblock_dealprice"
            )
            price = parse_price(price_el.inner_text()) if price_el else None

            availability_el = page.query_selector("#availability span")
            availability_text = availability_el.inner_text().lower() if availability_el else ""
            in_stock = "unavailable" not in availability_text and "out of stock" not in availability_text

        return PriceResult(price=price, currency="USD", in_stock=in_stock, title=title)
