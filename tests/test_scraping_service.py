import app.scraping_service as svc
from app.adapters.base import PriceResult
from app.models import Item, Listing, Notification


class SequenceAdapter:
    """Returns a scripted sequence of prices, one per call, for exercising
    the notify/dedup logic across consecutive scrapes."""

    name = "seqstore"

    def __init__(self, prices):
        self._prices = iter(prices)

    def search(self, query):
        return []

    def scrape(self, product_url):
        return PriceResult(price=next(self._prices), currency="USD", in_stock=True, title="X")


def _make_item_and_listing(db_session, store, threshold=50.0):
    item = Item(name="Test Item", threshold_price=threshold)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    listing = Listing(item_id=item.id, store=store, product_url="https://example.com/x", active=True)
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)
    return item, listing


def test_notifies_once_then_dedups_while_still_below_threshold(db_session, monkeypatch):
    sent_calls = []
    monkeypatch.setattr(svc, "send_price_drop_email", lambda **kwargs: sent_calls.append(kwargs) or True)
    monkeypatch.setitem(svc.ADAPTERS, "seqstore", SequenceAdapter([40.0, 40.0]))

    item, listing = _make_item_and_listing(db_session, "seqstore", threshold=50.0)

    svc.scrape_listing(db_session, listing)  # 40 <= 50 -> notify
    svc.scrape_listing(db_session, listing)  # still 40 <= 50 -> deduped, no repeat notify

    assert len(sent_calls) == 1
    assert sent_calls[0]["price"] == 40.0
    notif_count = db_session.query(Notification).filter(Notification.listing_id == listing.id).count()
    assert notif_count == 1


def test_rearms_after_price_rises_above_threshold(db_session, monkeypatch):
    sent_calls = []
    monkeypatch.setattr(svc, "send_price_drop_email", lambda **kwargs: sent_calls.append(kwargs) or True)
    monkeypatch.setitem(svc.ADAPTERS, "seqstore", SequenceAdapter([40.0, 60.0, 30.0]))

    item, listing = _make_item_and_listing(db_session, "seqstore", threshold=50.0)

    svc.scrape_listing(db_session, listing)  # 40 <= 50 -> notify #1
    svc.scrape_listing(db_session, listing)  # 60 > 50  -> no notify, re-arms
    svc.scrape_listing(db_session, listing)  # 30 <= 50 -> notify #2

    assert len(sent_calls) == 2
    assert [c["price"] for c in sent_calls] == [40.0, 30.0]


def test_no_notification_when_no_threshold_set(db_session, monkeypatch):
    sent_calls = []
    monkeypatch.setattr(svc, "send_price_drop_email", lambda **kwargs: sent_calls.append(kwargs) or True)
    monkeypatch.setitem(svc.ADAPTERS, "seqstore", SequenceAdapter([1.0]))

    item, listing = _make_item_and_listing(db_session, "seqstore", threshold=None)
    svc.scrape_listing(db_session, listing)

    assert sent_calls == []


def test_no_notification_when_price_above_threshold(db_session, monkeypatch):
    sent_calls = []
    monkeypatch.setattr(svc, "send_price_drop_email", lambda **kwargs: sent_calls.append(kwargs) or True)
    monkeypatch.setitem(svc.ADAPTERS, "seqstore", SequenceAdapter([99.0]))

    item, listing = _make_item_and_listing(db_session, "seqstore", threshold=50.0)
    svc.scrape_listing(db_session, listing)

    assert sent_calls == []


def test_scrape_error_does_not_create_price_point_or_notify(db_session, monkeypatch):
    sent_calls = []
    monkeypatch.setattr(svc, "send_price_drop_email", lambda **kwargs: sent_calls.append(kwargs) or True)

    class FailingAdapter:
        name = "failstore"

        def search(self, query):
            return []

        def scrape(self, product_url):
            return PriceResult(price=None, currency="USD", in_stock=False, error="blocked")

    monkeypatch.setitem(svc.ADAPTERS, "failstore", FailingAdapter())

    item, listing = _make_item_and_listing(db_session, "failstore", threshold=50.0)
    point = svc.scrape_listing(db_session, listing)

    assert point is None
    assert listing.last_error == "blocked"
    assert sent_calls == []


def test_unknown_store_returns_none_without_crashing(db_session):
    item, listing = _make_item_and_listing(db_session, "no-such-store", threshold=50.0)
    result = svc.scrape_listing(db_session, listing)
    assert result is None
