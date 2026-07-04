"""Dashboard — RealWorld-holdout evaluation source.

The default dashboard (``dashboard.build_summary``) aggregates the predictions
the recalc stored per card (``PredictionSession`` rows). This module offers an
alternative source that evaluates the **active models** on the held-out
``realworld_df`` exactly like training/HP-search do: rebuild the RealWorld
dataset (``_build_realworld_df``: PIT features, deterministic 50/50 swap, odds)
and score each active model with TTA — the same path that produces a version's
``realworld_accuracy``.

It is slower than the cached aggregation (it rebuilds the dataset + predicts in
~6s) so results are cached per ``(min_fights, with_odds)`` and invalidated
together with the main dashboard cache.

Output shape matches ``build_summary`` so the frontend consumes it unchanged,
plus ``source: "realworld_df"``.
"""
from __future__ import annotations

import threading

import numpy as np

from .dashboard import (
    _consensus, _consensus_tier, _empty_tier, _finalize_tier, _iso,
    _predicted_winner, _probability_tier, DASHBOARD_MODEL_ORDER,
)

_cache: dict = {}
_cache_lock = threading.Lock()


def invalidate() -> None:
    with _cache_lock:
        _cache.clear()


def _model_tta_proba(art: dict, rwdf) -> np.ndarray:
    """P(fighter_1 wins) per RealWorld fight with TTA — mirrors
    trainer.core.evaluate_realworld so the numbers match a version's
    realworld_accuracy exactly."""
    from ufc_core.transforms import FeatureTransformer
    from ufc_core.tta import build_tta_flip

    clf = art["clf"]
    feat_cols = art["feat_cols"]
    imputer = art.get("imputer")
    scaler = art.get("scaler")

    is_52f = any(c.startswith("f1_") for c in feat_cols)
    transformer = FeatureTransformer(enabled=True, delta_overrides=not is_52f)
    rw = rwdf.copy()
    for c in feat_cols:
        if c not in rw.columns:
            rw[c] = 0
    rw_t = imputer.transform(rw) if imputer is not None else rw
    rw_t = transformer.transform_df(rw_t)
    X = rw_t[feat_cols].values.astype(np.float32)
    np.nan_to_num(X, copy=False, nan=0.0)
    X_flip = build_tta_flip(X, feat_cols)
    if scaler is not None:
        X, X_flip = scaler.transform(X), scaler.transform(X_flip)
    p_orig = np.atleast_1d(clf.predict_proba(X)[:, 1])
    p_flip = np.atleast_1d(clf.predict_proba(X_flip)[:, 1])
    return np.clip((p_orig + (1.0 - p_flip)) / 2.0, 0.0, 1.0)


def build_realworld_summary(db, ds, min_fights: int = 0, with_odds: bool = False,
                            unanimous_only: bool = False) -> dict:
    """Evaluate the active models on the held-out realworld_df and return the
    same KPI shape as dashboard.build_summary (source='realworld_df')."""
    from ufc_core.trainer.core import recalculate_elo
    from lab_api.services.predict_engine import build_versions
    from lab_api.services.training import _build_realworld_df, _load_realworld_odds

    versions, _skipped = build_versions(db)
    # Preferred display order, restricted to models that actually loaded.
    present = {v.short for v in versions}
    models = [s for s in DASHBOARD_MODEL_ORDER if s in present] + \
             sorted(present - set(DASHBOARD_MODEL_ORDER))
    n_models = len(models)
    ver_by_short = {v.short: v for v in versions}

    cons_tiers = {"unanimous": _empty_tier(f"{n_models}-0"),
                  "majority": _empty_tier(f"{max(n_models - 1, 0)}-1"),
                  "split": _empty_tier("Dividido")}
    prob_tiers = {"low": _empty_tier("50-55%"), "medium": _empty_tier("55-60%"),
                  "high": _empty_tier("60-65%"), "very_high": _empty_tier("65-70%"),
                  "extreme": _empty_tier("70%+")}

    elo, elo_pre = recalculate_elo(data_store=ds, base_elo=1500.0, save_to_disk=False)
    rwdf = _build_realworld_df(ds, elo, elo_pre, 1500.0, odds_lookup=_load_realworld_odds())

    # Filters (applied once so every model scores the same aligned fight set).
    if min_fights > 0 and "f1_total_fights" in rwdf.columns:
        rwdf = rwdf[(rwdf["f1_total_fights"] >= min_fights)
                    & (rwdf["f2_total_fights"] >= min_fights)]
    if with_odds:
        has_odds = rwdf["odds_f1_american"].notna() & rwdf["odds_f2_american"].notna()
        rwdf = rwdf[has_odds]
    rwdf = rwdf.reset_index(drop=True)
    n = len(rwdf)

    if n == 0 or n_models == 0:
        return _empty_summary(models, n_models, min_fights, with_odds, unanimous_only, db)

    proba = {s: _model_tta_proba(ver_by_short[s].art, rwdf) for s in models}
    rw_label = rwdf["rw_label"].values.astype(int)
    events = rwdf["event"].tolist()
    f1s = rwdf["fighter_1"].tolist()
    f2s = rwdf["fighter_2"].tolist()
    dates = rwdf["event_date"].tolist()

    per_model = {s: {"correct": 0, "total": 0} for s in models}
    per_event: dict[str, dict] = {}
    n_correct = 0
    fight_rows: list[dict] = []

    for i in range(n):
        f1n, f2n = f1s[i], f2s[i]
        real = f1n if rw_label[i] == 1 else f2n
        votes = [(_predicted_winner(float(proba[s][i]), f1n, f2n), float(proba[s][i]))
                 for s in models]
        predicted, n_for, n_total, cons_prob = _consensus(votes, f1n, f2n)
        # Solo consenso unánime: descarta peleas sin acuerdo total entre modelos.
        if unanimous_only and n_for != n_total:
            continue
        ev = events[i]
        e = per_event.setdefault(ev, {
            "correct": 0, "total": 0, "date": _iso(dates[i]),
            "by_model": {s: {"correct": 0, "total": 0} for s in models},
        })
        for s, (pw, _pf) in zip(models, votes):
            hit = int(pw == real)
            per_model[s]["total"] += 1
            per_model[s]["correct"] += hit
            e["by_model"][s]["total"] += 1
            e["by_model"][s]["correct"] += hit
        correct = predicted == real
        n_correct += int(correct)
        ct = _consensus_tier(n_for, n_total)
        cons_tiers[ct]["total"] += 1
        cons_tiers[ct]["correct"] += int(correct)
        pt = _probability_tier(cons_prob)
        prob_tiers[pt]["total"] += 1
        prob_tiers[pt]["correct"] += int(correct)
        e["total"] += 1
        e["correct"] += int(correct)
        fight_rows.append({
            "event": ev, "date": _iso(dates[i]),
            "fighter_1": f1n, "fighter_2": f2n,
            "predicted_winner": predicted, "real_winner": real,
            "correct": correct, "consensus_pct": round(cons_prob * 100, 1),
        })

    def _ev_by_model(d: dict) -> dict:
        out = {}
        for s in models:
            bm = d["by_model"][s]
            acc = (bm["correct"] / bm["total"]) if bm["total"] else None
            out[s] = {"accuracy": round(acc, 4) if acc is not None else None,
                      "correct": bm["correct"], "total": bm["total"]}
        return out

    events_out = [{
        "event": ev, "date": d["date"], "location": "",
        "n_fights": d["total"], "n_fights_valid": d["total"], "n_correct": d["correct"],
        "is_past": True, "accuracy_by_model": _ev_by_model(d),
        "overall_accuracy": round(d["correct"] / d["total"], 4) if d["total"] else None,
    } for ev, d in per_event.items()]
    events_out.sort(key=lambda e: e["date"] or "", reverse=True)

    avg_by_model = {}
    for s in models:
        pm = per_model[s]
        acc = (pm["correct"] / pm["total"]) if pm["total"] else None
        avg_by_model[s] = {"avg_accuracy": round(acc, 4) if acc is not None else None,
                           "total_correct": pm["correct"], "total_fights": pm["total"],
                           "n_events": len(per_event)}
    ev_accs = [e["overall_accuracy"] for e in events_out if e["overall_accuracy"] is not None]
    avg_consensus = round(sum(ev_accs) / len(ev_accs), 4) if ev_accs else None
    fight_rows.sort(key=lambda r: r["date"] or "", reverse=True)

    from ufc_core.db import models as m
    return {
        "latest_event": events_out[0] if events_out else None,
        "n_predicted_events": len(events_out),
        "n_past_events": len(events_out),
        "n_predicted_fights": n * n_models,
        "n_fighters": db.query(m.Fighter).count(),
        "n_models": n_models,
        "models": list(models),
        "avg_consensus_accuracy": avg_consensus,
        "avg_by_model": avg_by_model,
        "accuracy_by_event": events_out,
        "recent_fights": fight_rows[:20],
        "disabled_models": [],
        "min_fights": min_fights,
        "with_odds": with_odds,
        "unanimous_only": unanimous_only,
        "source": "realworld_df",
        "consensus_tiers": {k: _finalize_tier(v) for k, v in cons_tiers.items()},
        "probability_tiers": {k: _finalize_tier(v) for k, v in prob_tiers.items()},
        # Special-case tiers are recalc-only (need fighter-history context); the
        # holdout source reports them empty so the UI degrades gracefully.
        "special_case_tiers": {k: _finalize_tier(_empty_tier(lbl)) for k, lbl in (
            ("dwcs_debut", "Debut DWCS"), ("no_history", "Sin historial"),
            ("combined", "Ambos casos"))},
        "special_case_fights": [],
    }


def _empty_summary(models, n_models, min_fights, with_odds, unanimous_only, db) -> dict:
    from ufc_core.db import models as m
    return {
        "latest_event": None, "n_predicted_events": 0, "n_past_events": 0,
        "n_predicted_fights": 0, "n_fighters": db.query(m.Fighter).count(),
        "n_models": n_models, "models": list(models), "avg_consensus_accuracy": None,
        "avg_by_model": {}, "accuracy_by_event": [], "recent_fights": [],
        "disabled_models": [], "min_fights": min_fights, "with_odds": with_odds,
        "unanimous_only": unanimous_only, "source": "realworld_df",
        "consensus_tiers": {k: _finalize_tier(_empty_tier(lbl)) for k, lbl in (
            ("unanimous", f"{n_models}-0"), ("majority", f"{max(n_models-1,0)}-1"),
            ("split", "Dividido"))},
        "probability_tiers": {k: _finalize_tier(_empty_tier(lbl)) for k, lbl in (
            ("low", "50-55%"), ("medium", "55-60%"), ("high", "60-65%"),
            ("very_high", "65-70%"), ("extreme", "70%+"))},
        "special_case_tiers": {k: _finalize_tier(_empty_tier(lbl)) for k, lbl in (
            ("dwcs_debut", "Debut DWCS"), ("no_history", "Sin historial"),
            ("combined", "Ambos casos"))},
        "special_case_fights": [],
    }


def get_realworld_summary(db, ds, min_fights: int = 0, with_odds: bool = False,
                          unanimous_only: bool = False) -> dict:
    key = (min_fights, with_odds, unanimous_only)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    data = build_realworld_summary(db, ds, min_fights, with_odds=with_odds,
                                   unanimous_only=unanimous_only)
    with _cache_lock:
        _cache[key] = data
    return data
