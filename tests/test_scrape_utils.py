from app.scrape_utils import (
    extract_json_ld,
    extract_next_data,
    find_first_key,
    find_product_ld,
    parse_price,
)


class TestParsePrice:
    def test_dollar_with_comma_and_cents(self):
        assert parse_price("$1,234.56") == 1234.56

    def test_plain_number_string(self):
        assert parse_price("42.50") == 42.50

    def test_int_passthrough(self):
        assert parse_price(42) == 42.0

    def test_float_passthrough(self):
        assert parse_price(42.5) == 42.5

    def test_none_returns_none(self):
        assert parse_price(None) is None

    def test_no_digits_returns_none(self):
        assert parse_price("Free shipping") is None

    def test_whole_dollar_no_cents(self):
        assert parse_price("$449") == 449.0


class TestExtractJsonLd:
    def test_single_product_block(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context": "https://schema.org", "@type": "Product", "name": "Widget"}
        </script>
        </head></html>
        """
        blocks = extract_json_ld(html)
        assert len(blocks) == 1
        assert blocks[0]["name"] == "Widget"

    def test_graph_wrapped_blocks(self):
        html = """
        <script type="application/ld+json">
        {"@graph": [{"@type": "Product", "name": "A"}, {"@type": "BreadcrumbList"}]}
        </script>
        """
        blocks = extract_json_ld(html)
        types = {b.get("@type") for b in blocks}
        assert types == {"Product", "BreadcrumbList"}

    def test_no_script_tags_returns_empty(self):
        assert extract_json_ld("<html><body>no data here</body></html>") == []

    def test_malformed_json_is_skipped_not_raised(self):
        html = '<script type="application/ld+json">{not valid json</script>'
        assert extract_json_ld(html) == []


class TestFindProductLd:
    def test_finds_product_among_other_types(self):
        blocks = [{"@type": "BreadcrumbList"}, {"@type": "Product", "name": "Found"}]
        product = find_product_ld(blocks)
        assert product is not None
        assert product["name"] == "Found"

    def test_matches_product_inside_type_list(self):
        blocks = [{"@type": ["Thing", "Product"], "name": "Multi"}]
        assert find_product_ld(blocks)["name"] == "Multi"

    def test_returns_none_when_absent(self):
        assert find_product_ld([{"@type": "BreadcrumbList"}]) is None

    def test_empty_list_returns_none(self):
        assert find_product_ld([]) is None


class TestExtractNextData:
    def test_extracts_and_parses(self):
        html = '<script id="__NEXT_DATA__">{"props": {"price": 9.99}}</script>'
        data = extract_next_data(html)
        assert data == {"props": {"price": 9.99}}

    def test_missing_tag_returns_none(self):
        assert extract_next_data("<html></html>") is None

    def test_malformed_json_returns_none(self):
        html = '<script id="__NEXT_DATA__">{not json</script>'
        assert extract_next_data(html) is None


class TestFindFirstKey:
    def test_finds_key_in_nested_dict(self):
        data = {"a": {"b": {"price": 42}}}
        assert find_first_key(data, {"price"}) == 42

    def test_finds_key_inside_list(self):
        data = {"items": [{"other": 1}, {"price": 7}]}
        assert find_first_key(data, {"price"}) == 7

    def test_returns_none_when_absent(self):
        assert find_first_key({"a": 1}, {"price"}) is None

    def test_skips_none_values(self):
        data = {"price": None, "nested": {"price": 5}}
        assert find_first_key(data, {"price"}) == 5
