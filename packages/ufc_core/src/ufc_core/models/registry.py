"""DB-backed model registry — replaces the legacy model_registry.json.

Persists `model`, `model_version`, and `active_model` rows.
Each method runs inside the session passed at construction time;
callers handle commit/rollback at their own boundary.
"""

from datetime import datetime, UTC

from sqlalchemy.orm import Session

from ufc_core.db import models as db_models


class ModelRegistry:
    """DB-backed replacement for the legacy model_registry.json."""

    def __init__(self, db: Session):
        self.db = db

    def _model(self, short: str) -> db_models.Model:
        m = (
            self.db.query(db_models.Model).filter_by(short=short).one_or_none()
        )
        if m is None:
            raise KeyError(f"Model '{short}' not registered")
        return m

    def register_version(
        self,
        short: str,
        *,
        feature_set: str,
        hp_json: dict | None,
        metrics_json: dict | None,
        artifact_uri: str,
        note: str | None = None,
    ) -> int:
        m = self._model(short)
        max_idx = (
            self.db.query(db_models.ModelVersion.version_idx)
                .filter_by(model_id=m.id)
                .order_by(db_models.ModelVersion.version_idx.desc())
                .first()
        )
        next_idx = (max_idx[0] + 1) if max_idx else 1

        v = db_models.ModelVersion(
            model_id=m.id,
            version_idx=next_idx,
            feature_set=feature_set,
            hp_json=hp_json,
            metrics_json=metrics_json,
            artifact_uri=artifact_uri,
            note=note,
            trained_at=datetime.now(UTC),
        )
        self.db.add(v)
        self.db.flush()
        return next_idx

    def set_active(self, short: str, version_idx: int) -> None:
        m = self._model(short)
        v = (
            self.db.query(db_models.ModelVersion)
                .filter_by(model_id=m.id, version_idx=version_idx)
                .one()
        )
        existing = (
            self.db.query(db_models.ActiveModel)
                .filter_by(model_id=m.id)
                .one_or_none()
        )
        if existing is None:
            self.db.add(db_models.ActiveModel(model_id=m.id, version_id=v.id))
        else:
            existing.version_id = v.id
            existing.activated_at = datetime.now(UTC)
        self.db.flush()

    def get_active(self, short: str) -> dict | None:
        m = self._model(short)
        am = (
            self.db.query(db_models.ActiveModel)
                .filter_by(model_id=m.id)
                .one_or_none()
        )
        if am is None:
            return None
        v = (
            self.db.query(db_models.ModelVersion)
                .filter_by(id=am.version_id)
                .one()
        )
        return {
            "short": short,
            "version_idx": v.version_idx,
            "feature_set": v.feature_set,
            "artifact_uri": v.artifact_uri,
            "metrics_json": v.metrics_json,
            "hp_json": v.hp_json,
        }

    def list_versions(self, short: str) -> list[dict]:
        m = self._model(short)
        rows = (
            self.db.query(db_models.ModelVersion)
                .filter_by(model_id=m.id)
                .order_by(db_models.ModelVersion.version_idx.asc())
                .all()
        )
        return [
            {
                "version_idx": r.version_idx,
                "feature_set": r.feature_set,
                "metrics_json": r.metrics_json,
                "hp_json": r.hp_json,
                "artifact_uri": r.artifact_uri,
                "starred": r.starred,
                "was_production": r.was_production,
                "note": r.note,
            }
            for r in rows
        ]

    def disable(self, short: str) -> None:
        m = self._model(short)
        existing = (
            self.db.query(db_models.ActiveModel)
                .filter_by(model_id=m.id)
                .one_or_none()
        )
        if existing is not None:
            self.db.delete(existing)
            self.db.flush()
