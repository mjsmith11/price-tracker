import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Item, PricePoint
from app.schemas import ItemCreate, ItemOut, ItemUpdate, PricePointOut

router = APIRouter(prefix="/api/items", tags=["items"])


@router.post("", response_model=ItemOut)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    item = Item(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[ItemOut])
def list_items(db: Session = Depends(get_db)):
    return db.query(Item).order_by(Item.created_at.desc()).all()


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")
    return item


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")
    db.delete(item)
    db.commit()


@router.get("/{item_id}/history", response_model=list[PricePointOut])
def item_history(item_id: int, store: str | None = None, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")

    listings = [l for l in item.listings if store is None or l.store == store]
    if not listings:
        return []
    store_by_listing_id = {l.id: l.store for l in listings}

    points = (
        db.query(PricePoint)
        .filter(PricePoint.listing_id.in_(store_by_listing_id.keys()))
        .order_by(PricePoint.scraped_at)
        .all()
    )
    return [
        PricePointOut(
            price=p.price,
            in_stock=p.in_stock,
            currency=p.currency,
            scraped_at=p.scraped_at,
            store=store_by_listing_id[p.listing_id],
        )
        for p in points
    ]


@router.post("/{item_id}/refresh")
def refresh_item(item_id: int, db: Session = Depends(get_db)):
    from app.scraping_service import scrape_listing

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")

    results = []
    for listing in item.listings:
        if not listing.active:
            continue
        point = scrape_listing(db, listing)
        results.append(
            {
                "listing_id": listing.id,
                "store": listing.store,
                "price": point.price if point else None,
                "error": listing.last_error,
            }
        )
    return {"scraped_at": datetime.datetime.now(datetime.timezone.utc), "results": results}
