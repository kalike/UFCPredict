from datetime import datetime, UTC

from lab_api.services import dashboard as dsvc


def _seed_event_with_predictions(db, ds_event_dates):
    """Create one past event, 2 fights with real_winner, a session with
    XGB/RF/CB/Deep predictions. Returns event name."""
    from ufc_core.db import models as m
    fa = m.Fighter(name="Alpha One", slug="alpha-one", ufcstats_url="http://ufcstats.com/alpha-one")
    fb = m.Fighter(name="Bravo Two", slug="bravo-two", ufcstats_url="http://ufcstats.com/bravo-two")
    fc = m.Fighter(name="Cain Three", slug="cain-three", ufcstats_url="http://ufcstats.com/cain-three")
    fd = m.Fighter(name="Delta Four", slug="delta-four", ufcstats_url="http://ufcstats.com/delta-four")
    db.add_all([fa, fb, fc, fd]); db.flush()
    ev = m.Event(name="UFC Dash Test", date=datetime(2025, 1, 1, tzinfo=UTC),
                 location="Test City", status="completed", source="scraped")
    db.add(ev); db.flush()
    f1 = m.Fight(event_id=ev.id, fighter_1_id=fa.id, fighter_2_id=fb.id,
                 result="win", real_winner="Alpha One", fight_order=1)
    f2 = m.Fight(event_id=ev.id, fighter_1_id=fc.id, fighter_2_id=fd.id,
                 result="win", real_winner="Delta Four", fight_order=2)
    db.add_all([f1, f2]); db.flush()
    sess = m.PredictionSession(event_id=ev.id, source="lab_preview", status="completed")
    db.add(sess); db.flush()
    for short in ("XGB", "RF", "CB", "Deep"):
        db.add(m.Prediction(session_id=sess.id, fight_id=f1.id, model_short=short,
                            version_idx=0, prob_f1=0.80, prob_f2=0.20))
        db.add(m.Prediction(session_id=sess.id, fight_id=f2.id, model_short=short,
                            version_idx=0, prob_f1=0.75, prob_f2=0.25))
    db.commit()
    ds_event_dates["UFC Dash Test"] = datetime(2025, 1, 1)
    return "UFC Dash Test"


def test_build_summary_computes_accuracy_and_consensus(client):
    from ufc_core.db.engine import SessionLocal
    from lab_api.deps import get_data_store
    from lab_api.services import dashboard as dsvc
    ds = get_data_store()
    db = SessionLocal()
    try:
        _seed_event_with_predictions(db, ds.event_dates)
        dsvc.invalidate()
        summary = dsvc.build_summary(db, ds, min_fights=0)
    finally:
        db.close()
    assert summary["n_past_events"] == 1
    ev = summary["accuracy_by_event"][0]
    assert ev["n_fights_valid"] == 2
    assert ev["n_correct"] == 1
    assert round(ev["overall_accuracy"], 4) == 0.5
    assert round(ev["accuracy_by_model"]["XGB"]["accuracy"], 4) == 0.5
    assert summary["consensus_tiers"]["unanimous"]["total"] >= 1


def test_predicted_winner_picks_f1_when_prob_ge_half():
    assert dsvc._predicted_winner(0.5, "A", "B") == "A"
    assert dsvc._predicted_winner(0.51, "A", "B") == "A"
    assert dsvc._predicted_winner(0.49, "A", "B") == "B"


def test_consensus_majority_3_1():
    votes = [("A", 0.8), ("A", 0.7), ("A", 0.6), ("B", 0.3)]
    winner, n_for, n_total, prob = dsvc._consensus(votes, "A", "B")
    assert winner == "A"
    assert n_for == 3
    assert n_total == 4
    assert round(prob, 4) == 0.6


def test_consensus_split_2_2_resolved_by_mean_prob():
    votes = [("A", 0.9), ("A", 0.8), ("B", 0.3), ("B", 0.2)]
    winner, n_for, n_total, prob = dsvc._consensus(votes, "A", "B")
    assert winner == "A"
    assert n_for == 2
    assert n_total == 4


def test_consensus_tier_labels_for_four_models():
    assert dsvc._consensus_tier(4, 4) == "unanimous"
    assert dsvc._consensus_tier(3, 4) == "majority"
    assert dsvc._consensus_tier(2, 4) == "split"


def test_probability_tier_bins():
    assert dsvc._probability_tier(0.52) == "low"
    assert dsvc._probability_tier(0.58) == "medium"
    assert dsvc._probability_tier(0.62) == "high"
    assert dsvc._probability_tier(0.68) == "very_high"
    assert dsvc._probability_tier(0.80) == "extreme"
