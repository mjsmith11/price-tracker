"""
barnesandnoble.com adapter.

Not Cloudflare-challenge-protected in testing (unlike lego.com), and product
pages carry a clean schema.org `Product` JSON-LD block with price/availability,
so scrape() is a straightforward JSON-LD read. Search has no JSON-LD, so it
walks the rendered DOM: each result is a `.product-item-card` tile with a
`.product-item-card__title` link (href `/w/<slug>/<id>?ean=...`) and a
`.product-item-card__current-price` (falls back to `.product-item-card__price`
for items with no sale price).
"""

import logging
from urllib.parse import quote

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import extract_json_ld, find_product_ld, new_page, parse_price, with_retries

logger = logging.getLogger("price_tracker.adapters.bn")

BASE_URL = "https://www.barnesandnoble.com"


class BarnesNobleAdapter:
    name = "barnesandnoble"

    def search(self, query: str) -> list[Candidate]:
        url = f"{BASE_URL}/search?q={quote(query)}"
        try:
            return with_retries(lambda: self._search(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bn search failed for %r: %s", query, exc)
            return []

    def _search(self, url: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        with new_page() as page:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(".product-item-card", timeout=15000)
            except Exception:
                logger.warning("no result tiles appeared on bn search page for %s", url)
                return []

            tiles = page.query_selector_all(".product-item-card")
            seen_urls = set()
            for tile in tiles:
                link = tile.query_selector(".product-item-card__title-container a[href]")
                title_el = tile.query_selector(".product-item-card__title")
                if not link or not title_el:
                    continue
                href = link.get_attribute("href")
                title = title_el.inner_text().strip()
                if not href or not title:
                    continue

                product_url = href if href.startswith("http") else BASE_URL + href
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)

                price_el = tile.query_selector(
                    ".product-item-card__current-price, .product-item-card__price"
                )
                price = parse_price(price_el.inner_text()) if price_el else None
                store_product_id = product_url.split("/")[-1].split("?")[0]

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

    def scrape(self, product_url: str) -> PriceResult:
        try:
            return with_retries(lambda: self._scrape(product_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bn scrape failed for %s: %s", product_url, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape(self, product_url: str) -> PriceResult:
        with new_page() as page:
            page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            html = page.content()

        product = find_product_ld(extract_json_ld(html))
        if not product:
            return PriceResult(
                price=None, currency="USD", in_stock=False,
                error="No Product JSON-LD found (markup change?)",
            )

        offers = product.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if not isinstance(offers, dict):
            return PriceResult(price=None, currency="USD", in_stock=False, error="No offers in JSON-LD")

        price = parse_price(offers.get("price"))
        availability = str(offers.get("availability", "")).lower()
        in_stock = "outofstock" not in availability
        currency = offers.get("priceCurrency", "USD")

        return PriceResult(price=price, currency=currency, in_stock=in_stock, title=product.get("name"))
