"""
lego.com adapter.

NOTE ON RELIABILITY: lego.com sits behind Cloudflare's bot-management JS
challenge. Whether a plain headless-Chromium request clears that challenge
depends on IP reputation (datacenter IPs are far more likely to be
challenged than a home connection) and Cloudflare's current heuristics, so
this must be validated from the actual deployment environment, not assumed.
When the challenge blocks us, scrape()/search() surface an error on the
listing (`last_error`) instead of raising, so the app stays usable and the
failure is visible in the UI.

Parsing prefers structured data (JSON-LD `Product`, falling back to the
Next.js `__NEXT_DATA__` blob) over CSS selectors, since markup changes far
more often than schema.org fields or the shape of a framework's data blob.
The DOM-based search fallback is the most likely piece to need adjustment
if lego.com changes their search page layout.
"""

import logging
from urllib.parse import quote

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import (
    extract_json_ld,
    extract_next_data,
    find_first_key,
    find_product_ld,
    new_page,
    parse_price,
    with_retries,
)

logger = logging.getLogger("price_tracker.adapters.lego")

BASE_URL = "https://www.lego.com"


class LegoAdapter:
    name = "lego"

    def search(self, query: str) -> list[Candidate]:
        url = f"{BASE_URL}/en-us/search?q={quote(query)}"
        try:
            return with_retries(lambda: self._search(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("lego search failed for %r: %s", query, exc)
            return []

    def _search(self, url: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        with new_page() as page:
            # domcontentloaded fires before Cloudflare's JS challenge resolves; give it
            # a few seconds to clear before looking for product tiles.
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            try:
                page.wait_for_selector('article[data-test="product-leaf"]', timeout=15000)
            except Exception:
                logger.warning("no product tiles appeared on lego search page for %s", url)
                return []

            tiles = page.query_selector_all('article[data-test="product-leaf"]')
            seen_urls = set()
            for tile in tiles:
                link = tile.query_selector('a[href*="/product/"][aria-label]')
                if not link:
                    continue
                href = link.get_attribute("href")
                title = (link.get_attribute("aria-label") or "").strip()
                if not href or not title:
                    continue

                product_url = (href if href.startswith("http") else BASE_URL + href).split("?")[0]
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)

                price = self._price_from_text(tile.inner_text())
                store_product_id = tile.get_attribute("data-test-key") or product_url.rstrip("/").split("-")[-1]

                candidates.append(
                    Candidate(
                        store=self.name,
                        product_url=product_url,
                        store_product_id=store_product_id,
                        title=title,
                        price=price,
                        currency="USD",
                    )
                )
        return candidates[:15]

    @staticmethod
    def _price_from_text(text: str) -> float | None:
        for line in text.splitlines():
            if "$" in line:
                p = parse_price(line)
                if p:
                    return p
        return None

    def scrape(self, product_url: str) -> PriceResult:
        try:
            return with_retries(lambda: self._scrape(product_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("lego scrape failed for %s: %s", product_url, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape(self, product_url: str) -> PriceResult:
        with new_page() as page:
            page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
            html = page.content()

        # 1. structured data: schema.org Product JSON-LD
        product = find_product_ld(extract_json_ld(html))
        if product:
            offers = product.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                price = parse_price(offers.get("price"))
                availability = str(offers.get("availability", "")).lower()
                in_stock = "outofstock" not in availability
                currency = offers.get("priceCurrency", "USD")
                if price is not None:
                    return PriceResult(
                        price=price,
                        currency=currency,
                        in_stock=in_stock,
                        title=product.get("name"),
                    )

        # 2. fallback: Next.js __NEXT_DATA__ blob
        next_data = extract_next_data(html)
        if next_data:
            price = find_first_key(next_data, {"price", "formattedAmount", "finalPrice"})
            in_stock_raw = find_first_key(next_data, {"inStock", "isInStock", "available"})
            price = parse_price(price)
            if price is not None:
                return PriceResult(
                    price=price,
                    currency="USD",
                    in_stock=bool(in_stock_raw) if in_stock_raw is not None else True,
                )

        return PriceResult(
            price=None,
            currency="USD",
            in_stock=False,
            error="Could not find price on page (Cloudflare challenge or markup change)",
        )
