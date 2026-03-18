"""HP Search worker — runs Optuna trials in a background thread.

Single-tenant: one search at a time. State for the "current run" lives
in a module-level dict guarded by a lock. Persisted history lives in
hp_search_study + hp_search_trial DB tables.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger("lab-api.hp_search")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "is_running": False,
    "study_id": None,
    "started_at": None,
    "finished_at": None,
    "model_short": None,
    "completed_trials": 0,
    "best_value": None,
    "step": None,
    "error": None,
}

SUPPORTED_FAMILIES = {"LGBM", "LG52", "XGB", "XG52"}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def _sample_lgbm_params(trial):
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 800, step=50),
        "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 7, 127, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 80),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 5.0, log=True),
    }


def _sample_xgb_params(trial):
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 800, step=50),
        "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 5.0, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
    }


def _build_clf(model_short: str, params: dict):
    if model_short in ("LGBM", "LG52"):
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_jobs=-1, verbose=-1, **params)
    if model_short in ("XGB", "XG52"):
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_jobs=-1, eval_metric="logloss", verbosity=0, **params,
        )
    raise ValueError(f"Unsupported family for HP search: {model_short}")


def start_hp_search(req: dict, study_id: int) -> dict:
    """Kick off an HP search in a background thread.

    Args:
        req: HpSearchRequest dict (model_short, feature_set, n_trials, dataset, ...).
        study_id: id of the HpSearchStudy row already created by the router.
    """
    with _lock:
        if _state["is_running"]:
            return {"started": False, "message": "Another HP search is already running"}
        _state.update({
            "is_running": True,
            "study_id": study_id,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "model_short": req.get("model_short"),
            "completed_trials": 0,
            "best_value": None,
            "step": "starting",
            "error": None,
        })

    def _job():
        from sqlalchemy.orm import Session
        import optuna
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db import models as db_models
        from ufc_core.data_loader import DataStoreDB
        from sklearn.metrics import accuracy_score

        model_short = req["model_short"]
        n_trials = int(req.get("n_trials", 50))
        dataset_key = req.get("dataset", "since2010")
        since_year = {"since2010": 2010, "since2015": 2015, "since2020": 2020}.get(dataset_key, 2010)

        db: Session = SessionLocal()
        study_row = db.query(db_models.HpSearchStudy).filter_by(id=study_id).one()

        try:
            if model_short not in SUPPORTED_FAMILIES:
                study_row.status = "not_supported"
                study_row.finished_at = datetime.now(UTC)
                db.commit()
                with _lock:
                    _state.update({
                        "is_running": False,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": f"HP search not supported for {model_short}",
                        "error": f"Only {sorted(SUPPORTED_FAMILIES)} supported",
                    })
                return

            with _lock:
                _state["step"] = "loading data"
            ds = DataStoreDB()
            ds.load()

            with _lock:
                _state["step"] = "building dataset"
            # Lazy import to avoid coupling at module load
            from lab_api.services.training import _build_dataset_simple
            from ufc_core.config import TEST_CUTOFF_DT
            df, feat_cols = _build_dataset_simple(ds, since_year)

            event_col = df["event_date"]
            try:
                event_col = event_col.dt.tz_localize(None)
            except (AttributeError, TypeError):
                pass
            train_df = df[event_col < TEST_CUTOFF_DT]
            test_df = df[event_col >= TEST_CUTOFF_DT]
            if len(train_df) < 50 or len(test_df) < 10:
                raise ValueError(f"Split too small: train={len(train_df)}, test={len(test_df)}")

            X_train, y_train = train_df[feat_cols].values, train_df["result"].values
            X_test, y_test = test_df[feat_cols].values, test_df["result"].values

            sampler_fn = _sample_lgbm_params if model_short in ("LGBM", "LG52") else _sample_xgb_params

            study_row.status = "running"
            db.commit()

            optuna.logging.set_verbosity(optuna.logging.WARNING)
            study = optuna.create_study(
                direction="maximize",
                sampler=optuna.samplers.TPESampler(seed=42),
            )

            def objective(trial: optuna.Trial) -> float:
                params = sampler_fn(trial)
                clf = _build_clf(model_short, params)
                clf.fit(X_train, y_train)
                preds = clf.predict(X_test)
                acc = float(accuracy_score(y_test, preds))

                # Persist trial row
                db.add(db_models.HpSearchTrial(
                    study_id=study_id,
                    trial_idx=trial.number,
                    params=params,
                    value=acc,
                    status="completed",
                ))
                db.commit()

                # Update progress
                with _lock:
                    _state["completed_trials"] = trial.number + 1
                    if _state["best_value"] is None or acc > _state["best_value"]:
                        _state["best_value"] = acc
                    _state["step"] = f"trial {trial.number + 1}/{n_trials} acc={acc:.4f}"
                return acc

            study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

            study_row.status = "completed"
            study_row.finished_at = datetime.now(UTC)
            study_row.params = {
                **(study_row.params or {}),
                "best_value": study.best_value,
                "best_params": study.best_params,
            }
            db.commit()

            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": f"done · best={study.best_value:.4f}",
                })
        except Exception as e:
            logger.exception("HP search failed")
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
