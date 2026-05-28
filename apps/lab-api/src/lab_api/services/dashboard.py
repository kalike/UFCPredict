"""Dashboard service — aggregates KPIs on-the-fly from the lab's normalized
schema (PredictionSession + Prediction + Fight + Event). Single-tenant
module-level cache, mirroring services/hp_search.py.

The lab does NOT precompute consensus like the legacy backend's SessionFight; we
compute predicted winner, consensus, tiers and accuracy from per-model
Prediction rows, restricted to the four canonical families.
"""

from __future__ import annotations

import threading
from typing import Any

DASHBOARD_MODELS = ("XGB", "RF", "CB", "Deep")

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {}  # keyed by min_fights


def _predicted_winner(prob_f1: float, f1_name: str, f2_name: str) -> str:
    return f1_name if prob_f1 >= 0.5 else f2_name


def _consensus(
    votes: list[tuple[str, float]], f1_name: str, f2_name: str
) -> tuple[str, int, int, float]:
    """votes: [(predicted_winner, prob_f1), ...]. Returns
    (consensus_winner, n_for_consensus, n_total, consensus_prob).
    Ties (2-2) resolved by mean prob_f1 >= 0.5 -> f1."""
    n_total = len(votes)
    n_f1 = sum(1 for w, _ in votes if w == f1_name)
    n_f2 = n_total - n_f1
    mean_prob_f1 = sum(p for _, p in votes) / n_total if n_total else 0.5
    if n_f1 > n_f2:
        winner, n_for = f1_name, n_f1
    elif n_f2 > n_f1:
        winner, n_for = f2_name, n_f2
    else:
        winner = f1_name if mean_prob_f1 >= 0.5 else f2_name
        n_for = n_f1 if winner == f1_name else n_f2
    consensus_prob = mean_prob_f1 if winner == f1_name else 1.0 - mean_prob_f1
    return winner, n_for, n_total, consensus_prob


def _consensus_tier(n_for: int, n_total: int) -> str:
    """Four-model tiers: 4-0 unanimous, 3-1 majority, 2-2 split."""
    if n_for == n_total:
        return "unanimous"
    if n_for == n_total - 1:
        return "majority"
    return "split"


def _probability_tier(prob: float) -> str:
    if prob >= 0.70:
        return "extreme"
    if prob >= 0.65:
        return "very_high"
    if prob >= 0.60:
        return "high"
    if prob >= 0.55:
        return "medium"
    return "low"
