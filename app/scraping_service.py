import datetime
import logging

from sqlalchemy.orm import Session

from app.adapters import ADAPTERS
from app.models import Listing, Notification, PricePoint
from app.notify import send_price_drop_email

logger = logging.getLogger("price_tracker.scraping_service")


def scrape_listing(db: Session, listing: Listing) -> PricePoint | None:
    adapter = ADAPTERS.get(listing.store)
    if adapter is None:
        logger.warning("no adapter registered for store %r", listing.store)
        return None

    result = adapter.scrape(listing.product_url)
    now = datetime.datetime.now(datetime.timezone.utc)

    listing.last_seen_at = now
    listing.last_error = result.error

    if result.error is not None:
        db.commit()
        return None

    listing.last_price = result.price
    listing.last_in_stock = result.in_stock
    if result.title:
        listing.title = result.title

    point = PricePoint(
        listing_id=listing.id,
        price=result.price,
        in_stock=result.in_stock,
        currency=result.currency,
    )
    db.add(point)
    db.commit()
    db.refresh(point)

    _maybe_notify(db, listing, point)
    return point


def _maybe_notify(db: Session, listing: Listing, point: PricePoint) -> None:
    item = listing.item
    threshold = item.threshold_price
    if threshold is None or point.price is None or point.price > threshold:
        return

    # Dedup: don't re-alert while price stays below threshold in consecutive
    # readings. Only notify again once it rises back above threshold and dips again.
    prior_points = (
        db.query(PricePoint)
        .filter(PricePoint.listing_id == listing.id, PricePoint.id != point.id)
        .order_by(PricePoint.scraped_at.desc())
        .limit(1)
        .all()
    )
    if prior_points and prior_points[0].price is not None and prior_points[0].price <= threshold:
        return

    sent = send_price_drop_email(
        item_name=item.name,
        store=listing.store,
        price=point.price,
        threshold=threshold,
        currency=point.currency,
        product_url=listing.product_url,
    )
    if sent:
        db.add(
            Notification(
                listing_id=listing.id,
                price_point_id=point.id,
                threshold=threshold,
                channel="email",
            )
        )
        db.commit()
