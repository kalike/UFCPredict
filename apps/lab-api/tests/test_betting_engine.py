from lab_api.schemas.betting import BettingConfig, QualifiedPick, BetCombo


def test_betting_config_defaults():
    c = BettingConfig()
    assert c.min_consensus_pct == 100
    assert c.min_model_prob == 0.52
    assert c.kelly_fraction == 0.25
    assert c.max_event_exposure_pct == 0.16
    assert c.excluded_picks == []


from lab_api.services.betting_engine import (
    american_to_decimal, qualify_picks, generate_event_plan,
)


def test_american_to_decimal():
    assert american_to_decimal(150) == 2.5
    assert american_to_decimal(-200) == 1.5
    assert american_to_decimal(0) is None


def _fight(f1, f2, winner, pct, prob_f1, o1, o2, real=None):
    return {
        "fighter_1": f1, "fighter_2": f2, "consensus_winner": winner,
        "consensus_pct": pct, "avg_prob_f1": prob_f1,
        "odds_f1_american": o1, "odds_f2_american": o2, "real_winner": real,
    }


def test_qualify_picks_filters_by_consensus():
    # qualify_picks filters by consensus_pct; prob filtering is done later in
    # generate_event_plan (per-type thresholds), not here.
    cfg = BettingConfig(min_consensus_pct=100, min_model_prob=0.55)
    fights = [
        _fight("Alice", "Bob", "Alice", 100, 0.70, -150, 130),    # qualifies
        _fight("Carl", "Dan", "Carl", 80, 0.70, -150, 130),       # below consensus → excluded
    ]
    picks = qualify_picks(fights, cfg)
    assert [p.pick for p in picks] == ["Alice"]
    assert picks[0].model_prob == 0.70


def test_generate_event_plan_singles_and_hit_resolution():
    # With only 1 fight → 1 qualified pick, doubles require ≥2 picks and triples ≥5,
    # so both are naturally empty without needing max_parlay_legs override.
    cfg = BettingConfig(min_consensus_pct=100, min_model_prob=0.55)
    fights = [_fight("Alice", "Bob", "Alice", 100, 0.70, -150, 130, real="Alice")]
    plan = generate_event_plan(fights, cfg, "UFC Test")
    assert plan.event_name == "UFC Test"
    assert len(plan.singles) == 1
    assert plan.singles[0].hit is True
    assert plan.doubles == [] and plan.triples == []
