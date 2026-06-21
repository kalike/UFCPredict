"""Dashboard service — aggregates realworld KPIs on-the-fly from the lab's
normalized schema (PredictionSession + Prediction + Fight + Event). Single-tenant
module-level cache, mirroring services/hp_search.py.

"Realworld" is the held-out out-of-sample partition: every real UFC/DWCS card
with event_date >= REALWORLD_CUTOFF_DATE (the same cutoff training flows exclude,
so the model never saw these fights). The dashboard evaluates ALL realworld events
— not just promoted ones, and not the pre-cutoff backtest history (UFC 1 in 1994
onward). fighter_history (PRIDE/Strikeforce/...) cards are excluded as non-UFC.
For each event we use its most recent recalc session
(PredictionSession.source == 'lab_recalc'). The real winner is derived from
Fight.result (win/loss relative to fighter_1), since scraped fights leave
Fight.real_winner empty — see routers/predictions._fight_real_winner.

The set of models is dynamic: whatever model families actually have predictions in
the realworld sessions (today only XGB). Consensus/tiers adapt to that count.
"""

from __future__ import annotations

import threading
from typing import Any

# Preferred display order; any other present model is appended alphabetically.
DASHBOARD_MODEL_ORDER = ("XGB", "RF", "CB", "Deep")
REALWORLD_SESSION_SOURCE = "lab_recalc"
# Real UFC cards (scraped past events + promoted ones); fighter_history is non-UFC.
REALWORLD_EVENT_SOURCES = ("scraped", "promoted")

_cache_lock = threading.Lock()
_cache: dict[Any, Any] = {}  # keyed by min_fights


def _predicted_winner(prob_f1: float, f1_name: str, f2_name: str) -> str:
    return f1_name if prob_f1 >= 0.5 else f2_name


def _real_winner(f1n: str, f2n: str, result: str | None, real_winner: str | None) -> str | None:
    """Resolve a completed fight's winner. Scraped fights store the outcome in
    Fight.result (win/loss relative to fighter_1); promoted sessions use the
    real_winner column. draw/nc -> None (not evaluable). Mirrors
    routers/predictions._fight_real_winner."""
    if real_winner:
        return real_winner
    if result == "win":
        return f1n
    if result == "loss":
        return f2n
    return None


def _consensus(
    votes: list[tuple[str, float]], f1_name: str, f2_name: str
) -> tuple[str, int, int, float]:
    """votes: [(predicted_winner, prob_f1), ...]. Returns
    (consensus_winner, n_for_consensus, n_total, consensus_prob).
    Ties resolved by mean prob_f1 >= 0.5 -> f1."""
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
    """unanimous = all models agree, majority = all-but-one, split = otherwise.
    Works for any model count (with 1 model every fight is 'unanimous')."""
    if n_total <= 0:
        return "split"
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


def _as_aware(dt):
    """Coerce a datetime to tz-aware (UTC) so naive and aware values can be
    compared. event_dates entries are naive while ev.date from the DB is
    tz-aware; mixing them in a comparison raises TypeError."""
    from datetime import timezone
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _fighter_fights_before(ds, name: str, before) -> int:
    """Count a fighter's prior bouts before `before` (datetime), DWCS counts as
    earlier than any UFC event (datetime.min)."""
    from datetime import datetime as _dt
    before = _as_aware(before)
    hist = ds.fighter_histories.get(name, [])
    n = 0
    for h in hist:
        ev_dt = _as_aware(ds.event_dates.get(h.get("event", ""), _dt.min))
        if ev_dt is not None and before is not None and ev_dt < before:
            n += 1
    return n


def _has_only_dwcs(ds, name: str, before) -> bool:
    from datetime import datetime as _dt
    before = _as_aware(before)
    hist = [h for h in ds.fighter_histories.get(name, [])
            if before is not None
            and _as_aware(ds.event_dates.get(h.get("event", ""), _dt.min)) < before]
    if len(hist) != 1:
        return False
    ev = (hist[0].get("event", "") or "").lower()
    return "dwcs" in ev or "contender series" in ev


def _realworld_sessions_by_event(db) -> dict[int, Any]:
    """Most recent realworld (lab_recalc) PredictionSession per event, restricted to
    real UFC cards (Event.source in scraped/promoted) in the held-out realworld
    window (event_date >= REALWORLD_CUTOFF_DATE)."""
    from ufc_core.config import REALWORLD_CUTOFF_DT
    from ufc_core.db import models as m
    cutoff = _as_aware(REALWORLD_CUTOFF_DT)
    rows = (db.query(m.PredictionSession)
              .join(m.Event, m.Event.id == m.PredictionSession.event_id)
              .filter(m.PredictionSession.source == REALWORLD_SESSION_SOURCE,
                      m.Event.source.in_(REALWORLD_EVENT_SOURCES),
                      m.Event.date >= cutoff)
              .order_by(m.PredictionSession.created_at.desc()).all())
    seen: dict[int, Any] = {}
    for s in rows:
        seen.setdefault(s.event_id, s)
    return seen


def _models_present(db, session_ids: list[int]) -> list[str]:
    """Model families that actually have predictions across the given sessions,
    in preferred order then alphabetical for any extras."""
    from ufc_core.db import models as m
    if not session_ids:
        return []
    rows = (db.query(m.Prediction.model_short).distinct()
              .filter(m.Prediction.session_id.in_(session_ids)).all())
    present = {r[0] for r in rows}
    ordered = [s for s in DASHBOARD_MODEL_ORDER if s in present]
    extra = sorted(present - set(ordered))
    return ordered + extra


def build_summary(db, ds, min_fights: int = 0, with_odds: bool = False) -> dict:
    from ufc_core.db import models as m

    # "Universo apostable": cuando with_odds, restringimos la agregación a las
    # peleas RealWorld con odds en ambos lados (las que de verdad apostarías).
    # Es un filtro de agregación análogo a min_fights — NO re-evalúa modelos,
    # solo descarta peleas sin odds del cómputo de accuracy/consenso/tiers.
    odds_lookup = None
    if with_odds:
        from lab_api.services.training import _load_realworld_odds
        odds_lookup = _load_realworld_odds()

    sessions_by_event = _realworld_sessions_by_event(db)
    session_ids = [s.id for s in sessions_by_event.values()]
    models = _models_present(db, session_ids)
    n_models = len(models)

    cons_tiers = {"unanimous": _empty_tier(f"{n_models}-0"),
                  "majority": _empty_tier(f"{max(n_models - 1, 0)}-1"),
                  "split": _empty_tier("Dividido")}
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
                                          for s in models}

    for event_id, sess in sessions_by_event.items():
        ev = db.query(m.Event).filter_by(id=event_id).one_or_none()
        if ev is None:
            continue
        ev_dt = ds.event_dates.get(ev.name) or ev.date
        fights = (db.query(m.Fight).filter_by(event_id=event_id)
                    .order_by(m.Fight.fight_order).all())
        preds = (db.query(m.Prediction)
                   .filter(m.Prediction.session_id == sess.id,
                           m.Prediction.model_short.in_(models)).all()) if models else []
        preds_by_fight: dict[int, dict[str, float]] = {}
        for p in preds:
            preds_by_fight.setdefault(p.fight_id, {})[p.model_short] = p.prob_f1

        n_fights = len(fights)
        n_valid = 0
        n_correct = 0
        model_acc = {s: {"correct": 0, "total": 0} for s in models}
        is_past = False

        for ft in fights:
            f1n = ft.fighter_1.name
            f2n = ft.fighter_2.name
            real = _real_winner(f1n, f2n, ft.result, ft.real_winner)
            f1_hist = bool(ds.fighter_histories.get(f1n))
            f2_hist = bool(ds.fighter_histories.get(f2n))
            f1_dwcs = _has_only_dwcs(ds, f1n, ev_dt) if ev_dt else False
            f2_dwcs = _has_only_dwcs(ds, f2n, ev_dt) if ev_dt else False
            # Universo apostable: descarta peleas sin odds en ambos lados.
            if odds_lookup is not None and (ev.name, frozenset({f1n, f2n})) not in odds_lookup:
                continue
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

        # Skip events that ended up with nothing evaluable (e.g. only draws/nc
        # or no predictions for the present models).
        if not is_past:
            continue

        acc_by_model = {}
        for s in models:
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
            "is_past": True, "accuracy_by_model": acc_by_model,
            "overall_accuracy": round(overall, 4) if overall is not None else None,
        })

    events_out.sort(key=lambda e: e["date"] or "", reverse=True)
    avg_by_model = {}
    for s in models:
        r = per_model_running[s]
        avg = (sum(r["accs"]) / len(r["accs"])) if r["accs"] else None
        avg_by_model[s] = {"avg_accuracy": round(avg, 4) if avg is not None else None,
                           "total_correct": r["correct"], "total_fights": r["total"],
                           "n_events": r["events"]}
    avg_consensus = None
    accs = [e["overall_accuracy"] for e in events_out if e["overall_accuracy"] is not None]
    if accs:
        avg_consensus = round(sum(accs) / len(accs), 4)
    all_fight_rows.sort(key=lambda r: r["date"] or "", reverse=True)

    n_predicted_fights = (
        db.query(m.Prediction)
          .filter(m.Prediction.session_id.in_(session_ids),
                  m.Prediction.model_short.in_(models)).count()
        if session_ids and models else 0
    )

    return {
        "latest_event": events_out[0] if events_out else None,
        "n_predicted_events": len(events_out),
        "n_past_events": len(events_out),
        "n_predicted_fights": n_predicted_fights,
        "n_fighters": db.query(m.Fighter).count(),
        "n_models": n_models,
        "models": list(models),
        "avg_consensus_accuracy": avg_consensus,
        "avg_by_model": avg_by_model,
        "accuracy_by_event": events_out,
        "recent_fights": all_fight_rows[:20],
        "disabled_models": [],
        "min_fights": min_fights,
        "with_odds": with_odds,
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
        sess = (db.query(m.PredictionSession)
                  .filter_by(event_id=ev.id, source=REALWORLD_SESSION_SOURCE)
                  .order_by(m.PredictionSession.created_at.desc()).first())
        ev_dt = ds.event_dates.get(ev.name) or ev.date
        if sess is not None:
            models = _models_present(db, [sess.id])
            fights = db.query(m.Fight).filter_by(event_id=ev.id).order_by(m.Fight.fight_order).all()
            preds = (db.query(m.Prediction).filter(
                m.Prediction.session_id == sess.id,
                m.Prediction.model_short.in_(models)).all()) if models else []
            pbf: dict[int, dict[str, float]] = {}
            for p in preds:
                pbf.setdefault(p.fight_id, {})[p.model_short] = p.prob_f1
            for ft in fights:
                f1n, f2n = ft.fighter_1.name, ft.fighter_2.name
                real = _real_winner(f1n, f2n, ft.result, ft.real_winner)
                if not real:
                    continue
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
                    "predicted_winner": predicted, "real_winner": real,
                    "correct": predicted == real,
                    "consensus_pct": round(cons_prob * 100, 1),
                })
    return {"event": event_name, "fights": fights_out}


def invalidate() -> None:
    with _cache_lock:
        _cache.clear()


def get_summary(db, ds, min_fights: int = 0, with_odds: bool = False) -> dict:
    key = (min_fights, with_odds)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    data = build_summary(db, ds, min_fights, with_odds=with_odds)
    with _cache_lock:
        _cache[key] = data
    return data
