from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Item, Listing
from app.schemas import ConfirmListingRequest, ListingOut

router = APIRouter(tags=["listings"])


@router.post("/api/items/{item_id}/listings", response_model=ListingOut)
def confirm_listing(item_id: int, payload: ConfirmListingRequest, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")

    listing = Listing(
        item_id=item.id,
        store=payload.store,
        product_url=payload.product_url,
        store_product_id=payload.store_product_id,
        title=payload.title,
        confirmed=True,
        active=True,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    from app.scraping_service import scrape_listing

    scrape_listing(db, listing)
    return listing


@router.delete("/api/listings/{listing_id}", status_code=204)
def delete_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "listing not found")
    db.delete(listing)
    db.commit()
