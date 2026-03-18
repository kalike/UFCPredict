"""Combo search router — exhaustive combinations of model versions.

F3: real worker integration replacing the completed_stub approach.
"""

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db
from lab_api.services import combo_search as combo_svc

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


class ComboRunStatus(BaseModel):
    is_running: bool
    study_id: int | None = None
    evaluated: int = 0
    total: int = 0
    best_value: float | None = None
    best_shorts: list[str] | None = None
    step: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


@router.post("/start", response_model=ComboStartResponse)
def start_combo(req: ComboSearchRequest, db: Session = Depends(get_db)) -> ComboStartResponse:
    existing = db.query(db_models.ComboSearchStudy).filter_by(name=req.name).one_or_none()
    if existing is not None:
        return ComboStartResponse(started=False, message=f"Study '{req.name}' already exists")
    study = db_models.ComboSearchStudy(
        name=req.name, status="queued", params=req.params,
    )
    db.add(study)
    db.commit()
    result = combo_svc.start_combo_search(req.params or {}, study.id)
    if not result["started"]:
        study.status = "rejected"
        db.commit()
        return ComboStartResponse(started=False, study_id=study.id, message=result.get("message"))
    return ComboStartResponse(started=True, study_id=study.id)


@router.get("/status", response_model=ComboRunStatus)
def status() -> ComboRunStatus:
    return ComboRunStatus(**combo_svc.get_status())


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
