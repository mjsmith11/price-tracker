"""
Regression coverage for a real production bug: the scrape interval job was
added with `next_run_time=None`, which APScheduler treats as "add this job
already paused" rather than "just skip the immediate first tick" (the
intent). It ran once via the separate one-off startup job and then never
again — price history silently stopped updating with no error anywhere.
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.scheduler import build_scheduler


def test_interval_jobs_are_not_paused_on_creation():
    scheduler = build_scheduler(BackgroundScheduler())
    scheduler.start()
    try:
        scrape_job = scheduler.get_job("scrape_all_active_listings")
        retention_job = scheduler.get_job("run_retention")

        # a paused job (the actual bug) has next_run_time == None forever
        assert scrape_job.next_run_time is not None
        assert retention_job.next_run_time is not None
    finally:
        scheduler.shutdown(wait=False)


def test_initial_scrape_job_is_registered_for_immediate_first_run():
    # checked before start() — it's a one-shot job that fires immediately
    # and is removed once running, so checking post-start would race it
    scheduler = build_scheduler(BackgroundScheduler())
    assert scheduler.get_job("initial_scrape") is not None
