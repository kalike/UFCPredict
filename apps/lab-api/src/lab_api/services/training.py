"""Training service — real LGBM/XGB/LR worker.

Single-tenant: only one job at a time. Other model_shorts (RF, SVM, MLP,
Deep, RNet, etc.) return status='not_implemented' so the UI can show "this
model can't be trained yet in lab" without crashing.
"""

import logging
import threading
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import joblib

from ufc_core.config import MODELS_DIR, TEST_CUTOFF_DT
from ufc_core.db.engine import SessionLocal
from ufc_core.db import models as db_models
from ufc_core.models.registry import ModelRegistry


logger = logging.getLogger("lab-api.training")

# Supported model_shorts in F2 maduro. Extend this set as more families are
# wired.  Each entry maps to the python import path for documentation purposes.
SUPPORTED: dict[str, str] = {
    # Boosters
    "LGBM":  "lightgbm.LGBMClassifier",
    "LG52":  "lightgbm.LGBMClassifier",
    "XGB":   "xgboost.XGBClassifier",
    "XG52":  "xgboost.XGBClassifier",
    "CB":    "catboost.CatBoostClassifier",
    "CB52":  "catboost.CatBoostClassifier",
    # Linear
    "LR":    "sklearn.linear_model.LogisticRegression",
    "LR52":  "sklearn.linear_model.LogisticRegression",
    # Trees
    "RF35":  "sklearn.ensemble.RandomForestClassifier",
    "RFda":  "sklearn.ensemble.RandomForestClassifier",
    "RF52":  "sklearn.ensemble.RandomForestClassifier",
    # Neural nets (sklearn)
    "MLP":   "sklearn.neural_network.MLPClassifier",
    "MLP2":  "sklearn.neural_network.MLPClassifier",
    "ML52":  "sklearn.neural_network.MLPClassifier",
    # SVM family
    "SVMb":  "sklearn.svm.SVC",
    "SVMg":  "sklearn.svm.SVC (GridSearchCV)",
    "SVMr":  "sklearn.svm.SVC (RobustScaler)",
}


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


def _build_classifier(family_key: str, feature_set: str = ""):
    """Return an unfitted classifier (or sklearn Pipeline) for the given family.

    MLP variants are wrapped in a Pipeline with StandardScaler so the network
    sees normalised inputs (parity with the legacy backend behaviour).
    """
    if family_key in ("LGBM", "LG52"):
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=400, learning_rate=0.05, num_leaves=31,
            min_child_samples=20, n_jobs=-1, verbose=-1,
        )
    if family_key in ("XGB", "XG52"):
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=400, learning_rate=0.05, max_depth=6,
            n_jobs=-1, eval_metric="logloss", verbosity=0,
        )
    if family_key in ("CB", "CB52"):
        from catboost import CatBoostClassifier
        return CatBoostClassifier(
            iterations=400, depth=6, learning_rate=0.05,
            verbose=False, allow_writing_files=False,
        )
    if family_key in ("LR", "LR52"):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        # Impute NaNs first; then scale; ElasticNet via saga.
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("lr", LogisticRegression(
                C=1.0, penalty="elasticnet", l1_ratio=0.5,
                solver="saga", max_iter=4000, n_jobs=-1,
            )),
        ])
    if family_key in ("RF35", "RFda", "RF52"):
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=400, max_depth=None, min_samples_split=5,
            min_samples_leaf=2, n_jobs=-1, random_state=42,
        )
    if family_key in ("MLP", "MLP2", "ML52"):
        from sklearn.impute import SimpleImputer
        from sklearn.neural_network import MLPClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        hidden_layer_sizes = (
            (64,) if family_key in ("MLP2", "ML52") else (128, 64)
        )
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("mlp", MLPClassifier(
                hidden_layer_sizes=hidden_layer_sizes,
                activation="relu", solver="adam",
                alpha=1e-4, learning_rate_init=1e-3,
                max_iter=300, early_stopping=True,
                validation_fraction=0.1, n_iter_no_change=20,
                random_state=42,
            )),
        ])
    if family_key in ("SVMb", "SVMg", "SVMr"):
        from sklearn.impute import SimpleImputer
        from sklearn.svm import SVC
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler, RobustScaler

        scaler = RobustScaler() if family_key == "SVMr" else StandardScaler()

        if family_key == "SVMg":
            from sklearn.model_selection import GridSearchCV
            base_svc = SVC(kernel="rbf", probability=True, random_state=42)
            # Small grid; n_jobs=1 because GridSearchCV+SVC parallelism is tricky.
            grid = GridSearchCV(
                base_svc,
                param_grid={"C": [0.5, 1.0, 4.0], "gamma": ["scale", 0.05]},
                cv=3, n_jobs=1, scoring="accuracy",
            )
            return Pipeline([
                ("imp", SimpleImputer(strategy="median")),
                ("scale", scaler),
                ("svm", grid),
            ])
        return Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("scale", scaler),
            ("svm", SVC(
                C=1.0, kernel="rbf", gamma="scale",
                probability=True, random_state=42,
            )),
        ])
    raise ValueError(f"No builder for family_key={family_key}")


def _build_dataset_simple(ds, since_year: int):
    """Build training DataFrame from DataStoreDB using compute_features_for_fights.

    Returns (df, feat_cols) where df has 'result', 'event_date', and all
    numeric feature columns.  feat_cols is a sorted list of those features.
    """
    import pandas as pd
    from ufc_core.features.engine import compute_features_for_fights
    from ufc_core.trainer.core import recalculate_elo

    # Compute temporally-correct ELO pre-fight ratings
    elo_ratings, elo_pre_fight = recalculate_elo(
        data_store=ds, base_elo=1500.0, save_to_disk=True,
    )

    # Collect unique fights from fighters_raw
    seen: set = set()
    fights: list[dict] = []
    for ftr in ds.fighters_raw:
        fname = ftr["name"]
        for fight in ftr.get("fights", []):
            opponent = fight.get("opponent", "")
            event = fight.get("event", "")
            result_raw = fight.get("result", "")
            if not opponent or not event:
                continue
            ev_date = ds.event_dates.get(event)
            if ev_date is None or ev_date.year < since_year:
                continue
            if result_raw not in ("win", "loss"):
                continue
            key = (*sorted([fname, opponent]), event)
            if key in seen:
                continue
            seen.add(key)
            # Canonicalise: fighter_1 = winner, fighter_2 = loser
            if result_raw == "win":
                fights.append({
                    "fighter_1": fname,
                    "fighter_2": opponent,
                    "event": event,
                    "result": 1,
                })
            else:
                fights.append({
                    "fighter_1": opponent,
                    "fighter_2": fname,
                    "event": event,
                    "result": 0,
                })

    if not fights:
        raise ValueError("No fights available to build dataset")

    df = compute_features_for_fights(
        fights=fights,
        fighter_histories=ds.fighter_histories,
        fighter_lookup=ds.fighter_lookup,
        event_dates=ds.event_dates,
        elo_ratings=elo_ratings,
        elo_pre_fight=elo_pre_fight,
        base_elo=1500.0,
    )

    # compute_features_for_fights returns a plain DataFrame (no second value)
    if isinstance(df, tuple):
        df = df[0]

    # Attach event_date from ds.event_dates if not already present
    if "event_date" not in df.columns:
        if "event" in df.columns:
            df["event_date"] = df["event"].map(ds.event_dates)

    # Attach result column from the fights list we built
    if "result" not in df.columns:
        result_map: dict[tuple, int] = {}
        for f in fights:
            result_map[(f["fighter_1"], f["fighter_2"], f["event"])] = f["result"]
        df["result"] = df.apply(
            lambda row: result_map.get(
                (row.get("fighter_1", ""), row.get("fighter_2", ""), row.get("event", ""))
            ),
            axis=1,
        )

    # Filter rows with valid event_date and result
    if "event_date" in df.columns:
        df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
        df = df[df["event_date"].notna()].copy()

    df = df[df["result"].notna()].copy()
    df["result"] = df["result"].astype(int)

    # Identify feature columns: numeric only, exclude metadata
    META = {"result", "event_date", "fighter_1", "fighter_2", "event",
            "f1_name", "f2_name"}
    feat_cols = sorted([
        c for c in df.columns
        if c not in META and pd.api.types.is_numeric_dtype(df[c])
    ])
    return df, feat_cols


def start_training(req: dict) -> dict:
    """Launch a training job in a background thread.

    Returns immediately with started=True and the training_session_id.
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

    ts_id_holder: list[int | None] = [None]

    def _job():
        model_short = req.get("model_short", "")
        feature_set = req.get("feature_set", "v7")
        dataset_key = req.get("dataset", "since2010")
        since_year = {"since2010": 2010, "since2015": 2015, "since2020": 2020}.get(
            dataset_key, 2010
        )

        db = SessionLocal()
        ts = db_models.TrainingSession(model_id=None, request=req, status="running")
        db.add(ts)
        db.commit()
        ts_id_holder[0] = ts.id

        try:
            # --- Guard: unsupported model_short ---
            if model_short not in SUPPORTED:
                error_msg = (
                    f"Model '{model_short}' has no lab trainer yet "
                    f"(supported: {sorted(SUPPORTED)})"
                )
                with _lock:
                    _state["step"] = f"not_implemented for {model_short}"
                ts.status = "not_implemented"
                ts.error_msg = error_msg
                ts.finished_at = datetime.now(UTC)
                db.commit()
                with _lock:
                    _state.update({
                        "is_running": False,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": "not_implemented",
                        "error": error_msg,
                    })
                return

            # --- Step 1: Load data ---
            with _lock:
                _state["step"] = "loading data"
            from ufc_core.data_loader import DataStoreDB
            ds = DataStoreDB()
            ds.load()

            # --- Step 2: Build dataset (includes ELO recalculation internally) ---
            with _lock:
                _state["step"] = "building dataset"
            df, feat_cols = _build_dataset_simple(ds, since_year)

            if len(df) < 100:
                raise ValueError(f"Dataset too small: {len(df)} rows")

            # --- Step 3: Train/test split ---
            cutoff = TEST_CUTOFF_DT  # naive datetime from config
            with _lock:
                _state["step"] = f"splitting train/test (cutoff {cutoff.date()})"

            # Ensure event_date is naive for comparison
            event_dates = df["event_date"]
            if hasattr(event_dates.dtype, "tz") and event_dates.dt.tz is not None:
                event_dates = event_dates.dt.tz_localize(None)

            train_mask = event_dates < cutoff
            test_mask = event_dates >= cutoff
            train_df = df[train_mask]
            test_df = df[test_mask]

            if len(train_df) < 50 or len(test_df) < 10:
                raise ValueError(
                    f"Split too small: train={len(train_df)}, test={len(test_df)}"
                )

            X_train = train_df[feat_cols].values
            y_train = train_df["result"].values
            X_test = test_df[feat_cols].values
            y_test = test_df["result"].values

            # --- Step 4: Train ---
            with _lock:
                _state["step"] = f"training {model_short} ({SUPPORTED[model_short]})"
            clf = _build_classifier(model_short, feature_set)
            clf.fit(X_train, y_train)

            # --- Step 5: Evaluate ---
            with _lock:
                _state["step"] = "evaluating"
            from sklearn.metrics import accuracy_score, log_loss
            preds = clf.predict(X_test)
            try:
                probs = clf.predict_proba(X_test)[:, 1]
            except Exception:
                probs = preds.astype(float)
            metrics = {
                "accuracy": float(accuracy_score(y_test, preds)),
                "log_loss": float(log_loss(y_test, probs)),
                "n_train": int(len(train_df)),
                "n_test": int(len(test_df)),
                "n_features": int(len(feat_cols)),
            }
            logger.info(
                "Training %s — acc=%.4f  log_loss=%.4f  n_train=%d  n_test=%d",
                model_short, metrics["accuracy"], metrics["log_loss"],
                metrics["n_train"], metrics["n_test"],
            )

            # --- Step 6: Determine version index ---
            m = db.query(db_models.Model).filter_by(short=model_short).one()
            max_v = (
                db.query(db_models.ModelVersion.version_idx)
                  .filter_by(model_id=m.id)
                  .order_by(db_models.ModelVersion.version_idx.desc())
                  .first()
            )
            next_idx = (max_v[0] + 1) if max_v else 1

            # --- Step 7: Persist artifact ---
            lab_models_dir = Path(MODELS_DIR) / "lab"
            lab_models_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = lab_models_dir / f"{model_short}_v{next_idx}.joblib"

            with _lock:
                _state["step"] = f"persisting artifact {artifact_path.name}"
            joblib.dump(
                {
                    "clf": clf,
                    "feat_cols": feat_cols,
                    "feature_set": feature_set,
                    "model_short": model_short,
                },
                artifact_path,
            )

            # --- Step 8: Register version ---
            with _lock:
                _state["step"] = "registering version"
            reg = ModelRegistry(db)
            v_idx = reg.register_version(
                short=model_short,
                feature_set=feature_set,
                hp_json={"dataset": dataset_key, "feat_count": len(feat_cols)},
                metrics_json=metrics,
                artifact_uri=f"file://{artifact_path}",
                note="Trained by lab-api training service",
            )

            # --- Step 9: Update training session ---
            v = (
                db.query(db_models.ModelVersion)
                  .filter_by(model_id=m.id, version_idx=v_idx)
                  .one()
            )
            ts.status = "completed"
            ts.model_id = m.id
            ts.result_version_id = v.id
            ts.finished_at = datetime.now(UTC)
            db.commit()

            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": f"done: acc={metrics['accuracy']:.4f}",
                    "result_version_id": v.id,
                })

        except Exception as e:
            logger.exception("training job failed")
            ts.status = "failed"
            ts.error_msg = repr(e)
            ts.finished_at = datetime.now(UTC)
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

    t = threading.Thread(target=_job, daemon=True)
    t.start()
    # Brief wait so ts_id gets committed before we return it to the caller
    t.join(timeout=0.5)

    with _lock:
        return {"started": True, "training_session_id": ts_id_holder[0]}
