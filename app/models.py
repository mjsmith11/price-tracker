import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    threshold_price: Mapped[float | None] = mapped_column(Float, default=None)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    store: Mapped[str] = mapped_column(String(64))
    product_url: Mapped[str] = mapped_column(Text)
    store_product_id: Mapped[str | None] = mapped_column(String(255), default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_price: Mapped[float | None] = mapped_column(Float, default=None)
    last_in_stock: Mapped[bool | None] = mapped_column(Boolean, default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped["Item"] = relationship(back_populates="listings")
    price_points: Mapped[list["PricePoint"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="PricePoint.scraped_at"
    )


class PricePoint(Base):
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    price: Mapped[float | None] = mapped_column(Float, default=None)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    scraped_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listing: Mapped["Listing"] = relationship(back_populates="price_points")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    price_point_id: Mapped[int] = mapped_column(ForeignKey("price_points.id"))
    threshold: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(32), default="email")
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
