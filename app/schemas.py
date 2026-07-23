import datetime

from pydantic import BaseModel, ConfigDict


class ItemCreate(BaseModel):
    name: str
    notes: str | None = None
    threshold_price: float | None = None
    currency: str = "USD"


class ItemUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    threshold_price: float | None = None


class PricePointOut(BaseModel):
    price: float | None
    in_stock: bool
    currency: str
    scraped_at: datetime.datetime
    store: str

    model_config = ConfigDict(from_attributes=True)


class ListingOut(BaseModel):
    id: int
    store: str
    product_url: str
    title: str | None
    active: bool
    last_seen_at: datetime.datetime | None
    last_price: float | None
    last_in_stock: bool | None
    last_error: str | None

    model_config = ConfigDict(from_attributes=True)


class ItemOut(BaseModel):
    id: int
    name: str
    notes: str | None
    threshold_price: float | None
    currency: str
    created_at: datetime.datetime
    listings: list[ListingOut] = []

    model_config = ConfigDict(from_attributes=True)


class CandidateOut(BaseModel):
    store: str
    product_url: str
    store_product_id: str | None
    title: str
    price: float | None
    currency: str
    image_url: str | None = None


class ConfirmListingRequest(BaseModel):
    store: str
    product_url: str
    store_product_id: str | None = None
    title: str | None = None
