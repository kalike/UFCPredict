"""HP search router — Optuna queue (stub).

F2 stub: records HpSearchStudy/Trial rows in DB but does not actually
run Optuna trials. The API surface matches what the UI expects so the
end-to-end flow renders correctly; the worker is wired later.
"""

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

router = APIRouter(prefix="/api/hp-search", tags=["hp_search"])


class HpSearchRequest(BaseModel):
    model_short: str
    feature_set: str = "v7"
    feat_type: str = "auto"
    dataset: str = "since2010"
    n_trials: int = 50
    params: dict | None = None


class HpStudySummary(BaseModel):
    id: int
    model_short: str
    feature_set: str
    feat_type: str
    dataset: str
    n_trials: int
    status: str
    started_at: str
    finished_at: str | None
    params: dict | None


class HpStartResponse(BaseModel):
    started: bool
    study_id: int | None = None
    message: str | None = None


@router.post("/start", response_model=HpStartResponse)
def start_search(req: HpSearchRequest, db: Session = Depends(get_db)) -> HpStartResponse:
    study = db_models.HpSearchStudy(
        model_short=req.model_short,
        feature_set=req.feature_set,
        feat_type=req.feat_type,
        dataset=req.dataset,
        n_trials=req.n_trials,
        status="running",
        params=req.params,
    )
    db.add(study)
    db.commit()
    # TODO: kick off real Optuna worker here. For F2 stub, immediately mark as completed.
    study.status = "completed_stub"
    study.finished_at = datetime.now(UTC)
    db.commit()
    return HpStartResponse(started=True, study_id=study.id)


@router.get("/studies", response_model=list[HpStudySummary])
def list_studies(limit: int = 50, db: Session = Depends(get_db)) -> list[HpStudySummary]:
    rows = (
        db.query(db_models.HpSearchStudy)
          .order_by(db_models.HpSearchStudy.started_at.desc())
          .limit(limit).all()
    )
    return [HpStudySummary(
        id=s.id, model_short=s.model_short, feature_set=s.feature_set,
        feat_type=s.feat_type, dataset=s.dataset, n_trials=s.n_trials,
        status=s.status,
        started_at=s.started_at.isoformat() if s.started_at else "",
        finished_at=s.finished_at.isoformat() if s.finished_at else None,
        params=s.params,
    ) for s in rows]


class HpTrialSummary(BaseModel):
    id: int
    study_id: int
    trial_idx: int
    params: dict
    value: float | None
    status: str


@router.get("/studies/{study_id}/trials", response_model=list[HpTrialSummary])
def list_trials(study_id: int, db: Session = Depends(get_db)) -> list[HpTrialSummary]:
    if db.query(db_models.HpSearchStudy).filter_by(id=study_id).one_or_none() is None:
        raise HTTPException(404, f"Study {study_id} not found")
    rows = (
        db.query(db_models.HpSearchTrial)
          .filter_by(study_id=study_id)
          .order_by(db_models.HpSearchTrial.trial_idx.asc())
          .all()
    )
    return [HpTrialSummary(
        id=t.id, study_id=t.study_id, trial_idx=t.trial_idx,
        params=t.params, value=t.value, status=t.status,
    ) for t in rows]
