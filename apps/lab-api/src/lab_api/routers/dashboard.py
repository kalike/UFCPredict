"""Dashboard router — aggregated KPIs over past events."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from lab_api.deps import get_data_store, get_db
from lab_api.services import dashboard as dsvc
from lab_api.services import recalculation as recalc_svc

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(
    min_fights: int = Query(0, ge=0),
    with_odds: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    ds = get_data_store()
    return dsvc.get_summary(db, ds, min_fights=min_fights, with_odds=with_odds)


@router.get("/event-fights")
def event_fights(
    event: str,
    min_fights: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    ds = get_data_store()
    out = dsvc.get_event_fights(db, ds, event, min_fights=min_fights)
    if not out["fights"]:
        raise HTTPException(404, f"No fights found for event '{event}'")
    return out


@router.get("/recalculation-status")
def recalculation_status() -> dict:
    return recalc_svc.get_status()


@router.post("/invalidate-cache")
def invalidate_cache(
    recalculate: bool = True,
    min_fights: int = Query(0, ge=0),
) -> dict:
    dsvc.invalidate()
    if recalculate and not recalc_svc.get_status()["is_running"]:
        res = recalc_svc.start_recalculation(None)
        return {
            "ok": True,
            "recalculating": res.get("started", False),
            "message": res.get("message"),
            "min_fights": min_fights,
        }
    return {"ok": True, "recalculating": False, "min_fights": min_fights}
