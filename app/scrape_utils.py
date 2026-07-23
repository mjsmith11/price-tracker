import json
import logging
import random
import re
import time
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

logger = logging.getLogger("price_tracker.scrape")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

PRICE_RE = re.compile(r"[\d,]+\.\d{2}|[\d,]+")


def parse_price(text: str | float | int | None) -> float | None:
    """Extract a float price from messy text like '$1,234.56' or 1234.56."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def extract_json_ld(html: str) -> list[dict]:
    """Pull all application/ld+json blocks out of raw HTML and parse them."""
    blocks = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            blocks.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                blocks.extend(d for d in data["@graph"] if isinstance(d, dict))
            else:
                blocks.append(data)
    return blocks


def find_product_ld(blocks: list[dict]) -> dict | None:
    for block in blocks:
        types = block.get("@type")
        if types == "Product" or (isinstance(types, list) and "Product" in types):
            return block
    return None


@contextmanager
def new_page(*, extra_headers: dict | None = None):
    """Launch a headless Chromium page with a randomized UA. Caller owns navigation.

    Bot-management services (Cloudflare et al.) fingerprint plain headless
    Chromium via `navigator.webdriver` and related signals. Disabling the
    automation-controlled flag and patching `navigator.webdriver` is what
    got us past lego.com's search-page challenge in testing; without it the
    same page served an interstitial instead of results.
    """
    ua = random.choice(USER_AGENTS)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            extra_http_headers=extra_headers or {},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def fetch_html(url: str, *, wait_selector: str | None = None, timeout_ms: int = 20000) -> str:
    """Load a URL in headless chromium and return the rendered HTML."""
    with new_page() as page:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                logger.warning("wait_for_selector(%s) timed out on %s", wait_selector, url)
        # small jitter so we don't fire requests in a tight, obviously-automated cadence
        time.sleep(random.uniform(0.3, 0.9))
        return page.content()


def extract_next_data(html: str) -> dict | None:
    """Pull a Next.js __NEXT_DATA__ JSON blob out of raw HTML, if present."""
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None


def find_first_key(data, keys: set[str]):
    """Depth-first search through nested dict/list JSON for the first matching key."""
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if k in keys and v is not None:
                    return v
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def with_retries(fn, *, attempts: int = 2, backoff_seconds: float = 2.0):
    last_exc = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - scraping must never crash the caller
            last_exc = exc
            logger.warning("attempt %s/%s failed: %s", attempt + 1, attempts, exc)
            if attempt < attempts - 1:
                time.sleep(backoff_seconds * (attempt + 1))
    raise last_exc
