"""Predictions router — serve cached predictions per event (F2 stub).

Real ensemble inference is wired later. For now, lists events and any
prediction_cache entries that exist.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class EventSummary(BaseModel):
    id: int
    name: str
    date: str | None
    status: str
    fight_count: int


class CacheEntry(BaseModel):
    event_id: int
    model_version_id: int
    computed_at: str
    expires_at: str | None
    payload: dict


@router.get("/events", response_model=list[EventSummary])
def list_events(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[EventSummary]:
    """List events filtered by status."""
    q = db.query(db_models.Event)
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(db_models.Event.date.desc().nullslast()).limit(limit).all()
    out = []
    for e in rows:
        fc = db.query(db_models.Fight).filter_by(event_id=e.id).count()
        out.append(EventSummary(
            id=e.id, name=e.name,
            date=e.date.isoformat() if e.date else None,
            status=e.status, fight_count=fc,
        ))
    return out


@router.get("/cache/{event_id}", response_model=list[CacheEntry])
def event_cache(event_id: int, db: Session = Depends(get_db)) -> list[CacheEntry]:
    if db.query(db_models.Event).filter_by(id=event_id).one_or_none() is None:
        raise HTTPException(404, f"Event {event_id} not found")
    rows = (
        db.query(db_models.PredictionCache)
          .filter_by(event_id=event_id)
          .order_by(db_models.PredictionCache.computed_at.desc())
          .all()
    )
    return [CacheEntry(
        event_id=c.event_id, model_version_id=c.model_version_id,
        computed_at=c.computed_at.isoformat() if c.computed_at else "",
        expires_at=c.expires_at.isoformat() if c.expires_at else None,
        payload=c.payload,
    ) for c in rows]
