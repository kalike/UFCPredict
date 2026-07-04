"""Value-vs-market metrics over the RealWorld window.

Pure, dependency-free (numpy only). Compares the model's TTA probability
against the no-vig implied probability of the market, on the subset of
fights that have both American odds. See
docs/specs/2026-06-17-value-metrics-realworld-design.md.
"""

from __future__ import annotations

import math

import numpy as np

TOSSUP_THRESHOLD = 0.55


def json_sanitize(obj):
    """Recursively replace non-finite floats (NaN/Inf) with None.

    PostgreSQL JSONB rejects NaN/Infinity tokens, so any metrics dict must pass
    through this before being persisted — a safety net against divide-by-zero or
    empty-slice means anywhere upstream silently producing a non-finite value.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_sanitize(v) for v in obj]
    return obj

# (label, lo, hi) on the favourite's no-vig probability. Last bucket is open-ended.
_BUCKETS = [
    ("toss-up (<55%)", 0.0, 0.55),
    ("leve (55-65%)", 0.55, 0.65),
    ("claro (65-75%)", 0.65, 0.75),
    ("fuerte (>75%)", 0.75, None),   # None = open-ended (no upper bound)
]


def _american_to_implied(odds: np.ndarray) -> np.ndarray:
    """American odds -> implied probability, vectorized. Callers must pass only
    valid American odds (|odds| >= 100); compute_value_metrics enforces that.

    np.where evaluates BOTH branches for every element, so the unused branch can
    still divide by zero (e.g. odds == +100 makes the negative branch's
    denominator 0). The result is discarded, but numpy would warn — errstate
    silences that benign warning.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        pos = 100.0 / (odds + 100.0)
        neg = -odds / (-odds + 100.0)
    return np.where(odds > 0, pos, neg)


def _r(v):
    return round(float(v), 4) if v is not None else None


def compute_value_metrics(
    proba_f1: np.ndarray,
    y: np.ndarray,
    odds_f1_american: np.ndarray,
    odds_f2_american: np.ndarray,
    *,
    tossup_threshold: float = TOSSUP_THRESHOLD,
    event_dates: np.ndarray | None = None,
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

    # Only fights with VALID American odds on both sides. Beyond NaN, exclude
    # 0 / sub-100 placeholders (|odds| < 100 is not a real American price): they
    # otherwise yield imp == 0 and a 0/0 no-vig division → NaN, which PostgreSQL
    # JSONB rejects on persist.
    mask = (
        ~np.isnan(o1) & ~np.isnan(o2)
        & (np.abs(o1) >= 100.0) & (np.abs(o2) >= 100.0)
    )
    n = int(mask.sum())
    if n == 0:
        return None

    p = proba_f1[mask]
    yy = y[mask]
    o1, o2 = o1[mask], o2[mask]

    imp1 = _american_to_implied(o1)
    imp2 = _american_to_implied(o2)
    denom = imp1 + imp2
    with np.errstate(divide="ignore", invalid="ignore"):
        imp1_novig = np.where(denom > 0, imp1 / denom, 0.5)  # market P(f1 wins), no-vig
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

    # --- ROI value-betting EV+ (neto de vig) + split temporal sel/val ---
    # Edge per side vs the WITH-VIG implied prob (imp1/imp2 already computed
    # above as the raw _american_to_implied, pre-no-vig). Bet 1u flat on the
    # higher-edge side when its edge > 0; with vig at most one side qualifies.
    dec1 = np.where(o1 > 0, 1.0 + o1 / 100.0, 1.0 + 100.0 / (-o1))
    dec2 = np.where(o2 > 0, 1.0 + o2 / 100.0, 1.0 + 100.0 / (-o2))
    edge1 = p - imp1
    edge2 = (1.0 - p) - imp2
    bet_f1 = (edge1 >= edge2) & (edge1 > 0)
    bet_f2 = (edge2 > edge1) & (edge2 > 0)
    has_pick = bet_f1 | bet_f2
    ret = np.zeros(n)
    ret[bet_f1] = np.where(yy[bet_f1] == 1, dec1[bet_f1] - 1.0, -1.0)
    ret[bet_f2] = np.where(yy[bet_f2] == 0, dec2[bet_f2] - 1.0, -1.0)

    def _roi(sub_mask):
        k = int(sub_mask.sum())
        roi = float(ret[sub_mask].mean()) if k > 0 else None
        return _r(roi), k

    # --- ROI dog-picks: flat-stake on the underdog only when the model backs it.
    # Reuses f1_is_dog / model_picks_dog / dog_won from Metric 2. This is the
    # narrow universe where the model tends to have real edge; the EV+ universe
    # above also bets favourites and bleeds vig on false edges.
    dec_dog = np.where(f1_is_dog, dec1, dec2)
    ret_dog = np.zeros(n)
    ret_dog[model_picks_dog] = np.where(
        dog_won[model_picks_dog], dec_dog[model_picks_dog] - 1.0, -1.0
    )

    def _roi_dog(sub_mask):
        k = int(sub_mask.sum())
        roi = float(ret_dog[sub_mask].mean()) if k > 0 else None
        return _r(roi), k

    roi_extra: dict = {}
    if event_dates is not None:
        ed = np.asarray(event_dates)[mask].astype("datetime64[D]").astype("int64")
        split_day = int(np.median(ed))  # median of fights-with-odds, not of picks
        sel = ed < split_day
        val = ~sel
        roi_ev, n_ev = _roi(has_pick)
        roi_sel, n_sel = _roi(has_pick & sel)
        roi_val, n_val = _roi(has_pick & val)
        roi_dog, n_dog = _roi_dog(model_picks_dog)
        roi_dog_sel, n_dog_sel = _roi_dog(model_picks_dog & sel)
        roi_dog_val, n_dog_val = _roi_dog(model_picks_dog & val)
        roi_extra = {
            "roi_ev": roi_ev, "n_picks_ev": n_ev,
            "roi_ev_sel": roi_sel, "n_picks_sel": n_sel,
            "roi_ev_val": roi_val, "n_picks_val": n_val,
            "roi_dog": roi_dog, "n_picks_dog": n_dog,
            "roi_dog_sel": roi_dog_sel, "n_picks_dog_sel": n_dog_sel,
            "roi_dog_val": roi_dog_val, "n_picks_dog_val": n_dog_val,
            "split_date": str(np.datetime64(split_day, "D")),
        }

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
        **roi_extra,
    }
