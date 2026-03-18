"""Combo Search worker — evaluates combinations of trained model versions.

Single-tenant: one search at a time.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, UTC
from itertools import combinations
from typing import Any

import joblib
import numpy as np


logger = logging.getLogger("lab-api.combo_search")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "is_running": False,
    "study_id": None,
    "started_at": None,
    "finished_at": None,
    "evaluated": 0,
    "total": 0,
    "best_value": None,
    "best_shorts": None,
    "step": None,
    "error": None,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def _load_artifact(uri: str) -> dict:
    path = uri[len("file://"):] if uri.startswith("file://") else uri
    return joblib.load(path)


def start_combo_search(req: dict, study_id: int) -> dict:
    """Spawn a background thread that enumerates and scores combinations."""
    with _lock:
        if _state["is_running"]:
            return {"started": False, "message": "Another combo search is already running"}
        _state.update({
            "is_running": True,
            "study_id": study_id,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "evaluated": 0,
            "total": 0,
            "best_value": None,
            "best_shorts": None,
            "step": "starting",
            "error": None,
        })

    def _job():
        from sqlalchemy.orm import Session
        from sklearn.metrics import accuracy_score, log_loss
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db import models as db_models
        from ufc_core.data_loader import DataStoreDB
        from ufc_core.config import TEST_CUTOFF_DT

        db: Session = SessionLocal()
        study_row = db.query(db_models.ComboSearchStudy).filter_by(id=study_id).one()

        sizes = req.get("sizes") or [2, 3]
        max_combos = int(req.get("max_combos", 60))
        only_starred = bool(req.get("only_starred", False))

        try:
            with _lock:
                _state["step"] = "loading data"
            ds = DataStoreDB()
            ds.load()

            with _lock:
                _state["step"] = "building dataset"
            from lab_api.services.training import _build_dataset_simple
            df, feat_cols = _build_dataset_simple(ds, 2010)

            event_col = df["event_date"]
            try:
                event_col = event_col.dt.tz_localize(None)
            except (AttributeError, TypeError):
                pass
            test_df = df[event_col >= TEST_CUTOFF_DT]
            if len(test_df) < 10:
                raise ValueError(f"Test split too small: {len(test_df)}")

            y_test = test_df["result"].astype(int).values

            # Discover candidate versions
            with _lock:
                _state["step"] = "loading model versions"
            mv_query = db.query(db_models.ModelVersion).join(
                db_models.Model, db_models.Model.id == db_models.ModelVersion.model_id
            )
            if only_starred:
                mv_query = mv_query.filter(db_models.ModelVersion.starred.is_(True))
            mvs = mv_query.all()

            candidates: list[dict] = []
            for v in mvs:
                m = db.query(db_models.Model).filter_by(id=v.model_id).one()
                try:
                    art = _load_artifact(v.artifact_uri)
                except Exception as e:
                    logger.warning("could not load %s v%s: %s", m.short, v.version_idx, e)
                    continue
                clf = art["clf"]
                vfeat = art.get("feat_cols", feat_cols)
                # Ensure feature alignment — fill missing with 0
                missing = [c for c in vfeat if c not in df.columns]
                if missing:
                    use_X = np.zeros((len(test_df), len(vfeat)), dtype=float)
                    present_idx = [i for i, c in enumerate(vfeat) if c in df.columns]
                    use_X[:, present_idx] = test_df[[vfeat[i] for i in present_idx]].values
                else:
                    use_X = test_df[vfeat].values
                try:
                    probs = clf.predict_proba(use_X)[:, 1].astype(float)
                except Exception as e:
                    logger.warning("predict_proba failed for %s v%s: %s", m.short, v.version_idx, e)
                    continue
                candidates.append({
                    "version_id": v.id, "version_idx": v.version_idx,
                    "short": m.short, "probs": probs,
                })

            if len(candidates) < 2:
                raise ValueError(
                    f"Need at least 2 trained model versions; got {len(candidates)}"
                )

            # Enumerate combinations
            combos: list[tuple] = []
            for k in sizes:
                if k > len(candidates):
                    continue
                for combo in combinations(range(len(candidates)), k):
                    combos.append(combo)
                    if len(combos) >= max_combos:
                        break
                if len(combos) >= max_combos:
                    break
            combos = combos[:max_combos]

            with _lock:
                _state["total"] = len(combos)
                _state["step"] = f"evaluating {len(combos)} combinations"

            study_row.status = "running"
            db.commit()

            best_acc = -1.0
            best_shorts: list[str] | None = None
            for trial_idx, combo in enumerate(combos):
                # Average probabilities
                stacked = np.column_stack([candidates[i]["probs"] for i in combo])
                avg = stacked.mean(axis=1)
                preds = (avg >= 0.5).astype(int)
                acc = float(accuracy_score(y_test, preds))
                try:
                    ll = float(log_loss(y_test, avg.clip(1e-6, 1 - 1e-6)))
                except Exception:
                    ll = None

                shorts = [candidates[i]["short"] for i in combo]
                version_ids = [candidates[i]["version_id"] for i in combo]

                db.add(db_models.ComboSearchTrial(
                    study_id=study_id,
                    trial_idx=trial_idx,
                    params={"shorts": shorts, "version_ids": version_ids, "log_loss": ll},
                    value=acc,
                    status="completed",
                ))
                db.commit()

                if acc > best_acc:
                    best_acc = acc
                    best_shorts = shorts

                with _lock:
                    _state["evaluated"] = trial_idx + 1
                    _state["best_value"] = best_acc
                    _state["best_shorts"] = best_shorts
                    _state["step"] = f"trial {trial_idx + 1}/{len(combos)} acc={acc:.4f}"

            study_row.status = "completed"
            study_row.finished_at = datetime.now(UTC)
            study_row.params = {
                **(study_row.params or {}),
                "best_value": best_acc,
                "best_shorts": best_shorts,
                "n_evaluated": len(combos),
            }
            db.commit()

            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": f"done · best_acc={best_acc:.4f} ({best_shorts})",
                })
        except Exception as e:
            logger.exception("combo search failed")
            study_row.status = "failed"
            study_row.finished_at = datetime.now(UTC)
            try:
                db.commit()
            except Exception:
                db.rollback()
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
