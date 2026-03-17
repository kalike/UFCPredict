"""Training service — single in-flight job orchestrator for the lab.

Single-tenant: only one training job runs at a time. State lives in a
module-level dict guarded by a lock.
"""

import logging
import threading
from datetime import datetime, UTC
from typing import Any


logger = logging.getLogger("lab-api.training")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "model_short": None,
    "step": None,
    "result_version_id": None,
    "error": None,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def start_training(req: dict) -> dict:
    """Launch a training job in a background thread.

    Args:
        req: TrainJobConfig dict (model_short, dataset, feature_set,
             feat_type, test_cutoff, min_fights, use_pit, ...).
    """
    with _lock:
        if _state["is_running"]:
            return {"started": False, "message": "A training job is already running"}
        _state.update({
            "is_running": True,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "model_short": req.get("model_short"),
            "step": "starting",
            "result_version_id": None,
            "error": None,
        })

    ts_id = None

    def _job():
        nonlocal ts_id
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db import models as db_models

        db = SessionLocal()
        ts = db_models.TrainingSession(model_id=None, request=req, status="running")
        db.add(ts)
        db.commit()
        ts_id = ts.id

        try:
            with _lock:
                _state["step"] = "loading data"

            # Minimal: stub — full trainer flow is large. Record a placeholder.
            # The real ufc_core.trainer.core.train_model integration is
            # the subject of a follow-up task; here we mark the session as
            # complete without an artifact so the UI can show end-to-end.
            with _lock:
                _state["step"] = "skipped (trainer integration pending)"

            ts.status = "skipped"
            ts.finished_at = datetime.now(UTC)
            db.commit()

            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": "done (stub)",
                })

        except Exception as e:
            logger.exception("training job failed")
            ts.status = "failed"
            ts.error_msg = repr(e)
            ts.finished_at = datetime.now(UTC)
            db.commit()
            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": "failed",
                    "error": repr(e),
                })
        finally:
            db.close()

    t = threading.Thread(target=_job, daemon=True)
    t.start()
    t.join(timeout=0.1)  # brief join to let ts_id get set before returning

    with _lock:
        # ts_id might still be None if thread hasn't committed yet; that's ok
        return {"started": True, "training_session_id": ts_id}
