"""Tests for the lab_session_provider adapter and the betting router."""
from lab_api.services.lab_session_provider import fight_to_dict


def test_betting_defaults(client):
    r = client.get("/api/betting/defaults")
    assert r.status_code == 200
    assert r.json()["min_model_prob"] == 0.52


def test_backtest_empty_when_no_promoted_sessions(client):
    r = client.post("/api/betting/backtest", json={})
    assert r.status_code == 200
    body = r.json()
    assert "strategies" in body and "singles" in body["strategies"]


def test_fight_to_dict_maps_consensus_and_odds():
    rf = {
        "fighter_1": "Alice", "fighter_2": "Bob",
        "consensus": {"consensus_winner": "Alice", "consensus_pct": 100.0,
                      "fighter_1_votes": 5, "fighter_2_votes": 0, "total_models": 5},
        "prob_f1": 0.70, "prob_f2": 0.30,
        "odds_f1_american": -150, "odds_f2_american": 130,
        "real_winner": "Alice",
        "fighter_1_n_fights": 12, "fighter_2_n_fights": 9,
        "community_picks": None,
    }
    d = fight_to_dict(rf)
    assert d["consensus_winner"] == "Alice"
    assert d["consensus_pct"] == 100.0
    assert d["avg_prob_f1"] == 0.70
    assert d["odds_f1_american"] == -150
    assert d["real_winner"] == "Alice"
    assert d["fighter_1_n_fights"] == 12
