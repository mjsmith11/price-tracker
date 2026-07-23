"""
target.com adapter.

Not bot-protection-blocked in testing. Search results and product pages
are both server-rendered, but Target's component library (data-test
attributes) doesn't cleanly tag "this is the title" / "this is the price"
on search tiles the way lego.com or Barnes & Noble do — the same
`data-test="text-quill"` marker is reused for lots of unrelated text. So
search() falls back to a text heuristic on each tile: price is the first
`$X.XX`-shaped line, title is the longest remaining line after filtering
out known badge/logistics text ("Highly rated", "Pickup ready within...",
"Ships free", star ratings, etc.) — in practice the real product title is
reliably the longest surviving line.

Product pages are cleaner: `[data-test="product-price"]` and
`[data-test="product-title"]` are stable, purpose-built markers. There's
no schema.org JSON-LD on target.com product pages (checked; zero ld+json
blocks) and no useful client-side API call to piggyback on either — price
is server-rendered directly into the page, so DOM selectors are actually
the *most* stable option here, not a fallback.

Stock is intentionally coarse: Target shows separate pickup/shipping/
delivery availability per store, which doesn't collapse into a single
true/false cleanly. We only report out-of-stock when the page explicitly
says "sold out" (an unambiguous negative signal) and otherwise assume the
price is still actionable.

Observed in testing: Target tolerates occasional requests fine but
soft-throttles rapid *repeated identical* search queries from the same IP
(tiles fail to render for a stretch, then come back after ~20s of no
traffic). `with_retries` covers isolated blips; sustained throttling would
need a longer backoff. Not expected to matter at the scheduler's real
cadence (each listing scraped a few hours apart, with pacing between
listings), but worth knowing if search suddenly returns empty.
"""

import logging
import re
from urllib.parse import quote

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import new_page, parse_price, with_retries

logger = logging.getLogger("price_tracker.adapters.target")

BASE_URL = "https://www.target.com"

BADGE_LINE_RE = re.compile(
    r"stars|bought in last|highly rated|rarely returned|only \d+ left|"
    r"pickup|delivery|shipping|ships free|add to cart|ready within|arrives|"
    r"loved for|^at |^\(\d+\)$|^\$|^\d+(\.\d+)?$|sponsored",
    re.IGNORECASE,
)
PRICE_SEARCH_RE = re.compile(r"\$[\d,]+\.\d{2}")


class TargetAdapter:
    name = "target"

    def search(self, query: str) -> list[Candidate]:
        url = f"{BASE_URL}/s?searchTerm={quote(query)}"
        try:
            return with_retries(lambda: self._search(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("target search failed for %r: %s", query, exc)
            return []

    def _search(self, url: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        with new_page() as page:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            try:
                page.wait_for_selector('[data-test="ListingPageProductListing"]', timeout=15000)
            except Exception:
                logger.warning("no product tiles appeared on target search page for %s", url)
                return []

            tiles = page.query_selector_all('[data-test="ListingPageProductListing"]')
            seen_urls = set()
            for tile in tiles:
                link = tile.query_selector('a[href*="/p/"]')
                if not link:
                    continue
                href = link.get_attribute("href")
                if not href:
                    continue
                product_url = (href if href.startswith("http") else BASE_URL + href).split("?")[0]
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)

                text = tile.inner_text()
                title = self._title_from_text(text)
                price = self._price_from_text(text)
                if not title:
                    continue

                tcin_match = re.search(r"A-(\d+)$", product_url)
                candidates.append(
                    Candidate(
                        store=self.name,
                        product_url=product_url,
                        store_product_id=tcin_match.group(1) if tcin_match else None,
                        title=title,
                        price=price,
                        currency="USD",
                    )
                )
        return candidates[:15]

    @staticmethod
    def _title_from_text(text: str) -> str | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        candidates = [line for line in lines if len(line) > 8 and not BADGE_LINE_RE.search(line)]
        return max(candidates, key=len) if candidates else None

    @staticmethod
    def _price_from_text(text: str) -> float | None:
        # a variant/bundle product's price often renders as a range, e.g.
        # "$449.99 - $499.99" — take the low end as the trackable price.
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("$"):
                match = PRICE_SEARCH_RE.search(line)
                if match:
                    return parse_price(match.group())
        return None

    def scrape(self, product_url: str) -> PriceResult:
        try:
            return with_retries(lambda: self._scrape(product_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("target scrape failed for %s: %s", product_url, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape(self, product_url: str) -> PriceResult:
        with new_page() as page:
            page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            price_el = page.query_selector('[data-test="product-price"]')
            title_el = page.query_selector('[data-test="product-title"]')
            if not price_el:
                return PriceResult(
                    price=None, currency="USD", in_stock=False,
                    error="Could not find price element on page (markup change?)",
                )

            price = parse_price(price_el.inner_text())
            title = title_el.inner_text().strip() if title_el else None
            body_text = page.inner_text("body").lower()
            in_stock = "sold out" not in body_text

        return PriceResult(price=price, currency="USD", in_stock=in_stock, title=title)
