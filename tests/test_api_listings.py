def test_confirm_listing_scrapes_immediately(client, fake_adapter):
    item = client.post("/api/items", json={"name": "Item"}).json()

    resp = client.post(
        f"/api/items/{item['id']}/listings",
        json={"store": "fakestore", "product_url": "https://example.com/p/1", "title": "Fake Product"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["store"] == "fakestore"
    assert body["last_price"] == 19.99
    assert body["last_in_stock"] is True
    assert body["last_error"] is None
    assert fake_adapter.scrape_calls == ["https://example.com/p/1"]


def test_confirm_listing_missing_item_404s(client, fake_adapter):
    resp = client.post(
        "/api/items/999/listings",
        json={"store": "fakestore", "product_url": "https://example.com/p/1"},
    )
    assert resp.status_code == 404


def test_delete_listing(client, fake_adapter):
    item = client.post("/api/items", json={"name": "Item"}).json()
    listing = client.post(
        f"/api/items/{item['id']}/listings",
        json={"store": "fakestore", "product_url": "https://example.com/p/1"},
    ).json()

    resp = client.delete(f"/api/listings/{listing['id']}")
    assert resp.status_code == 204

    item_after = client.get(f"/api/items/{item['id']}").json()
    assert item_after["listings"] == []


def test_delete_missing_listing_404s(client):
    resp = client.delete("/api/listings/999")
    assert resp.status_code == 404


def test_refresh_item_rescrapes_all_active_listings(client, fake_adapter):
    item = client.post("/api/items", json={"name": "Item"}).json()
    client.post(
        f"/api/items/{item['id']}/listings",
        json={"store": "fakestore", "product_url": "https://example.com/p/1"},
    )
    assert len(fake_adapter.scrape_calls) == 1  # from the confirm

    resp = client.post(f"/api/items/{item['id']}/refresh")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["price"] == 19.99
    assert len(fake_adapter.scrape_calls) == 2  # confirm + refresh


def test_history_reflects_scrapes(client, fake_adapter):
    item = client.post("/api/items", json={"name": "Item"}).json()
    client.post(
        f"/api/items/{item['id']}/listings",
        json={"store": "fakestore", "product_url": "https://example.com/p/1"},
    )
    client.post(f"/api/items/{item['id']}/refresh")

    resp = client.get(f"/api/items/{item['id']}/history")
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) == 2
    assert all(p["store"] == "fakestore" for p in points)
    assert all(p["price"] == 19.99 for p in points)
