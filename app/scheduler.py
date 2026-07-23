import logging
import time

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import settings
from app.db import SessionLocal
from app.models import Listing
from app.retention import prune_old_price_points
from app.scraping_service import scrape_listing

logger = logging.getLogger("price_tracker.scheduler")


def scrape_all_active_listings() -> None:
    db = SessionLocal()
    try:
        listings = db.query(Listing).filter(Listing.active.is_(True)).all()
        logger.info("scraping %d active listing(s)", len(listings))
        for listing in listings:
            try:
                scrape_listing(db, listing)
            except Exception:
                logger.exception("unhandled error scraping listing %s (%s)", listing.id, listing.store)
            # be polite between requests, especially across listings at the same store
            time.sleep(3)
    finally:
        db.close()


def run_retention() -> None:
    db = SessionLocal()
    try:
        prune_old_price_points(db)
    finally:
        db.close()


def run() -> None:
    scheduler = BlockingScheduler()
    interval_hours = settings.scrape_interval_hours
    scheduler.add_job(
        scrape_all_active_listings,
        "interval",
        hours=interval_hours,
        next_run_time=None,  # first run scheduled below, staggered slightly after startup
        id="scrape_all_active_listings",
    )
    scheduler.add_job(
        run_retention,
        "interval",
        days=1,
        id="run_retention",
    )
    logger.info(
        "scheduler starting, scrape interval = %.2fh, retention = %d day(s)",
        interval_hours, settings.price_history_retention_days,
    )

    # kick off an initial run shortly after startup rather than waiting a full interval
    scheduler.add_job(scrape_all_active_listings, "date", id="initial_scrape")

    scheduler.start()


if __name__ == "__main__":
    run()
