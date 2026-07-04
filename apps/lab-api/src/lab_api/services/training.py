"""Training service — real worker for the lab's canonical model catalog.

Single-tenant: only one job at a time. The lab trains exactly four model
families (XGB, RF, CB, Deep). Any other model_short returns
status='not_implemented' so the UI can show "this model can't be trained in
lab" without crashing.
"""

import logging
import threading
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import joblib

from ufc_core.config import MODELS_DIR, TEST_CUTOFF_DT, REALWORLD_CUTOFF_DT
from ufc_core.db.engine import SessionLocal
from ufc_core.db import models as db_models
from ufc_core.features.engine import compute_fight_features
from ufc_core.models.registry import ModelRegistry
from ufc_core.tapology.picks_repo import (
    load_db_picks_lookup, orient_picks_for_fight,
)
from ufc_core.trainer.value_metrics import json_sanitize


logger = logging.getLogger("lab-api.training")

# Canonical trainable models in the lab. Single source of truth for both the
# worker (which builds the classifier) and the /api/models/trainable endpoint
# (which feeds the UI dropdown). Each entry carries the metadata needed to
# auto-register the Model row on first train.
TRAINABLE: dict[str, dict[str, str]] = {
    "XGB":  {"label": "XGBoost",       "family": "xgboost",  "default_feat_type": "52f", "impl": "xgboost.XGBClassifier"},
    "RF":   {"label": "Random Forest", "family": "sklearn",  "default_feat_type": "52f", "impl": "sklearn.ensemble.RandomForestClassifier"},
    "CB":   {"label": "CatBoost",      "family": "catboost", "default_feat_type": "52f", "impl": "catboost.CatBoostClassifier"},
    "Deep": {"label": "Deep MLP",      "family": "pytorch",  "default_feat_type": "52f", "impl": "ufc_core.models.pytorch_arch.DeepMLP"},
}

# Backwards-compatible alias: short -> import path (used in status messages).
SUPPORTED: dict[str, str] = {k: v["impl"] for k, v in TRAINABLE.items()}


_lock = threading.Lock()
_state: dict[str, Any] = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "model_short": None,      # model of the job currently running
    "step": None,
    "pct": 0.0,               # progress of the current job (0-100)
    "job_index": 0,           # 0-based index of the current job in the batch
    "n_jobs": 0,
    "job_label": None,
    "result_version_id": None,  # db id of the last registered version (compat)
    "logs": [],               # rolling tail of human-readable log lines
    "results": [],            # accumulated per-job results
    "error": None,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def _log(msg: str) -> None:
    line = f"{datetime.now(UTC).strftime('%H:%M:%S')}  {msg}"
    with _lock:
        _state["logs"] = (_state["logs"] + [line])[-200:]
    logger.info(msg)


_SINCE_YEAR = {"since2010": 2010, "since2015": 2015, "since2020": 2020}


def _since_year(dataset_key: str) -> int:
    return _SINCE_YEAR.get(dataset_key, 2010)


def _job_label(job: dict) -> str:
    parts = [job.get("model_short", "?"), job.get("dataset", "since2010")]
    mf = job.get("min_fights")
    if mf:
        parts.append(f"mf={mf}")
    ft = job.get("feat_type", "auto")
    if ft and ft != "auto":
        parts.append(str(ft))
    aug = job.get("augment")
    parts.append("aug" if aug is True else ("no-aug" if aug is False else "aug:auto"))
    fs = job.get("feature_set")
    if fs:
        parts.append(str(fs))
    return " | ".join(str(p) for p in parts)


def _build_classifier(family_key: str, feature_set: str = "", params: dict | None = None):
    """Return an unfitted classifier for one of the four canonical families.

    `params` (e.g. an adopted HP-search trial) overrides the family defaults.
    """
    hp = dict(params or {})
    if family_key == "XGB":
        from xgboost import XGBClassifier
        defaults = dict(n_estimators=400, learning_rate=0.05, max_depth=6)
        return XGBClassifier(
            **{**defaults, **hp},
            n_jobs=-1, eval_metric="logloss", verbosity=0,
        )
    if family_key == "RF":
        from sklearn.ensemble import RandomForestClassifier
        defaults = dict(n_estimators=400, max_depth=None, min_samples_split=5,
                        min_samples_leaf=2)
        return RandomForestClassifier(
            **{**defaults, **hp}, n_jobs=-1, random_state=42,
        )
    if family_key == "CB":
        from catboost import CatBoostClassifier
        merged = {**dict(iterations=400, depth=6, learning_rate=0.05), **hp}
        # Match the legacy backend: don't force a bootstrap_type — CatBoost defaults to
        # MVS, which honours subsample and tolerates bagging_temperature.
        return CatBoostClassifier(
            **merged, verbose=False, allow_writing_files=False, random_seed=42,
        )
    if family_key == "Deep":
        from lab_api.services.torch_wrap import make_deep_mlp
        kw: dict = dict(epochs=40, batch_size=64, lr=1e-3)
        if "hidden_dims" in hp:
            hd = hp["hidden_dims"]
            kw["hidden_dims"] = (
                tuple(int(x) for x in hd.split(",")) if isinstance(hd, str) else tuple(hd)
            )
        for k in ("epochs", "batch_size", "lr", "weight_decay", "dropout", "patience"):
            if k in hp:
                kw[k] = hp[k]
        return make_deep_mlp(**kw)
    raise ValueError(f"No builder for family_key={family_key}")


VALID_FEATURE_SETS = ("legacy", "v2", "v3", "v4", "v5", "v6", "v7")


def _select_feat_cols(df, feat_type: str, feature_set: str) -> list[str]:
    """Select feature columns for the requested feature set / feat type.

    Delegates to ufc_core's _get_feature_cols — the single source of truth
    for feature-set definitions (legacy/v2..v7, 52f vs delta) — so the lab
    trains on exactly the same column subsets as the main backend.
    """
    from ufc_core.trainer.core import _get_feature_cols

    # The UI field is free text; an unknown set would silently skip every
    # filter branch and train on the unfiltered superset.
    if feature_set not in VALID_FEATURE_SETS:
        raise ValueError(
            f"Unknown feature_set {feature_set!r} "
            f"(valid: {', '.join(VALID_FEATURE_SETS)})"
        )

    cols = _get_feature_cols(df, feat_type=feat_type, feature_set=feature_set)
    if not cols:
        raise ValueError(
            f"No feature columns selected "
            f"(feature_set={feature_set!r}, feat_type={feat_type!r})"
        )
    return cols


def _resolve_feat_type(job: dict, model_short: str) -> str:
    """Resolve feat_type='auto' to the model's default (52f for all four)."""
    feat_type = job.get("feat_type") or "auto"
    if feat_type == "auto":
        feat_type = TRAINABLE.get(model_short, {}).get("default_feat_type", "52f")
    return feat_type


def _build_dataset_simple(ds, since_year: int):
    """Build training DataFrame from DataStoreDB using compute_features_for_fights.

    Returns (df, feat_cols) where df has 'result', 'event_date', and all
    numeric feature columns.  feat_cols is the full numeric superset — each
    job narrows it per feature_set/feat_type via _select_feat_cols.
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


def _feature_importance(clf, feat_cols: list[str], top: int = 15) -> list[dict]:
    """Top-N feature importances when the estimator exposes them (XGB/RF/CB).

    Deep (PyTorch) has no native importances → returns an empty list.
    """
    imp = getattr(clf, "feature_importances_", None)
    if imp is None:
        return []
    pairs = sorted(
        zip(feat_cols, (float(x) for x in imp)), key=lambda p: p[1], reverse=True
    )[:top]
    return [{"feature": f, "importance": v} for f, v in pairs]


def _eval_metrics(model, X_test, y_test, X_train, y_train) -> dict:
    """Held-out metrics matching the legacy backend's eval step.

    confusion_matrix is stored as sklearn's order with labels=[1, 0] so the
    positive class (fighter_1 wins, label 1) comes first:
        [[TP, FN],
         [FP, TN]]   (rows = real F1/F2, cols = pred F1/F2)
    """
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, log_loss, confusion_matrix,
    )
    y_pred = model.predict(X_test)
    try:
        proba = model.predict_proba(X_test)[:, 1]
    except Exception:
        proba = y_pred.astype(float)
    try:
        auc = float(roc_auc_score(y_test, proba))
    except ValueError:
        auc = None
    try:
        ll = float(log_loss(y_test, proba, labels=[0, 1]))
    except Exception:
        ll = None
    acc = float(accuracy_score(y_test, y_pred))
    train_acc = float(accuracy_score(y_train, model.predict(X_train)))
    cm = confusion_matrix(y_test, y_pred, labels=[1, 0]).tolist()
    return {
        "accuracy": round(acc, 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "auc": round(auc, 4) if auc is not None else None,
        "log_loss": round(ll, 4) if ll is not None else None,
        "train_accuracy": round(train_acc, 4),
        "overfit_gap": round(train_acc - acc, 4),
        "confusion_matrix": cm,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
    }


def _load_realworld_odds() -> dict:
    """Lookup {(event_name, frozenset({f1_name, f2_name})): {name: odds_american}}
    for RealWorld fights that have both odds.

    Source: the lab `fight` table (backfilled from Tapology). Uses its own short
    read-only session so callers don't need to thread a db handle through
    _build_realworld_df. Mirrors the Tapology-picks key shape used in
    _build_realworld_df.
    """
    from sqlalchemy.orm import aliased
    from ufc_core.db.engine import session_scope
    from ufc_core.db import models as m
    from ufc_core.config import REALWORLD_CUTOFF_DT

    lookup: dict = {}
    with session_scope() as db:
        F1 = aliased(m.Fighter)
        F2 = aliased(m.Fighter)
        rows = (
            db.query(
                m.Event.name, F1.name, F2.name,
                m.Fight.odds_f1_american, m.Fight.odds_f2_american,
            )
            .join(m.Event, m.Event.id == m.Fight.event_id)
            .join(F1, F1.id == m.Fight.fighter_1_id)
            .join(F2, F2.id == m.Fight.fighter_2_id)
            .filter(m.Event.date >= REALWORLD_CUTOFF_DT)
            .filter(m.Fight.odds_f1_american.isnot(None))
            .filter(m.Fight.odds_f2_american.isnot(None))
            .all()
        )
        for ev, n1, n2, o1, o2 in rows:
            lookup[(ev, frozenset({n1, n2}))] = {n1: int(o1), n2: int(o2)}
    return lookup


def _build_realworld_df(ds, elo_ratings, elo_pre_fight, base_elo: float = 1500.0,
                        odds_lookup: dict | None = None):
    """Build the held-out realworld DataFrame exactly like the legacy backend.

    Fights with event_date >= REALWORLD_CUTOFF_DT and a known result, with a
    deterministic 50/50 positional swap (seed 42), PIT-correct features
    (before_event_date = event date), and rw_label / rw_real_winner targets.

    When ``odds_lookup`` is provided, each row also carries
    ``odds_f1_american`` / ``odds_f2_american`` assigned BY FIGHTER (orientation
    is randomized, so odds follow the name, not the column position).
    """
    import numpy as np
    import pandas as pd

    rng = np.random.RandomState(42)
    seen: set = set()
    rows: list[dict] = []
    # Load Tapology picks once (DB-only; empty dict in file mode). Critical for
    # feature_set='v7': without this every held-out fight gets neutral tap_*
    # imputation while training rows have the real values, so the model's
    # strongest signal is dead at eval time and realworld_accuracy collapses.
    tapology_picks_by_key = load_db_picks_lookup()
    for ftr in ds.fighters_raw:
        fname = ftr["name"]
        for fight in ftr.get("fights", []):
            opp = fight.get("opponent", "")
            ev = fight.get("event", "")
            res = fight.get("result", "")
            if not opp or not ev or res not in ("win", "loss"):
                continue
            ev_date = ds.event_dates.get(ev)
            if ev_date is None or ev_date < REALWORLD_CUTOFF_DT:
                continue
            key = (*sorted([fname, opp]), ev)
            if key in seen:
                continue
            seen.add(key)
            winner, loser = (fname, opp) if res == "win" else (opp, fname)
            if rng.random() < 0.5:
                f1, f2, label = winner, loser, 1.0
            else:
                f1, f2, label = loser, winner, 0.0
            picks_entry = tapology_picks_by_key.get((ev, frozenset({f1, f2})))
            picks = orient_picks_for_fight(picks_entry, f1) if picks_entry else None
            row = compute_fight_features(
                f1_name=f1, f2_name=f2,
                fighter_histories=ds.fighter_histories,
                fighter_lookup=ds.fighter_lookup,
                event_dates=ds.event_dates,
                event=ev,
                elo_pre_fight=elo_pre_fight, elo_ratings=elo_ratings, base_elo=base_elo,
                before_event_date=ev_date, event_date=ev_date,  # PIT
                tapology_picks=picks,
            )
            if row is None:
                continue
            row["fighter_1"], row["fighter_2"], row["event"] = f1, f2, ev
            row["rw_label"] = label
            row["rw_real_winner"] = winner
            row["event_date"] = ev_date
            if odds_lookup is not None:
                od = odds_lookup.get((ev, frozenset({f1, f2})))
                row["odds_f1_american"] = od.get(f1) if od else None
                row["odds_f2_american"] = od.get(f2) if od else None
            rows.append(row)
    return pd.DataFrame(rows)


def _train_one_job(db, ts, job: dict, df, realworld_df) -> dict:
    """Replicate the legacy backend's train_single_model flow with ufc_core helpers:
    3-way temporal split, shared preprocess (augment→features→impute→transform),
    held-out eval, production retrain on all pre-realworld data, and realworld
    TTA evaluation. Persists + registers the production model in the lab DB.

    `df` is produced by ufc_core._build_dataset (already PIT-aware, min_fights
    filtered, and realworld-excluded).
    """
    import numpy as np
    from ufc_core.trainer.core import _augment_35f, _preprocess_split, evaluate_realworld
    from ufc_core.imputer import FeatureImputer

    model_short = job.get("model_short", "")
    feature_set = job.get("feature_set", "v7")
    dataset_key = job.get("dataset", "since2010")
    min_fights = int(job.get("min_fights") or 0)
    do_augment = job.get("augment") is True
    hp_params = job.get("hp_params") or None  # adopted HP-search trial params
    label = _job_label(job)
    if model_short not in SUPPORTED:
        raise ValueError(
            f"Model '{model_short}' is not trainable (supported: {sorted(SUPPORTED)})"
        )
    feat_type = _resolve_feat_type(job, model_short)

    # --- 3-way split (df already excludes realworld >= REALWORLD_CUTOFF_DT) ---
    _set(step="splitting train / test-val", pct=15.0)
    train_df = df[df["event_date"] < TEST_CUTOFF_DT].copy()
    test_df = df[df["event_date"] >= TEST_CUTOFF_DT].copy()
    if len(train_df) < 50 or len(test_df) < 10:
        raise ValueError(f"Split too small: train={len(train_df)}, test={len(test_df)}")

    # --- Shared preprocess: augment(train) → features → impute → transform ---
    _set(step=f"preprocess ({feature_set}/{feat_type})", pct=30.0)
    pp = _preprocess_split(
        train_df, test_df, feat_type=feat_type, feature_set=feature_set,
        do_augment=do_augment, scaler_type=None,
    )
    feat_cols = pp.feat_cols
    _log(f"{feature_set}/{feat_type}: {len(feat_cols)} cols | "
         f"train={len(pp.y_train)} test-val={len(pp.y_test)} | "
         f"aug={'on' if do_augment else 'off'}")

    # --- Held-out eval model (train only) ---
    _set(step=f"training {model_short} (holdout)", pct=45.0)
    eval_model = _build_classifier(model_short, feature_set, params=hp_params)
    eval_model.fit(pp.X_train, pp.y_train)
    _set(step="evaluating (test-val)", pct=65.0)
    metrics = _eval_metrics(eval_model, pp.X_test, pp.y_test, pp.X_train, pp.y_train)

    # --- Production retrain on ALL pre-realworld data (train + test-val) ---
    _set(step="production retrain (full)", pct=78.0)
    full_df = df.copy()
    if do_augment:
        full_df = _augment_35f(full_df)
    for c in feat_cols:
        if c not in full_df.columns:
            full_df[c] = 0
    imputer_prod = FeatureImputer().fit(full_df, feat_cols)
    full_imp = pp.transformer.transform_df(imputer_prod.transform(full_df))
    X_full = full_imp[feat_cols].values.astype(np.float32)
    y_full = full_df["result"].values.astype(np.float32)
    prod_model = _build_classifier(model_short, feature_set, params=hp_params)
    prod_model.fit(X_full, y_full)
    fi = _feature_importance(prod_model, feat_cols)
    metrics["n_production"] = int(len(df))
    metrics["n_features"] = int(len(feat_cols))
    # Persist the rich pieces the model-detail screen needs (parity with the
    # legacy backend): top feature importances + the realworld per-event breakdown.
    metrics["feature_importance"] = fi

    # --- Realworld eval (held-out >= REALWORLD_CUTOFF, TTA) ---
    _set(step="realworld eval", pct=88.0)
    rw = {"realworld_accuracy": None, "realworld_correct": 0,
          "realworld_total": 0, "realworld_events": []}
    if realworld_df is not None and len(realworld_df) > 0:
        rw = evaluate_realworld(
            prod_model, None, imputer_prod, feat_cols, realworld_df,
            is_pytorch=False, min_fights=min_fights,
        )
        _log(f"Realworld: {rw['realworld_correct']}/{rw['realworld_total']} "
             f"acc={rw['realworld_accuracy']}")
    metrics.update({k: rw[k] for k in
                    ("realworld_accuracy", "realworld_correct", "realworld_total")})
    metrics["realworld_events"] = rw.get("realworld_events", [])

    # --- Auto-register Model row (idempotent) ---
    m = db.query(db_models.Model).filter_by(short=model_short).one_or_none()
    if m is None:
        meta = TRAINABLE[model_short]
        m = db_models.Model(
            short=model_short, family=meta["family"],
            default_feat_type=meta["default_feat_type"], description=meta["label"],
        )
        db.add(m)
        db.commit()
    max_v = (
        db.query(db_models.ModelVersion.version_idx)
          .filter_by(model_id=m.id)
          .order_by(db_models.ModelVersion.version_idx.desc())
          .first()
    )
    next_idx = (max_v[0] + 1) if max_v else 1

    # --- Persist artifact (model + preprocessing for inference parity) ---
    _set(step="persisting artifact", pct=95.0)
    lab_models_dir = Path(MODELS_DIR) / "lab"
    lab_models_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = lab_models_dir / f"{model_short}_v{next_idx}.joblib"
    joblib.dump(
        {"clf": prod_model, "feat_cols": feat_cols, "feature_set": feature_set,
         "feat_type": feat_type, "model_short": model_short,
         "imputer": imputer_prod, "transformer": pp.transformer, "scaler": None},
        artifact_path,
    )

    # --- Register version ---
    reg = ModelRegistry(db)
    origin = job.get("origin") or "retrain"
    v_idx = reg.register_version(
        short=model_short, feature_set=feature_set,
        hp_json={"dataset": dataset_key, "feat_count": len(feat_cols),
                 "min_fights": min_fights, "augment": do_augment,
                 "feat_type": feat_type, "use_pit": bool(job.get("use_pit")),
                 "origin": origin,
                 # delta_win_streak uses the odd clip_sym_6 override for 35f.
                 "delta_overrides": (feat_type == "35f"),
                 **({"hp_params": hp_params} if hp_params else {})},
        # JSONB rejects NaN/Inf — strip any (e.g. from value-vs-market metrics
        # on fights without odds) before persisting.
        metrics_json=json_sanitize(metrics), artifact_uri=f"file://{artifact_path}",
        note=f"Trained by lab-api ({origin}): {label}",
    )
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

    _set(step=f"done: acc={metrics['accuracy']:.4f} rw={rw['realworld_accuracy']}",
         pct=100.0, result_version_id=v.id)
    return {
        "model_short": model_short, "job_label": label, "dataset": dataset_key,
        "accuracy": metrics["accuracy"], "log_loss": metrics.get("log_loss"),
        "auc": metrics.get("auc"), "overfit_gap": metrics.get("overfit_gap"),
        "n_train": int(len(pp.y_train)), "n_test": int(len(pp.y_test)),
        "n_features": int(len(feat_cols)),
        "realworld_accuracy": rw["realworld_accuracy"],
        "realworld_correct": rw["realworld_correct"],
        "realworld_total": rw["realworld_total"],
        "realworld_events": rw["realworld_events"],
        "feature_importance": fi,
        "version_idx": v_idx, "version_id": v.id, "error": None,
    }


def _run_batch(jobs: list[dict]) -> None:
    from ufc_core.data_loader import DataStoreDB
    from ufc_core.trainer.core import _build_dataset, recalculate_elo

    n = len(jobs)
    _set(step="starting", pct=0.0)
    _log(f"Batch de {n} job(s) iniciado")
    db = SessionLocal()
    ds = None  # lazy-loaded on the first trainable job
    elo_ratings = elo_pre_fight = realworld_df = None
    try:
        # Cache datasets by (since_year, use_pit, min_fights) — _build_dataset
        # applies min_fights and PIT, so each combination is a distinct frame.
        dataset_cache: dict[tuple, object] = {}
        results: list[dict] = []
        for i, job in enumerate(jobs):
            model_short = job.get("model_short", "")
            label = _job_label(job)
            _set(model_short=model_short, job_index=i, n_jobs=n,
                 job_label=label, step="starting", pct=0.0, error=None)
            _log(f"[{i + 1}/{n}] {label}")

            ts = db_models.TrainingSession(model_id=None, request=job, status="running")
            db.add(ts)
            db.commit()

            try:
                # Validate before touching data so unsupported models fail fast
                # (avoids loading the whole DataStore for a no-op job, which
                # would keep is_running=True and starve queued requests).
                if model_short not in SUPPORTED:
                    raise ValueError(
                        f"Model '{model_short}' is not trainable "
                        f"(supported: {sorted(SUPPORTED)})"
                    )
                if ds is None:
                    _set(step="loading data", pct=2.0)
                    _log("Cargando datos…")
                    ds = DataStoreDB()
                    ds.load()
                    # Naive event dates so cutoff comparisons never mix tz-aware
                    # and tz-naive datetimes.
                    for k, val in list(ds.event_dates.items()):
                        if getattr(val, "tzinfo", None) is not None:
                            ds.event_dates[k] = val.replace(tzinfo=None)
                    _set(step="recalculating ELO", pct=4.0)
                    _log("Recalculando ELO (pre-fight)…")
                    elo_ratings, elo_pre_fight = recalculate_elo(
                        data_store=ds, base_elo=1500.0, save_to_disk=True,
                    )
                    _set(step="building realworld set", pct=6.0)
                    _log("Construyendo conjunto realworld…")
                    realworld_df = _build_realworld_df(
                        ds, elo_ratings, elo_pre_fight, 1500.0,
                        odds_lookup=_load_realworld_odds(),
                    )
                    _log(f"Realworld: {len(realworld_df)} peleas "
                         f"(>= {REALWORLD_CUTOFF_DT.date()})")

                since_year = _since_year(job.get("dataset", "since2010"))
                use_pit = bool(job.get("use_pit"))
                mf = int(job.get("min_fights") or 0)
                key = (since_year, use_pit, mf)
                if key not in dataset_cache:
                    _set(step="building dataset (PIT)" if use_pit else "building dataset",
                         pct=8.0)
                    _log(f"Construyendo dataset since={since_year} "
                         f"pit={use_pit} min_fights={mf}…")
                    dataset_cache[key] = _build_dataset(
                        ds, elo_ratings, 1500.0, since_year, None,
                        elo_pre_fight, mf, use_pit,
                    )
                df = dataset_cache[key]
                if len(df) < 100:
                    raise ValueError(f"Dataset too small: {len(df)} rows")

                result = _train_one_job(db, ts, job, df, realworld_df)
                results.append(result)
                _set(results=list(results))
                _log(f"[{i + 1}/{n}] ✓ {model_short} acc={result['accuracy']:.4f} "
                     f"rw={result['realworld_accuracy']} (v{result['version_idx']})")
            except Exception as e:
                logger.exception("training job failed")
                ts.status = "failed"
                ts.error_msg = repr(e)
                ts.finished_at = datetime.now(UTC)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                results.append({
                    "model_short": model_short, "job_label": label,
                    "dataset": job.get("dataset"), "accuracy": None, "log_loss": None,
                    "n_train": None, "n_test": None, "n_features": None,
                    "feature_importance": [], "version_idx": None, "version_id": None,
                    "error": str(e),
                })
                _set(results=list(results))
                _log(f"[{i + 1}/{n}] ✗ {model_short}: {e}")

        # --- Finalise: reflect single-job outcome in `step` for back-compat ---
        n_fail = sum(1 for r in results if r.get("error"))
        n_ok = len(results) - n_fail
        if n == 1 and n_fail == 1:
            only = results[0]
            is_unsupported = "is not trainable" in (only.get("error") or "")
            _set(is_running=False, finished_at=datetime.now(UTC).isoformat(),
                 step="not_implemented" if is_unsupported else "failed",
                 error=only.get("error"))
        else:
            _set(is_running=False, finished_at=datetime.now(UTC).isoformat(),
                 step=(f"done ({n_ok} ok, {n_fail} failed)" if n_fail else "done"),
                 pct=100.0)
        _log(f"Batch completado: {n_ok} ok, {n_fail} con error")
    except Exception as e:
        logger.exception("batch failed")
        _set(is_running=False, finished_at=datetime.now(UTC).isoformat(),
             step="failed", error=repr(e))
    finally:
        db.close()


def start_batch(jobs: list[dict]) -> dict:
    """Launch a sequential batch of training jobs in a background thread."""
    if not jobs:
        return {"started": False, "message": "No jobs provided"}
    with _lock:
        if _state["is_running"]:
            return {"started": False, "message": "A training job is already running"}
        _state.update({
            "is_running": True,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "model_short": jobs[0].get("model_short"),
            "step": "starting",
            "pct": 0.0,
            "job_index": 0,
            "n_jobs": len(jobs),
            "job_label": None,
            "result_version_id": None,
            "logs": [],
            "results": [],
            "error": None,
        })
    t = threading.Thread(target=_run_batch, args=(list(jobs),), daemon=True)
    t.start()
    return {"started": True, "n_jobs": len(jobs)}


def start_training(req: dict) -> dict:
    """Back-compat single-job entry point (wraps start_batch with one job)."""
    res = start_batch([req])
    if not res.get("started"):
        return res
    return {"started": True, "training_session_id": None}
