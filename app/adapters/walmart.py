"""
walmart.com adapter — best-effort, expected to fail often.

CONFIRMED IN TESTING: every request (search and product pages alike) was
immediately served PerimeterX's "Robot or human?" interactive challenge
page, even with the same stealth launch args that got lego.com and
bestbuy.com through their bot checks. PerimeterX challenges typically
require solving an interactive puzzle / passing device-fingerprint and
mouse-movement heuristics that plain headless Chromium cannot satisfy —
this is a materially harder wall than Cloudflare's or Akamai's checks
elsewhere in this codebase, not just "the same thing but stricter".

This was tested from a datacenter-class sandbox IP. PerimeterX scoring
weighs IP reputation heavily, so a home-server residential IP (the actual
deployment target) may fare differently — better or worse — which is why
this adapter still exists rather than being left unimplemented. It uses
the same JSON-LD-first approach as the other adapters on the (perhaps
optimistic) chance a request gets through, and explicitly detects the
block page so failures show up as a clear "blocked by Walmart" error on
the listing instead of a confusing empty parse.

If this consistently fails from your home server too, that's expected —
per the plan, Walmart was flagged from the start as the store most likely
to not work with a free-scraping-only approach.
"""

import logging
from urllib.parse import quote

from app.adapters.base import Candidate, PriceResult
from app.scrape_utils import extract_json_ld, find_product_ld, new_page, parse_price, with_retries

logger = logging.getLogger("price_tracker.adapters.walmart")

BASE_URL = "https://www.walmart.com"


def _is_blocked(title: str, html: str) -> bool:
    return "robot or human" in title.lower() or "/blocked?" in html[:2000]


class WalmartAdapter:
    name = "walmart"

    def search(self, query: str) -> list[Candidate]:
        url = f"{BASE_URL}/search?q={quote(query)}"
        try:
            return with_retries(lambda: self._search(url), attempts=1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("walmart search failed for %r: %s", query, exc)
            return []

    def _search(self, url: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        with new_page() as page:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            title = page.title()
            html = page.content()
            if _is_blocked(title, html):
                logger.warning("walmart blocked the search request for %r (PerimeterX challenge)", url)
                return []

            try:
                page.wait_for_selector('a[link-identifier="linkText"], a[href*="/ip/"]', timeout=10000)
            except Exception:
                logger.warning("no product links appeared on walmart search page for %s", url)
                return []

            links = page.query_selector_all('a[href*="/ip/"]')
            seen_urls = set()
            for link in links:
                href = link.get_attribute("href")
                if not href or "/ip/" not in href:
                    continue
                product_url = (href if href.startswith("http") else BASE_URL + href).split("?")[0]
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)

                title_text = (link.get_attribute("aria-label") or link.inner_text() or "").strip()
                if not title_text:
                    continue

                store_product_id = product_url.rstrip("/").split("/")[-1]
                candidates.append(
                    Candidate(
                        store=self.name,
                        product_url=product_url,
                        store_product_id=store_product_id,
                        title=title_text,
                        price=None,
                        currency="USD",
                    )
                )
        return candidates[:15]

    def scrape(self, product_url: str) -> PriceResult:
        try:
            return with_retries(lambda: self._scrape(product_url), attempts=1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("walmart scrape failed for %s: %s", product_url, exc)
            return PriceResult(price=None, currency="USD", in_stock=False, error=str(exc))

    def _scrape(self, product_url: str) -> PriceResult:
        with new_page() as page:
            page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            title = page.title()
            html = page.content()

        if _is_blocked(title, html):
            return PriceResult(
                price=None, currency="USD", in_stock=False,
                error="Blocked by Walmart's bot check (PerimeterX) — see adapter notes",
            )

        product = find_product_ld(extract_json_ld(html))
        if not product:
            return PriceResult(
                price=None, currency="USD", in_stock=False,
                error="No Product JSON-LD found (page loaded but markup didn't match)",
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
