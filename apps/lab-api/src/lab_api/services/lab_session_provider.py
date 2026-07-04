"""Adapt lab prediction sessions to the dict shape the betting engine expects.

The engine (ported from the legacy backend) consumes plain dicts with the keys
`consensus_winner`, `consensus_pct`, `avg_prob_f1`, odds and `real_winner`.
Lab sessions are stored as Prediction rows and rebuilt into RichFightPrediction
by predictions._reconstruct_session_fights. This module bridges the two.
"""
from __future__ import annotations

import threading

from sqlalchemy import func
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_data_store

# Reconstructing the realworld backtest set from Prediction rows is expensive
# (~4.5s for ~46 events) and identical across backtests that only change the
# betting config. Cache it, keyed by a cheap DB fingerprint that changes when
# new recalc sessions appear (so a fresh recalc transparently invalidates it).
_cache_lock = threading.Lock()
_promoted_cache: dict = {"fp": None, "data": None}


def _realworld_fingerprint(db: Session) -> tuple[int, int]:
    row = (
        db.query(
            func.count(db_models.PredictionSession.id),
            func.max(db_models.PredictionSession.id),
        )
        .filter(db_models.PredictionSession.source == "lab_recalc")
        .one()
    )
    return (int(row[0] or 0), int(row[1] or 0))


def invalidate_promoted_cache() -> None:
    with _cache_lock:
        _promoted_cache["fp"] = None
        _promoted_cache["data"] = None


def _get(obj, key, default=None):
    """Read a field from either a pydantic model or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def fight_to_dict(rf) -> dict:
    """Map a RichFightPrediction (model or dict) to the engine's fight dict."""
    consensus = _get(rf, "consensus")
    consensus_winner = _get(consensus, "consensus_winner") if consensus else None
    consensus_pct = _get(consensus, "consensus_pct", 0.0) if consensus else 0.0
    return {
        "fighter_1": _get(rf, "fighter_1"),
        "fighter_2": _get(rf, "fighter_2"),
        "consensus_winner": consensus_winner,
        "consensus_pct": consensus_pct,
        "avg_prob_f1": _get(rf, "prob_f1"),
        "odds_f1_american": _get(rf, "odds_f1_american"),
        "odds_f2_american": _get(rf, "odds_f2_american"),
        "real_winner": _get(rf, "real_winner"),
        "fighter_1_n_fights": _get(rf, "fighter_1_n_fights"),
        "fighter_2_n_fights": _get(rf, "fighter_2_n_fights"),
        "community_picks": _get(rf, "community_picks"),
    }


def get_session_fights(db: Session, session_id: int) -> tuple[str, list[dict]]:
    """Return (event_name, fight_dicts) for one session."""
    from lab_api.routers.predictions import _reconstruct_session_fights

    s = db.query(db_models.PredictionSession).filter_by(id=session_id).one_or_none()
    if s is None:
        return "", []
    ev = db.query(db_models.Event).filter_by(id=s.event_id).one_or_none()
    ds = get_data_store()
    fights = _reconstruct_session_fights(db, ds, s.id)
    return (ev.name if ev else ""), [fight_to_dict(rf) for rf in fights]


def list_promoted_sessions(db: Session) -> list[dict]:
    """The realworld backtest set: ONE session per real UFC event with results.

    Reuses the dashboard's `_realworld_sessions_by_event`, which keeps only the
    most recent lab_recalc session per event in the held-out realworld window
    (event_date >= REALWORLD_CUTOFF). Recalculation accumulates many lab_recalc
    sessions per event over time; iterating all of them would multiply every
    event in the betting backtest (the "realworld appears triplicated" bug).
    Sessions whose fights have no real_winner yet are skipped.
    """
    from lab_api.routers.predictions import _reconstruct_session_fights
    from lab_api.services.dashboard import _realworld_sessions_by_event

    fp = _realworld_fingerprint(db)
    with _cache_lock:
        if _promoted_cache["fp"] == fp and _promoted_cache["data"] is not None:
            return _promoted_cache["data"]

    ds = get_data_store()
    by_event = _realworld_sessions_by_event(db)
    out: list[dict] = []
    for event_id, s in by_event.items():
        ev = db.query(db_models.Event).filter_by(id=event_id).one_or_none()
        fights = [fight_to_dict(rf) for rf in _reconstruct_session_fights(db, ds, s.id)]
        if not any(f.get("real_winner") for f in fights):
            continue
        out.append({
            "id": s.id,
            "event": ev.name if ev else "",
            "created_at": (ev.date.isoformat() if (ev and ev.date)
                           else (s.created_at.isoformat() if s.created_at else "")),
            "fights": fights,
        })
    out.sort(key=lambda x: x["created_at"])
    with _cache_lock:
        _promoted_cache["fp"] = fp
        _promoted_cache["data"] = out
    return out
