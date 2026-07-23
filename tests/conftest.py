import os
import tempfile

# must happen before any `app.*` import, since app.config.Settings() reads
# the environment once at import time and app.db builds its engine from it
_tmp_dir = tempfile.mkdtemp(prefix="price_tracker_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ.setdefault("SMTP_HOST", "")
os.environ.setdefault("EMAIL_FROM", "")
os.environ.setdefault("EMAIL_TO", "")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.adapters import ADAPTERS  # noqa: E402
from app.adapters.base import PriceResult  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    """Every test gets a fresh schema — simplest reliable isolation for a small suite."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    return TestClient(app)


class FakeAdapter:
    """A StoreAdapter double so item/listing tests never touch the network."""

    name = "fakestore"

    def __init__(self, price=19.99, in_stock=True, title="Fake Product"):
        self.result = PriceResult(price=price, currency="USD", in_stock=in_stock, title=title)
        self.scrape_calls = []

    def search(self, query):
        return []

    def scrape(self, product_url):
        self.scrape_calls.append(product_url)
        return self.result


@pytest.fixture()
def fake_adapter(monkeypatch):
    fake = FakeAdapter()
    monkeypatch.setitem(ADAPTERS, fake.name, fake)
    return fake
