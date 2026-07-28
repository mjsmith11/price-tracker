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


def build_scheduler(scheduler):
    """Register jobs on a (not-yet-started) scheduler instance.

    Split out from run() so tests can verify the jobs actually recur —
    this is exactly what broke previously: `next_run_time=None` on the
    interval job doesn't just delay its first tick, it adds the job in a
    permanently *paused* state (APScheduler's documented behavior) that
    nothing in this code ever resumed. It ran once via the one-off
    "initial_scrape" job and then never again.
    """
    interval_hours = settings.scrape_interval_hours
    scheduler.add_job(
        scrape_all_active_listings,
        "interval",
        hours=interval_hours,
        id="scrape_all_active_listings",
    )
    scheduler.add_job(
        run_retention,
        "interval",
        days=1,
        id="run_retention",
    )
    # kick off an immediate first run rather than waiting a full interval;
    # the interval job above still recurs normally afterwards
    scheduler.add_job(scrape_all_active_listings, "date", id="initial_scrape")
    return scheduler


def run() -> None:
    scheduler = build_scheduler(BlockingScheduler())
    logger.info(
        "scheduler starting, scrape interval = %.2fh, retention = %d day(s)",
        settings.scrape_interval_hours, settings.price_history_retention_days,
    )
    scheduler.start()


if __name__ == "__main__":
    run()
