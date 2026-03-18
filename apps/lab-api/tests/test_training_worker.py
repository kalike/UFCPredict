"""End-to-end training worker test — requires real scraped data in ufc_lab_test."""

import time
import pytest

from ufc_core.db.base import Base
from ufc_core.db.engine import engine as test_engine_default
from ufc_core.db import models as db_models
from ufc_core.db.engine import SessionLocal


def _seed_model_catalog(db):
    """Ensure at least LGBM and Deep model rows exist for tests."""
    for short, family, description in [
        ("LGBM", "sklearn", "LightGBM"),
        ("Deep", "pytorch", "DeepMLP ResNet"),
    ]:
        existing = db.query(db_models.Model).filter_by(short=short).one_or_none()
        if existing is None:
            db.add(db_models.Model(
                short=short, family=family,
                default_feat_type="35f", description=description,
            ))
    db.commit()


def test_training_unsupported_model_marks_not_implemented(client, test_engine):
    """Calling train on an unsupported model_short returns not_implemented status."""
    Base.metadata.create_all(test_engine)
    db = SessionLocal()
    try:
        _seed_model_catalog(db)
    finally:
        db.close()

    # "UNSUPPORTED_XYZ123" is not in SUPPORTED; it should trigger not_implemented.
    r = client.post("/api/models/train", json={"model_short": "UNSUPPORTED_XYZ123"})
    assert r.status_code == 200

    # Poll for completion (the job runs in a daemon thread)
    for _ in range(30):
        time.sleep(0.1)
        s = client.get("/api/models/train/status").json()
        if not s["is_running"]:
            break

    s = client.get("/api/models/train/status").json()
    assert s["is_running"] is False, f"Job still running after timeout: {s}"
    assert "not_implemented" in (s.get("step") or ""), (
        f"Expected 'not_implemented' in step, got: {s}"
    )
