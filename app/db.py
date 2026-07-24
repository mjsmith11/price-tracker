import datetime

from sqlalchemy import DateTime, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime that's always UTC-aware, in and out.

    SQLite has no native timezone storage — it silently drops tzinfo on
    round-trip, so a value written as UTC comes back naive. Pydantic then
    serializes that naive datetime with no offset marker, which browsers
    parse as *local* time instead of converting from UTC — the timestamp
    displays as if it were already in the viewer's timezone, unshifted.
    This type re-attaches UTC on the way out (and defensively on the way
    in) so every datetime that leaves the API is unambiguous.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime.datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value

    def process_result_value(self, value: datetime.datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
