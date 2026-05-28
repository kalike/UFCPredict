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


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _empty_tier(label: str) -> dict:
    return {"correct": 0, "total": 0, "accuracy": None, "label": label}


def _finalize_tier(t: dict) -> dict:
    t["accuracy"] = (t["correct"] / t["total"]) if t["total"] else None
    return t


def _fighter_fights_before(ds, name: str, before) -> int:
    """Count a fighter's prior bouts before `before` (datetime), DWCS counts as
    earlier than any UFC event (datetime.min)."""
    from datetime import datetime as _dt
    hist = ds.fighter_histories.get(name, [])
    n = 0
    for h in hist:
        ev_dt = ds.event_dates.get(h.get("event", ""), _dt.min)
        if ev_dt is not None and ev_dt < before:
            n += 1
    return n


def _has_only_dwcs(ds, name: str, before) -> bool:
    from datetime import datetime as _dt
    hist = [h for h in ds.fighter_histories.get(name, [])
            if ds.event_dates.get(h.get("event", ""), _dt.min) < before]
    if len(hist) != 1:
        return False
    ev = (hist[0].get("event", "") or "").lower()
    return "dwcs" in ev or "contender series" in ev


def _latest_sessions_by_event(db):
    """Most recent PredictionSession per event_id."""
    from ufc_core.db import models as m
    rows = (db.query(m.PredictionSession)
              .order_by(m.PredictionSession.created_at.desc()).all())
    seen: dict[int, Any] = {}
    for s in rows:
        seen.setdefault(s.event_id, s)
    return seen


def build_summary(db, ds, min_fights: int = 0) -> dict:
    from ufc_core.db import models as m

    sessions_by_event = _latest_sessions_by_event(db)
    cons_tiers = {"unanimous": _empty_tier("4-0"), "majority": _empty_tier("3-1"),
                  "split": _empty_tier("2-2")}
    prob_tiers = {"low": _empty_tier("50-55%"), "medium": _empty_tier("55-60%"),
                  "high": _empty_tier("60-65%"), "very_high": _empty_tier("65-70%"),
                  "extreme": _empty_tier("70%+")}
    spec_tiers = {"dwcs_debut": _empty_tier("Debut DWCS"),
                  "no_history": _empty_tier("Sin historial"),
                  "combined": _empty_tier("Ambos casos")}
    special_case_fights: list[dict] = []

    events_out: list[dict] = []
    all_fight_rows: list[dict] = []
    per_model_running: dict[str, dict] = {s: {"correct": 0, "total": 0, "accs": [], "events": 0}
                                          for s in DASHBOARD_MODELS}

    for event_id, sess in sessions_by_event.items():
        ev = db.query(m.Event).filter_by(id=event_id).one_or_none()
        if ev is None:
            continue
        ev_dt = ds.event_dates.get(ev.name) or ev.date
        fights = (db.query(m.Fight).filter_by(event_id=event_id)
                    .order_by(m.Fight.fight_order).all())
        preds = (db.query(m.Prediction)
                   .filter(m.Prediction.session_id == sess.id,
                           m.Prediction.model_short.in_(DASHBOARD_MODELS)).all())
        preds_by_fight: dict[int, dict[str, float]] = {}
        for p in preds:
            preds_by_fight.setdefault(p.fight_id, {})[p.model_short] = p.prob_f1

        n_fights = len(fights)
        n_valid = 0
        n_correct = 0
        model_acc = {s: {"correct": 0, "total": 0} for s in DASHBOARD_MODELS}
        is_past = False

        for ft in fights:
            f1n = ft.fighter_1.name
            f2n = ft.fighter_2.name
            real = ft.real_winner
            f1_hist = bool(ds.fighter_histories.get(f1n))
            f2_hist = bool(ds.fighter_histories.get(f2n))
            f1_dwcs = _has_only_dwcs(ds, f1n, ev_dt) if ev_dt else False
            f2_dwcs = _has_only_dwcs(ds, f2n, ev_dt) if ev_dt else False
            probs = preds_by_fight.get(ft.id, {})
            has_consensus = len(probs) > 0
            predicted = None
            if has_consensus:
                votes = [(_predicted_winner(pf, f1n, f2n), pf) for pf in probs.values()]
                predicted, n_for, n_total, cons_prob = _consensus(votes, f1n, f2n)
            if real:
                is_past = True
                if (ev_dt is not None
                        and _fighter_fights_before(ds, f1n, ev_dt) >= min_fights
                        and _fighter_fights_before(ds, f2n, ev_dt) >= min_fights):
                    if has_consensus:
                        n_valid += 1
                        correct = predicted == real
                        if correct:
                            n_correct += 1
                        for short, pf in probs.items():
                            pw = _predicted_winner(pf, f1n, f2n)
                            model_acc[short]["total"] += 1
                            if pw == real:
                                model_acc[short]["correct"] += 1
                        ct = _consensus_tier(n_for, n_total)
                        cons_tiers[ct]["total"] += 1
                        if correct:
                            cons_tiers[ct]["correct"] += 1
                        pt = _probability_tier(cons_prob)
                        prob_tiers[pt]["total"] += 1
                        if correct:
                            prob_tiers[pt]["correct"] += 1
                        all_fight_rows.append({
                            "event": ev.name, "date": _iso(ev_dt),
                            "fighter_1": f1n, "fighter_2": f2n,
                            "predicted_winner": predicted, "real_winner": real,
                            "correct": correct, "consensus_pct": round(cons_prob * 100, 1),
                        })
                if has_consensus:
                    is_dwcs = f1_dwcs or f2_dwcs
                    is_no_hist = not (f1_hist and f2_hist)
                    correct = predicted == real
                    if is_dwcs:
                        spec_tiers["dwcs_debut"]["total"] += 1
                        spec_tiers["dwcs_debut"]["correct"] += int(correct)
                    if is_no_hist:
                        spec_tiers["no_history"]["total"] += 1
                        spec_tiers["no_history"]["correct"] += int(correct)
                    if is_dwcs or is_no_hist:
                        spec_tiers["combined"]["total"] += 1
                        spec_tiers["combined"]["correct"] += int(correct)
                        special_case_fights.append({
                            "event": ev.name, "date": _iso(ev_dt),
                            "fighter_1": f1n, "fighter_2": f2n,
                            "real_winner": real, "predicted_winner": predicted,
                            "correct": correct,
                            "fighter_1_dwcs_only": f1_dwcs, "fighter_2_dwcs_only": f2_dwcs,
                            "fighter_1_has_history": f1_hist, "fighter_2_has_history": f2_hist,
                        })

        acc_by_model = {}
        for s in DASHBOARD_MODELS:
            ma = model_acc[s]
            acc = (ma["correct"] / ma["total"]) if ma["total"] else None
            acc_by_model[s] = {"accuracy": round(acc, 4) if acc is not None else None,
                               "correct": ma["correct"], "total": ma["total"]}
            if ma["total"]:
                per_model_running[s]["correct"] += ma["correct"]
                per_model_running[s]["total"] += ma["total"]
                per_model_running[s]["accs"].append(acc)
                per_model_running[s]["events"] += 1
        overall = (n_correct / n_valid) if n_valid else None
        events_out.append({
            "event": ev.name, "date": _iso(ev_dt), "location": ev.location or "",
            "n_fights": n_fights, "n_fights_valid": n_valid, "n_correct": n_correct,
            "is_past": is_past, "accuracy_by_model": acc_by_model,
            "overall_accuracy": round(overall, 4) if overall is not None else None,
        })

    events_out.sort(key=lambda e: e["date"] or "", reverse=True)
    past_events = [e for e in events_out if e["is_past"]]
    avg_by_model = {}
    for s in DASHBOARD_MODELS:
        r = per_model_running[s]
        avg = (sum(r["accs"]) / len(r["accs"])) if r["accs"] else None
        avg_by_model[s] = {"avg_accuracy": round(avg, 4) if avg is not None else None,
                           "total_correct": r["correct"], "total_fights": r["total"],
                           "n_events": r["events"]}
    avg_consensus = None
    accs = [e["overall_accuracy"] for e in past_events if e["overall_accuracy"] is not None]
    if accs:
        avg_consensus = round(sum(accs) / len(accs), 4)
    all_fight_rows.sort(key=lambda r: r["date"] or "", reverse=True)

    return {
        "latest_event": past_events[0] if past_events else None,
        "n_predicted_events": len(events_out),
        "n_past_events": len(past_events),
        "n_predicted_fights": db.query(m.Prediction).filter(
            m.Prediction.model_short.in_(DASHBOARD_MODELS)).count(),
        "n_fighters": db.query(m.Fighter).count(),
        "n_models": len(DASHBOARD_MODELS),
        "avg_consensus_accuracy": avg_consensus,
        "avg_by_model": avg_by_model,
        "accuracy_by_event": events_out,
        "recent_fights": all_fight_rows[:20],
        "disabled_models": [],
        "min_fights": min_fights,
        "consensus_tiers": {k: _finalize_tier(v) for k, v in cons_tiers.items()},
        "probability_tiers": {k: _finalize_tier(v) for k, v in prob_tiers.items()},
        "special_case_tiers": {k: _finalize_tier(v) for k, v in spec_tiers.items()},
        "special_case_fights": special_case_fights,
    }


def get_event_fights(db, ds, event_name: str, min_fights: int = 0) -> dict:
    from ufc_core.db import models as m
    ev = db.query(m.Event).filter_by(name=event_name).one_or_none()
    fights_out: list[dict] = []
    if ev is not None:
        sess = (db.query(m.PredictionSession).filter_by(event_id=ev.id)
                  .order_by(m.PredictionSession.created_at.desc()).first())
        ev_dt = ds.event_dates.get(ev.name) or ev.date
        if sess is not None:
            fights = db.query(m.Fight).filter_by(event_id=ev.id).order_by(m.Fight.fight_order).all()
            preds = (db.query(m.Prediction).filter(
                m.Prediction.session_id == sess.id,
                m.Prediction.model_short.in_(DASHBOARD_MODELS)).all())
            pbf: dict[int, dict[str, float]] = {}
            for p in preds:
                pbf.setdefault(p.fight_id, {})[p.model_short] = p.prob_f1
            for ft in fights:
                if not ft.real_winner:
                    continue
                f1n, f2n = ft.fighter_1.name, ft.fighter_2.name
                if ev_dt is not None and not (
                        _fighter_fights_before(ds, f1n, ev_dt) >= min_fights
                        and _fighter_fights_before(ds, f2n, ev_dt) >= min_fights):
                    continue
                probs = pbf.get(ft.id, {})
                if not probs:
                    continue
                votes = [(_predicted_winner(pf, f1n, f2n), pf) for pf in probs.values()]
                predicted, _, _, cons_prob = _consensus(votes, f1n, f2n)
                fights_out.append({
                    "event": ev.name, "date": _iso(ev_dt),
                    "fighter_1": f1n, "fighter_2": f2n,
                    "predicted_winner": predicted, "real_winner": ft.real_winner,
                    "correct": predicted == ft.real_winner,
                    "consensus_pct": round(cons_prob * 100, 1),
                })
    return {"event": event_name, "fights": fights_out}


def invalidate() -> None:
    with _cache_lock:
        _cache.clear()


def get_summary(db, ds, min_fights: int = 0) -> dict:
    with _cache_lock:
        if min_fights in _cache:
            return _cache[min_fights]
    data = build_summary(db, ds, min_fights)
    with _cache_lock:
        _cache[min_fights] = data
    return data
