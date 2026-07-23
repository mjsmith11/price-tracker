"""Entrypoint for the `worker` docker compose service: runs the periodic scrape/notify scheduler."""
import logging

from app.db import Base, engine
from app.scheduler import run

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    run()
