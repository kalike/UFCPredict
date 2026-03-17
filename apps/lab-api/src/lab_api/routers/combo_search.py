"""Combo search router — exhaustive combinations of model versions (stub).

F2 stub: records ComboSearchStudy/Trial rows in DB but does not actually
evaluate combinations. The worker integration comes later.
"""

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

router = APIRouter(prefix="/api/combo-search", tags=["combo_search"])


class ComboSearchRequest(BaseModel):
    name: str
    params: dict | None = None


class ComboStartResponse(BaseModel):
    started: bool
    study_id: int | None = None
    message: str | None = None


class ComboStudySummary(BaseModel):
    id: int
    name: str
    status: str
    started_at: str
    finished_at: str | None
    params: dict | None


@router.post("/start", response_model=ComboStartResponse)
def start_combo(req: ComboSearchRequest, db: Session = Depends(get_db)) -> ComboStartResponse:
    # Uniqueness check
    existing = db.query(db_models.ComboSearchStudy).filter_by(name=req.name).one_or_none()
    if existing is not None:
        return ComboStartResponse(started=False, message=f"Study '{req.name}' already exists")

    study = db_models.ComboSearchStudy(
        name=req.name, status="running", params=req.params,
    )
    db.add(study)
    db.commit()
    # TODO: kick off real combo worker. For F2 stub, mark as completed immediately.
    study.status = "completed_stub"
    study.finished_at = datetime.now(UTC)
    db.commit()
    return ComboStartResponse(started=True, study_id=study.id)


@router.get("/studies", response_model=list[ComboStudySummary])
def list_combo_studies(limit: int = 50, db: Session = Depends(get_db)) -> list[ComboStudySummary]:
    rows = (
        db.query(db_models.ComboSearchStudy)
          .order_by(db_models.ComboSearchStudy.started_at.desc())
          .limit(limit).all()
    )
    return [ComboStudySummary(
        id=s.id, name=s.name, status=s.status,
        started_at=s.started_at.isoformat() if s.started_at else "",
        finished_at=s.finished_at.isoformat() if s.finished_at else None,
        params=s.params,
    ) for s in rows]


class ComboTrialSummary(BaseModel):
    id: int
    study_id: int
    trial_idx: int
    params: dict
    value: float | None
    status: str


@router.get("/studies/{study_id}/trials", response_model=list[ComboTrialSummary])
def list_combo_trials(study_id: int, db: Session = Depends(get_db)) -> list[ComboTrialSummary]:
    if db.query(db_models.ComboSearchStudy).filter_by(id=study_id).one_or_none() is None:
        raise HTTPException(404, f"Study {study_id} not found")
    rows = (
        db.query(db_models.ComboSearchTrial)
          .filter_by(study_id=study_id)
          .order_by(db_models.ComboSearchTrial.trial_idx.asc())
          .all()
    )
    return [ComboTrialSummary(
        id=t.id, study_id=t.study_id, trial_idx=t.trial_idx,
        params=t.params, value=t.value, status=t.status,
    ) for t in rows]
