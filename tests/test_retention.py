import datetime

from app.config import settings
from app.models import Item, Listing, PricePoint
from app.retention import prune_old_price_points


def _make_listing_with_points(db_session, *, old_days, recent_days):
    item = Item(name="Retention test")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    listing = Listing(item_id=item.id, store="lego", product_url="https://example.com/x", active=True)
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    now = datetime.datetime.now(datetime.timezone.utc)
    old = PricePoint(
        listing_id=listing.id, price=10.0, in_stock=True, currency="USD",
        scraped_at=now - datetime.timedelta(days=old_days),
    )
    recent = PricePoint(
        listing_id=listing.id, price=20.0, in_stock=True, currency="USD",
        scraped_at=now - datetime.timedelta(days=recent_days),
    )
    db_session.add_all([old, recent])
    db_session.commit()
    return listing


def test_prunes_only_points_older_than_retention_window(db_session, monkeypatch):
    monkeypatch.setattr(settings, "price_history_retention_days", 730)
    listing = _make_listing_with_points(db_session, old_days=800, recent_days=5)

    deleted = prune_old_price_points(db_session)

    remaining = db_session.query(PricePoint).filter(PricePoint.listing_id == listing.id).all()
    assert deleted == 1
    assert len(remaining) == 1
    assert remaining[0].price == 20.0


def test_retention_disabled_when_zero(db_session, monkeypatch):
    monkeypatch.setattr(settings, "price_history_retention_days", 0)
    listing = _make_listing_with_points(db_session, old_days=5000, recent_days=5)

    deleted = prune_old_price_points(db_session)

    remaining = db_session.query(PricePoint).filter(PricePoint.listing_id == listing.id).count()
    assert deleted == 0
    assert remaining == 2
