import datetime
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models import PricePoint

logger = logging.getLogger("price_tracker.retention")


def prune_old_price_points(db: Session) -> int:
    """Delete price points older than the configured retention window.

    A price tracker's whole point is long-term trend history, so this is a
    safety valve against years of unbounded growth, not aggressive pruning
    — set PRICE_HISTORY_RETENTION_DAYS to 0 to disable entirely.
    """
    if settings.price_history_retention_days <= 0:
        return 0

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=settings.price_history_retention_days
    )
    deleted = (
        db.query(PricePoint)
        .filter(PricePoint.scraped_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    if deleted:
        logger.info("pruned %d price point(s) older than %s", deleted, cutoff.date())
    return deleted
