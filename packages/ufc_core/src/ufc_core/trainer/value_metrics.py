"""Value-vs-market metrics over the RealWorld window.

Pure, dependency-free (numpy only). Compares the model's TTA probability
against the no-vig implied probability of the market, on the subset of
fights that have both American odds. See
docs/specs/2026-06-17-value-metrics-realworld-design.md.
"""

from __future__ import annotations

import numpy as np

TOSSUP_THRESHOLD = 0.55

# (label, lo, hi) on the favourite's no-vig probability. Last bucket is open-ended.
_BUCKETS = [
    ("toss-up (<55%)", 0.0, 0.55),
    ("leve (55-65%)", 0.55, 0.65),
    ("claro (65-75%)", 0.65, 0.75),
    ("fuerte (>75%)", 0.75, None),   # None = open-ended (no upper bound)
]


def _american_to_implied(odds: np.ndarray) -> np.ndarray:
    """American odds -> implied probability, vectorized. Valid UFC odds are
    always <= -100 or >= +100, so the two branches never see odds == 0."""
    return np.where(odds > 0, 100.0 / (odds + 100.0), -odds / (-odds + 100.0))


def _r(v):
    return round(float(v), 4) if v is not None else None


def compute_value_metrics(
    proba_f1: np.ndarray,
    y: np.ndarray,
    odds_f1_american: np.ndarray,
    odds_f2_american: np.ndarray,
    *,
    tossup_threshold: float = TOSSUP_THRESHOLD,
) -> dict | None:
    """Return the value-metrics dict, or None if no fight has both odds.

    proba_f1: model TTA probability that fighter_1 wins.
    y:        1.0 if fighter_1 won, else 0.0.
    odds_*:   American odds aligned with proba_f1/y; NaN where missing.
    """
    proba_f1 = np.asarray(proba_f1, dtype=float)
    y = np.asarray(y, dtype=float)
    o1 = np.asarray(odds_f1_american, dtype=float)
    o2 = np.asarray(odds_f2_american, dtype=float)

    mask = ~np.isnan(o1) & ~np.isnan(o2)
    n = int(mask.sum())
    if n == 0:
        return None

    p = proba_f1[mask]
    yy = y[mask]
    o1, o2 = o1[mask], o2[mask]

    imp1 = _american_to_implied(o1)
    imp2 = _american_to_implied(o2)
    imp1_novig = imp1 / (imp1 + imp2)          # market P(f1 wins), no-vig
    fav_prob = np.maximum(imp1_novig, 1.0 - imp1_novig)

    pred_f1 = (p >= 0.5).astype(float)         # 1 if model picks fighter_1

    # --- Metric 1: toss-up accuracy ---
    tu = fav_prob < tossup_threshold
    tu_n = int(tu.sum())
    if tu_n > 0:
        tu_acc = float((pred_f1[tu] == yy[tu]).mean())
        tu_edge = tu_acc - 0.5
    else:
        tu_acc = tu_edge = None

    # --- Metric 2: upset detection ---
    f1_is_dog = imp1_novig < 0.5                       # f1 is the underdog?
    model_picks_dog = np.where(f1_is_dog, pred_f1 == 1, pred_f1 == 0)
    dog_won = np.where(f1_is_dog, yy == 1, yy == 0)

    underdog_pick_n = int(model_picks_dog.sum())
    underdog_pick_hits = int((model_picks_dog & dog_won).sum())
    upset_precision = (underdog_pick_hits / underdog_pick_n) if underdog_pick_n > 0 else None
    upset_total = int(dog_won.sum())
    upset_detected = int((dog_won & model_picks_dog).sum())
    upset_recall = (upset_detected / upset_total) if upset_total > 0 else None

    # --- Metric 3: brier / logloss model vs market ---
    # Both model and market probabilities are in the fighter_1 frame (P(f1 wins)),
    # aligned with y, so the brier/logloss comparison is apples-to-apples.
    eps = 1e-15

    def _logloss(pr):
        pr = np.clip(pr, eps, 1.0 - eps)
        return float(-(yy * np.log(pr) + (1.0 - yy) * np.log(1.0 - pr)).mean())

    brier_model = float(((p - yy) ** 2).mean())
    brier_market = float(((imp1_novig - yy) ** 2).mean())
    logloss_model = _logloss(p)
    logloss_market = _logloss(imp1_novig)

    # --- Breakdown per bucket ---
    buckets = []
    for label, lo, hi in _BUCKETS:
        b = (fav_prob >= lo) if hi is None else (fav_prob >= lo) & (fav_prob < hi)
        bn = int(b.sum())
        bacc = float((pred_f1[b] == yy[b]).mean()) if bn > 0 else None
        bupset = float(dog_won[b].mean()) if bn > 0 else None
        buckets.append({
            "label": label, "lo": lo, "hi": hi, "n": bn,
            "model_accuracy": _r(bacc), "upset_rate": _r(bupset),
        })

    return {
        "tossup_threshold": tossup_threshold,
        "n_with_odds": n,
        "tossup_n": tu_n,
        "tossup_accuracy": _r(tu_acc),
        "tossup_edge": _r(tu_edge),
        "underdog_pick_n": underdog_pick_n,
        "underdog_pick_hits": underdog_pick_hits,
        "upset_precision": _r(upset_precision),
        "upset_total": upset_total,
        "upset_detected": upset_detected,
        "upset_recall": _r(upset_recall),
        "brier_model": _r(brier_model),
        "brier_market": _r(brier_market),
        "brier_delta": _r(brier_model - brier_market),
        "logloss_model": _r(logloss_model),
        "logloss_market": _r(logloss_market),
        "logloss_delta": _r(logloss_model - logloss_market),
        "buckets": buckets,
    }
