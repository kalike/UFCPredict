"""Integration tests for the rich predictions endpoints (arbitrary matchups,
sessions, past-events). Reuses the synthetic seeder + training path from
test_e2e_train_predict so an active model exists for inference.
"""

from ufc_core.db.base import Base
from ufc_core.db.engine import SessionLocal
from ufc_core.db import models as db_models

from tests.test_e2e_train_predict import _Seeder, _wait_idle


def _ensure_active_model(client, test_engine) -> tuple[str, str]:
    """Seed synthetic data + ensure an active XGB version. Returns (f1, f2)
    names of two seeded fighters with history."""
    Base.metadata.create_all(test_engine)
    db = SessionLocal()
    try:
        existing = (
            db.query(db_models.Fighter)
              .filter(db_models.Fighter.name.like(f"{_Seeder.PREFIX}%"))
              .first()
        )
        if existing is None:
            seeder = _Seeder(db)
            seeder.seed_fighters()
            seeder.seed_events()
            seeder.attach_fighter_raw()
        names = [
            f.name for f in db.query(db_models.Fighter)
            .filter(db_models.Fighter.name.like(f"{_Seeder.PREFIX}%"))
            .order_by(db_models.Fighter.name).limit(2).all()
        ]
        # Is there already an active model?
        has_active = db.query(db_models.ActiveModel).first() is not None
    finally:
        db.close()

    # Refresh the cached data store so it sees the freshly seeded fighters.
    from lab_api.deps import get_data_store
    get_data_store.cache_clear()

    if not has_active:
        r = client.post(
            "/api/models/train",
            json={"model_short": "XGB", "feature_set": "v7", "dataset": "since2010"},
        )
        assert r.status_code == 200, r.text
        final = _wait_idle(client, timeout_seconds=180)
        assert not final["is_running"], f"train did not finish: {final}"
        version_idx = final["result_version_id"]
        assert version_idx is not None, final
        db = SessionLocal()
        try:
            m = db.query(db_models.Model).filter_by(short="XGB").one()
            v = (db.query(db_models.ModelVersion).filter_by(model_id=m.id)
                 .order_by(db_models.ModelVersion.version_idx.desc()).first())
            vidx = v.version_idx
        finally:
            db.close()
        r = client.post(f"/api/models/XGB/versions/{vidx}/activate")
        assert r.status_code == 200, r.text

    return names[0], names[1]


def test_predict_arbitrary_matchup_rich_shape(client, test_engine):
    f1, f2 = _ensure_active_model(client, test_engine)
    r = client.post("/api/predictions/", json={
        "event_name": "Smoke Card",
        "fights": [{"fighter_1": f1, "fighter_2": f2}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event"] == "Smoke Card"
    assert body["n_models"] >= 1
    assert len(body["fights"]) == 1
    fight = body["fights"][0]
    # rich fields present
    assert fight["models"], "no per-model breakdown"
    for short, mv in fight["models"].items():
        assert set(mv) >= {"full_name", "predicted_winner", "probability_f1", "confidence"}
        assert 0.0 <= mv["probability_f1"] <= 1.0
    assert fight["consensus"]["total_models"] == len(fight["models"])
    assert abs(fight["prob_f1"] + fight["prob_f2"] - 1.0) < 1e-5
    assert "fighter_1_methods" in fight and "fighter_2_methods" in fight
    assert fight["fighter_1_has_history"] is True


def test_predict_arbitrary_unknown_fighters_skipped(client, test_engine):
    _ensure_active_model(client, test_engine)
    r = client.post("/api/predictions/", json={
        "event_name": "Ghost Card",
        "fights": [{"fighter_1": "Nobody Zzz", "fighter_2": "Phantom Qqq"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["fights"]) == 0
    assert len(body["skipped"]) == 1


def test_session_save_list_detail_mark(client, test_engine):
    f1, f2 = _ensure_active_model(client, test_engine)
    pred = client.post("/api/predictions/", json={
        "event_name": "Session Card",
        "fights": [{"fighter_1": f1, "fighter_2": f2}],
    }).json()
    fight = pred["fights"][0]

    save = client.post("/api/predictions/sessions", json={
        "event": "Session Card",
        "fights": [{
            "fighter_1": fight["fighter_1"],
            "fighter_2": fight["fighter_2"],
            "models": fight["models"],
            "consensus_winner": fight["consensus"]["consensus_winner"],
            "consensus_pct": fight["consensus"]["consensus_pct"],
        }],
    })
    assert save.status_code == 200, save.text
    sid = save.json()["id"]
    assert save.json()["ok"] is True

    lst = client.get("/api/predictions/sessions").json()
    assert any(s["id"] == sid for s in lst)

    detail = client.get(f"/api/predictions/sessions/{sid}").json()
    assert detail["n_fights"] == 1
    assert detail["fights"][0]["models"]

    # mark a real winner → accuracy recomputed
    winner = fight["consensus"]["consensus_winner"]
    mark = client.patch(f"/api/predictions/sessions/{sid}/result",
                        json={"fight_index": 0, "real_winner": winner})
    assert mark.status_code == 200, mark.text
    mb = mark.json()
    assert mb["n_results"] == 1
    assert mb["n_correct"] == 1
    assert mb["accuracy"] == 1.0

    # promote + cleanup
    promo = client.post(f"/api/predictions/sessions/{sid}/promote", json={})
    assert promo.status_code == 200, promo.text
    assert promo.json()["ok"] is True

    dele = client.delete(f"/api/predictions/sessions/{sid}")
    assert dele.status_code == 200


def test_past_events_accuracy(client, test_engine):
    """Past-events lists the realworld held-out partition (date >= cutoff) and
    scores each model against Fight.result."""
    from datetime import datetime, UTC

    _ensure_active_model(client, test_engine)

    # Seed a realworld completed event (>= REALWORLD_CUTOFF_DT) with results.
    ev_name = "E2E_Realworld Card"
    db = SessionLocal()
    try:
        fighters = (
            db.query(db_models.Fighter)
              .filter(db_models.Fighter.name.like(f"{_Seeder.PREFIX}%"))
              .order_by(db_models.Fighter.name).limit(4).all()
        )
        if db.query(db_models.Event).filter_by(name=ev_name).one_or_none() is None:
            ev = db_models.Event(
                name=ev_name, date=datetime(2025, 8, 1, tzinfo=UTC),
                status="completed", source="scraped",
            )
            db.add(ev); db.flush()
            for i in range(0, 4, 2):
                db.add(db_models.Fight(
                    event_id=ev.id,
                    fighter_1_id=fighters[i].id, fighter_2_id=fighters[i + 1].id,
                    result="win", method="U-DEC", round=3, time="5:00",
                    fight_order=i // 2,
                ))
            db.commit()
    finally:
        db.close()

    events = client.get("/api/predictions/past-events").json()
    assert isinstance(events, list)
    assert any(e["name"] == ev_name for e in events), events
    pe = client.get(f"/api/predictions/past-events/{ev_name}").json()
    assert pe["event"] == ev_name
    assert pe["n_fights_valid"] >= 1
    assert pe["accuracy"], "no per-model accuracy"
    for short, acc in pe["accuracy"].items():
        assert acc["total"] >= 1
        assert 0.0 <= acc["accuracy"] <= 1.0
    # the winner (fighter_1, result=win) should be surfaced on the card
    assert any(f["real_winner"] for f in pe["fights"])
