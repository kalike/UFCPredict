"""System router — health + model registry view."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models
from ufc_core.db.engine import engine

from lab_api.deps import get_db

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness probe: returns OK if API is reachable. Also checks DB connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(db_models.Event.__table__.select().limit(1))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e!r}"
    return {"status": "ok", "db": db_status}


@router.get("/registry")
def list_registry(db: Session = Depends(get_db)) -> dict:
    """List all registered models + their active version (if any)."""
    out: dict[str, dict | None] = {}
    models = db.query(db_models.Model).all()
    for m in models:
        active = (
            db.query(db_models.ActiveModel).filter_by(model_id=m.id).one_or_none()
        )
        if active is None:
            out[m.short] = None
            continue
        v = (
            db.query(db_models.ModelVersion).filter_by(id=active.version_id).one()
        )
        out[m.short] = {
            "version_idx": v.version_idx,
            "feature_set": v.feature_set,
            "artifact_uri": v.artifact_uri,
            "trained_at": v.trained_at.isoformat() if v.trained_at else None,
        }
    return {"models": out}
