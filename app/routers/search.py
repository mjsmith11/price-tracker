from fastapi import APIRouter, Query

from app.adapters import ADAPTERS
from app.schemas import CandidateOut

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[CandidateOut])
def search(q: str = Query(..., min_length=1), stores: str | None = None):
    """Search across all (or a filtered set of) store adapters for a query."""
    wanted = set(stores.split(",")) if stores else set(ADAPTERS.keys())
    results: list[CandidateOut] = []
    for name, adapter in ADAPTERS.items():
        if name not in wanted:
            continue
        for candidate in adapter.search(q):
            results.append(CandidateOut(**candidate.__dict__))
    return results


@router.get("/stores")
def list_stores():
    return sorted(ADAPTERS.keys())
