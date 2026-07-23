"""
Tests for the hand-written text/DOM heuristics inside each adapter — the
parts most likely to silently break when a store tweaks its markup. These
use real sample text captured from the live sites during development, not
synthetic data, so they double as a record of the shapes each adapter was
built against.
"""

from app.adapters.bestbuy import SKU_QUERY_RE
from app.adapters.lego import LegoAdapter
from app.adapters.target import TargetAdapter
from app.adapters.walmart import _is_blocked
from app.adapters.woot import WootAdapter


class TestLegoPriceFromText:
    def test_finds_price_on_dollar_line(self):
        text = "18+\n9090\n4.5\nLEGO® Titanic\n$679.99\nBackorder\nExclusives"
        assert LegoAdapter._price_from_text(text) == 679.99

    def test_no_dollar_line_returns_none(self):
        assert LegoAdapter._price_from_text("Coming soon\nNotify me") is None


class TestTargetHeuristics:
    REAL_TILE_TEXT = (
        "Highly rated\n$23.99\nLEGO™ City Fire Rescue Boat Toy, "
        "Floats on Water Set 60373\n4.8\n4.85 out of 5 stars\n(97)\n"
        "Only 3 left\n at Carmel East 151st Street\nPickup \n"
        "ready within 2 hours\nDelivery \nas soon as 7pm EDT\nShipping \n"
        "arrives Sat, Jul 25\nShips free - exclusions apply\nAdd to cart"
    )

    def test_title_from_real_tile_text(self):
        title = TargetAdapter._title_from_text(self.REAL_TILE_TEXT)
        assert title == "LEGO™ City Fire Rescue Boat Toy, Floats on Water Set 60373"

    def test_price_from_real_tile_text(self):
        assert TargetAdapter._price_from_text(self.REAL_TILE_TEXT) == 23.99

    def test_price_range_takes_low_end(self):
        text = "Bestseller\n$449.99 - $499.99\nRarely returned\nNintendo™ Switch 2 Console"
        assert TargetAdapter._price_from_text(text) == 449.99

    def test_title_excludes_badge_lines(self):
        title = TargetAdapter._title_from_text("Sponsored\n$4.99\nRarely returned\nActual Product Title Here")
        assert title == "Actual Product Title Here"

    def test_no_price_line_returns_none(self):
        assert TargetAdapter._price_from_text("Sold out\nNotify me when available") is None


class TestWootPriceFromTile:
    def test_dollars_and_cents_on_separate_lines(self):
        text = "$\n449\n00\n(NEW) Nintendo Switch 2"
        assert WootAdapter._price_from_tile(text) == 449.00

    def test_dollars_only_defaults_cents_to_zero(self):
        assert WootAdapter._price_from_tile("$\n99\nSome Deal") == 99.00

    def test_no_price_returns_none(self):
        assert WootAdapter._price_from_tile("Sold Out\nNo longer available") is None


class TestWalmartBlockDetection:
    def test_detects_robot_or_human_title(self):
        assert _is_blocked("Robot or human?", "<html></html>") is True

    def test_detects_blocked_path_in_html(self):
        html = '<html><a href="/blocked?url=abc">redirecting</a></html>'
        assert _is_blocked("Walmart.com", html) is True

    def test_normal_page_not_flagged(self):
        assert _is_blocked("LEGO Titanic - Walmart.com", "<html>real content</html>") is False


class TestBestBuySkuQueryRegex:
    def test_extracts_sku_from_query_string(self):
        url = "https://www.bestbuy.com/product/switch-2-system/J7GSL57TGH?skuId=6614313"
        match = SKU_QUERY_RE.search(url)
        assert match is not None
        assert match.group(1) == "6614313"

    def test_no_match_when_absent(self):
        url = "https://www.bestbuy.com/product/switch-2-system/J7GSL57TGH"
        assert SKU_QUERY_RE.search(url) is None
