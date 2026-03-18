"""Recalculation router — re-predict over historical events."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db
from lab_api.services import recalculation as recalc_svc

router = APIRouter(prefix="/api/recalculation", tags=["recalculation"])


class RecalcRequest(BaseModel):
    event_ids: list[int] | None = None


class RecalcStartResponse(BaseModel):
    started: bool
    message: str | None = None


class RecalcStatus(BaseModel):
    is_running: bool
    started_at: str | None = None
    finished_at: str | None = None
    total_events: int = 0
    completed_events: int = 0
    skipped_events: int = 0
    step: str | None = None
    error: str | None = None


class RecalcRun(BaseModel):
    session_id: int
    event_id: int
    event_name: str
    created_at: str


@router.post("/run", response_model=RecalcStartResponse)
def start_recalc(req: RecalcRequest) -> RecalcStartResponse:
    result = recalc_svc.start_recalculation(req.event_ids)
    if not result["started"]:
        return RecalcStartResponse(started=False, message=result.get("message"))
    return RecalcStartResponse(started=True)


@router.get("/status", response_model=RecalcStatus)
def status() -> RecalcStatus:
    return RecalcStatus(**recalc_svc.get_status())


@router.get("/runs", response_model=list[RecalcRun])
def list_runs(limit: int = 30, db: Session = Depends(get_db)) -> list[RecalcRun]:
    """Recent lab_recalc prediction sessions."""
    rows = (
        db.query(db_models.PredictionSession)
          .filter_by(source="lab_recalc")
          .order_by(db_models.PredictionSession.created_at.desc())
          .limit(limit).all()
    )
    out = []
    for s in rows:
        ev = db.query(db_models.Event).filter_by(id=s.event_id).one()
        out.append(RecalcRun(
            session_id=s.id, event_id=s.event_id, event_name=ev.name,
            created_at=s.created_at.isoformat() if s.created_at else "",
        ))
    return out
