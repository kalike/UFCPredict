from ufc_core.db import Base, models as db_models
from ufc_core.models.registry import ModelRegistry


def test_register_activate_get_active(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    db_session.add(db_models.Model(
        short="lgbm", family="sklearn", default_feat_type="52f", description="LightGBM"
    ))
    db_session.commit()

    reg = ModelRegistry(db_session)
    v_idx = reg.register_version(
        "lgbm",
        feature_set="v7",
        hp_json={"lr": 0.05},
        metrics_json={"accuracy": 0.66},
        artifact_uri="s3://b/k.tar.gz",
    )
    reg.set_active("lgbm", v_idx)
    active = reg.get_active("lgbm")
    assert active["version_idx"] == v_idx
    assert active["feature_set"] == "v7"
    assert active["artifact_uri"] == "s3://b/k.tar.gz"


def test_register_version_increments(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    db_session.add(db_models.Model(
        short="xgb", family="sklearn", default_feat_type="52f", description="XGBoost"
    ))
    db_session.commit()

    reg = ModelRegistry(db_session)
    v1 = reg.register_version("xgb", feature_set="v6", hp_json=None,
                              metrics_json=None, artifact_uri="s3://x/v1")
    v2 = reg.register_version("xgb", feature_set="v7", hp_json=None,
                              metrics_json=None, artifact_uri="s3://x/v2")
    assert v1 == 1
    assert v2 == 2

    versions = reg.list_versions("xgb")
    assert len(versions) == 2


def test_disable_removes_active(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    db_session.add(db_models.Model(
        short="mlp", family="pytorch", default_feat_type="35f", description="MLP"
    ))
    db_session.commit()

    reg = ModelRegistry(db_session)
    v = reg.register_version("mlp", feature_set="v7", hp_json=None,
                             metrics_json=None, artifact_uri="local://m.pt")
    reg.set_active("mlp", v)
    assert reg.get_active("mlp") is not None

    reg.disable("mlp")
    assert reg.get_active("mlp") is None
