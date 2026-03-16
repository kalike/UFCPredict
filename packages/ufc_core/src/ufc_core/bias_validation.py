"""
UFC Predictor — Bias Validation Engine
=======================================
Runs 4 positional-bias tests on each model:
  A) Accuracy identical with original vs. randomised fighter order
  B) Same winner predicted regardless of slot (100 % consistency)
  C) Perfect probability symmetry: P(A vs B) + P(B vs A) = 1.0
  D) Balanced P(F1) distribution once ordering is randomised
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np

from ufc_core.config import BASE_ELO
from ufc_core.data_loader import DataStoreDB as DataStore
from ufc_core.features.engine import compute_features_for_fights
from ufc_core.models.registry import ModelRegistry
from ufc_core.predictor.core import run_predictions

logger = logging.getLogger("ufc-bias")

# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────


def run_bias_validation(
    data_store: DataStore,
    registry: ModelRegistry,
    *,
    model_shorts: list[str] | None = None,
    seed: int = 42,
) -> dict:
    """Run the full 4-test bias suite.

    Parameters
    ----------
    data_store : loaded DataStore
    registry   : loaded ModelRegistry
    model_shorts : optional list of short names to restrict to
    seed       : RNG seed for reproducible swap pattern

    Returns
    -------
    {
        "n_fights": int,
        "n_swapped": int,
        "models": {
            "<short>": {
                "test_a": { "acc_orig": float, "acc_rand": float, "delta": float, "pass": bool },
                "test_b": { "consistent": int, "inconsistent": int, "pct": float, "pass": bool },
                "test_c": { "max_delta": float, "mean_delta": float, "pass": bool },
                "test_d": { "p_f1_orig": float, "p_f1_rand": float,
                             "pct_pred_f1_orig": float, "pct_pred_f1_rand": float },
                "pass_all": bool,
            }
        },
        "pass_all": bool,
        "ran_at": str,      # ISO timestamp
    }
    """
    rng = np.random.RandomState(seed)
    now = datetime.now()

    # ── Collect past fights ──
    events = data_store.get_predicted_events()
    past_events = [e for e in events if e.get("date") and e["date"] < now]

    fights_original: list[dict] = []
    fights_random: list[dict] = []

    for ev in past_events:
        ev_name = ev["canonical_name"]
        for fight in data_store.get_fights_by_event(ev_name):
            f1 = fight.get("fighter_1", "")
            f2 = fight.get("fighter_2", "")
            if not f1 or not f2:
                continue
            fights_original.append(fight)

            if rng.random() < 0.5:
                swapped = dict(fight)
                swapped["fighter_1"] = f2
                swapped["fighter_2"] = f1
                swapped["odds_f1_american"] = fight.get("odds_f2_american")
                swapped["odds_f2_american"] = fight.get("odds_f1_american")
                swapped["result"] = 0
                fights_random.append(swapped)
            else:
                fights_random.append(fight)

    n_fights = len(fights_original)
    if n_fights == 0:
        return {
            "n_fights": 0,
            "n_swapped": 0,
            "models": {},
            "pass_all": True,
            "ran_at": now.isoformat(),
        }

    n_swapped = sum(
        1
        for o, r in zip(fights_original, fights_random, strict=False)
        if o["fighter_1"] != r["fighter_1"]
    )

    # ── Compute features ──
    df_orig, _ = compute_features_for_fights(
        fights_original,
        data_store.fighter_histories,
        data_store.fighter_lookup,
        data_store.event_dates,
        registry.elo_ratings,
        BASE_ELO,
    )
    df_rand, _ = compute_features_for_fights(
        fights_random,
        data_store.fighter_histories,
        data_store.fighter_lookup,
        data_store.event_dates,
        registry.elo_ratings,
        BASE_ELO,
    )

    # ── Predictions ──
    res_orig = run_predictions(df_orig, registry)
    res_rand = run_predictions(df_rand, registry)

    y_real_orig = df_orig["result"].values
    y_real_rand = df_rand["result"].values

    f1_names_orig = df_orig["fighter_1"].values
    f2_names_orig = df_orig["fighter_2"].values
    f1_names_rand = df_rand["fighter_1"].values
    f2_names_rand = df_rand["fighter_2"].values

    n_computed = min(len(df_orig), len(df_rand))
    swap_indices = [i for i in range(n_computed) if f1_names_orig[i] != f1_names_rand[i]]

    # ── Per-model tests ──
    model_results: dict[str, dict] = {}

    for model_name in sorted(res_orig.keys()):
        short = registry._get_short_name(model_name)
        if model_shorts and short not in model_shorts:
            continue

        pred_o = res_orig[model_name]["y_pred"]
        pred_r = res_rand[model_name]["y_pred"]
        p_o = res_orig[model_name]["y_proba"]
        p_r = res_rand[model_name]["y_proba"]

        # ── TEST A: Accuracy orig vs rand ──
        acc_o = float(np.mean(pred_o == y_real_orig))
        acc_r = float(np.mean(pred_r == y_real_rand))
        delta_a = abs(acc_o - acc_r)

        # ── TEST B: Same winner regardless of position ──
        consistent = 0
        inconsistent = 0
        for i in range(n_computed):
            winner_orig = f1_names_orig[i] if pred_o[i] == 1 else f2_names_orig[i]
            winner_rand = f1_names_rand[i] if pred_r[i] == 1 else f2_names_rand[i]
            if winner_orig == winner_rand:
                consistent += 1
            else:
                inconsistent += 1
        pct_consist = consistent / max(consistent + inconsistent, 1) * 100

        # ── TEST C: Probability symmetry ──
        if swap_indices:
            deltas_c = []
            for i in swap_indices:
                expected = 1.0 - p_o[i]
                actual = p_r[i]
                deltas_c.append(abs(expected - actual))
            deltas_arr = np.array(deltas_c)
            max_delta_c = float(np.max(deltas_arr))
            mean_delta_c = float(np.mean(deltas_arr))
        else:
            max_delta_c = 0.0
            mean_delta_c = 0.0

        # ── TEST D: Distribution P(F1) ──
        p_f1_orig = float(np.mean(p_o))
        p_f1_rand = float(np.mean(p_r))
        pct_pred_f1_orig = float(np.mean(pred_o == 1) * 100)
        pct_pred_f1_rand = float(np.mean(pred_r == 1) * 100)

        pass_a = delta_a < 0.001
        pass_b = inconsistent == 0
        pass_c = max_delta_c < 0.001

        model_results[short] = {
            "test_a": {
                "acc_orig": round(acc_o, 4),
                "acc_rand": round(acc_r, 4),
                "delta": round(delta_a, 6),
                "pass": pass_a,
            },
            "test_b": {
                "consistent": consistent,
                "inconsistent": inconsistent,
                "pct": round(pct_consist, 1),
                "pass": pass_b,
            },
            "test_c": {
                "max_delta": round(max_delta_c, 6),
                "mean_delta": round(mean_delta_c, 6),
                "pass": pass_c,
            },
            "test_d": {
                "p_f1_orig": round(p_f1_orig, 4),
                "p_f1_rand": round(p_f1_rand, 4),
                "pct_pred_f1_orig": round(pct_pred_f1_orig, 1),
                "pct_pred_f1_rand": round(pct_pred_f1_rand, 1),
            },
            "pass_all": pass_a and pass_b and pass_c,
        }

    return {
        "n_fights": n_fights,
        "n_swapped": n_swapped,
        "models": model_results,
        "pass_all": all(m["pass_all"] for m in model_results.values()),
        "ran_at": now.isoformat(),
    }
