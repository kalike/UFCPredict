"""Models router — registry views + training trigger.

The lab trains four canonical model families (XGB, RF, CB, Deep). The
trainable catalog is exposed via GET /api/models/trainable so the UI can
render a fixed dropdown instead of a free-text field.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models
from ufc_core.models.registry import ModelRegistry

from lab_api.deps import get_db
from lab_api.services import training as training_svc

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelSummary(BaseModel):
    short: str
    family: str
    default_feat_type: str
    description: str | None
    active_version: int | None


class TrainableModel(BaseModel):
    short: str
    label: str
    family: str


class VersionSummary(BaseModel):
    version_idx: int
    feature_set: str
    artifact_uri: str
    metrics_json: dict | None
    hp_json: dict | None
    starred: bool
    was_production: bool
    note: str | None


class TrainRequest(BaseModel):
    model_short: str
    dataset: str = "since2010"
    augment: bool | None = None
    feature_set: str = "v7"
    feat_type: str = "auto"
    test_cutoff: int | str = 2024
    min_fights: int = 0
    # PIT on by default: features must use only pre-fight history (no temporal
    # leakage). Matches HP search, which always trains with use_pit=True.
    use_pit: bool = True


class BatchTrainRequest(BaseModel):
    jobs: list[TrainRequest]


class BatchTrainResponse(BaseModel):
    started: bool
    message: str | None = None
    n_jobs: int = 0


class TrainResponse(BaseModel):
    started: bool
    message: str | None = None
    training_session_id: int | None = None


class TrainStatus(BaseModel):
    is_running: bool
    started_at: str | None = None
    finished_at: str | None = None
    model_short: str | None = None
    step: str | None = None
    pct: float = 0.0
    job_index: int = 0
    n_jobs: int = 0
    job_label: str | None = None
    result_version_id: int | None = None
    logs: list[str] = []
    results: list[dict] = []
    error: str | None = None


class MarkRequest(BaseModel):
    starred: bool | None = None
    note: str | None = None


@router.get("/trainable", response_model=list[TrainableModel])
def list_trainable() -> list[TrainableModel]:
    """List the canonical models the lab can train (feeds the UI dropdown)."""
    return [
        TrainableModel(short=short, label=meta["label"], family=meta["family"])
        for short, meta in training_svc.TRAINABLE.items()
    ]


@router.get("/", response_model=list[ModelSummary])
def list_models(db: Session = Depends(get_db)) -> list[ModelSummary]:
    """List all registered models with their active version (if any)."""
    out = []
    for m in db.query(db_models.Model).all():
        am = (
            db.query(db_models.ActiveModel)
              .filter_by(model_id=m.id)
              .one_or_none()
        )
        active_idx = None
        if am is not None:
            v = db.query(db_models.ModelVersion).filter_by(id=am.version_id).one()
            active_idx = v.version_idx
        out.append(ModelSummary(
            short=m.short, family=m.family,
            default_feat_type=m.default_feat_type,
            description=m.description, active_version=active_idx,
        ))
    return out


@router.get("/{short}/versions", response_model=list[VersionSummary])
def list_versions(short: str, db: Session = Depends(get_db)) -> list[VersionSummary]:
    try:
        rows = ModelRegistry(db).list_versions(short)
    except KeyError:
        raise HTTPException(404, f"Model '{short}' not registered")
    return [VersionSummary(**r) for r in rows]


@router.post("/{short}/versions/{version_idx}/activate")
def activate_version(short: str, version_idx: int, db: Session = Depends(get_db)) -> dict:
    try:
        ModelRegistry(db).set_active(short, version_idx)
    except KeyError as e:
        raise HTTPException(404, str(e))
    db.commit()
    return {"ok": True, "short": short, "version_idx": version_idx}


@router.post("/{short}/disable")
def disable_model(short: str, db: Session = Depends(get_db)) -> dict:
    try:
        ModelRegistry(db).disable(short)
    except KeyError:
        raise HTTPException(404, f"Model '{short}' not registered")
    db.commit()
    return {"ok": True, "short": short}


@router.patch("/{short}/versions/{version_idx}/mark")
def mark_version(short: str, version_idx: int, req: MarkRequest,
                 db: Session = Depends(get_db)) -> dict:
    m = db.query(db_models.Model).filter_by(short=short).one_or_none()
    if m is None:
        raise HTTPException(404, f"Model '{short}' not registered")
    v = (
        db.query(db_models.ModelVersion)
          .filter_by(model_id=m.id, version_idx=version_idx)
          .one_or_none()
    )
    if v is None:
        raise HTTPException(404, f"Version {version_idx} not found for '{short}'")
    if req.starred is not None:
        v.starred = req.starred
    if req.note is not None:
        v.note = req.note
    db.commit()
    return {"ok": True, "starred": v.starred, "note": v.note}


def _delete_artifact(uri: str | None) -> None:
    """Best-effort removal of a version's on-disk artifact (file:// URIs)."""
    if not uri or not uri.startswith("file://"):
        return
    from pathlib import Path
    try:
        Path(uri[len("file://"):]).unlink(missing_ok=True)
    except OSError:
        pass


def _purge_version(db: Session, v) -> None:
    """Clear dependent refs, drop the on-disk artifact, and delete the version.

    These FKs have no ON DELETE, so the row delete would otherwise fail (every
    trained version is referenced by its TrainingSession.result_version_id, and
    possibly prediction_cache / publish_run rows). The caller commits.
    """
    db.query(db_models.TrainingSession).filter_by(result_version_id=v.id).update(
        {"result_version_id": None}, synchronize_session=False
    )
    db.query(db_models.PredictionCache).filter_by(model_version_id=v.id).delete(
        synchronize_session=False
    )
    db.query(db_models.PublishRun).filter_by(model_version_id=v.id).delete(
        synchronize_session=False
    )
    _delete_artifact(v.artifact_uri)
    db.delete(v)


class DeleteBatchRequest(BaseModel):
    version_idxs: list[int]


@router.delete("/{short}/versions/{version_idx}")
def delete_version(short: str, version_idx: int, db: Session = Depends(get_db)) -> dict:
    m = db.query(db_models.Model).filter_by(short=short).one_or_none()
    if m is None:
        raise HTTPException(404, f"Model '{short}' not registered")
    v = (
        db.query(db_models.ModelVersion)
          .filter_by(model_id=m.id, version_idx=version_idx)
          .one_or_none()
    )
    if v is None:
        raise HTTPException(404, f"Version {version_idx} not found")
    am = db.query(db_models.ActiveModel).filter_by(model_id=m.id).one_or_none()
    if am and am.version_id == v.id:
        raise HTTPException(400, "Cannot delete the active version; disable or switch first.")

    _purge_version(db, v)
    db.commit()
    return {"ok": True}


@router.post("/{short}/versions/delete-batch")
def delete_versions_batch(short: str, req: DeleteBatchRequest,
                          db: Session = Depends(get_db)) -> dict:
    """Delete several versions at once. Skips the active version (reported back)."""
    m = db.query(db_models.Model).filter_by(short=short).one_or_none()
    if m is None:
        raise HTTPException(404, f"Model '{short}' not registered")
    am = db.query(db_models.ActiveModel).filter_by(model_id=m.id).one_or_none()
    active_vid = am.version_id if am else None

    deleted: list[int] = []
    skipped: list[dict] = []
    for idx in req.version_idxs:
        v = (
            db.query(db_models.ModelVersion)
              .filter_by(model_id=m.id, version_idx=idx)
              .one_or_none()
        )
        if v is None:
            skipped.append({"version_idx": idx, "reason": "not found"})
            continue
        if active_vid is not None and v.id == active_vid:
            skipped.append({"version_idx": idx, "reason": "active"})
            continue
        _purge_version(db, v)
        deleted.append(idx)
    db.commit()
    return {"deleted": deleted, "skipped": skipped}


@router.post("/train", response_model=TrainResponse)
def train(req: TrainRequest) -> TrainResponse:
    result = training_svc.start_training(req.model_dump())
    if not result["started"]:
        return TrainResponse(started=False, message=result.get("message"))
    return TrainResponse(
        started=True,
        training_session_id=result.get("training_session_id"),
    )


@router.post("/retrain/batch", response_model=BatchTrainResponse)
def retrain_batch(req: BatchTrainRequest) -> BatchTrainResponse:
    """Launch a sequential batch of training jobs (the retrain queue)."""
    jobs = [j.model_dump() for j in req.jobs]
    result = training_svc.start_batch(jobs)
    if not result["started"]:
        return BatchTrainResponse(started=False, message=result.get("message"))
    return BatchTrainResponse(started=True, n_jobs=result.get("n_jobs", len(jobs)))


@router.get("/train/status", response_model=TrainStatus)
def train_status() -> TrainStatus:
    return TrainStatus(**training_svc.get_status())
