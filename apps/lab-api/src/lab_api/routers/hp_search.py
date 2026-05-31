"""HP search router — Optuna real worker.

Kicks off a background Optuna study (LGBM / XGB supported in first pass).
Other families return started=False with a message.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db
from lab_api.services import hp_search as hp_svc
from lab_api.services import training as training_svc

router = APIRouter(prefix="/api/hp-search", tags=["hp_search"])


class HpObjective(BaseModel):
    metric: str
    direction: str = "maximize"


class HpSearchRequest(BaseModel):
    model_short: str
    feature_set: str = "v7"
    feat_type: str = "auto"
    dataset: str = "since2010"
    min_fights: int = 0
    n_trials: int = 50
    objectives: list[HpObjective] | None = None
    # When > 0, optimize a single penalized objective: primary − λ·overfit
    # (overrides multi-objective Pareto). λ = overfit_penalty.
    overfit_penalty: float = 0.0
    # A/B fighter-swap augmentation during search; defaults ON (parity with the
    # legacy backend's D+Aug PRO models). Persisted so adopt trains the same way.
    augment: bool = True
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
        status="queued",
        # Persist min_fights + augment so the adopt flow rebuilds the exact job.
        params={**(req.params or {}), "min_fights": req.min_fights, "augment": req.augment},
    )
    db.add(study)
    db.commit()
    result = hp_svc.start_hp_search(req.model_dump(), study.id)
    if not result["started"]:
        # Mark queued study as rejected so it doesn't sit in 'queued' forever
        study.status = "rejected"
        db.commit()
        return HpStartResponse(started=False, study_id=study.id, message=result.get("message"))
    return HpStartResponse(started=True, study_id=study.id)


class HpRunStatus(BaseModel):
    is_running: bool
    study_id: int | None = None
    model_short: str | None = None
    completed_trials: int = 0
    n_trials: int = 0
    best_value: float | None = None
    objectives: list[dict] = []
    step: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


@router.get("/status", response_model=HpRunStatus)
def status() -> HpRunStatus:
    return HpRunStatus(**hp_svc.get_status())


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


def _live_study_id() -> int | None:
    """The study actually executing right now (in-memory worker), if any.

    A study whose DB row still says 'running' after a server restart is a
    stale/zombie row, NOT the live one — it must remain deletable.
    """
    st = hp_svc.get_status()
    return st.get("study_id") if st.get("is_running") else None


@router.delete("/studies/{study_id}")
def delete_study(study_id: int, db: Session = Depends(get_db)) -> dict:
    """Delete an HP study and its trials (cascade). Refuses only if it's the
    one actively running in the worker (not a stale 'running' DB row)."""
    study = db.query(db_models.HpSearchStudy).filter_by(id=study_id).one_or_none()
    if study is None:
        raise HTTPException(404, f"Study {study_id} not found")
    if _live_study_id() == study_id:
        raise HTTPException(409, "Cannot delete the study that is currently running")
    db.delete(study)
    db.commit()
    return {"ok": True}


class DeleteStudiesRequest(BaseModel):
    ids: list[int]


@router.post("/studies/delete-batch")
def delete_studies_batch(req: DeleteStudiesRequest, db: Session = Depends(get_db)) -> dict:
    """Delete several studies at once. Skips the actively-running one (if any)."""
    live = _live_study_id()
    deleted = 0
    skipped: list[int] = []
    for sid in req.ids:
        if sid == live:
            skipped.append(sid)
            continue
        study = db.query(db_models.HpSearchStudy).filter_by(id=sid).one_or_none()
        if study is None:
            continue
        db.delete(study)
        deleted += 1
    db.commit()
    return {"deleted": deleted, "skipped": skipped}


class HpTrialSummary(BaseModel):
    id: int
    study_id: int
    trial_idx: int
    params: dict
    value: float | None
    metrics: dict | None
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
        params=t.params, value=t.value, metrics=t.metrics, status=t.status,
    ) for t in rows]


class HpAdoptItem(BaseModel):
    study_id: int
    trial_idx: int


class HpAdoptRequest(BaseModel):
    items: list[HpAdoptItem]


class HpAdoptResponse(BaseModel):
    started: bool
    n_jobs: int = 0
    message: str | None = None


@router.post("/adopt", response_model=HpAdoptResponse)
def adopt_trials(req: HpAdoptRequest, db: Session = Depends(get_db)) -> HpAdoptResponse:
    """Adopt selected trials and launch their real training (one job per trial).

    Each job re-runs the full lab training pipeline (_train_one_job) with the
    trial's hyperparameters and the originating study's feature_set/feat_type/
    dataset/min_fights, registering a new model version on success.
    """
    if not req.items:
        raise HTTPException(400, "No trials to adopt")

    jobs: list[dict] = []
    for it in req.items:
        study = db.query(db_models.HpSearchStudy).filter_by(id=it.study_id).one_or_none()
        if study is None:
            raise HTTPException(404, f"Study {it.study_id} not found")
        trial = (
            db.query(db_models.HpSearchTrial)
              .filter_by(study_id=it.study_id, trial_idx=it.trial_idx)
              .one_or_none()
        )
        if trial is None:
            raise HTTPException(404, f"Trial {it.trial_idx} not found in study {it.study_id}")
        min_fights = int((study.params or {}).get("min_fights", 0))
        # Train the adopted model the same way it was searched (augment ON by
        # default for studies created before this field existed).
        augment = bool((study.params or {}).get("augment", True))
        jobs.append({
            "model_short": study.model_short,
            "feature_set": study.feature_set,
            "feat_type": study.feat_type,
            "dataset": study.dataset,
            "min_fights": min_fights,
            "use_pit": True,
            "augment": augment,
            "origin": "hp_search",
            "hp_params": trial.params,
        })

    result = training_svc.start_batch(jobs)
    return HpAdoptResponse(
        started=result.get("started", False),
        n_jobs=result.get("n_jobs", 0),
        message=result.get("message"),
    )
