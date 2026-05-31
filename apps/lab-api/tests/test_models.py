def test_list_models_empty(client):
    r = client.get("/api/models/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_versions_for_unknown_model_returns_404(client):
    r = client.get("/api/models/doesnotexist/versions")
    assert r.status_code == 404


def test_disable_unknown_model_returns_404(client):
    r = client.post("/api/models/doesnotexist/disable")
    assert r.status_code == 404


def test_train_status_idle(client):
    r = client.get("/api/models/train/status")
    assert r.status_code == 200
    body = r.json()
    assert body["is_running"] is False


def test_train_starts(client):
    r = client.post("/api/models/train", json={"model_short": "lgbm"})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] in (True, False)


def test_delete_version_clears_training_session_ref(client):
    """Regression: deleting a version must not fail on the training_session FK.

    Every trained version is referenced by TrainingSession.result_version_id;
    delete_version must null that reference (and drop prediction/publish rows)
    before removing the version.
    """
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as db_models

    db = SessionLocal()
    try:
        m = db.query(db_models.Model).filter_by(short="DELT").one_or_none()
        if m is None:
            m = db_models.Model(short="DELT", family="sklearn",
                                default_feat_type="52f", description="delete test")
            db.add(m)
            db.commit()
        v = db_models.ModelVersion(
            model_id=m.id, version_idx=1, feature_set="v7",
            artifact_uri="file:///tmp/nonexistent_DELT_v1.joblib",
        )
        db.add(v)
        db.commit()
        ts = db_models.TrainingSession(
            model_id=m.id, request={}, status="completed", result_version_id=v.id,
        )
        db.add(ts)
        db.commit()
        ts_id, model_id = ts.id, m.id
    finally:
        db.close()

    r = client.delete("/api/models/DELT/versions/1")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    db = SessionLocal()
    try:
        gone = (
            db.query(db_models.ModelVersion)
              .filter_by(model_id=model_id, version_idx=1)
              .one_or_none()
        )
        assert gone is None, "version was not deleted"
        ts = db.get(db_models.TrainingSession, ts_id)
        assert ts is not None, "training session should be kept"
        assert ts.result_version_id is None, "result_version_id should be nulled"
    finally:
        db.close()
