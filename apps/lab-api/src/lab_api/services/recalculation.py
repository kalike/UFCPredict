"""Recalculation service — re-runs predict against past events.

Single-tenant. Reuses the predict-future logic but iterates over events.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger("lab-api.recalculation")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "total_events": 0,
    "completed_events": 0,
    "skipped_events": 0,
    "step": None,
    "error": None,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def start_recalculation(event_ids: list[int] | None) -> dict:
    with _lock:
        if _state["is_running"]:
            return {"started": False, "message": "A recalculation is already running"}
        _state.update({
            "is_running": True,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "total_events": 0,
            "completed_events": 0,
            "skipped_events": 0,
            "step": "starting",
            "error": None,
        })

    def _job():
        from sqlalchemy.orm import Session
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db import models as db_models

        db: Session = SessionLocal()
        try:
            if event_ids:
                events = (
                    db.query(db_models.Event).filter(
                        db_models.Event.id.in_(event_ids)
                    ).all()
                )
            else:
                # Default scope = the RealWorld held-out window only (event_date >=
                # REALWORLD_CUTOFF over real UFC cards), matching what the dashboard
                # evaluates — not the whole scraped backtest history.
                from datetime import timezone
                from ufc_core.config import REALWORLD_CUTOFF_DT
                cutoff = REALWORLD_CUTOFF_DT.replace(tzinfo=timezone.utc)
                events = (
                    db.query(db_models.Event)
                      .filter(db_models.Event.status == "completed",
                              db_models.Event.source.in_(("scraped", "promoted")),
                              db_models.Event.date >= cutoff)
                      .order_by(db_models.Event.date.desc().nullslast())
                      .all()
                )

            with _lock:
                _state["total_events"] = len(events)

            if not events:
                with _lock:
                    _state.update({
                        "is_running": False,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": "no events to recalc",
                    })
                return

            # Active models snapshot
            active_rows = db.query(db_models.ActiveModel).all()
            if not active_rows:
                with _lock:
                    _state.update({
                        "is_running": False,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": "no active models",
                        "error": "Activate at least one trained model first",
                    })
                return

            from lab_api.routers.predictions import predict_event

            # We call predict_event directly with a fresh session per event.
            for ev in events:
                ev_id = ev.id
                with _lock:
                    _state["step"] = f"recalc event {ev_id} ({ev.name})"
                # Use a fresh session because predict_event manages its own commits.
                from ufc_core.db.engine import SessionLocal as _SL
                sub_db = _SL()
                try:
                    # Source = lab_recalc so we can distinguish from lab_preview later
                    try:
                        resp = predict_event(ev_id, db=sub_db)
                        # Tag the just-created session
                        sess = (
                            sub_db.query(db_models.PredictionSession)
                                  .filter_by(id=resp.session_id).one()
                        )
                        sess.source = "lab_recalc"
                        sub_db.commit()
                        with _lock:
                            _state["completed_events"] += 1
                    except Exception as e:
                        logger.warning("recalc event %s failed: %s", ev_id, e)
                        with _lock:
                            _state["skipped_events"] += 1
                finally:
                    sub_db.close()

            # The new lab_recalc sessions changed what the dashboard shows —
            # drop the cached summaries so the next request rebuilds with them.
            try:
                from lab_api.services import dashboard as _dsvc
                from lab_api.services import dashboard_realworld as _rwsvc
                _dsvc.invalidate()
                _rwsvc.invalidate()
            except Exception:
                logger.warning("dashboard cache invalidation after recalc failed",
                               exc_info=True)

            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": (
                        f"done · completed={_state['completed_events']}"
                        f" skipped={_state['skipped_events']}"
                    ),
                })
        except Exception as e:
            logger.exception("recalculation failed")
            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": "failed",
                    "error": repr(e),
                })
        finally:
            db.close()

    threading.Thread(target=_job, daemon=True).start()
    return {"started": True}
