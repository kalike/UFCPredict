import numpy as np
from ufc_core.trainer.value_metrics import compute_value_metrics


def test_returns_none_when_no_odds():
    out = compute_value_metrics(
        proba_f1=np.array([0.6, 0.4]),
        y=np.array([1.0, 0.0]),
        odds_f1_american=np.array([np.nan, np.nan]),
        odds_f2_american=np.array([np.nan, np.nan]),
    )
    assert out is None


def test_tossup_accuracy_and_edge():
    # Two pick'em fights (-110/-110 -> fav_prob ~0.5 < 0.55 => toss-up).
    # Model picks f1 in both (p>=0.5). f1 wins fight 0, loses fight 1 => 1/2 acc.
    out = compute_value_metrics(
        proba_f1=np.array([0.7, 0.55]),
        y=np.array([1.0, 0.0]),
        odds_f1_american=np.array([-110.0, -110.0]),
        odds_f2_american=np.array([-110.0, -110.0]),
    )
    assert out is not None
    assert out["tossup_n"] == 2
    assert out["tossup_accuracy"] == 0.5
    assert out["tossup_edge"] == 0.0
    assert out["tossup_threshold"] == 0.55
    assert out["n_with_odds"] == 2


def test_upset_detection_precision_recall():
    # f1_is_dog when its implied < 0.5. Model picks the dog when it backs that side.
    # A: f1 is dog (+200), model backs f1 (0.6>=0.5), f1 wins  -> dog pick, hit
    # B: f1 is dog (+200), model backs f1 (0.6>=0.5), f1 loses -> dog pick, miss
    # C: f2 is dog (+200), model backs f2 (0.3<0.5),  f2 wins  -> dog pick, hit
    # D: f2 is dog (+200), model backs f1 (0.8>=0.5), f2 wins  -> dog won, NOT picked
    out = compute_value_metrics(
        proba_f1=np.array([0.6, 0.6, 0.3, 0.8]),
        y=np.array([1.0, 0.0, 0.0, 0.0]),
        odds_f1_american=np.array([200.0, 200.0, -250.0, -250.0]),
        odds_f2_american=np.array([-250.0, -250.0, 200.0, 200.0]),
    )
    # Dog picks by model: A (f1), B (f1), C (f2) -> 3 picks
    assert out["underdog_pick_n"] == 3
    # Dog actually won: A (f1 won), C (f2 won), D (f2 won) -> 3 upsets total
    assert out["upset_total"] == 3
    # Dog picks that hit: A and C -> 2
    assert out["underdog_pick_hits"] == 2
    assert out["upset_precision"] == round(2 / 3, 4)
    # Upsets detected by model: A and C (D undetected) -> 2 of 3
    assert out["upset_detected"] == 2
    assert out["upset_recall"] == round(2 / 3, 4)


def test_brier_vs_market_delta_sign():
    # Perfect model (p == y), market mediocre -> brier_delta < 0 (model better)
    out = compute_value_metrics(
        proba_f1=np.array([1.0, 0.0]),
        y=np.array([1.0, 0.0]),
        odds_f1_american=np.array([-110.0, -110.0]),
        odds_f2_american=np.array([-110.0, -110.0]),
    )
    assert out["brier_model"] == 0.0
    assert out["brier_market"] > 0.0
    assert out["brier_delta"] < 0.0
    assert out["logloss_delta"] < 0.0


def test_buckets_partition_all_fights():
    out = compute_value_metrics(
        proba_f1=np.array([0.6, 0.6, 0.6, 0.6]),
        y=np.array([1.0, 1.0, 1.0, 1.0]),
        # fav_probs ~ 0.5, ~0.6, ~0.7, ~0.85
        odds_f1_american=np.array([-110.0, -150.0, -250.0, -600.0]),
        odds_f2_american=np.array([-110.0, 130.0, 200.0, 425.0]),
    )
    assert [b["n"] for b in out["buckets"]] == [1, 1, 1, 1]
    assert sum(b["n"] for b in out["buckets"]) == out["n_with_odds"]
