from dataclasses import dataclass
from typing import Protocol


@dataclass
class Candidate:
    store: str
    product_url: str
    store_product_id: str | None
    title: str
    price: float | None
    currency: str = "USD"
    image_url: str | None = None


@dataclass
class PriceResult:
    price: float | None
    currency: str
    in_stock: bool
    title: str | None = None
    error: str | None = None


class StoreAdapter(Protocol):
    name: str

    def search(self, query: str) -> list[Candidate]:
        """Search the store for a query, returning candidate listings for the user to confirm."""
        ...

    def scrape(self, product_url: str) -> PriceResult:
        """Fetch the current price/availability for a known product URL."""
        ...
