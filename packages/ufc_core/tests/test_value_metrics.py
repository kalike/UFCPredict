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


def test_evaluate_realworld_attaches_value_when_odds_present():
    """evaluate_realworld must add 'realworld_value' iff the df carries odds.

    Builds a tiny 35f realworld_df + a trivial logistic model so the call path
    (impute -> transform -> TTA -> value metrics) runs end to end.
    """
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from ufc_core.imputer import FeatureImputer
    from ufc_core.trainer.core import evaluate_realworld, REALWORLD_CUTOFF_DT

    feat_cols = ["delta_a", "delta_b"]
    rows = []
    for i in range(6):
        rows.append({
            "delta_a": float(i - 3), "delta_b": float(3 - i),
            "rw_label": float(i % 2),
            "rw_real_winner": "F1" if i % 2 else "F2",
            "fighter_1": "F1", "fighter_2": "F2", "event": f"E{i}",
            "event_date": REALWORLD_CUTOFF_DT.replace(year=2025, month=6, day=1),
            "f1_total_fights": 5, "f2_total_fights": 5,
            "odds_f1_american": -110.0, "odds_f2_american": -110.0,
        })
    df = pd.DataFrame(rows)
    imputer = FeatureImputer().fit(df, feat_cols)
    model = LogisticRegression().fit(df[feat_cols].values, df["rw_label"].values)

    out = evaluate_realworld(model, None, imputer, feat_cols, df, is_pytorch=False, min_fights=0)
    assert "realworld_value" in out
    assert out["realworld_value"]["n_with_odds"] == 6
    assert out["realworld_value"]["tossup_threshold"] == 0.55

    # Without odds columns -> no realworld_value key.
    out2 = evaluate_realworld(
        model, None, imputer, feat_cols,
        df.drop(columns=["odds_f1_american", "odds_f2_american"]),
        is_pytorch=False, min_fights=0,
    )
    assert "realworld_value" not in out2
