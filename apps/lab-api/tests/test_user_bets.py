import pytest
from ufc_core.db.engine import SessionLocal
from ufc_core.db import models as m
from lab_api.services import user_bets as svc


@pytest.fixture
def seeded_event(test_engine):
    """One promoted event with a resolved fight (Alice beat Bob)."""
    db = SessionLocal()
    fa = m.Fighter(name="Alice UB", slug="alice-ub", ufcstats_url="http://x/alice-ub")
    fb = m.Fighter(name="Bob UB", slug="bob-ub", ufcstats_url="http://x/bob-ub")
    db.add_all([fa, fb]); db.flush()
    ev = m.Event(name="UFC UB Test", source="promoted", status="completed")
    db.add(ev); db.flush()
    fight = m.Fight(event_id=ev.id, fighter_1_id=fa.id, fighter_2_id=fb.id,
                    odds_f1_american=-150, odds_f2_american=130,
                    real_winner="Alice UB", fight_order=0)
    db.add(fight); db.commit()
    eid = ev.id
    yield eid
    db.query(m.LabUserBet).filter_by(event_id=eid).delete()
    db.query(m.Fight).filter_by(event_id=eid).delete()
    db.query(m.Event).filter_by(id=eid).delete()
    db.query(m.Fighter).filter(m.Fighter.slug.in_(["alice-ub", "bob-ub"])).delete(synchronize_session=False)
    db.commit(); db.close()


def test_import_and_auto_resolve_winner(seeded_event):
    with SessionLocal() as db:
        combo = {"type": "single", "stake": 30.0, "combined_odds": 1.8,
                 "potential_return": 54.0,
                 "picks": [{"pick": "Alice UB", "fighter_1": "Alice UB", "fighter_2": "Bob UB"}]}
        bets = svc.import_from_combos(db, "UFC UB Test", [combo])
        assert len(bets) == 1
        assert bets[0]["status"] == "won"
        assert bets[0]["actual_return"] == pytest.approx(54.0)


def test_compute_stats_engine_comparison(seeded_event):
    with SessionLocal() as db:
        combo = {"type": "single", "stake": 30.0, "combined_odds": 1.8,
                 "potential_return": 54.0,
                 "picks": [{"pick": "Alice UB", "fighter_1": "Alice UB", "fighter_2": "Bob UB"}]}
        svc.import_from_combos(db, "UFC UB Test", [combo])
        stats = svc.compute_stats(db, event_id=seeded_event)
        assert stats["n_bets"] == 1
        assert stats["n_won"] == 1
        assert "engine_comparison" in stats


def test_promote_resolves_pending_bets(client, test_engine):
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as m
    db = SessionLocal()
    fa = m.Fighter(name="Cara PR", slug="cara-pr", ufcstats_url="http://x/cara-pr")
    fb = m.Fighter(name="Dina PR", slug="dina-pr", ufcstats_url="http://x/dina-pr")
    db.add_all([fa, fb]); db.flush()
    # scheduled event (not yet promoted) + a pending session + resolved fight
    ev = m.Event(name="UFC PR Test", source="preview", status="scheduled")
    db.add(ev); db.flush()
    sess = m.PredictionSession(event_id=ev.id, source="lab_preview", status="completed")
    db.add(sess); db.flush()
    fight = m.Fight(event_id=ev.id, fighter_1_id=fa.id, fighter_2_id=fb.id,
                    odds_f1_american=-150, odds_f2_american=130,
                    real_winner="Cara PR", fight_order=0)
    db.add(fight)
    bet = m.LabUserBet(event_id=ev.id, bet_type="single",
                       picks=[{"pick": "Cara PR", "fighter_1": "Cara PR", "fighter_2": "Dina PR"}],
                       combo_key="single:Cara PR", combined_odds=1.8, stake=30.0,
                       potential_return=54.0, status="pending")
    db.add(bet); db.commit()
    sid, eid = sess.id, ev.id
    db.close()

    r = client.post(f"/api/predictions/sessions/{sid}/promote", json={})
    assert r.status_code == 200, r.text

    r = client.get(f"/api/user-bets?event_id={eid}")
    assert r.json()[0]["status"] == "won"

    db = SessionLocal()
    db.query(m.LabUserBet).filter_by(event_id=eid).delete()
    db.query(m.Prediction).filter_by(session_id=sid).delete()
    db.query(m.PredictionSession).filter_by(id=sid).delete()
    db.query(m.Fight).filter_by(event_id=eid).delete()
    db.query(m.Event).filter_by(id=eid).delete()
    db.query(m.Fighter).filter(m.Fighter.slug.in_(["cara-pr", "dina-pr"])).delete(synchronize_session=False)
    db.commit(); db.close()


def test_user_bets_import_endpoint(client, seeded_event):
    body = {"event_name": "UFC UB Test", "combos": [{
        "type": "single", "picks": [{"pick": "Alice UB", "fighter_1": "Alice UB",
        "fighter_2": "Bob UB", "pick_odds_american": -150, "model_prob": 0.7,
        "decimal_odds": 1.8, "implied_prob": 0.6, "edge": 0.1, "ev_per_unit": 0.26,
        "kelly_full": 0.3, "kelly_quarter": 0.07, "score": 0.79, "consensus_pct": 100}],
        "combined_prob": 0.7, "combined_odds": 1.8, "ev": 0.26, "stake": 30.0,
        "potential_return": 54.0}]}
    r = client.post("/api/user-bets/import", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["n_imported"] == 1
    r = client.get(f"/api/user-bets?event_id={seeded_event}")
    assert r.json()[0]["status"] == "won"
