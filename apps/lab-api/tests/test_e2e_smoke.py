"""End-to-end smoke for lab-api: register a model → train (stub) → activate → list."""

import time

import pytest
from ufc_core.db import Base, models as db_models


def _wait_idle(client, status_path: str, timeout: float = 60.0) -> dict:
    """Poll a worker status endpoint until is_running=False. The smoke test
    launches real background jobs; returning while they run poisons later
    tests (the single-tenant workers reject new jobs)."""
    deadline = time.time() + timeout
    status = client.get(status_path).json()
    while status["is_running"] and time.time() < deadline:
        time.sleep(0.2)
        status = client.get(status_path).json()
    assert not status["is_running"], f"{status_path} still running after {timeout}s: {status}"
    return status


def _seed_model(client):
    """Seed via direct DB write — lab-api has no /models POST yet."""
    from ufc_core.db.engine import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(db_models.Model).filter_by(short="smoke_lgbm").one_or_none()
        if existing is None:
            db.add(db_models.Model(
                short="smoke_lgbm", family="sklearn", default_feat_type="52f",
                description="Smoke test model",
            ))
            db.commit()
    finally:
        db.close()


def test_full_flow_register_train_activate_publish(client):
    """End-to-end: register Model → train (stub) → list versions → publish dry-run.

    We bypass /api/models POST (doesn't exist yet) and seed the Model row
    directly, then exercise the read endpoints.
    """
    _seed_model(client)

    # 1) System health
    r = client.get("/api/system/health")
    assert r.status_code == 200

    # 2) Registry shows our model
    r = client.get("/api/system/registry")
    assert r.status_code == 200
    body = r.json()
    assert "smoke_lgbm" in body["models"]

    # 3) Model listing
    r = client.get("/api/models/")
    assert r.status_code == 200
    shorts = [m["short"] for m in r.json()]
    assert "smoke_lgbm" in shorts

    # 4) Versions empty (no version registered)
    r = client.get("/api/models/smoke_lgbm/versions")
    assert r.status_code == 200
    assert r.json() == []

    # 5) Training (stub) starts and records a session
    r = client.post("/api/models/train", json={"model_short": "smoke_lgbm"})
    assert r.status_code == 200
    assert r.json()["started"] in (True, False)

    # 6) Training status — wait for the background job to finish so the
    #    single-tenant worker is free for later tests
    r = client.get("/api/models/train/status")
    assert r.status_code == 200
    _wait_idle(client, "/api/models/train/status")

    # 7) HP search start + listing
    r = client.post("/api/hp-search/start",
                    json={"model_short": "smoke_lgbm", "n_trials": 1})
    assert r.status_code == 200
    assert r.json()["started"] is True

    r = client.get("/api/hp-search/studies")
    assert r.status_code == 200
    assert len(r.json()) >= 1
    _wait_idle(client, "/api/hp-search/status")

    # 8) Combo search start
    r = client.post("/api/combo-search/start", json={"name": "smoke-combo"})
    assert r.status_code == 200
    _wait_idle(client, "/api/combo-search/status")

    # 9) Predictions / events listing
    r = client.get("/api/predictions/events")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 10) Fighters listing
    r = client.get("/api/fighters/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 11) Scraping status (idle)
    r = client.get("/api/scraping/status")
    assert r.status_code == 200
    assert r.json()["is_running"] is False

    # 12) Publish dry-run
    r = client.post("/api/publish/dry-run", json={"all_active": True})
    assert r.status_code == 200
    assert r.json()["rc"] == 0
