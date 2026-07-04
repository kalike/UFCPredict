from datetime import datetime, UTC

from lab_api.services import dashboard as dsvc


def _mk_fighter(db, name, slug):
    from ufc_core.db import models as m
    f = m.Fighter(name=name, slug=slug, ufcstats_url=f"http://ufcstats.com/{slug}")
    db.add(f); db.flush()
    return f


# Default event date sits inside the realworld window (>= REALWORLD_CUTOFF 2025-05-01).
_RW_DATE = datetime(2025, 6, 1, tzinfo=UTC)


def _seed_realworld_event(db, *, models=("XGB", "RF", "CB", "Deep"),
                          event_name="UFC Dash Test", event_source="scraped",
                          session_source="lab_recalc", event_date=_RW_DATE, suffix="a"):
    """One real card with 2 fights whose winner comes from Fight.result
    (not real_winner, which scraped fights leave empty), a realworld session
    with predictions from `models`. Returns event name.

    Fight 1: all models pick Alpha (prob_f1 high), result='win' -> Alpha wins -> correct.
    Fight 2: all models pick Cain (prob_f1 high), result='loss' -> Delta wins -> wrong.
    """
    from ufc_core.db import models as m
    fa = _mk_fighter(db, f"Alpha {suffix}", f"alpha-{suffix}")
    fb = _mk_fighter(db, f"Bravo {suffix}", f"bravo-{suffix}")
    fc = _mk_fighter(db, f"Cain {suffix}", f"cain-{suffix}")
    fd = _mk_fighter(db, f"Delta {suffix}", f"delta-{suffix}")
    ev = m.Event(name=event_name, date=event_date,
                 location="Test City", status="completed", source=event_source)
    db.add(ev); db.flush()
    f1 = m.Fight(event_id=ev.id, fighter_1_id=fa.id, fighter_2_id=fb.id,
                 result="win", fight_order=1)   # Alpha wins
    f2 = m.Fight(event_id=ev.id, fighter_1_id=fc.id, fighter_2_id=fd.id,
                 result="loss", fight_order=2)  # Delta wins
    db.add_all([f1, f2]); db.flush()
    sess = m.PredictionSession(event_id=ev.id, source=session_source, status="completed")
    db.add(sess); db.flush()
    for short in models:
        db.add(m.Prediction(session_id=sess.id, fight_id=f1.id, model_short=short,
                            version_idx=0, prob_f1=0.80, prob_f2=0.20))
        db.add(m.Prediction(session_id=sess.id, fight_id=f2.id, model_short=short,
                            version_idx=0, prob_f1=0.75, prob_f2=0.25))
    db.commit()
    return event_name


def test_build_summary_derives_winner_and_consensus(client):
    from ufc_core.db.engine import SessionLocal
    from lab_api.deps import get_data_store
    ds = get_data_store()
    db = SessionLocal()
    try:
        _seed_realworld_event(db, suffix="rw")
        dsvc.invalidate()
        summary = dsvc.build_summary(db, ds, min_fights=0)
    finally:
        db.close()
    by_event = {e["event"]: e for e in summary["accuracy_by_event"]}
    ev = by_event["UFC Dash Test"]
    # winner derived from Fight.result -> 1 of 2 fights correct
    assert ev["n_fights_valid"] == 2
    assert ev["n_correct"] == 1
    assert round(ev["overall_accuracy"], 4) == 0.5
    assert round(ev["accuracy_by_model"]["XGB"]["accuracy"], 4) == 0.5
    # 4 models all agreeing -> a 4-0 unanimous tier entry
    assert summary["consensus_tiers"]["unanimous"]["total"] >= 1
    assert summary["n_models"] == 4
    assert summary["models"] == ["XGB", "RF", "CB", "Deep"]


def test_models_present_is_dynamic_and_ordered(client):
    """_models_present returns only families with predictions, in preferred order
    (DASHBOARD_MODEL_ORDER) regardless of insertion order. Tested in isolation
    against specific session ids (the session-scoped DB is shared across tests)."""
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as m
    db = SessionLocal()
    try:
        _seed_realworld_event(db, models=("XGB",), event_name="UFC Solo XGB", suffix="solo")
        solo = (db.query(m.PredictionSession).join(m.Event, m.Event.id == m.PredictionSession.event_id)
                  .filter(m.Event.name == "UFC Solo XGB").one())
        assert dsvc._models_present(db, [solo.id]) == ["XGB"]

        _seed_realworld_event(db, models=("Deep", "XGB"), event_name="UFC Two Models", suffix="two")
        two = (db.query(m.PredictionSession).join(m.Event, m.Event.id == m.PredictionSession.event_id)
                 .filter(m.Event.name == "UFC Two Models").one())
        # inserted Deep first, but preferred order puts XGB before Deep
        assert dsvc._models_present(db, [two.id]) == ["XGB", "Deep"]
    finally:
        db.close()


def test_summary_excludes_non_realworld(client):
    """The realworld window is event_date >= REALWORLD_CUTOFF over real UFC cards.
    Pre-cutoff backtest history (e.g. UFC 1, 1994), fighter_history cards and
    non-recalc sessions are all excluded; a recent scraped card is included."""
    from datetime import datetime, UTC
    from ufc_core.db.engine import SessionLocal
    from lab_api.deps import get_data_store
    ds = get_data_store()
    db = SessionLocal()
    try:
        _seed_realworld_event(db, event_name="UFC 1 Backtest", event_source="scraped",
                              event_date=datetime(1994, 3, 11, tzinfo=UTC), suffix="bt")
        _seed_realworld_event(db, event_name="PRIDE Legacy", event_source="fighter_history",
                              suffix="fh")
        _seed_realworld_event(db, event_name="UFC Preview Only", session_source="lab_preview",
                              suffix="pv")
        _seed_realworld_event(db, event_name="UFC Recent Scraped", event_source="scraped",
                              suffix="rs")
        dsvc.invalidate()
        summary = dsvc.build_summary(db, ds, min_fights=0)
    finally:
        db.close()
    names = {e["event"] for e in summary["accuracy_by_event"]}
    assert "UFC 1 Backtest" not in names        # excluded: before REALWORLD_CUTOFF
    assert "PRIDE Legacy" not in names          # excluded: fighter_history (non-UFC)
    assert "UFC Preview Only" not in names       # excluded: not a realworld (recalc) session
    assert "UFC Recent Scraped" in names         # included: scraped card inside the window


def test_predicted_winner_picks_f1_when_prob_ge_half():
    assert dsvc._predicted_winner(0.5, "A", "B") == "A"
    assert dsvc._predicted_winner(0.51, "A", "B") == "A"
    assert dsvc._predicted_winner(0.49, "A", "B") == "B"


def test_real_winner_from_result():
    assert dsvc._real_winner("A", "B", "win", None) == "A"
    assert dsvc._real_winner("A", "B", "loss", None) == "B"
    assert dsvc._real_winner("A", "B", "draw", None) is None
    assert dsvc._real_winner("A", "B", "nc", None) is None
    # explicit real_winner column wins over result
    assert dsvc._real_winner("A", "B", "loss", "A") == "A"


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


def test_consensus_tier_single_model_is_unanimous():
    assert dsvc._consensus_tier(1, 1) == "unanimous"


def test_probability_tier_bins():
    assert dsvc._probability_tier(0.52) == "low"
    assert dsvc._probability_tier(0.58) == "medium"
    assert dsvc._probability_tier(0.62) == "high"
    assert dsvc._probability_tier(0.68) == "very_high"
    assert dsvc._probability_tier(0.80) == "extreme"


def test_build_summary_handles_tz_aware_event_dates(client):
    """Regression: ev.date comes tz-aware from the DB, while the default in
    _fighter_fights_before / _has_only_dwcs (datetime.min) and other event_dates
    entries may be naive. Comparing them must not raise TypeError."""
    from ufc_core.db.engine import SessionLocal
    from lab_api.deps import get_data_store
    ds = get_data_store()
    db = SessionLocal()
    ev_name = "UFC TZ Aware Test"
    try:
        _seed_realworld_event(db, models=("XGB",), event_name=ev_name, suffix="tz")
        ds.event_dates[ev_name] = datetime(2025, 6, 1, tzinfo=UTC)
        ds.fighter_histories["Alpha tz"] = [{"event": "Some Old Fight 2024"}]
        dsvc.invalidate()
        summary = dsvc.build_summary(db, ds, min_fights=1)
    finally:
        ds.fighter_histories.pop("Alpha tz", None)
        ds.event_dates.pop(ev_name, None)
        db.close()
    assert any(e["event"] == ev_name for e in summary["accuracy_by_event"])


def test_summary_endpoint_shape(client):
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "latest_event", "n_past_events", "n_fighters", "n_models", "models",
        "avg_by_model", "accuracy_by_event", "recent_fights",
        "consensus_tiers", "probability_tiers", "special_case_tiers",
        "special_case_fights", "disabled_models", "min_fights", "with_odds",
        "unanimous_only",
    ):
        assert key in body, f"missing {key}"
    assert isinstance(body["models"], list)
    assert body["with_odds"] is False
    assert body["unanimous_only"] is False


def test_with_odds_restricts_to_fights_with_odds(client):
    """with_odds=True ("universo apostable") only aggregates RealWorld fights
    that carry odds on both sides — a filter analogous to min_fights, no model
    re-evaluation. Seeds one card whose 2 fights have odds on only one of them.
    """
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as m
    from lab_api.deps import get_data_store
    ds = get_data_store()
    db = SessionLocal()
    try:
        _seed_realworld_event(db, event_name="UFC Odds Toggle", suffix="odds")
        ev = db.query(m.Event).filter_by(name="UFC Odds Toggle").one()
        # Odds only on fight_order=1 (Alpha vs Bravo, the correct pick).
        f1 = db.query(m.Fight).filter_by(event_id=ev.id, fight_order=1).one()
        f1.odds_f1_american = -150
        f1.odds_f2_american = 130
        db.commit()
        dsvc.invalidate()
        full = dsvc.build_summary(db, ds, min_fights=0)
        apostable = dsvc.build_summary(db, ds, min_fights=0, with_odds=True)
    finally:
        db.close()
    full_ev = {e["event"]: e for e in full["accuracy_by_event"]}["UFC Odds Toggle"]
    apost_map = {e["event"]: e for e in apostable["accuracy_by_event"]}
    assert full["with_odds"] is False
    assert apostable["with_odds"] is True
    # Full view: both fights counted. Apostable: only the one with odds.
    assert full_ev["n_fights_valid"] == 2
    apost_ev = apost_map["UFC Odds Toggle"]
    assert apost_ev["n_fights_valid"] == 1
    assert apost_ev["n_correct"] == 1  # the fight with odds was the correct pick


def test_unanimous_only_filters_non_consensus(client):
    """unanimous_only=True restricts every KPI to fights where all models agree
    on the winner (the betting-strategy universe). Seeds one unanimous fight and
    one 3-1 split; only the unanimous one survives the filter."""
    from datetime import datetime, UTC
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as m
    from lab_api.deps import get_data_store
    ds = get_data_store()
    db = SessionLocal()
    try:
        fa = _mk_fighter(db, "Uno u", "uno-u")
        fb = _mk_fighter(db, "Dos u", "dos-u")
        fc = _mk_fighter(db, "Tres u", "tres-u")
        fd = _mk_fighter(db, "Cuatro u", "cuatro-u")
        ev = m.Event(name="UFC Unanimity", date=datetime(2025, 6, 2, tzinfo=UTC),
                     location="X", status="completed", source="scraped")
        db.add(ev); db.flush()
        f1 = m.Fight(event_id=ev.id, fighter_1_id=fa.id, fighter_2_id=fb.id,
                     result="win", fight_order=1)
        f2 = m.Fight(event_id=ev.id, fighter_1_id=fc.id, fighter_2_id=fd.id,
                     result="win", fight_order=2)
        db.add_all([f1, f2]); db.flush()
        sess = m.PredictionSession(event_id=ev.id, source="lab_recalc", status="completed")
        db.add(sess); db.flush()
        for s in ("XGB", "RF", "CB", "Deep"):  # fight 1: all pick f1 (unanimous)
            db.add(m.Prediction(session_id=sess.id, fight_id=f1.id, model_short=s,
                                version_idx=0, prob_f1=0.80, prob_f2=0.20))
        for s in ("XGB", "RF", "CB"):          # fight 2: 3 pick f1...
            db.add(m.Prediction(session_id=sess.id, fight_id=f2.id, model_short=s,
                                version_idx=0, prob_f1=0.70, prob_f2=0.30))
        db.add(m.Prediction(session_id=sess.id, fight_id=f2.id, model_short="Deep",
                            version_idx=0, prob_f1=0.30, prob_f2=0.70))  # ...1 dissents (3-1)
        db.commit()
        dsvc.invalidate()
        full = dsvc.build_summary(db, ds, min_fights=0)
        unan = dsvc.build_summary(db, ds, min_fights=0, unanimous_only=True)
    finally:
        db.close()
    assert full["unanimous_only"] is False
    assert unan["unanimous_only"] is True
    full_ev = {e["event"]: e for e in full["accuracy_by_event"]}["UFC Unanimity"]
    unan_ev = {e["event"]: e for e in unan["accuracy_by_event"]}["UFC Unanimity"]
    assert full_ev["n_fights_valid"] == 2   # both fights counted
    assert unan_ev["n_fights_valid"] == 1   # only the unanimous one


def test_summary_rejects_unknown_source(client):
    r = client.get("/api/dashboard/summary", params={"source": "bogus"})
    assert r.status_code == 422


def test_realworld_source_shape(client):
    """source=realworld evaluates active models on realworld_df. With an empty
    test DB (no active models / no fighters) it returns the same shape with
    source='realworld_df' rather than erroring."""
    r = client.get("/api/dashboard/summary", params={"source": "realworld"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "realworld_df"
    for key in ("n_models", "models", "avg_by_model", "consensus_tiers",
                "probability_tiers", "min_fights", "with_odds", "unanimous_only"):
        assert key in body, f"missing {key}"


def test_event_fights_404_when_unknown(client):
    r = client.get("/api/dashboard/event-fights", params={"event": "No Such Event"})
    assert r.status_code == 404


def test_recalculation_status_endpoint(client):
    r = client.get("/api/dashboard/recalculation-status")
    assert r.status_code == 200
    assert "is_running" in r.json()
