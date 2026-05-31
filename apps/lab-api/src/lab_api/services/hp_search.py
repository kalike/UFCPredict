"""HP Search worker — Optuna over the legacy backend's 4-fold temporal CV.

Single-tenant: one search at a time. The "current run" state lives in a
module-level dict guarded by a lock; persisted history lives in the
hp_search_study + hp_search_trial DB tables.

Methodology mirrors the legacy backend (the legacy hp_search):
  * 4 rolling temporal folds (expanding train window), realworld held out.
  * Per fold: the SAME _preprocess_split used by the real training flow
    (augment → features → impute → transform). Augmentation defaults ON
    (mirrors the legacy backend's D+Aug PRO models); pass req["augment"]=False
    to disable.
  * Optuna objective = mean of the chosen metric(s) across folds; multi-
    objective searches build a Pareto front.
  * Per trial we also record prod_* (last/production fold) and realworld_*
    (a production-style refit evaluated TTA on the held-out realworld set).
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
    "n_trials": 0,
    "best_value": None,
    "objectives": [],
    "step": None,
    "error": None,
}

# The four canonical lab families (see training.TRAINABLE) all support HP search.
SUPPORTED_FAMILIES = {"XGB", "RF", "CB", "Deep"}

# Metrics that improve when they go DOWN (objective direction defaults).
MINIMIZE_METRICS = {"logloss", "brier", "overfit"}
VALID_METRICS = {"accuracy", "logloss", "brier", "f1", "overfit", "auc"}


def get_status() -> dict:
    with _lock:
        return dict(_state)


# ──────────────────────────────────────────────────────────────────────
# Hyperparameter samplers / builders (one per canonical family)
# ──────────────────────────────────────────────────────────────────────
def _sample_params(model_short: str, trial) -> dict:
    """Suggest a hyperparameter set for one trial. Returns JSON-serializable
    values only (persisted to hp_search_trial.params).

    Ranges mirror the legacy backend's HP_SEARCH_SPACES (the legacy trainer) so
    the lab explores the same, well-regularized regions instead of saturating
    the train set. Two deliberate deviations from the legacy backend:
      * CatBoost drops `bagging_temperature` (incompatible with `subsample`,
        which needs a Bernoulli bootstrap — see _build_clf).
      * Deep MLP keeps a moderate `epochs` range: the lab wrapper has no
        early-stopping/patience, so the legacy backend's 150–400 would be both
        impractically slow (one realworld refit per trial) and overfit-prone.
    """
    if model_short == "XGB":
        # Hardened vs the legacy backend: shallow trees + heavy regularization to
        # curb XGB's tendency to memorize the train set on this dataset.
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
            "max_depth": trial.suggest_int("max_depth", 2, 4),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 0.8),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 0.7),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.01, 5.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 5, 30),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        }
    if model_short == "RF":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 700, step=100),
            "max_depth": trial.suggest_categorical("max_depth", [4, 6, 8, 10, 12, 16]),
            "min_samples_split": trial.suggest_int("min_samples_split", 3, 25),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 40),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.3, 0.5]),
            "max_samples": trial.suggest_float("max_samples", 0.6, 0.95, step=0.05),
            "criterion": trial.suggest_categorical("criterion", ["gini", "entropy"]),
            "class_weight": trial.suggest_categorical(
                "class_weight", [None, "balanced", "balanced_subsample"]
            ),
        }
    if model_short == "CB":
        return {
            "iterations": trial.suggest_int("iterations", 100, 500, step=50),
            "depth": trial.suggest_int("depth", 3, 7),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 0.95),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 0.5, 20.0, log=True),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 15, 60),
            "random_strength": trial.suggest_float("random_strength", 0.1, 10.0, log=True),
        }
    if model_short == "Deep":
        return {
            "hidden_dims": trial.suggest_categorical(
                "hidden_dims",
                ["64,32", "128,64", "128,64,32", "128,128,64,64", "256,128,64"],
            ),
            "dropout": trial.suggest_float("dropout", 0.1, 0.4, step=0.05),
            "lr": trial.suggest_float("lr", 1e-4, 5e-3, log=True),
            "weight_decay": trial.suggest_float("weight_decay", 1e-5, 5e-2, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128, 256]),
            "epochs": trial.suggest_int("epochs", 40, 120, step=20),
        }
    raise ValueError(f"Unsupported family for HP search: {model_short}")


def _build_clf(model_short: str, params: dict):
    if model_short == "XGB":
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_jobs=-1, eval_metric="logloss", verbosity=0, **params,
        )
    if model_short == "RF":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(n_jobs=-1, random_state=42, **params)
    if model_short == "CB":
        from catboost import CatBoostClassifier
        p = dict(params)
        # subsample requires a non-Bayesian bootstrap in CatBoost.
        if "subsample" in p:
            p.setdefault("bootstrap_type", "Bernoulli")
        return CatBoostClassifier(
            verbose=False, allow_writing_files=False, random_seed=42, **p,
        )
    if model_short == "Deep":
        from lab_api.services.torch_wrap import make_deep_mlp
        p = dict(params)
        hd = p.pop("hidden_dims")
        hidden = tuple(int(x) for x in hd.split(",")) if isinstance(hd, str) else tuple(hd)
        return make_deep_mlp(hidden_dims=hidden, **p)
    raise ValueError(f"Unsupported family for HP search: {model_short}")


def _parse_objectives(req: dict) -> list[dict]:
    """Normalize the request's objectives into [{metric, direction}, ...]."""
    raw = req.get("objectives")
    objectives: list[dict] = []
    if raw:
        for obj in raw:
            m = obj.get("metric")
            if m not in VALID_METRICS:
                continue
            d = obj.get("direction") or ("minimize" if m in MINIMIZE_METRICS else "maximize")
            objectives.append({"metric": m, "direction": d})
    if not objectives:
        objectives = [{"metric": "accuracy", "direction": "maximize"}]
    return objectives


def _fold_definitions():
    """The 4 rolling temporal folds (expanding train, realworld held out).

    Each fold's `label` is the validation window (year range) shown per trial.
    """
    from datetime import datetime as _dt
    from ufc_core.config import TEST_CUTOFF_DT, REALWORLD_CUTOFF_DT
    tc, rc = TEST_CUTOFF_DT.year, REALWORLD_CUTOFF_DT.year
    return [
        {"val_start": _dt(2019, 1, 1), "val_end": _dt(2021, 1, 1), "label": "2019–21"},
        {"val_start": _dt(2021, 1, 1), "val_end": _dt(2023, 1, 1), "label": "2021–23"},
        {"val_start": _dt(2023, 1, 1), "val_end": TEST_CUTOFF_DT, "label": f"2023–{tc % 100}"},
        {"val_start": TEST_CUTOFF_DT, "val_end": REALWORLD_CUTOFF_DT, "label": f"{tc % 100}–{rc % 100} (prod)"},
    ]


def _compute_fold_metrics(y_train, y_val, y_pred, proba, train_pred) -> dict:
    """All metrics for a single fold (mirrors the legacy backend)."""
    import numpy as np  # noqa: F401
    from sklearn.metrics import (
        accuracy_score, log_loss, brier_score_loss, f1_score, roc_auc_score,
    )
    p = proba if proba is not None else y_pred.astype(float)
    train_acc = accuracy_score(y_train, train_pred) if train_pred is not None else None
    val_acc = accuracy_score(y_val, y_pred)
    metrics = {
        "accuracy": float(val_acc),
        "train_accuracy": float(train_acc) if train_acc is not None else None,
        "logloss": float(log_loss(y_val, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y_val, p)),
        "f1": float(f1_score(y_val, y_pred, zero_division=0)),
        "overfit": float(abs(train_acc - val_acc)) if train_acc is not None else 0.0,
    }
    if proba is not None:
        try:
            metrics["auc"] = float(roc_auc_score(y_val, proba))
        except ValueError:
            metrics["auc"] = float(val_acc)
    else:
        metrics["auc"] = float(val_acc)
    return metrics


def start_hp_search(req: dict, study_id: int) -> dict:
    """Kick off an HP search in a background thread.

    Args:
        req: HpSearchRequest dict (model_short, feature_set, feat_type, dataset,
             min_fights, n_trials, objectives).
        study_id: id of the HpSearchStudy row already created by the router.
    """
    objectives = _parse_objectives(req)
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
            "n_trials": int(req.get("n_trials", 50)),
            "best_value": None,
            "objectives": objectives,
            "step": "starting",
            "error": None,
        })

    def _job():
        from sqlalchemy.orm import Session
        import numpy as np
        import optuna
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db import models as db_models
        from ufc_core.data_loader import DataStoreDB
        from ufc_core.config import REALWORLD_CUTOFF_DT
        from ufc_core.trainer.core import (
            _build_dataset, _preprocess_split, evaluate_realworld, recalculate_elo,
        )
        from ufc_core.imputer import FeatureImputer
        from lab_api.services.training import _build_realworld_df, _resolve_feat_type

        model_short = req["model_short"]
        n_trials = int(req.get("n_trials", 50))
        min_fights = int(req.get("min_fights") or 0)
        feature_set = req.get("feature_set", "v7")
        dataset_key = req.get("dataset", "since2010")
        since_year = {"since2010": 2010, "since2015": 2015, "since2020": 2020}.get(dataset_key, 2010)
        primary = objectives[0]
        prim_metric, prim_dir = primary["metric"], primary["direction"]
        overfit_penalty = float(req.get("overfit_penalty") or 0.0)
        use_penalty = overfit_penalty > 0
        # A/B fighter-swap augmentation, ON by default (parity with the
        # legacy backend's D+Aug PRO models). Searching without it would explore a
        # different train distribution than the adopted model trains on.
        do_augment = bool(req.get("augment", True))
        # Penalized mode collapses to a single objective: primary − λ·overfit.
        is_multi = len(objectives) > 1 and not use_penalty

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
            for k, val in list(ds.event_dates.items()):
                if getattr(val, "tzinfo", None) is not None:
                    ds.event_dates[k] = val.replace(tzinfo=None)

            with _lock:
                _state["step"] = "recalculating ELO (pre-fight)"
            elo_ratings, elo_pre_fight = recalculate_elo(
                data_store=ds, base_elo=1500.0, save_to_disk=True,
            )

            feat_type = _resolve_feat_type(req, model_short)
            with _lock:
                _state["step"] = f"building dataset ({feature_set}/{feat_type})"
            df = _build_dataset(
                ds, elo_ratings, base_elo=1500.0, since_year=since_year,
                elo_pre_fight=elo_pre_fight, min_fights=min_fights,
                use_pit=True, exclude_realworld=True,
            )
            # tz-naive event_date so fold comparisons never mix tz-aware/naive.
            ev = df["event_date"]
            try:
                df["event_date"] = ev.dt.tz_localize(None)
            except (AttributeError, TypeError):
                pass

            realworld_df = _build_realworld_df(ds, elo_ratings, elo_pre_fight, 1500.0)
            folds = _fold_definitions()

            study_row.status = "running"
            db.commit()

            optuna.logging.set_verbosity(optuna.logging.WARNING)
            if use_penalty:
                # Maximize a single penalized score: primary − λ·overfit.
                study = optuna.create_study(
                    direction="maximize",
                    sampler=optuna.samplers.TPESampler(seed=42),
                )
            elif is_multi:
                study = optuna.create_study(
                    directions=[o["direction"] for o in objectives],
                    sampler=optuna.samplers.TPESampler(seed=42),
                )
            else:
                study = optuna.create_study(
                    direction=prim_dir,
                    sampler=optuna.samplers.TPESampler(seed=42),
                )

            def _better(a: float, b: float) -> bool:
                return a < b if prim_dir == "minimize" else a > b

            def objective(trial):
                params = _sample_params(model_short, trial)

                fold_metrics: dict[str, list[float]] = {
                    "accuracy": [], "train_accuracy": [], "logloss": [], "brier": [],
                    "auc": [], "f1": [], "overfit": [],
                }
                per_fold: list[dict] = []  # [{label, accuracy, train_accuracy, n_val}] in fold order
                for fold in folds:
                    train_mask = df["event_date"] < fold["val_start"]
                    val_mask = (df["event_date"] >= fold["val_start"]) & (df["event_date"] < fold["val_end"])
                    train_fold = df[train_mask].copy()
                    val_fold = df[val_mask].copy()
                    if len(train_fold) == 0 or len(val_fold) == 0:
                        continue
                    pp = _preprocess_split(
                        train_fold, val_fold, feat_type=feat_type,
                        feature_set=feature_set, do_augment=do_augment, scaler_type=None,
                    )
                    clf = _build_clf(model_short, params)
                    clf.fit(pp.X_train, pp.y_train)
                    y_pred = clf.predict(pp.X_test)
                    train_pred = clf.predict(pp.X_train)
                    proba = None
                    if hasattr(clf, "predict_proba"):
                        pr = clf.predict_proba(pp.X_test)
                        proba = pr[:, 1] if pr.shape[1] > 1 else pr[:, 0]
                    fm = _compute_fold_metrics(pp.y_train, pp.y_test, y_pred, proba, train_pred)
                    for k, v in fm.items():
                        if v is not None:
                            fold_metrics[k].append(v)
                    per_fold.append({
                        "label": fold["label"],
                        "accuracy": fm["accuracy"],
                        "train_accuracy": fm["train_accuracy"],
                        "n_val": int(len(val_fold)),
                    })

                if not fold_metrics["accuracy"]:
                    return [0.0] * len(objectives) if is_multi else 0.0

                means = {k: float(np.mean(v)) for k, v in fold_metrics.items() if v}
                prod = {k: float(v[-1]) for k, v in fold_metrics.items() if v}

                # Realworld held-out: production-style refit on ALL pre-realworld
                # data, evaluated TTA on the held-out realworld set. We score it
                # two ways from the SAME refit (the fit is the expensive part):
                #   * realworld_*    → min_fights=0 (full set, comparable across jobs)
                #   * realworld_mf_* → the job's own min_fights (the subset you'd
                #     actually bet on if you applied that filter)
                rw = {"realworld_accuracy": None, "realworld_correct": 0, "realworld_total": 0}
                rw_mf = {
                    "realworld_mf_accuracy": None, "realworld_mf_correct": 0,
                    "realworld_mf_total": 0, "realworld_min_fights": min_fights,
                }
                try:
                    pp_full = _preprocess_split(
                        df.copy(), df.copy(), feat_type=feat_type,
                        feature_set=feature_set, do_augment=do_augment, scaler_type=None,
                    )
                    feat_cols = pp_full.feat_cols
                    full_df = df.copy()
                    for c in feat_cols:
                        if c not in full_df.columns:
                            full_df[c] = 0
                    imputer_prod = FeatureImputer().fit(full_df, feat_cols)
                    full_imp = pp_full.transformer.transform_df(imputer_prod.transform(full_df))
                    X_full = full_imp[feat_cols].values.astype(np.float32)
                    y_full = full_df["result"].values.astype(np.float32)
                    prod_model = _build_clf(model_short, params)
                    prod_model.fit(X_full, y_full)
                    if realworld_df is not None and len(realworld_df) > 0:
                        rw_eval = evaluate_realworld(
                            prod_model, None, imputer_prod, feat_cols, realworld_df,
                            is_pytorch=False, min_fights=0,
                        )
                        rw = {
                            "realworld_accuracy": rw_eval.get("realworld_accuracy"),
                            "realworld_correct": rw_eval.get("realworld_correct", 0),
                            "realworld_total": rw_eval.get("realworld_total", 0),
                        }
                        # Subset filtered by the job's min_fights (skip re-eval
                        # when it's 0 — identical to the full set).
                        if min_fights > 0:
                            mf_eval = evaluate_realworld(
                                prod_model, None, imputer_prod, feat_cols, realworld_df,
                                is_pytorch=False, min_fights=min_fights,
                            )
                            rw_mf = {
                                "realworld_mf_accuracy": mf_eval.get("realworld_accuracy"),
                                "realworld_mf_correct": mf_eval.get("realworld_correct", 0),
                                "realworld_mf_total": mf_eval.get("realworld_total", 0),
                                "realworld_min_fights": min_fights,
                            }
                        else:
                            rw_mf = {
                                "realworld_mf_accuracy": rw["realworld_accuracy"],
                                "realworld_mf_correct": rw["realworld_correct"],
                                "realworld_mf_total": rw["realworld_total"],
                                "realworld_min_fights": 0,
                            }
                except Exception:
                    logger.exception("realworld eval failed for trial %s (non-fatal)", trial.number)

                metrics = {
                    "mean_accuracy": means.get("accuracy"),
                    "mean_train_accuracy": means.get("train_accuracy"),
                    "mean_auc": means.get("auc"),
                    "mean_f1": means.get("f1"),
                    "mean_logloss": means.get("logloss"),
                    "mean_brier": means.get("brier"),
                    "mean_overfit": means.get("overfit"),
                    "prod_accuracy": prod.get("accuracy"),
                    "prod_brier": prod.get("brier"),
                    "fold_accuracies": per_fold,
                    **rw,
                    **rw_mf,
                    "is_pareto": False,
                }

                db.add(db_models.HpSearchTrial(
                    study_id=study_id,
                    trial_idx=trial.number,
                    params=params,
                    value=means.get(prim_metric),
                    metrics=metrics,
                    status="completed",
                ))
                db.commit()

                with _lock:
                    _state["completed_trials"] = trial.number + 1
                    pv = means.get(prim_metric)
                    if pv is not None and (_state["best_value"] is None or _better(pv, _state["best_value"])):
                        _state["best_value"] = pv
                    _state["step"] = (
                        f"trial {trial.number + 1}/{n_trials} "
                        f"{prim_metric}={means.get(prim_metric, 0):.4f} "
                        f"rw={rw['realworld_accuracy'] if rw['realworld_accuracy'] is not None else '-'}"
                    )

                if use_penalty:
                    po = means.get(prim_metric, 0.0)
                    po = po if prim_dir == "maximize" else -po
                    return po - overfit_penalty * means.get("overfit", 0.0)
                obj_values = [means.get(o["metric"], 0.0) for o in objectives]
                return obj_values if is_multi else obj_values[0]

            study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

            # Mark Pareto-optimal (or single best) trials.
            if is_multi:
                pareto_numbers = {t.number for t in study.best_trials}
            else:
                pareto_numbers = {study.best_trial.number} if study.best_trial else set()
            if pareto_numbers:
                rows = db.query(db_models.HpSearchTrial).filter_by(study_id=study_id).all()
                for r in rows:
                    if r.trial_idx in pareto_numbers:
                        m = dict(r.metrics or {})
                        m["is_pareto"] = True
                        r.metrics = m
                db.commit()

            best_summary: dict = {}
            try:
                if use_penalty and study.best_trial:
                    # study.best_value is the penalized score; report the winner's
                    # actual accuracy so the "best" column stays an accuracy.
                    bt = (
                        db.query(db_models.HpSearchTrial)
                          .filter_by(study_id=study_id, trial_idx=study.best_trial.number)
                          .one_or_none()
                    )
                    best_summary = {
                        "best_value": (bt.metrics or {}).get("mean_accuracy") if bt else None,
                        "best_params": study.best_params,
                    }
                elif not is_multi:
                    best_summary = {"best_value": study.best_value, "best_params": study.best_params}
            except Exception:
                pass

            study_row.status = "completed"
            study_row.finished_at = datetime.now(UTC)
            study_row.params = {
                **(study_row.params or {}),
                "objectives": objectives,
                "overfit_penalty": overfit_penalty,
                **best_summary,
            }
            db.commit()

            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": f"done · {n_trials} trials · realworld held-out ≥ {REALWORLD_CUTOFF_DT.date()}",
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
