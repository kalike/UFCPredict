from datetime import datetime
from unittest.mock import patch

from lab_api.schemas.betting import BettingConfig
from lab_api.services.backtest_engine import _backtest_over_sessions


def _session(real="Alice"):
    return {
        "event": "UFC BT", "created_at": "2025-06-01",
        "fights": [{
            "fighter_1": "Alice", "fighter_2": "Bob",
            "consensus_winner": "Alice", "consensus_pct": 100,
            "avg_prob_f1": 0.70, "odds_f1_american": -150,
            "odds_f2_american": 130, "real_winner": real,
        }],
    }


def test_backtest_resolves_winning_single():
    # 1 fight → 1 qualified pick; doubles/triples are naturally empty without override.
    cfg = BettingConfig(min_consensus_pct=100, min_model_prob=0.55)
    resp = _backtest_over_sessions([_session(real="Alice")], cfg)
    assert resp.total_events == 1
    assert "singles" in resp.strategies
    assert resp.strategies["singles"].total_return > 0
    assert resp.strategies["singles"].profit > 0


def test_backtest_losing_single_has_zero_return():
    # 1 fight → 1 qualified pick; when the pick loses, return is 0 and profit negative.
    cfg = BettingConfig(min_consensus_pct=100, min_model_prob=0.55)
    resp = _backtest_over_sessions([_session(real="Bob")], cfg)
    assert resp.strategies["singles"].total_return == 0.0
    assert resp.strategies["singles"].profit < 0


def _two_fight_session(name, win_both):
    """One session with two qualifying fights (→ 2 singles + 1 double)."""
    return {
        "event": name, "created_at": "2025-06-01",
        "fights": [
            {"fighter_1": "A", "fighter_2": "B", "consensus_winner": "A", "consensus_pct": 100,
             "avg_prob_f1": 0.70, "odds_f1_american": -150, "odds_f2_american": 130,
             "real_winner": "A" if win_both else "B"},
            {"fighter_1": "C", "fighter_2": "D", "consensus_winner": "C", "consensus_pct": 100,
             "avg_prob_f1": 0.66, "odds_f1_american": -120, "odds_f2_american": 110,
             "real_winner": "C" if win_both else "D"},
        ],
    }


def test_backtest_total_aggregates_singles_doubles_triples():
    from lab_api.services.backtest_engine import _max_drawdown

    cfg = BettingConfig(min_consensus_pct=100, min_model_prob=0.55)
    # Event 1 wins (PnL up), event 2 loses (PnL down) → a real drawdown.
    sessions = [_two_fight_session("ev1", True), _two_fight_session("ev2", False)]
    resp = _backtest_over_sessions(sessions, cfg)

    assert resp.total is not None
    tot = resp.total
    s = resp.strategies["singles"]
    d = resp.strategies["doubles"]
    t = resp.strategies["triples"]

    # Aggregates the three bet types, NOT baseline.
    assert tot.total_stake == round(s.total_stake + d.total_stake + t.total_stake, 2)
    assert tot.total_return == round(s.total_return + d.total_return + t.total_return, 2)
    assert tot.profit == round(s.profit + d.profit + t.profit, 2)
    assert tot.total_bets == s.total_bets + d.total_bets + t.total_bets

    # Combined cumulative PnL = point-by-point sum of the three series.
    assert len(tot.cumulative_pnl) == len(s.cumulative_pnl)
    for i in range(len(tot.cumulative_pnl)):
        assert tot.cumulative_pnl[i] == round(
            s.cumulative_pnl[i] + d.cumulative_pnl[i] + t.cumulative_pnl[i], 2
        )

    # Max DD = largest continuous loss over the COMBINED series.
    assert tot.max_drawdown == round(_max_drawdown(tot.cumulative_pnl), 2)
    assert tot.max_drawdown <= 0


def test_list_promoted_sessions_is_cached(test_engine):
    """Reconstruction is expensive (~4.5s for 46 events). Two consecutive calls
    with no DB change must reconstruct ONCE and serve the second from cache."""
    from unittest.mock import MagicMock, patch
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as m
    import lab_api.services.lab_session_provider as prov

    db = SessionLocal()
    ev = m.Event(name="UFC Cache Test", source="promoted", status="completed", date=datetime(2025, 6, 1))
    db.add(ev)
    db.flush()
    db.add(m.PredictionSession(event_id=ev.id, source="lab_recalc", status="completed"))
    db.commit()
    eid = ev.id

    fake = [{
        "fighter_1": "A", "fighter_2": "B", "consensus_winner": "A", "consensus_pct": 100,
        "avg_prob_f1": 0.7, "odds_f1_american": -150, "odds_f2_american": 130,
        "real_winner": "A", "fighter_1_n_fights": 5, "fighter_2_n_fights": 5, "community_picks": None,
    }]
    recon = MagicMock(return_value=fake)
    prov.invalidate_promoted_cache()
    try:
        with patch("lab_api.services.lab_session_provider.get_data_store"), patch(
            "lab_api.routers.predictions._reconstruct_session_fights", recon
        ):
            prov.list_promoted_sessions(db)
            prov.list_promoted_sessions(db)
        assert recon.call_count == 1, f"expected 1 reconstruction (cache hit), got {recon.call_count}"
    finally:
        prov.invalidate_promoted_cache()
        db.query(m.PredictionSession).filter_by(event_id=eid).delete()
        db.query(m.Event).filter_by(id=eid).delete()
        db.commit()
        db.close()


def test_list_promoted_sessions_dedups_by_event(test_engine):
    """An event with several accumulated lab_recalc sessions must appear ONCE
    in the backtest set (regression: recalc piles up ~22 sessions per event,
    which previously multiplied every realworld event in the betting section)."""
    from ufc_core.db.engine import SessionLocal
    from ufc_core.db import models as m

    db = SessionLocal()
    name = "UFC RW Dedup Test"
    ev = m.Event(name=name, source="promoted", status="completed", date=datetime(2025, 6, 1))
    db.add(ev)
    db.flush()
    for _ in range(3):  # three accumulated realworld recalc runs for the same event
        db.add(m.PredictionSession(event_id=ev.id, source="lab_recalc", status="completed"))
    db.commit()
    eid = ev.id

    fake_fight = {
        "fighter_1": "A", "fighter_2": "B", "consensus_winner": "A", "consensus_pct": 100,
        "avg_prob_f1": 0.70, "odds_f1_american": -150, "odds_f2_american": 130,
        "real_winner": "A", "fighter_1_n_fights": 5, "fighter_2_n_fights": 5,
        "community_picks": None,
    }
    try:
        with patch("lab_api.services.lab_session_provider.get_data_store"), patch(
            "lab_api.routers.predictions._reconstruct_session_fights", return_value=[fake_fight]
        ):
            from lab_api.services.lab_session_provider import list_promoted_sessions

            result = list_promoted_sessions(db)
        mine = [r for r in result if r["event"] == name]
        assert len(mine) == 1, f"expected 1 entry for the event, got {len(mine)}"
    finally:
        db.query(m.PredictionSession).filter_by(event_id=eid).delete()
        db.query(m.Event).filter_by(id=eid).delete()
        db.commit()
        db.close()
