import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Query

from app.adapters import ADAPTERS
from app.schemas import CandidateOut

router = APIRouter(prefix="/api/search", tags=["search"])
logger = logging.getLogger("price_tracker.search")


@router.get("", response_model=list[CandidateOut])
def search(q: str = Query(..., min_length=1), stores: str | None = None):
    """Search across all (or a filtered set of) store adapters for a query.

    Each adapter drives its own headless browser and can take several
    seconds — longer if a store is throttling. Run in parallel so total
    latency is bounded by the slowest single store instead of the sum of
    all of them (sequentially, searching all 7 stores took ~50s).
    """
    wanted = set(stores.split(",")) if stores else set(ADAPTERS.keys())
    adapters = [(name, adapter) for name, adapter in ADAPTERS.items() if name in wanted]
    if not adapters:
        return []

    results: list[CandidateOut] = []
    with ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        future_to_name = {pool.submit(adapter.search, q): name for name, adapter in adapters}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                candidates = future.result()
            except Exception:
                logger.exception("adapter %r raised during search (should degrade gracefully instead)", name)
                continue
            results.extend(CandidateOut(**c.__dict__) for c in candidates)
    return results


@router.get("/stores")
def list_stores():
    return sorted(ADAPTERS.keys())
