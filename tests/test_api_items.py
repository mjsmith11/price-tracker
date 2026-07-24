def test_create_item(client):
    resp = client.post("/api/items", json={"name": "LEGO Titanic 10294", "threshold_price": 500})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "LEGO Titanic 10294"
    assert body["threshold_price"] == 500
    assert body["listings"] == []


def test_created_at_is_timezone_aware_utc(client):
    """Regression test: SQLite silently drops tzinfo on round-trip, which
    made timestamps serialize without a UTC marker — browsers then parsed
    them as local time instead of converting, so times displayed unshifted
    (looked like UTC regardless of the viewer's actual timezone)."""
    import datetime

    body = client.post("/api/items", json={"name": "Item"}).json()
    # py3.10's fromisoformat doesn't accept a trailing "Z" (3.11+ does)
    raw = body["created_at"].replace("Z", "+00:00")
    parsed = datetime.datetime.fromisoformat(raw)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.timedelta(0)


def test_list_items(client):
    client.post("/api/items", json={"name": "Item A"})
    client.post("/api/items", json={"name": "Item B"})
    resp = client.get("/api/items")
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()}
    assert names == {"Item A", "Item B"}


def test_get_missing_item_404s(client):
    resp = client.get("/api/items/999")
    assert resp.status_code == 404


def test_update_item_threshold(client):
    item = client.post("/api/items", json={"name": "Item", "threshold_price": 100}).json()
    resp = client.patch(f"/api/items/{item['id']}", json={"threshold_price": 75})
    assert resp.status_code == 200
    assert resp.json()["threshold_price"] == 75
    # name should be untouched by a partial update
    assert resp.json()["name"] == "Item"


def test_update_item_name_and_threshold_together(client):
    item = client.post("/api/items", json={"name": "Old name", "threshold_price": 100}).json()
    resp = client.patch(f"/api/items/{item['id']}", json={"name": "New name", "threshold_price": 250})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New name"
    assert body["threshold_price"] == 250


def test_update_item_can_clear_threshold(client):
    item = client.post("/api/items", json={"name": "Item", "threshold_price": 100}).json()
    resp = client.patch(f"/api/items/{item['id']}", json={"threshold_price": None})
    assert resp.status_code == 200
    assert resp.json()["threshold_price"] is None


def test_update_missing_item_404s(client):
    resp = client.patch("/api/items/999", json={"name": "X"})
    assert resp.status_code == 404


def test_delete_item(client):
    item = client.post("/api/items", json={"name": "Throwaway"}).json()
    resp = client.delete(f"/api/items/{item['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/items/{item['id']}").status_code == 404


def test_delete_item_cascades_listings(client, fake_adapter):
    item = client.post("/api/items", json={"name": "Item"}).json()
    listing = client.post(
        f"/api/items/{item['id']}/listings",
        json={"store": "fakestore", "product_url": "https://example.com/p/1"},
    ).json()

    client.delete(f"/api/items/{item['id']}")

    resp = client.delete(f"/api/listings/{listing['id']}")
    assert resp.status_code == 404  # already gone via cascade
