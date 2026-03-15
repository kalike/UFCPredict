from ufc_core.db import Base, models


def test_model_version_active_unique(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    m = models.Model(short="lgbm", family="sklearn", default_feat_type="52f",
                     description="LightGBM ensemble")
    db_session.add(m)
    db_session.flush()

    v1 = models.ModelVersion(model_id=m.id, version_idx=1, feature_set="v7",
                            hp_json={"lr": 0.05}, metrics_json={"accuracy": 0.66},
                            artifact_uri="s3://b/k.tar.gz")
    db_session.add(v1)
    db_session.flush()

    am = models.ActiveModel(model_id=m.id, version_id=v1.id)
    db_session.add(am)
    db_session.flush()
    assert am.model_id == m.id
