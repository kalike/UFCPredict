"""
UFC Predictor — Training Engine.

Provides functions to retrain models from scratch using the existing
feature-engineering pipeline, with configurable dataset, augmentation,
and temporal cutoff.
"""

import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import random

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.svm import SVC

try:
    from lightgbm import LGBMClassifier
except ImportError:
    LGBMClassifier = None  # type: ignore

try:
    from xgboost import XGBClassifier
except ImportError:
    XGBClassifier = None  # type: ignore

try:
    from catboost import CatBoostClassifier
except ImportError:
    CatBoostClassifier = None  # type: ignore

from ufc_core.config import BASE_ELO as _CFG_BASE_ELO
from ufc_core.config import ELO_RATINGS as ELO_RATINGS_PATH
from ufc_core.config import MODELS_DIR
from ufc_core.config import REALWORLD_CUTOFF_DATE, TEST_CUTOFF_DATE
# DeepMLP, TabularResNet imported lazily from .pytorch_architectures
# to avoid loading torch/libomp at module level (conflicts with LightGBM on macOS ARM)

logger = logging.getLogger("ufc-trainer")

# Uniform temporal cutoffs (parsed once). Used by every training flow so that
# the same (train, test/val, realworld) partition holds whether a model is
# trained directly, tuned with Optuna, or re-evaluated by RecalculationService.
TEST_CUTOFF_DT = datetime.strptime(TEST_CUTOFF_DATE, "%Y-%m-%d")
REALWORLD_CUTOFF_DT = datetime.strptime(REALWORLD_CUTOFF_DATE, "%Y-%m-%d")

# ──────────────────────────────────────────────────────────────────────
# ELO recalculation
# ──────────────────────────────────────────────────────────────────────

K_FACTOR = 32


def _expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def recalculate_elo(
    data_store,
    base_elo: float = _CFG_BASE_ELO,
    save_to_disk: bool = True,
) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """Recalculate ELO ratings from all fights, ordered chronologically.

    Returns:
        elo_ratings: {fighter_name: current_elo}
        elo_pre_fight: {(fighter_name, event): elo_before_that_fight}
    """
    all_fights: list[dict] = []
    # Exclude predicted events from ELO calculation too
    predicted_event_names: set[str] = set()
    if hasattr(data_store, "predicted_events"):
        predicted_event_names = {ev["canonical_name"] for ev in data_store.predicted_events}
    for ftr in data_store.fighters_raw:
        name = ftr["name"]
        for fight in ftr.get("fights", []):
            event = fight.get("event", "")
            result = fight.get("result", "")
            opponent = fight.get("opponent", "")
            if event not in data_store.event_dates or result not in ("win", "loss") or not opponent:
                continue
            if event in predicted_event_names:
                continue
            all_fights.append(
                {
                    "fighter": name,
                    "opponent": opponent,
                    "event": event,
                    "date": data_store.event_dates[event],
                    "result": result,
                }
            )

    # Deduplicate (same fight appears for both fighters)
    seen_keys: set = set()
    unique_fights: list[dict] = []
    for f in all_fights:
        key = (*sorted([f["fighter"], f["opponent"]]), f["event"])
        if key not in seen_keys:
            seen_keys.add(key)
            unique_fights.append(f)

    unique_fights.sort(key=lambda x: x["date"])

    elo_ratings: dict[str, float] = {}
    elo_pre_fight: dict[tuple[str, str], float] = {}

    for fight in unique_fights:
        f1, f2 = fight["fighter"], fight["opponent"]
        if f1 not in elo_ratings:
            elo_ratings[f1] = base_elo
        if f2 not in elo_ratings:
            elo_ratings[f2] = base_elo

        elo_f1, elo_f2 = elo_ratings[f1], elo_ratings[f2]
        elo_pre_fight[(f1, fight["event"])] = elo_f1
        elo_pre_fight[(f2, fight["event"])] = elo_f2

        score_f1 = 1.0 if fight["result"] == "win" else 0.0
        exp_f1 = _expected_score(elo_f1, elo_f2)

        elo_ratings[f1] = elo_f1 + K_FACTOR * (score_f1 - exp_f1)
        elo_ratings[f2] = elo_f2 + K_FACTOR * ((1.0 - score_f1) - (1.0 - exp_f1))

    logger.info(
        f"ELO recalculado: {len(elo_ratings):,} peleadores, {len(unique_fights):,} combates"
    )

    if save_to_disk:
        joblib.dump(elo_ratings, ELO_RATINGS_PATH)
        logger.info(f"ELO guardado en {ELO_RATINGS_PATH}")

    return elo_ratings, elo_pre_fight


# ──────────────────────────────────────────────────────────────────────
# Model catalogue — hyperparameters per model type
# ──────────────────────────────────────────────────────────────────────

MODEL_CATALOGUE: dict[str, dict[str, Any]] = {
    "RF35": {
        "full_name": "RF (35f) PRO",
        "algo": "RandomForest",
        "features": "35f",
        "augment": False,
        "params": dict(
            n_estimators=500,
            max_depth=6,
            min_samples_split=10,
            min_samples_leaf=20,
            max_features="sqrt",
            max_samples=0.8,
            random_state=42,
            n_jobs=-1,
        ),
        "scaler": None,
    },
    "RFda": {
        "full_name": "RF D+Aug (35f) PRO",
        "algo": "RandomForest",
        "features": "35f",
        "augment": True,
        "params": dict(
            n_estimators=500,
            max_depth=6,
            min_samples_split=10,
            min_samples_leaf=20,
            max_features="sqrt",
            max_samples=0.8,
            random_state=42,
            n_jobs=-1,
        ),
        "scaler": None,
    },
    "LGBM": {
        "full_name": "LGBM D+Aug (35f) PRO",
        "algo": "LGBM",
        "features": "35f",
        "augment": True,
        "params": dict(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.075,
            subsample=0.75,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=5.0,
            min_child_samples=35,
            random_state=42,
            verbose=-1,
        ),
        "scaler": None,
    },
    "LG52": {
        "full_name": "LGBM D+Aug (52f v3) PRO",
        "algo": "LGBM",
        "features": "52f",
        "augment": True,
        "params": dict(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.075,
            subsample=0.75,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=5.0,
            min_child_samples=35,
            random_state=42,
            verbose=-1,
        ),
        "scaler": None,
    },
    "RF52": {
        "full_name": "RF D+Aug (52f) PRO",
        "algo": "RandomForest",
        "features": "52f",
        "augment": True,
        "params": dict(
            n_estimators=500,
            max_depth=6,
            min_samples_split=10,
            min_samples_leaf=20,
            max_features="sqrt",
            max_samples=0.8,
            random_state=42,
            n_jobs=-1,
        ),
        "scaler": None,
    },
    "MLP": {
        "full_name": "MLP sklearn (35f) PRO",
        "algo": "MLP",
        "features": "35f",
        "augment": True,
        "params": dict(
            hidden_layer_sizes=(128, 64, 32),
            alpha=0.005,
            learning_rate_init=0.001,
            solver="adam",
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
            random_state=42,
        ),
        "scaler": "standard",
    },
    "SVMb": {
        "full_name": "SVM Base (35f) PRO",
        "algo": "SVM",
        "features": "35f",
        "augment": False,
        "params": dict(C=1.0, kernel="rbf", gamma="scale", probability=True, random_state=42),
        "scaler": "standard",
    },
    "SVMg": {
        "full_name": "SVM GSearch (35f) PRO",
        "algo": "SVM",
        "features": "35f",
        "augment": False,
        "params": dict(C=1.0, kernel="poly", gamma="scale", probability=True, random_state=42),
        "scaler": "standard",
    },
    "SVMr": {
        "full_name": "SVM Robust (35f) PRO",
        "algo": "SVM",
        "features": "35f",
        "augment": False,
        "params": dict(C=1.0, kernel="rbf", gamma="scale", probability=True, random_state=42),
        "scaler": "robust",
    },
    "Deep": {
        "full_name": "DeepMLP (35f) PRO",
        "algo": "DeepMLP",
        "features": "35f",
        "augment": True,
        "params": dict(
            hidden_dims=[128, 128, 64, 64],
            dropout=0.25,
            lr=0.001,
            weight_decay=1e-4,
            epochs=300,
            batch_size=256,
            patience=30,
        ),
        "scaler": "standard",
    },
    "RNet": {
        "full_name": "ResNet (35f) PRO",
        "algo": "TabularResNet",
        "features": "35f",
        "augment": True,
        "params": dict(
            hidden_dim=128,
            n_blocks=5,
            dropout=0.25,
            lr=0.001,
            weight_decay=5e-4,
            epochs=300,
            batch_size=256,
            patience=30,
        ),
        "scaler": "standard",
    },
    "XGB": {
        "full_name": "XGB D+Aug (35f) PRO",
        "algo": "XGBoost",
        "features": "35f",
        "augment": True,
        "params": dict(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.075,
            subsample=0.75,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=5.0,
            min_child_weight=5,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        ),
        "scaler": None,
    },
    "XG52": {
        "full_name": "XGB D+Aug (52f) PRO",
        "algo": "XGBoost",
        "features": "52f",
        "augment": True,
        "params": dict(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.075,
            subsample=0.75,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=5.0,
            min_child_weight=5,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        ),
        "scaler": None,
    },
    "CB": {
        "full_name": "CB D+Aug (35f) PRO",
        "algo": "CatBoost",
        "features": "35f",
        "augment": True,
        "params": dict(
            iterations=200,
            depth=4,
            learning_rate=0.075,
            subsample=0.75,
            l2_leaf_reg=5.0,
            min_data_in_leaf=35,
            random_seed=42,
            verbose=0,
        ),
        "scaler": None,
    },
    "CB52": {
        "full_name": "CB D+Aug (52f) PRO",
        "algo": "CatBoost",
        "features": "52f",
        "augment": True,
        "params": dict(
            iterations=200,
            depth=4,
            learning_rate=0.075,
            subsample=0.75,
            l2_leaf_reg=5.0,
            min_data_in_leaf=35,
            random_seed=42,
            verbose=0,
        ),
        "scaler": None,
    },
    "LR": {
        "full_name": "LR ElasticNet (35f) PRO",
        "algo": "LogisticRegression",
        "features": "35f",
        "augment": True,
        "params": dict(
            penalty="elasticnet",
            solver="saga",
            C=1.0,
            l1_ratio=0.5,
            max_iter=1000,
            random_state=42,
        ),
        "scaler": "standard",
    },
    "LR52": {
        "full_name": "LR ElasticNet (52f) PRO",
        "algo": "LogisticRegression",
        "features": "52f",
        "augment": True,
        "params": dict(
            penalty="elasticnet",
            solver="saga",
            C=1.0,
            l1_ratio=0.5,
            max_iter=1000,
            random_state=42,
        ),
        "scaler": "standard",
    },
    "MLP2": {
        "full_name": "MLP Shallow (35f) PRO",
        "algo": "MLPShallow",
        "features": "35f",
        "augment": True,
        "params": dict(
            hidden_layer_sizes=(64, 32),
            alpha=0.005,
            learning_rate_init=0.001,
            solver="adam",
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
            random_state=42,
        ),
        "scaler": "standard",
    },
    "ML52": {
        "full_name": "MLP Shallow (52f) PRO",
        "algo": "MLPShallow",
        "features": "52f",
        "augment": True,
        "params": dict(
            hidden_layer_sizes=(64, 32),
            alpha=0.005,
            learning_rate_init=0.001,
            solver="adam",
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
            random_state=42,
        ),
        "scaler": "standard",
    },
}


# ──────────────────────────────────────────────────────────────────────
# Training progress
# ──────────────────────────────────────────────────────────────────────


@dataclass
class TrainProgress:
    """Mutable object shared to stream training progress."""

    model_short: str = ""
    step: str = "idle"  # building_data | augmenting | fitting | evaluating | saving | done | error
    pct: float = 0.0  # 0-100
    message: str = ""
    metrics: dict = field(default_factory=dict)
    error: str | None = None
    job_index: int = 0
    n_jobs: int = 0
    job_label: str = ""


# ──────────────────────────────────────────────────────────────────────
# Dataset builder
# ──────────────────────────────────────────────────────────────────────

DATASET_CUTOFFS = {
    "since2010": 2010,
    "since2015": 2015,
    "since2020": 2020,
}


def _build_dataset(
    data_store,
    elo_ratings: dict,
    base_elo: float,
    since_year: int = 2010,
    progress: TrainProgress | None = None,
    elo_pre_fight: dict[tuple[str, str], float] | None = None,
    min_fights: int = 0,
    use_pit: bool = False,
    exclude_realworld: bool = True,
) -> pd.DataFrame:
    """Build the ML dataset from raw fight data, filtering events >= since_year.

    If elo_pre_fight is provided, uses the temporally-correct ELO for each
    fight (the rating *before* that fight took place). Otherwise falls back
    to the current (final) elo_ratings dict.

    When exclude_realworld=True (the default for every training flow) any fight
    with event_date >= REALWORLD_CUTOFF_DT is dropped so no training loop can
    ever see the held-out set.
    """
    from ufc_core.features.engine import compute_fight_features

    if progress:
        progress.step = "building_data"
        progress.message = f"Construyendo dataset (desde {since_year})..."
        progress.pct = 5

    # Exclude events that appear in predicciones.txt (predicted events)
    # so we never train on fights we made predictions for.
    predicted_event_names: set[str] = set()
    if hasattr(data_store, "predicted_events"):
        predicted_event_names = {ev["canonical_name"] for ev in data_store.predicted_events}
        if predicted_event_names:
            logger.info(
                "Excluyendo %d eventos predichos del entrenamiento: %s",
                len(predicted_event_names),
                ", ".join(sorted(predicted_event_names)),
            )

    # Collect all fights from fighters_raw that belong to events >= since_year
    fights_list: list[dict] = []
    excluded_count = 0
    for ftr in data_store.fighters_raw:
        fname = ftr["name"]
        for fight in ftr.get("fights", []):
            ev = fight.get("event", "")
            ev_date = data_store.event_dates.get(ev)
            if ev_date and ev_date.year >= since_year:
                if ev in predicted_event_names:
                    excluded_count += 1
                    continue
                fights_list.append(
                    {
                        "fighter_1": fname,
                        "fighter_2": fight.get("opponent", ""),
                        "result_raw": fight.get("result", ""),
                        "event": ev,
                        "event_date": ev_date,
                    }
                )

    if excluded_count > 0:
        logger.info(
            "Entradas excluidas de eventos predichos: %d (~%d combates únicos)",
            excluded_count,
            excluded_count // 2,
        )

    # Deduplicate (same fight appears for both fighters)
    # Randomly assign fighter_1/fighter_2 so we get ~50% result=1 and ~50% result=0
    rng = np.random.RandomState(42)
    seen = set()
    unique_fights: list[dict] = []
    for f in fights_list:
        key = (*sorted([f["fighter_1"], f["fighter_2"]]), f["event"])
        if key not in seen:
            seen.add(key)
            is_winner = f["result_raw"] == "win"
            # Determine canonical fighter_1 (winner) and fighter_2 (loser)
            if is_winner:
                winner, loser = f["fighter_1"], f["fighter_2"]
            else:
                winner, loser = f["fighter_2"], f["fighter_1"]
            # Randomly swap with 50% probability
            if rng.random() < 0.5:
                unique_fights.append(
                    {
                        "fighter_1": winner,
                        "fighter_2": loser,
                        "result": 1,
                        "event": f["event"],
                        "event_date": f["event_date"],
                    }
                )
            else:
                unique_fights.append(
                    {
                        "fighter_1": loser,
                        "fighter_2": winner,
                        "result": 0,
                        "event": f["event"],
                        "event_date": f["event_date"],
                    }
                )

    if progress:
        progress.message = f"Procesando {len(unique_fights)} combates..."
        progress.pct = 15

    # Build tapology_picks lookup once (DB-only; falls back to empty for file mode)
    tapology_picks_by_key: dict = {}
    try:
        from ufc_core.db.engine import SessionLocal as _SyncSessionLocal
        from ufc_core.tapology.picks_repo import build_picks_lookup_by_event_pair
        with _SyncSessionLocal() as _session:
            tapology_picks_by_key = build_picks_lookup_by_event_pair(_session)
        logger.info("Tapology picks lookup: %d entries", len(tapology_picks_by_key))
    except Exception as exc:
        logger.info(
            "Tapology picks lookup unavailable (%s); using neutral imputation", exc,
        )
        tapology_picks_by_key = {}

    from ufc_core.tapology.picks_repo import orient_picks_for_fight

    # Compute features for each fight
    rows = []
    for _, fight in enumerate(unique_fights):
        picks_entry = tapology_picks_by_key.get(
            (fight["event"], frozenset({fight["fighter_1"], fight["fighter_2"]}))
        )
        picks = orient_picks_for_fight(picks_entry, fight["fighter_1"]) if picks_entry else None

        row = compute_fight_features(
            f1_name=fight["fighter_1"],
            f2_name=fight["fighter_2"],
            fighter_histories=data_store.fighter_histories,
            fighter_lookup=data_store.fighter_lookup,
            event_dates=data_store.event_dates,
            event=fight["event"],
            result=fight["result"],
            before_event_date=fight["event_date"] if use_pit else None,
            event_date=fight["event_date"],
            elo_pre_fight=elo_pre_fight,
            elo_ratings=elo_ratings,
            base_elo=base_elo,
            tapology_picks=picks,
        )
        if row is not None:
            row["event_date"] = fight["event_date"]
            row["event_year"] = fight["event_date"].year
            rows.append(row)

    df = pd.DataFrame(rows)

    # Add ELO — prefer temporally-correct pre-fight ELO when available
    if len(df) > 0:
        if elo_pre_fight:
            df["f1_elo"] = df.apply(
                lambda r: elo_pre_fight.get((r["fighter_1"], r["event"]), base_elo),
                axis=1,
            )
            df["f2_elo"] = df.apply(
                lambda r: elo_pre_fight.get((r["fighter_2"], r["event"]), base_elo),
                axis=1,
            )
        elif elo_ratings:
            df["f1_elo"] = df["fighter_1"].map(lambda n: elo_ratings.get(n, base_elo))
            df["f2_elo"] = df["fighter_2"].map(lambda n: elo_ratings.get(n, base_elo))
        else:
            df["f1_elo"] = base_elo
            df["f2_elo"] = base_elo
        df["delta_elo"] = df["f1_elo"] - df["f2_elo"]

    # Filter by min_fights: exclude rows where either fighter has < min_fights
    if min_fights > 0 and len(df) > 0:
        before = len(df)
        mask = (df["f1_total_fights"] >= min_fights) & (df["f2_total_fights"] >= min_fights)
        df = df[mask].reset_index(drop=True)
        dropped = before - len(df)
        if progress:
            progress.message = f"Filtro min_fights={min_fights}: eliminados {dropped} combates"
        logger.info("min_fights=%d: eliminados %d de %d combates", min_fights, dropped, before)

    # Held-out safety: every training flow must exclude fights >= REALWORLD_CUTOFF.
    if exclude_realworld and len(df) > 0:
        before = len(df)
        df = df[df["event_date"] < REALWORLD_CUTOFF_DT].reset_index(drop=True)
        dropped = before - len(df)
        if dropped:
            logger.info(
                "Excluidas %d filas realworld (event_date >= %s)",
                dropped, REALWORLD_CUTOFF_DT.strftime("%Y-%m-%d"),
            )

    if progress:
        progress.message = f"Dataset: {len(df)} filas"
        progress.pct = 25

    return df


def _augment_35f(df: pd.DataFrame) -> pd.DataFrame:
    """Data augmentation for 35f: negate all delta_* and flip result."""
    aug = df.copy()
    delta_cols = [c for c in df.columns if c.startswith("delta_")]
    for c in delta_cols:
        aug[c] = -aug[c]
    # Swap f1/f2 individual columns
    f1_cols = [c for c in df.columns if c.startswith("f1_")]
    f2_cols = [c for c in df.columns if c.startswith("f2_")]
    for f1c, f2c in zip(sorted(f1_cols), sorted(f2_cols), strict=True):
        aug[f1c], aug[f2c] = df[f2c].values, df[f1c].values
    aug["result"] = 1 - aug["result"]
    # Swap fighter names
    aug["fighter_1"], aug["fighter_2"] = df["fighter_2"].values, df["fighter_1"].values
    return pd.concat([df, aug], ignore_index=True)


# V2 feature suffixes — excluded when feature_set="legacy"
V2_FEATURE_SUFFIXES = {
    "chin_damage_score",
    "recent_damage_trend",
    "avg_opp_elo",
    "recent_opp_elo",
    "avg_opp_elo_of_losses",
}

# V3 exclusions — redundant (r>0.90) or near-zero importance features
# Source: Feature Report V2 (2026-04-03), sections D and H
V3_EXCLUDED_SUFFIXES = {
    "avg_distance_landed",   # r=0.952 con avg_sig_str_landed
    "avg_head_landed",       # r=0.922 con avg_sig_str_landed
    "striking_volume",       # r=0.930 con avg_sig_str_landed (derivada)
    "avg_opp_elo",           # r=0.942 con recent_opp_elo
    "height_in",             # importancia < 0.001
    "avg_reversals",         # importancia < 0.001
    # "reach_in" removed from exclusions — re-included in V3 feature set
}

# V4 exclusions — V3 + reach_in (low temporal importance over last 5 years)
V4_EXCLUDED_SUFFIXES = V3_EXCLUDED_SUFFIXES | {"reach_in"}

# V5 exclusions — V3 + features with VIF=inf or r_pb < 0.01
# Source: Data Quality Audit (2026-04-17)
V5_EXCLUDED_SUFFIXES = V3_EXCLUDED_SUFFIXES | {
    "dec_rate",              # VIF=inf, linearly dependent on finish_rate
    "momentum",              # VIF=inf, derived from win_rate/recent_win_rate
    "recent_damage_trend",   # r_pb=-0.005, pure noise
    "avg_clinch_landed",     # r_pb=0.005, pure noise
    "southpaw",              # stance feature excluded from V5 (included in V6+)
}

# V6 = V5 + southpaw (stance encoding: Orthodox=0, Switch=0.5, Southpaw=1)
# Source: Data Quality Audit (2026-04-17), stance available for 88% of fighters
V6_EXCLUDED_SUFFIXES = V5_EXCLUDED_SUFFIXES - {"southpaw"}


# V7 — Tapology community picks features
TAP_ASYM_SUFFIX = "tap_win_pct"  # asymmetric (per-fighter, prefixed f1_/f2_/delta_)
TAP_SYM_COLS = ("tap_consensus_strength", "tap_log_volume", "tap_has_data")  # bare-name fight-level scalars

# Add asymmetric suffix to all non-V7 exclusions so V2..V6 ignore it.
# (Symmetric bare-name cols never enter the prefix filter, so no exclusion needed for them.)
V2_FEATURE_SUFFIXES = V2_FEATURE_SUFFIXES | {TAP_ASYM_SUFFIX}
V3_EXCLUDED_SUFFIXES = V3_EXCLUDED_SUFFIXES | {TAP_ASYM_SUFFIX}
V4_EXCLUDED_SUFFIXES = V4_EXCLUDED_SUFFIXES | {TAP_ASYM_SUFFIX}
V5_EXCLUDED_SUFFIXES = V5_EXCLUDED_SUFFIXES | {TAP_ASYM_SUFFIX}
V6_EXCLUDED_SUFFIXES = V6_EXCLUDED_SUFFIXES | {TAP_ASYM_SUFFIX}

# V7 = V6 minus the tap exclusion. Symmetric tap columns are added explicitly
# in _get_feature_cols (they have no f1_/f2_/delta_ prefix so they don't pass the
# normal filter).
V7_EXCLUDED_SUFFIXES = V6_EXCLUDED_SUFFIXES - {TAP_ASYM_SUFFIX}


def _get_feature_cols(
    df: pd.DataFrame, feat_type: str, feature_set: str = "v2"
) -> list[str]:
    """Get feature column names for a given feature set version.

    feature_set values:
      - "legacy": excludes V2 features (chin, SoS, damage trend) + tap_*
      - "v2": all features except tap_* (current default)
      - "v3": V2 features minus redundant/low-importance ones + tap_*
      - "v4": V3 minus reach_in (low temporal importance) + tap_*
      - "v5": V3 minus dec_rate/momentum/recent_damage_trend/avg_clinch_landed + tap_*
      - "v6": V5 + southpaw (stance encoding) + tap_* exclusion
      - "v7": V6 + tapology picks (3 asym prefixed + 3 sym bare-name)
    """
    if feat_type == "52f":
        f1_cols = sorted([c for c in df.columns if c.startswith("f1_")])
        f2_cols = sorted([c for c in df.columns if c.startswith("f2_")])
        cols = f1_cols + f2_cols
    else:
        cols = sorted([c for c in df.columns if c.startswith("delta_")])

    if feature_set == "legacy":
        cols = [c for c in cols if not any(c.endswith(s) for s in V2_FEATURE_SUFFIXES)]
    elif feature_set == "v2":
        cols = [c for c in cols if not c.endswith(TAP_ASYM_SUFFIX)]
    elif feature_set == "v3":
        cols = [c for c in cols if not any(c.endswith(s) for s in V3_EXCLUDED_SUFFIXES)]
    elif feature_set == "v4":
        cols = [c for c in cols if not any(c.endswith(s) for s in V4_EXCLUDED_SUFFIXES)]
    elif feature_set == "v5":
        cols = [c for c in cols if not any(c.endswith(s) for s in V5_EXCLUDED_SUFFIXES)]
    elif feature_set == "v6":
        cols = [c for c in cols if not any(c.endswith(s) for s in V6_EXCLUDED_SUFFIXES)]
    elif feature_set == "v7":
        cols = [c for c in cols if not any(c.endswith(s) for s in V7_EXCLUDED_SUFFIXES)]
        cols += [c for c in TAP_SYM_COLS if c in df.columns]

    return cols


# ──────────────────────────────────────────────────────────────────────
# PyTorch training helpers
# ──────────────────────────────────────────────────────────────────────


def _train_pytorch_model(
    model,  # nn.Module — lazy import
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray | None,
    y_val: np.ndarray | None,
    lr: float = 0.001,
    weight_decay: float = 1e-4,
    epochs: int = 300,
    batch_size: int = 256,
    patience: int = 30,
    progress: TrainProgress | None = None,
    use_early_stopping: bool = True,
):
    """Train a PyTorch model.

    When use_early_stopping=True (default): runs ReduceLROnPlateau against the
    given X_val/y_val and restores the best state by val_loss.
    When use_early_stopping=False: trains for exactly `epochs` epochs with no
    validation; X_val/y_val are ignored (may be None). Used by the production
    retrain after Optuna has already chosen `epochs`.
    """
    import torch
    import torch.nn as nn

    if use_early_stopping and (X_val is None or y_val is None):
        raise ValueError("X_val/y_val required when use_early_stopping=True")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=0.5,
        patience=7,
    ) if use_early_stopping else None
    criterion = nn.BCEWithLogitsLoss()

    X_t = torch.FloatTensor(X_train)
    y_t = torch.FloatTensor(y_train)
    X_v = torch.FloatTensor(X_val) if use_early_stopping else None
    y_v = torch.FloatTensor(y_val) if use_early_stopping else None

    best_loss = float("inf")
    wait = 0
    best_state = None

    for epoch in range(epochs):
        model.train()
        indices = torch.randperm(len(X_t))
        epoch_loss = 0
        n_batches = 0

        for start in range(0, len(X_t), batch_size):
            batch_idx = indices[start : start + batch_size]
            xb, yb = X_t[batch_idx], y_t[batch_idx]
            optimizer.zero_grad()
            out = model(xb).squeeze(-1)
            loss = criterion(out, yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1

        if use_early_stopping:
            model.eval()
            with torch.no_grad():
                val_out = model(X_v).squeeze(-1)
                val_loss = criterion(val_out, y_v).item()

            scheduler.step(val_loss)

            if val_loss < best_loss:
                best_loss = val_loss
                wait = 0
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
            else:
                wait += 1

            if progress and epoch % 10 == 0:
                pct_base = 40
                pct_range = 40
                progress.pct = pct_base + (epoch / epochs) * pct_range
                progress.message = (
                    f"Epoch {epoch}/{epochs} — val_loss={val_loss:.4f} — patience={wait}/{patience}"
                )

            if wait >= patience:
                break
        else:
            if progress and epoch % 10 == 0:
                pct_base = 40
                pct_range = 40
                progress.pct = pct_base + (epoch / epochs) * pct_range
                progress.message = f"Epoch {epoch}/{epochs} (prod retrain, no early stop)"

    if use_early_stopping and best_state:
        model.load_state_dict(best_state)
    model.eval()
    return model


# ──────────────────────────────────────────────────────────────────────
# Feature importance helpers
# ──────────────────────────────────────────────────────────────────────


class _PyTorchPredictor:
    """Sklearn-compatible wrapper for PyTorch binary classifiers."""

    def __init__(self, model):
        self._model = model

    def fit(self, X, y):
        return self

    def score(self, X, y):
        return float(np.mean(self.predict(X) == y))

    def predict(self, X: np.ndarray) -> np.ndarray:
        import torch

        self._model.eval()
        with torch.no_grad():
            proba = torch.sigmoid(
                self._model(torch.FloatTensor(X)).squeeze(-1)
            ).numpy()
        return (proba >= 0.5).astype(int)


def _permutation_importance(
    model, X_test: np.ndarray, y_test: np.ndarray, feat_cols: list[str],
    n_repeats: int = 10, is_pytorch: bool = False,
) -> list[dict]:
    """Compute permutation importance for models without native feature_importances_."""
    from sklearn.inspection import permutation_importance as sklearn_perm_importance

    estimator = _PyTorchPredictor(model) if is_pytorch else model
    result = sklearn_perm_importance(
        estimator, X_test, y_test, n_repeats=n_repeats, random_state=42,
        n_jobs=1 if is_pytorch else -1,
    )
    imp = [
        {"feature": feat_cols[i], "importance": round(float(v), 6)}
        for i, v in enumerate(result.importances_mean)
    ]
    imp.sort(key=lambda x: x["importance"], reverse=True)
    return imp


# ──────────────────────────────────────────────────────────────────────
# Main training function
# ──────────────────────────────────────────────────────────────────────

PYTORCH_SEED = 42


def _seed_pytorch(seed: int = PYTORCH_SEED) -> None:
    """Fix all random seeds for reproducible PyTorch training."""
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def evaluate_realworld(
    model,
    scaler,
    imputer,
    feat_cols: list[str],
    realworld_df: pd.DataFrame,
    is_pytorch: bool = False,
    min_fights: int = 2,
) -> dict:
    """Evaluate a model on realworld (promoted) fights with known results.

    Uses TTA (Test-Time Augmentation) to match production prediction behavior.
    Returns dict with realworld_accuracy, realworld_correct, realworld_total, realworld_events.
    """
    from ufc_core.transforms import FeatureTransformer

    # 35f (delta_*) opts into the odd clip_sym_6 override so the negation-based
    # TTA flip below (-X) matches what the model trained on. 52f keeps defaults.
    is_52f = any(c.startswith("f1_") for c in feat_cols)
    transformer = FeatureTransformer(enabled=True, delta_overrides=not is_52f)
    rw = realworld_df.copy()

    # Defensive filter: realworld is strictly event_date >= REALWORLD_CUTOFF_DT.
    # build_realworld_df already enforces this; we re-apply it here so no
    # other caller can accidentally feed pre-realworld rows into evaluation.
    if "event_date" in rw.columns and len(rw) > 0:
        before = len(rw)
        rw = rw[rw["event_date"] >= REALWORLD_CUTOFF_DT].reset_index(drop=True)
        dropped = before - len(rw)
        if dropped:
            logger.info(
                "evaluate_realworld: descartadas %d filas con event_date < %s",
                dropped, REALWORLD_CUTOFF_DT.strftime("%Y-%m-%d"),
            )

    # Filter by min_fights using PIT-correct columns from feature computation
    if min_fights > 0 and "f1_total_fights" in rw.columns:
        mask = (rw["f1_total_fights"] >= min_fights) & (rw["f2_total_fights"] >= min_fights)
        rw = rw[mask].reset_index(drop=True)
    if len(rw) == 0:
        return {
            "realworld_accuracy": None,
            "realworld_correct": 0,
            "realworld_total": 0,
            "realworld_events": [],
        }

    # Ensure all feat_cols are present
    for c in feat_cols:
        if c not in rw.columns:
            rw[c] = 0

    rw_imputed = imputer.transform(rw)
    rw_imputed = transformer.transform_df(rw_imputed)
    X_rw = rw_imputed[feat_cols].values.astype(np.float32)
    np.nan_to_num(X_rw, copy=False, nan=0.0)
    y_rw = rw["rw_label"].values.astype(np.float32)

    # Scale
    if scaler is not None:
        X_rw_sc = scaler.transform(X_rw)
    else:
        X_rw_sc = X_rw

    # TTA flip: negate for 35f (delta_*), swap halves for 52f (f1_*/f2_*)
    if is_52f:
        n_half = sum(1 for c in feat_cols if c.startswith("f1_"))
        X_rw_flip = np.hstack([X_rw[:, n_half:], X_rw[:, :n_half]])
    else:
        X_rw_flip = -X_rw

    if scaler is not None:
        X_rw_flip_sc = scaler.transform(X_rw_flip)
    else:
        X_rw_flip_sc = X_rw_flip

    if is_pytorch:
        import torch

        model.eval()
        with torch.no_grad():
            p_orig = torch.sigmoid(
                model(torch.FloatTensor(X_rw_sc)).squeeze(-1)
            ).numpy()
            p_flip = torch.sigmoid(
                model(torch.FloatTensor(X_rw_flip_sc)).squeeze(-1)
            ).numpy()
    else:
        p_orig = model.predict_proba(X_rw_sc)[:, 1]
        p_flip = model.predict_proba(X_rw_flip_sc)[:, 1]

    p_orig = np.atleast_1d(p_orig)
    p_flip = np.atleast_1d(p_flip)
    proba_rw = (p_orig + (1 - p_flip)) / 2  # TTA

    y_rw_pred = (proba_rw >= 0.5).astype(int)

    rw_correct = int((y_rw_pred == y_rw).sum())
    rw_total = len(y_rw)
    rw_acc = round(rw_correct / rw_total, 4) if rw_total > 0 else None

    # Per-event/per-fight breakdown
    rw_events: dict[str, dict] = {}
    for idx in range(len(rw)):
        ev = rw.iloc[idx].get("event", "Unknown")
        f1 = rw.iloc[idx].get("fighter_1", "?")
        f2 = rw.iloc[idx].get("fighter_2", "?")
        real_winner = rw.iloc[idx].get("rw_real_winner", "?")
        label = int(y_rw[idx])
        pred = int(y_rw_pred[idx])
        correct = pred == label
        predicted_winner = f1 if pred == 1 else f2

        if ev not in rw_events:
            ed = rw.iloc[idx].get("event_date")
            try:
                ed_iso = ed.isoformat() if ed is not None else None
            except AttributeError:
                ed_iso = str(ed) if ed is not None else None
            rw_events[ev] = {"correct": 0, "total": 0, "fights": [], "date": ed_iso}
        rw_events[ev]["total"] += 1
        if correct:
            rw_events[ev]["correct"] += 1
        rw_events[ev]["fights"].append({
            "fighter_1": f1,
            "fighter_2": f2,
            "predicted_winner": predicted_winner,
            "real_winner": real_winner,
            "correct": correct,
        })

    # Newest first (events without a date sink to the end).
    events_out = [
        {"event": ev, "date": d.get("date"),
         "correct": d["correct"], "total": d["total"], "fights": d["fights"]}
        for ev, d in rw_events.items()
    ]
    events_out.sort(key=lambda e: (e["date"] is not None, e["date"] or ""), reverse=True)

    result = {
        "realworld_accuracy": rw_acc,
        "realworld_correct": rw_correct,
        "realworld_total": rw_total,
        "realworld_events": events_out,
    }

    # Value-vs-market metrics, only when the held-out df carries odds (RealWorld
    # window; backfilled from Tapology). Aligned with proba_rw / y_rw post-filter.
    if "odds_f1_american" in rw.columns and "odds_f2_american" in rw.columns:
        import pandas as pd
        from ufc_core.trainer.value_metrics import compute_value_metrics
        rv = compute_value_metrics(
            proba_rw, y_rw,
            pd.to_numeric(rw["odds_f1_american"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(rw["odds_f2_american"], errors="coerce").to_numpy(dtype=float),
            event_dates=(
                pd.to_datetime(rw["event_date"]).to_numpy()
                if "event_date" in rw.columns else None
            ),
        )
        if rv is not None:
            result["realworld_value"] = rv

    return result



# CAL_CUTOFF removed — Platt calibration disabled (was hurting realworld accuracy)


def _build_calibration_from_predictions(
    data_store,
    model,
    scaler,
    imputer,
    feat_cols: list[str],
    feat_type: str,
    is_pytorch: bool,
    elo_ratings: dict | None = None,
    elo_pre_fight: dict | None = None,
    base_elo: float = 1500,
    min_fights: int = 0,
    seed: int = 42,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Build calibration data from predicciones.txt fights before CAL_CUTOFF.

    Uses the production model to predict on truly out-of-sample fights
    (excluded from training by predicted_event_names filter).
    Fighter_1 in predicciones.txt is always the real winner.
    Returns (proba_tta, labels) or (None, None) if not enough data.
    """
    from ufc_core.features.engine import compute_fight_features
    from ufc_core.transforms import FeatureTransformer

    if not hasattr(data_store, "fight_cards") or not data_store.fight_cards:
        logger.warning("No fight_cards in data_store — skipping calibration")
        return None, None

    rng = np.random.RandomState(seed)
    rows = []
    labels = []
    seen = set()
    cal_event_counts: dict[str, int] = {}
    cal_event_dates: dict[str, str] = {}

    for fight in data_store.fight_cards:
        winner = fight["fighter_1"]
        loser = fight["fighter_2"]
        event = fight.get("event", "")

        # Only use fights before cutoff
        ev_date = data_store.event_dates.get(event)
        if ev_date is None or ev_date >= CAL_CUTOFF:
            continue

        # Deduplicate
        key = tuple(sorted([winner, loser])) + (event,)
        if key in seen:
            continue
        seen.add(key)

        cal_event_counts[event] = cal_event_counts.get(event, 0) + 1
        cal_event_dates[event] = ev_date.strftime("%Y-%m-%d")

        # Random swap to eliminate positional bias
        if rng.random() < 0.5:
            f1, f2, label = winner, loser, 1.0
        else:
            f1, f2, label = loser, winner, 0.0

        row = compute_fight_features(
            f1_name=f1,
            f2_name=f2,
            fighter_histories=data_store.fighter_histories,
            fighter_lookup=data_store.fighter_lookup,
            event_dates=data_store.event_dates,
            event=event,
            odds_f1_american=fight.get("odds_f1_american"),
            odds_f2_american=fight.get("odds_f2_american"),
            before_event_date=ev_date,
            elo_ratings=elo_ratings,
            elo_pre_fight=elo_pre_fight,
            base_elo=base_elo,
        )
        if row is None:
            continue

        # PIT ELO override
        if elo_pre_fight:
            row["f1_elo"] = elo_pre_fight.get((f1, event), base_elo)
            row["f2_elo"] = elo_pre_fight.get((f2, event), base_elo)
            row["delta_elo"] = row["f1_elo"] - row["f2_elo"]

        # min_fights filter
        f1_fights = row.get("f1_total_fights", 0) or 0
        f2_fights = row.get("f2_total_fights", 0) or 0
        if f1_fights < min_fights or f2_fights < min_fights:
            continue

        rows.append(row)
        labels.append(label)

    if len(rows) < 30:
        logger.warning(
            "Only %d calibration fights from predicciones.txt (need >= 30)",
            len(rows),
        )
        return None, None

    transformer = FeatureTransformer(enabled=True)
    df_cal = pd.DataFrame(rows)
    y = np.array(labels, dtype=np.float32)

    for c in feat_cols:
        if c not in df_cal.columns:
            df_cal[c] = 0

    df_cal = imputer.transform(df_cal)
    df_cal = transformer.transform_df(df_cal)
    X = df_cal[feat_cols].values.astype(np.float32)
    np.nan_to_num(X, copy=False, nan=0.0)

    # TTA flip
    is_52f = feat_type == "52f"
    if is_52f:
        n_half = sum(1 for c in feat_cols if c.startswith("f1_"))
        X_flip = np.hstack([X[:, n_half:], X[:, :n_half]])
    else:
        X_flip = -X

    # Scale
    if scaler is not None:
        X = scaler.transform(X)
        X_flip = scaler.transform(X_flip)

    # Predict with production model (TTA)
    if is_pytorch:
        import torch
        model.eval()
        with torch.no_grad():
            p_orig = torch.sigmoid(model(torch.FloatTensor(X)).squeeze(-1)).numpy()
            p_flip = torch.sigmoid(model(torch.FloatTensor(X_flip)).squeeze(-1)).numpy()
    else:
        p_orig = model.predict_proba(X)[:, 1]
        p_flip = model.predict_proba(X_flip)[:, 1]

    p_orig = np.atleast_1d(p_orig)
    p_flip = np.atleast_1d(p_flip)
    proba_tta = (p_orig + (1 - p_flip)) / 2

    # Per-event summary for auditability
    for ev, cnt in sorted(cal_event_counts.items(), key=lambda x: cal_event_dates.get(x[0], "")):
        logger.info("  CAL event: %s | %s | %d fights", cal_event_dates.get(ev, "?"), ev, cnt)

    logger.info(
        "Calibration dataset: %d fights from predicciones.txt (before %s), "
        "label distribution: %.1f%% positive",
        len(y), CAL_CUTOFF.strftime("%Y-%m"), y.mean() * 100,
    )
    return proba_tta, y


def _fit_platt_calibrator(y_proba_raw: np.ndarray, y_true: np.ndarray):
    """Fit a Platt scaling calibrator (LogisticRegression on raw probabilities)."""
    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    lr.fit(y_proba_raw.reshape(-1, 1), y_true)
    return lr


def recalibrate_model(
    model_short: str,
    **kwargs,
) -> dict:
    """Re-fit Platt calibrator for an active model without retraining.

    Uses the persisted temporal test fold probabilities (cal_data .npz)
    from the training run. Requires the model to have been trained with
    the updated pipeline that saves cal_data_path.
    """
    if model_short not in MODEL_CATALOGUE:
        raise ValueError(f"Unknown model: {model_short}")

    reg = load_model_registry()
    model_entry = reg.get("models", {}).get(model_short, {})
    active_idx = model_entry.get("active_version")
    if active_idx is None:
        raise ValueError(f"No active version for {model_short}")

    versions = model_entry.get("versions", [])
    if active_idx < 0 or active_idx >= len(versions):
        raise ValueError(f"Invalid active version index for {model_short}")

    version = versions[active_idx]

    # Load persisted calibration data
    cal_data_path = version.get("cal_data_path")
    if not cal_data_path or not Path(cal_data_path).exists():
        raise ValueError(
            f"No calibration data for {model_short}. "
            "Retrain the model to generate temporal test fold data."
        )

    data = np.load(cal_data_path)
    cal_proba = data["proba"]
    cal_labels = data["labels"]

    if len(cal_labels) < 30:
        raise ValueError(f"Only {len(cal_labels)} calibration samples (need >= 30)")

    # Fit and save calibrator
    calibrator = _fit_platt_calibrator(cal_proba, cal_labels)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_dir = MODELS_DIR / "retrained"
    new_dir.mkdir(exist_ok=True)
    cal_path = new_dir / f"{model_short}_calibrator_{timestamp}.joblib"
    joblib.dump(calibrator, cal_path)

    # Delete old calibrator file if exists
    old_cal_path = version.get("calibrator_path")
    if old_cal_path:
        old_p = Path(old_cal_path)
        if old_p.exists():
            old_p.unlink()

    # Update registry
    version["calibrator_path"] = str(cal_path)
    save_model_registry(reg)

    logger.info(
        "%s: Platt calibrator re-fitted on %d test fold fights, saved to %s",
        model_short, len(cal_labels), cal_path,
    )
    return {
        "ok": True,
        "short": model_short,
        "calibrator_path": str(cal_path),
        "n_calibration_fights": len(cal_labels),
    }


def load_version_model(
    version: dict, cat: dict,
) -> tuple[object, object, object, list[str], bool]:
    """Load a model version from disk for evaluation purposes.

    Returns (model, scaler, imputer, feat_cols, is_pytorch).
    Does NOT store anything in the registry — objects are for temporary use.
    """
    from ufc_core.imputer import FeatureImputer

    algo = cat.get("algo", "")
    is_pytorch = algo in ("DeepMLP", "TabularResNet")
    saved_path = version.get("saved_path")
    if not saved_path or not Path(saved_path).exists():
        raise FileNotFoundError(f"Model file not found: {saved_path}")

    # Load model
    if is_pytorch:
        import torch
        from ufc_core.models.pytorch_arch import DeepMLP, TabularResNet

        params = version.get("params") or cat.get("params", {})
        state_dict = torch.load(saved_path, map_location="cpu", weights_only=True)

        # Infer n_features from first layer weight shape
        first_weight_key = next((k for k in state_dict if k.endswith(".weight")), None)
        n_features = state_dict[first_weight_key].shape[1] if first_weight_key else 35

        if algo == "DeepMLP":
            hidden_dims = params.get("hidden_dims", [128, 128, 64, 64])
            if isinstance(hidden_dims, str):
                hidden_dims = json.loads(hidden_dims)
            model = DeepMLP(n_features, hidden_dims, dropout=params.get("dropout", 0.25))
        else:
            model = TabularResNet(
                n_features,
                hidden_dim=params.get("hidden_dim", 128),
                n_blocks=params.get("n_blocks", 5),
                dropout=params.get("dropout", 0.25),
            )
        model.load_state_dict(state_dict)
        model.eval()
    else:
        model = joblib.load(saved_path)

    # Load scaler
    scaler = None
    scaler_path = version.get("scaler_path")
    if scaler_path and Path(scaler_path).exists():
        scaler = joblib.load(scaler_path)

    # Load imputer
    imputer = None
    imputer_path = version.get("imputer_path")
    if imputer_path and Path(imputer_path).exists():
        imputer = FeatureImputer.load(imputer_path)

    # Feature columns
    feat_cols = version.get("feat_cols") or []

    return model, scaler, imputer, feat_cols, is_pytorch


# ──────────────────────────────────────────────────────────────────────
# Shared preprocessing for train/HP search alignment
# ──────────────────────────────────────────────────────────────────────

@dataclass
class PreprocessResult:
    """Artifacts produced by _preprocess_split."""
    X_train: np.ndarray
    y_train: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    feat_cols: list
    scaler: object  # StandardScaler | RobustScaler | None
    imputer: object  # FeatureImputer
    transformer: object  # FeatureTransformer


def _preprocess_split(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feat_type: str,
    feature_set: str,
    do_augment: bool,
    scaler_type: str | None,
) -> PreprocessResult:
    """Shared pipeline: augment → features → impute → transform → scale.

    Used by both train_single_model and HP search to guarantee identical
    preprocessing for the same data split.
    """
    from ufc_core.imputer import FeatureImputer
    from ufc_core.transforms import FeatureTransformer

    # 1. Augmentation (only on train)
    if do_augment:
        train_df = _augment_35f(train_df)

    # 2. Feature columns (always discovered post-augment on train)
    feat_cols = _get_feature_cols(train_df, feat_type, feature_set=feature_set)

    # 3. Ensure all columns present
    for c in feat_cols:
        if c not in train_df.columns:
            train_df[c] = 0
        if c not in test_df.columns:
            test_df[c] = 0

    # 4. Impute
    imputer = FeatureImputer().fit(train_df, feat_cols)
    train_imputed = imputer.transform(train_df)
    test_imputed = imputer.transform(test_df)

    # 5. Transform — 35f opts into the odd clip_sym_6 for delta_win_streak so it
    # keeps its sign and stays TTA-symmetric (52f has no delta_ cols → no-op).
    transformer = FeatureTransformer(enabled=True, delta_overrides=(feat_type == "35f"))
    train_imputed = transformer.transform_df(train_imputed)
    test_imputed = transformer.transform_df(test_imputed)

    # 6. Extract arrays
    X_train = train_imputed[feat_cols].values.astype(np.float32)
    y_train = train_df["result"].values.astype(np.float32)
    X_test = test_imputed[feat_cols].values.astype(np.float32)
    y_test = test_df["result"].values.astype(np.float32)

    # 7. Scale
    scaler = None
    if scaler_type == "standard":
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
    elif scaler_type == "robust":
        scaler = RobustScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)

    return PreprocessResult(
        X_train=X_train, y_train=y_train,
        X_test=X_test, y_test=y_test,
        feat_cols=feat_cols, scaler=scaler,
        imputer=imputer, transformer=transformer,
    )


def train_single_model(
    model_short: str,
    data_store,
    elo_ratings: dict,
    base_elo: float,
    feats_35: list[str],
    feats_52: list[str],
    dataset_key: str = "since2010",
    force_augment: bool | None = None,
    test_cutoff_year: int | None = None,
    test_cutoff_date: str | None = None,
    progress: TrainProgress | None = None,
    elo_pre_fight: dict[tuple[str, str], float] | None = None,
    min_fights: int = 0,
    use_pit: bool = False,
    feature_set: str = "legacy",
    realworld_df: pd.DataFrame | None = None,
    feat_type_override: str | None = None,
) -> dict:
    """Train a single model and return metrics + path to saved model.

    The temporal split is fixed by the global cutoffs (TEST_CUTOFF_DT and
    REALWORLD_CUTOFF_DT) so every training flow sees the same partition.
    `test_cutoff_year` and `test_cutoff_date` are kept for backwards-compatible
    request payloads but are ignored — emit a warning if a caller sets them.
    """
    if model_short not in MODEL_CATALOGUE:
        raise ValueError(f"Unknown model: {model_short}")

    if test_cutoff_year is not None or test_cutoff_date is not None:
        logger.warning(
            "%s: test_cutoff_year/test_cutoff_date are deprecated and ignored; "
            "using TEST_CUTOFF=%s / REALWORLD_CUTOFF=%s",
            model_short,
            TEST_CUTOFF_DT.strftime("%Y-%m-%d"),
            REALWORLD_CUTOFF_DT.strftime("%Y-%m-%d"),
        )

    cat = MODEL_CATALOGUE[model_short]
    since_year = DATASET_CUTOFFS.get(dataset_key, 2010)

    if progress:
        progress.model_short = model_short
        progress.step = "building_data"
        progress.pct = 0

    # 1. Build dataset (always excludes realworld — hard guarantee).
    df = _build_dataset(
        data_store, elo_ratings, base_elo, since_year, progress, elo_pre_fight, min_fights, use_pit
    )
    if len(df) == 0:
        raise ValueError("Empty dataset")

    # 2. Clean NaN in result
    df = df.dropna(subset=["result"])
    df["result"] = df["result"].astype(int)

    # 3. Fixed temporal split:
    #    train = event_date < TEST_CUTOFF_DT
    #    test/val = TEST_CUTOFF_DT <= event_date < REALWORLD_CUTOFF_DT
    # df already guarantees event_date < REALWORLD_CUTOFF_DT.
    train_df = df[df["event_date"] < TEST_CUTOFF_DT].copy()
    test_df = df[df["event_date"] >= TEST_CUTOFF_DT].copy()

    if len(train_df) == 0 or len(test_df) == 0:
        raise ValueError(f"Split vacío: train={len(train_df)}, test={len(test_df)}")

    if progress:
        progress.step = "augmenting"
        progress.pct = 30
        progress.message = f"Train={len(train_df)}, Test={len(test_df)}"

    # 4-6. Augment → features → impute → transform → scale (shared pipeline)
    do_augment = force_augment if force_augment is not None else cat["augment"]
    feat_type = feat_type_override if feat_type_override else cat["features"]
    scaler_type = cat.get("scaler")

    pp = _preprocess_split(
        train_df, test_df,
        feat_type=feat_type, feature_set=feature_set,
        do_augment=do_augment, scaler_type=scaler_type,
    )
    X_train_sc, y_train = pp.X_train, pp.y_train
    X_test_sc, y_test = pp.X_test, pp.y_test
    feat_cols = pp.feat_cols
    scaler = pp.scaler
    transformer = pp.transformer

    from ufc_core.imputer import FeatureImputer

    if progress:
        progress.step = "fitting"
        progress.pct = 35
        progress.message = f"Entrenando {cat['algo']}..."

    # 7. Train
    algo = cat["algo"]
    params = cat["params"]
    saved_model = None
    feature_importance = None
    is_pytorch = False

    if algo == "RandomForest":
        rf_params = {**params}
        if not rf_params.get("bootstrap", True):
            rf_params.pop("max_samples", None)
        model = RandomForestClassifier(**rf_params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "LGBM":
        if LGBMClassifier is None:
            raise ImportError("lightgbm not installed")
        model = LGBMClassifier(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "MLP":
        model = MLPClassifier(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = _permutation_importance(model, X_test_sc, y_test, feat_cols)

    elif algo == "SVM":
        model = SVC(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = _permutation_importance(model, X_test_sc, y_test, feat_cols)

    elif algo == "XGBoost":
        if XGBClassifier is None:
            raise ImportError("xgboost not installed")
        model = XGBClassifier(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "CatBoost":
        if CatBoostClassifier is None:
            raise ImportError("catboost not installed")
        model = CatBoostClassifier(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "LogisticRegression":
        model = LogisticRegression(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = _permutation_importance(model, X_test_sc, y_test, feat_cols)

    elif algo == "MLPShallow":
        model = MLPClassifier(**params)
        model.fit(X_train_sc, y_train)
        saved_model = model
        feature_importance = _permutation_importance(model, X_test_sc, y_test, feat_cols)

    elif algo == "DeepMLP":
        from ufc_core.models.pytorch_arch import DeepMLP
        is_pytorch = True
        _seed_pytorch()
        model = DeepMLP(len(feat_cols), params["hidden_dims"], params["dropout"])
        model = _train_pytorch_model(
            model,
            X_train_sc,
            y_train,
            X_test_sc,
            y_test,
            lr=params["lr"],
            weight_decay=params["weight_decay"],
            epochs=params["epochs"],
            batch_size=params["batch_size"],
            patience=params["patience"],
            progress=progress,
        )
        saved_model = model
        feature_importance = _permutation_importance(
            model, X_test_sc, y_test, feat_cols, is_pytorch=True,
        )

    elif algo == "TabularResNet":
        from ufc_core.models.pytorch_arch import TabularResNet
        is_pytorch = True
        _seed_pytorch()
        model = TabularResNet(
            len(feat_cols), params["hidden_dim"], params["n_blocks"], params["dropout"]
        )
        model = _train_pytorch_model(
            model,
            X_train_sc,
            y_train,
            X_test_sc,
            y_test,
            lr=params["lr"],
            weight_decay=params["weight_decay"],
            epochs=params["epochs"],
            batch_size=params["batch_size"],
            patience=params["patience"],
            progress=progress,
        )
        saved_model = model
        feature_importance = _permutation_importance(
            model, X_test_sc, y_test, feat_cols, is_pytorch=True,
        )
    else:
        raise ValueError(f"Unknown algo: {algo}")

    if progress:
        progress.step = "evaluating"
        progress.pct = 85
        progress.message = "Evaluando..."

    # 8. Evaluate
    if is_pytorch:
        import torch

        saved_model.eval()
        with torch.no_grad():
            X_t = torch.FloatTensor(X_test_sc)
            proba_test = torch.sigmoid(saved_model(X_t).squeeze(-1)).numpy()
        y_pred = (proba_test >= 0.5).astype(int)
        # Train accuracy
        with torch.no_grad():
            X_tr_t = torch.FloatTensor(X_train_sc)
            proba_train = torch.sigmoid(saved_model(X_tr_t).squeeze(-1)).numpy()
        y_pred_train = (proba_train >= 0.5).astype(int)
    else:
        y_pred = saved_model.predict(X_test_sc)
        proba_test = None
        if hasattr(saved_model, "predict_proba"):
            pp = saved_model.predict_proba(X_test_sc)
            proba_test = pp[:, 1] if pp.shape[1] > 1 else pp[:, 0]
        y_pred_train = saved_model.predict(X_train_sc)

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    try:
        auc = float(roc_auc_score(y_test, proba_test)) if proba_test is not None else None
    except ValueError:
        auc = None  # Only one class in y_test
    cm = confusion_matrix(y_test, y_pred).tolist()
    train_acc = accuracy_score(y_train, y_pred_train)

    metrics = {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "auc": round(auc, 4) if (auc is not None and not math.isnan(auc)) else None,
        "confusion_matrix": cm,
        "train_accuracy": round(train_acc, 4),
        "overfit_gap": round(train_acc - acc, 4),
        "n_train": len(y_train),
        "n_test": len(y_test),
        "n_production": None,  # filled after production retrain
    }

    if progress:
        progress.step = "saving"
        progress.pct = 92
        progress.message = f"Accuracy={acc:.4f} | Re-entrenando con todos los datos..."

    # 9. PRODUCTION RETRAIN — fit on ALL data (train + test) for the model that gets saved
    # Metrics above are from the held-out evaluation; the production model uses all available data.
    full_df = df.copy()
    if do_augment:
        full_df = _augment_35f(full_df)
    for c in feat_cols:
        if c not in full_df.columns:
            full_df[c] = 0

    imputer_prod = FeatureImputer().fit(full_df, feat_cols)
    full_imputed = imputer_prod.transform(full_df)
    full_imputed = transformer.transform_df(full_imputed)
    X_full = full_imputed[feat_cols].values.astype(np.float32)
    y_full = full_df["result"].values.astype(np.float32)

    # Re-fit scaler on full data
    scaler = None
    scaler_type = cat.get("scaler")
    if scaler_type == "standard":
        scaler = StandardScaler()
        X_full_sc = scaler.fit_transform(X_full)
    elif scaler_type == "robust":
        scaler = RobustScaler()
        X_full_sc = scaler.fit_transform(X_full)
    else:
        X_full_sc = X_full

    # Re-train on full dataset
    if algo == "RandomForest":
        rf_prod_params = {**params}
        if not rf_prod_params.get("bootstrap", True):
            rf_prod_params.pop("max_samples", None)
        prod_model = RandomForestClassifier(**rf_prod_params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(prod_model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "LGBM":
        prod_model = LGBMClassifier(**params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(prod_model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "MLP":
        # Production retrain: disable early stopping so the model fits the full
        # pre-realworld dataset deterministically with the epochs/iterations
        # Optuna already chose, instead of slicing an internal random holdout.
        mlp_prod_params = {**params, "early_stopping": False}
        mlp_prod_params.pop("validation_fraction", None)
        mlp_prod_params.pop("n_iter_no_change", None)
        prod_model = MLPClassifier(**mlp_prod_params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        # feature_importance already computed on eval model (step 7) — no data leakage

    elif algo == "SVM":
        prod_model = SVC(**params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        # feature_importance already computed on eval model (step 7) — no data leakage

    elif algo == "XGBoost":
        prod_model = XGBClassifier(**params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(prod_model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "CatBoost":
        prod_model = CatBoostClassifier(**params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        feature_importance = [
            {"feature": feat_cols[i], "importance": round(float(v), 6)}
            for i, v in enumerate(prod_model.feature_importances_)
        ]
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    elif algo == "LogisticRegression":
        prod_model = LogisticRegression(**params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        # feature_importance already computed on eval model (step 7) — no data leakage

    elif algo == "MLPShallow":
        mlp_prod_params = {**params, "early_stopping": False}
        mlp_prod_params.pop("validation_fraction", None)
        mlp_prod_params.pop("n_iter_no_change", None)
        prod_model = MLPClassifier(**mlp_prod_params)
        prod_model.fit(X_full_sc, y_full)
        saved_model = prod_model
        # feature_importance already computed on eval model (step 7) — no data leakage

    elif algo == "DeepMLP":
        from ufc_core.models.pytorch_arch import DeepMLP

        _seed_pytorch()
        prod_model = DeepMLP(len(feat_cols), params["hidden_dims"], params["dropout"])
        # Production retrain: fit on everything pre-realworld with fixed epochs
        # (no early stopping, no random val holdout). Optuna already chose epochs.
        prod_model = _train_pytorch_model(
            prod_model,
            X_full_sc,
            y_full,
            X_val=None,
            y_val=None,
            lr=params["lr"],
            weight_decay=params["weight_decay"],
            epochs=params["epochs"],
            batch_size=params["batch_size"],
            patience=params["patience"],
            progress=None,
            use_early_stopping=False,
        )
        saved_model = prod_model
        # feature_importance already computed on eval model (step 7) — no data leakage

    elif algo == "TabularResNet":
        from ufc_core.models.pytorch_arch import TabularResNet

        _seed_pytorch()
        prod_model = TabularResNet(
            len(feat_cols), params["hidden_dim"], params["n_blocks"], params["dropout"]
        )
        prod_model = _train_pytorch_model(
            prod_model,
            X_full_sc,
            y_full,
            X_val=None,
            y_val=None,
            lr=params["lr"],
            weight_decay=params["weight_decay"],
            epochs=params["epochs"],
            batch_size=params["batch_size"],
            patience=params["patience"],
            progress=None,
            use_early_stopping=False,
        )
        saved_model = prod_model
        # feature_importance already computed on eval model (step 7) — no data leakage

    logger.info(
        "%s: modelo productivo re-entrenado con TODOS los datos (%d filas, %d sin augmentar)",
        model_short,
        len(X_full),
        len(df),
    )
    metrics["n_production"] = len(df)  # unique fights used (before augment)

    if progress:
        progress.pct = 92
        progress.message = f"Accuracy={acc:.4f} | Guardando modelo productivo..."

    # 10. Save production model
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_dir = MODELS_DIR / "retrained"
    new_dir.mkdir(exist_ok=True)

    if is_pytorch:
        import torch
        save_path = new_dir / f"{model_short}_{timestamp}.pt"
        torch.save(saved_model.state_dict(), save_path)
    else:
        save_path = new_dir / f"{model_short}_{timestamp}.joblib"
        joblib.dump(saved_model, save_path)

    # Save scaler if used
    scaler_path = None
    if scaler is not None:
        scaler_path = new_dir / f"{model_short}_scaler_{timestamp}.joblib"
        joblib.dump(scaler, scaler_path)

    # Save imputer
    imputer_path = new_dir / f"imputer_{timestamp}.joblib"
    imputer_prod.save(imputer_path)

    # 11. REAL-WORLD EVALUATION (no calibrator — raw probabilities)
    if realworld_df is not None and len(realworld_df) > 0:
        try:
            rw_metrics = evaluate_realworld(
                model=saved_model,
                scaler=scaler,
                imputer=imputer_prod,
                feat_cols=feat_cols,
                realworld_df=realworld_df,
                is_pytorch=is_pytorch,
                min_fights=min_fights,
            )
            metrics.update(rw_metrics)
            if rw_metrics["realworld_accuracy"] is not None:
                logger.info(
                    "%s: realworld accuracy = %.4f, %d/%d",
                    model_short, rw_metrics["realworld_accuracy"],
                    rw_metrics["realworld_correct"], rw_metrics["realworld_total"],
                )
        except Exception as e:
            logger.warning("%s: realworld eval failed: %s", model_short, e)
            metrics["realworld_accuracy"] = None
            metrics["realworld_correct"] = 0
            metrics["realworld_total"] = 0

    if progress:
        rw_info = ""
        if metrics.get("realworld_accuracy") is not None:
            rw_info = f" | RW={metrics['realworld_accuracy']:.4f} ({metrics['realworld_correct']}/{metrics['realworld_total']})"
        progress.step = "done"
        progress.pct = 100
        progress.message = f"✅ {model_short} entrenado — Accuracy={acc:.4f}{rw_info}"
        progress.metrics = metrics

    result = {
        "model_short": model_short,
        "full_name": cat["full_name"],
        "algo": cat["algo"],
        "features": feat_type,
        "params": {
            k: str(v) if not isinstance(v, (int, float, bool, str)) else v
            for k, v in params.items()
        },
        "test_cutoff": TEST_CUTOFF_DT.strftime("%Y-%m-%d"),
        "realworld_cutoff": REALWORLD_CUTOFF_DT.strftime("%Y-%m-%d"),
        "dataset": dataset_key,
        "since_year": since_year,
        "augmented": do_augment,
        "feature_set": feature_set,
        "min_fights": min_fights,
        "use_pit": use_pit,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "saved_path": str(save_path),
        "scaler_path": str(scaler_path) if scaler_path else None,
        "imputer_path": str(imputer_path),
        "feat_cols": feat_cols,
        "trained_at": datetime.now().isoformat(),
    }

    # Save metadata JSON
    meta_path = new_dir / f"{model_short}_{timestamp}_meta.json"
    with open(meta_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    return result


# ──────────────────────────────────────────────────────────────────────
# Model registry JSON (persist metadata for all trained versions)
# ──────────────────────────────────────────────────────────────────────

REGISTRY_JSON = MODELS_DIR / "model_registry.json"


def load_model_registry() -> dict:
    """Load the model registry from disk."""
    if REGISTRY_JSON.exists():
        with open(REGISTRY_JSON) as f:
            return json.load(f)
    return {"models": {}, "disabled_models": []}


def _sanitize_nan(obj):
    """Recursively replace NaN/Inf with None for JSON safety."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


def save_model_registry(registry: dict) -> None:
    """Save the model registry to disk atomically.

    Writes to a sibling temp file and renames into place. Prevents partial-read
    JSONDecodeError when other processes (API endpoints, dashboards) read the
    registry concurrently with a write.
    """
    tmp_path = REGISTRY_JSON.with_suffix(REGISTRY_JSON.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(_sanitize_nan(registry), f, indent=2, default=str)
    os.replace(tmp_path, REGISTRY_JSON)


# ──────────────────────────────────────────────────────────────────────
# Model combinations (named presets of active models + active versions)
# ──────────────────────────────────────────────────────────────────────

COMBINATIONS_JSON = MODELS_DIR / "model_combinations.json"


def load_combinations() -> dict:
    """Load saved model combinations from disk."""
    if COMBINATIONS_JSON.exists():
        try:
            with open(COMBINATIONS_JSON) as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("combinations"), list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"combinations": []}


def save_combinations(data: dict) -> None:
    """Persist model combinations to disk atomically (write-tmp + rename)."""
    tmp_path = COMBINATIONS_JSON.with_suffix(COMBINATIONS_JSON.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(_sanitize_nan(data), f, indent=2, default=str)
    os.replace(tmp_path, COMBINATIONS_JSON)


def snapshot_current_state() -> dict[str, dict]:
    """Capture the current {short: {active, active_version}} state.

    Only includes shorts present in MODEL_CATALOGUE so the combination stays
    aligned with the real-world set of models. Ens3 (virtual ensemble) is
    excluded because it has no active_version concept.
    """
    reg = load_model_registry()
    disabled = set(reg.get("disabled_models", []))
    models_entry = reg.get("models", {})
    snapshot: dict[str, dict] = {}
    for short in MODEL_CATALOGUE:
        if short == "Ens3":
            continue
        entry = models_entry.get(short, {})
        snapshot[short] = {
            "active": short not in disabled,
            "active_version": entry.get("active_version"),
        }
    return snapshot


def apply_combo_state(models: dict[str, dict]) -> dict:
    """Atomically apply a combination's state to the registry.

    Sets `disabled_models` and each `active_version` in a single load/save
    cycle so the registry never lingers in a partial state. Unknown shorts
    are skipped. Versions that no longer exist get clamped to None.

    Returns a summary dict with:
      - applied: shorts whose state was written
      - skipped_unknown: shorts in combo not in MODEL_CATALOGUE
      - clamped_versions: shorts whose desired version no longer exists
      - changed_versions: shorts whose active_version actually changed
        (caller must hot-reload these in memory)
    """
    reg = load_model_registry()
    registry_models = reg.get("models", {})

    applied: list[str] = []
    skipped_unknown: list[str] = []
    clamped_versions: list[str] = []
    changed_versions: list[str] = []

    # Rebuild disabled set from scratch using the combo's active flags;
    # shorts not in the combo keep their current disabled status.
    current_disabled = set(reg.get("disabled_models", []))
    new_disabled = set(current_disabled)

    for short, entry in models.items():
        if short not in MODEL_CATALOGUE:
            skipped_unknown.append(short)
            continue

        desired_active = bool(entry.get("active", True))
        if desired_active:
            new_disabled.discard(short)
        else:
            new_disabled.add(short)

        desired_version = entry.get("active_version")
        reg_entry = registry_models.setdefault(
            short, {"versions": [], "active_version": None}
        )
        n_versions = len(reg_entry.get("versions", []))
        previous_version = reg_entry.get("active_version")

        final_version: int | None
        if desired_version is None:
            final_version = None
        elif isinstance(desired_version, int) and 0 <= desired_version < n_versions:
            final_version = desired_version
        else:
            final_version = None
            clamped_versions.append(short)

        if final_version != previous_version:
            changed_versions.append(short)

        reg_entry["active_version"] = final_version
        applied.append(short)

    reg["disabled_models"] = sorted(new_disabled)
    save_model_registry(reg)
    return {
        "applied": applied,
        "skipped_unknown": skipped_unknown,
        "clamped_versions": clamped_versions,
        "changed_versions": changed_versions,
    }


def ensure_pro_versions() -> None:
    """Seed the registry with the original PRO models if not already present.

    For each model in MODEL_CATALOGUE, if the registry has no versions yet,
    create a 'version 0' entry pointing to the original PRO file so it
    appears in the version list.
    """
    from ufc_core.config import MODEL_FILES, PYTORCH_MODELS

    reg = load_model_registry()
    changed = False

    for short, cat in MODEL_CATALOGUE.items():
        if short == "Ens3":
            continue

        model_entry = reg.get("models", {}).get(short, {})
        versions = model_entry.get("versions", [])

        # Check if there's already a version flagged as original_pro
        has_pro = any(v.get("origin") == "original_pro" for v in versions)
        if has_pro:
            continue

        # Find the PRO file path
        full_name = cat["full_name"]
        pro_path = MODEL_FILES.get(full_name) or PYTORCH_MODELS.get(full_name)
        if pro_path is None or not pro_path.exists():
            continue

        pro_version = {
            "trained_at": "2024-01-01T00:00:00",
            "metrics": {},
            "dataset": "since2010",
            "test_cutoff": 2024,
            "augmented": cat.get("augment", False),
            "feature_set": "legacy",
            "feat_type": cat["features"],
            "min_fights": 0,
            "use_pit": False,
            "saved_path": str(pro_path),
            "scaler_path": None,
            "feature_importance": None,
            "params": {k: v for k, v in cat["params"].items() if k not in ("random_state", "n_jobs", "verbose")},
            "origin": "original_pro",
            "was_production": True,
        }

        if short not in reg["models"]:
            reg["models"][short] = {"versions": [], "active_version": None}

        # Insert as first version (index 0)
        reg["models"][short]["versions"].insert(0, pro_version)

        # Adjust active_version: shift existing index by +1
        active = reg["models"][short].get("active_version")
        if active is not None:
            reg["models"][short]["active_version"] = active + 1
        else:
            # If no active version, set the PRO as active
            reg["models"][short]["active_version"] = 0
            pro_version["was_production"] = False  # it IS production, not ex

        changed = True
        logger.info("Registered original PRO model as version 0 for %s", short)

    if changed:
        save_model_registry(reg)


def register_training_result(result: dict) -> None:
    """Register a training result in the persistent registry."""
    reg = load_model_registry()
    short = result["model_short"]
    if short not in reg["models"]:
        reg["models"][short] = {"versions": [], "active_version": None}

    version_entry = {
        "trained_at": result["trained_at"],
        "metrics": result["metrics"],
        "dataset": result["dataset"],
        "test_cutoff": result["test_cutoff"],
        "augmented": result["augmented"],
        "feature_set": result.get("feature_set", "legacy"),
        "feat_type": result.get("features", "35f"),
        "min_fights": result.get("min_fights", 0),
        "use_pit": result.get("use_pit", False),
        "saved_path": result["saved_path"],
        "scaler_path": result.get("scaler_path"),
        "imputer_path": result.get("imputer_path"),
        "calibrator_path": result.get("calibrator_path"),
        "cal_data_path": result.get("cal_data_path"),
        "feature_importance": result.get("feature_importance"),
        "params": result.get("params"),
        "feat_cols": result.get("feat_cols"),
    }
    if result.get("origin"):
        version_entry["origin"] = result["origin"]
    reg["models"][short]["versions"].append(version_entry)
    save_model_registry(reg)


def accept_new_version(model_short: str, version_idx: int) -> bool:
    """Accept a new model version as the active one (would require model reload)."""
    reg = load_model_registry()
    if model_short not in reg["models"]:
        return False
    versions = reg["models"][model_short]["versions"]
    if version_idx < 0 or version_idx >= len(versions):
        return False

    # Mark previous active version as was_production
    prev_active = reg["models"][model_short].get("active_version")
    if prev_active is not None and prev_active != version_idx:
        if 0 <= prev_active < len(versions):
            versions[prev_active]["was_production"] = True

    # Mark new active version as production (remove was_production if present)
    versions[version_idx].pop("was_production", None)

    reg["models"][model_short]["active_version"] = version_idx
    save_model_registry(reg)
    return True


def mark_version(
    model_short: str,
    version_idx: int,
    starred: bool | None = None,
    note: str | None = None,
) -> bool:
    """Set starred flag and/or note on a version.

    `starred=None` leaves the flag untouched; pass True/False to update.
    `note=None` leaves the note untouched; pass "" to clear it.
    """
    reg = load_model_registry()
    if model_short not in reg["models"]:
        return False
    versions = reg["models"][model_short]["versions"]
    if version_idx < 0 or version_idx >= len(versions):
        return False

    v = versions[version_idx]
    if starred is not None:
        v["starred"] = bool(starred)
    if note is not None:
        note_clean = note.strip()
        if note_clean:
            v["note"] = note_clean[:200]  # cap length
        else:
            v.pop("note", None)

    save_model_registry(reg)
    return True


def delete_version(model_short: str, version_idx: int) -> bool:
    """Delete a retrained version: remove from registry and delete files from disk."""
    reg = load_model_registry()
    if model_short not in reg["models"]:
        return False
    versions = reg["models"][model_short]["versions"]
    if version_idx < 0 or version_idx >= len(versions):
        return False

    version = versions[version_idx]

    # Block deletion of the currently active version only
    active = reg["models"][model_short].get("active_version")
    if active == version_idx:
        return False

    # Delete model file from disk
    saved_path = version.get("saved_path")
    if saved_path:
        p = Path(saved_path)
        if p.exists():
            p.unlink()
            logger.info(f"Deleted model file: {p}")
        # Also delete the *_meta.json companion
        meta = p.with_name(p.stem + "_meta.json")
        if meta.exists():
            meta.unlink()
            logger.info(f"Deleted meta file: {meta}")

    # Delete scaler file if any
    scaler_path = version.get("scaler_path")
    if scaler_path:
        sp = Path(scaler_path)
        if sp.exists():
            sp.unlink()
            logger.info(f"Deleted scaler file: {sp}")

    # Delete calibrator file if any
    calibrator_path = version.get("calibrator_path")
    if calibrator_path:
        cp = Path(calibrator_path)
        if cp.exists():
            cp.unlink()
            logger.info(f"Deleted calibrator file: {cp}")

    # Delete calibration data file if any
    cal_data_path = version.get("cal_data_path")
    if cal_data_path:
        cdp = Path(cal_data_path)
        if cdp.exists():
            cdp.unlink()
            logger.info(f"Deleted cal_data file: {cdp}")

    # Remove from registry
    versions.pop(version_idx)

    # Adjust active_version index
    active = reg["models"][model_short].get("active_version")
    if active is not None:
        if active == version_idx:
            reg["models"][model_short]["active_version"] = None
        elif active > version_idx:
            reg["models"][model_short]["active_version"] = active - 1

    # Clean up empty model entry
    if len(versions) == 0:
        del reg["models"][model_short]

    save_model_registry(reg)

    # Propagate the shift to every saved combination so their index references
    # stay in sync with the registry. Combos that pointed at the deleted index
    # are marked unavailable by setting active_version=None.
    _shift_combinations_after_delete(model_short, [version_idx])

    return True


def delete_versions_batch(model_short: str, version_indices: list[int]) -> dict:
    """Delete multiple versions at once, handling index shifts atomically."""
    reg = load_model_registry()
    if model_short not in reg["models"]:
        return {"deleted": [], "errors": ["Model not found"]}

    versions = reg["models"][model_short]["versions"]
    active = reg["models"][model_short].get("active_version")

    deleted = []
    errors = []

    for idx in version_indices:
        if idx < 0 or idx >= len(versions):
            errors.append(f"Index {idx} fuera de rango")
        elif active == idx:
            errors.append(f"Index {idx} es la version activa")
        else:
            deleted.append(idx)

    if not deleted:
        return {"deleted": [], "errors": errors}

    # Delete files from disk before modifying the list
    for idx in deleted:
        version = versions[idx]
        saved_path = version.get("saved_path")
        if saved_path:
            p = Path(saved_path)
            if p.exists():
                p.unlink()
                logger.info(f"Deleted model file: {p}")
            meta = p.with_name(p.stem + "_meta.json")
            if meta.exists():
                meta.unlink()
                logger.info(f"Deleted meta file: {meta}")
        scaler_path = version.get("scaler_path")
        if scaler_path:
            sp = Path(scaler_path)
            if sp.exists():
                sp.unlink()
                logger.info(f"Deleted scaler file: {sp}")
        calibrator_path = version.get("calibrator_path")
        if calibrator_path:
            cp = Path(calibrator_path)
            if cp.exists():
                cp.unlink()
                logger.info(f"Deleted calibrator file: {cp}")
        cal_data_path = version.get("cal_data_path")
        if cal_data_path:
            cdp = Path(cal_data_path)
            if cdp.exists():
                cdp.unlink()
                logger.info(f"Deleted cal_data file: {cdp}")

    # Pop in descending order to preserve indices
    for idx in sorted(deleted, reverse=True):
        versions.pop(idx)

    # Adjust active_version once
    if active is not None:
        if active in deleted:
            reg["models"][model_short]["active_version"] = None
        else:
            shift = sum(1 for i in deleted if i < active)
            reg["models"][model_short]["active_version"] = active - shift

    if len(versions) == 0:
        del reg["models"][model_short]

    save_model_registry(reg)

    # Propagate the shift to every saved combination.
    _shift_combinations_after_delete(model_short, deleted)

    return {"deleted": deleted, "errors": errors}


def _shift_combinations_after_delete(model_short: str, deleted_indices: list[int]) -> None:
    """Update model_combinations.json so saved combos stay consistent after one
    or more versions of ``model_short`` were deleted.

    - active_version == a deleted idx → set to None (combo's reference is gone).
    - active_version > max(deleted)   → shifted by how many deleted indices sit below it.
    """
    if not deleted_indices:
        return
    combos = load_combinations()
    if not combos:
        return
    deleted_sorted = sorted(set(deleted_indices))
    changed = False
    for combo_entry in combos.values():
        if not isinstance(combo_entry, dict):
            continue
        models = combo_entry.get("models") or {}
        entry = models.get(model_short)
        if not entry:
            continue
        current = entry.get("active_version")
        if current is None:
            continue
        if current in deleted_sorted:
            entry["active_version"] = None
            changed = True
        else:
            shift = sum(1 for i in deleted_sorted if i < current)
            if shift:
                entry["active_version"] = current - shift
                changed = True
    if changed:
        save_combinations(combos)
        logger.info(
            "Shifted combinations after deleting %s indices %s",
            model_short, deleted_sorted,
        )


def toggle_model_active(model_short: str, active: bool) -> bool:
    """Enable or disable a model from the prediction ensemble."""
    reg = load_model_registry()
    disabled = set(reg.get("disabled_models", []))
    if active:
        disabled.discard(model_short)
    else:
        disabled.add(model_short)
    reg["disabled_models"] = list(disabled)
    save_model_registry(reg)
    return True


# ──────────────────────────────────────────────────────────────────────
# HP Search helpers (used by HpSearchService)
# ──────────────────────────────────────────────────────────────────────

HP_SEARCH_SPACES: dict[str, list[dict[str, Any]]] = {
    "RandomForest": [
        {"name": "n_estimators", "type": "int", "low": 200, "high": 700, "step": 100},
        {"name": "max_depth", "type": "categorical", "choices": [4, 6, 8, 10, 12, 16]},
        {"name": "min_samples_split", "type": "int", "low": 3, "high": 25},
        {"name": "min_samples_leaf", "type": "int", "low": 5, "high": 40},
        {"name": "max_features", "type": "categorical", "choices": ["sqrt", "log2", 0.3, 0.5]},
        {"name": "max_samples", "type": "float", "low": 0.6, "high": 0.95, "step": 0.05},
        {"name": "criterion", "type": "categorical", "choices": ["gini", "entropy"]},
        {"name": "class_weight", "type": "categorical", "choices": [None, "balanced", "balanced_subsample"]},
    ],
    "LGBM": [
        {"name": "n_estimators", "type": "int", "low": 100, "high": 500, "step": 50},
        {"name": "max_depth", "type": "int", "low": 3, "high": 7},
        {"name": "learning_rate", "type": "float", "low": 0.01, "high": 0.2, "log": True},
        {"name": "num_leaves", "type": "int", "low": 15, "high": 63, "step": 4},
        {"name": "subsample", "type": "float", "low": 0.6, "high": 0.95},
        {"name": "colsample_bytree", "type": "float", "low": 0.5, "high": 1.0},
        {"name": "reg_alpha", "type": "float", "low": 0.001, "high": 5.0, "log": True},
        {"name": "reg_lambda", "type": "float", "low": 0.5, "high": 15.0, "log": True},
        {"name": "min_child_samples", "type": "int", "low": 15, "high": 60},
    ],
    "MLP": [
        {"name": "hidden_layer_sizes", "type": "categorical", "choices": [[64, 32], [128, 64], [128, 64, 32], [256, 128], [256, 128, 64], [256, 128, 64, 32]]},
        {"name": "alpha", "type": "float", "low": 0.0005, "high": 0.5, "log": True},
        {"name": "learning_rate_init", "type": "float", "low": 3e-4, "high": 5e-3, "log": True},
        {"name": "max_iter", "type": "int", "low": 300, "high": 800, "step": 100},
        # step=0.02 so the catalogue default 0.10 is reachable.
        {"name": "validation_fraction", "type": "float", "low": 0.08, "high": 0.20, "step": 0.02},
        {"name": "n_iter_no_change", "type": "int", "low": 15, "high": 35, "step": 5},
    ],
    "SVM": [
        {"name": "C", "type": "float", "low": 0.01, "high": 20.0, "log": True},
        {"name": "gamma", "type": "categorical", "choices": ["scale", 0.001, 0.005, 0.01, 0.05, 0.1]},
        {"name": "kernel", "type": "categorical", "choices": ["rbf", "poly"]},
        {"name": "class_weight", "type": "categorical", "choices": [None, "balanced"]},
    ],
    "DeepMLP": [
        {"name": "hidden_dims", "type": "categorical", "choices": [[64, 32], [128, 64], [128, 64, 32], [128, 128, 64, 64], [256, 128, 64]]},
        {"name": "dropout", "type": "float", "low": 0.1, "high": 0.4, "step": 0.05},
        {"name": "lr", "type": "float", "low": 1e-4, "high": 5e-3, "log": True},
        # low bumped to 1e-5 so the catalogue default 1e-4 is not on the edge.
        {"name": "weight_decay", "type": "float", "low": 1e-5, "high": 5e-2, "log": True},
        # 256 added so the catalogue default batch_size is reachable.
        {"name": "batch_size", "type": "categorical", "choices": [32, 64, 128, 256]},
        {"name": "epochs", "type": "int", "low": 150, "high": 400, "step": 50},
        {"name": "patience", "type": "int", "low": 15, "high": 40, "step": 5},
    ],
    "TabularResNet": [
        {"name": "hidden_dim", "type": "categorical", "choices": [64, 128, 256]},
        {"name": "n_blocks", "type": "int", "low": 2, "high": 6},
        {"name": "dropout", "type": "float", "low": 0.1, "high": 0.4, "step": 0.05},
        {"name": "lr", "type": "float", "low": 1e-4, "high": 5e-3, "log": True},
        {"name": "weight_decay", "type": "float", "low": 1e-5, "high": 5e-2, "log": True},
        {"name": "batch_size", "type": "categorical", "choices": [32, 64, 128, 256]},
        {"name": "epochs", "type": "int", "low": 150, "high": 400, "step": 50},
        {"name": "patience", "type": "int", "low": 15, "high": 40, "step": 5},
    ],
    "XGBoost": [
        {"name": "n_estimators", "type": "int", "low": 100, "high": 500, "step": 50},
        {"name": "max_depth", "type": "int", "low": 3, "high": 7},
        {"name": "learning_rate", "type": "float", "low": 0.01, "high": 0.2, "log": True},
        {"name": "subsample", "type": "float", "low": 0.6, "high": 0.95},
        {"name": "colsample_bytree", "type": "float", "low": 0.5, "high": 1.0},
        {"name": "reg_alpha", "type": "float", "low": 0.001, "high": 5.0, "log": True},
        {"name": "reg_lambda", "type": "float", "low": 0.5, "high": 15.0, "log": True},
        {"name": "min_child_weight", "type": "int", "low": 2, "high": 15},
        {"name": "gamma", "type": "float", "low": 0.0, "high": 3.0},
    ],
    "CatBoost": [
        {"name": "iterations", "type": "int", "low": 100, "high": 500, "step": 50},
        {"name": "depth", "type": "int", "low": 3, "high": 7},
        {"name": "learning_rate", "type": "float", "low": 0.01, "high": 0.2, "log": True},
        {"name": "subsample", "type": "float", "low": 0.6, "high": 0.95},
        {"name": "l2_leaf_reg", "type": "float", "low": 0.5, "high": 20.0, "log": True},
        {"name": "min_data_in_leaf", "type": "int", "low": 15, "high": 60},
        {"name": "random_strength", "type": "float", "low": 0.1, "high": 10.0, "log": True},
        {"name": "bagging_temperature", "type": "float", "low": 0.0, "high": 3.0},
    ],
    "LogisticRegression": [
        {"name": "C", "type": "float", "low": 0.005, "high": 20.0, "log": True},
        {"name": "l1_ratio", "type": "float", "low": 0.0, "high": 1.0, "step": 0.1},
        {"name": "class_weight", "type": "categorical", "choices": [None, "balanced"]},
    ],
    "MLPShallow": [
        {"name": "hidden_layer_sizes", "type": "categorical", "choices": [[32, 16], [64, 32], [128, 64], [64, 32, 16], [128, 64, 32]]},
        {"name": "alpha", "type": "float", "low": 0.0005, "high": 0.5, "log": True},
        {"name": "learning_rate_init", "type": "float", "low": 3e-4, "high": 5e-3, "log": True},
        {"name": "max_iter", "type": "int", "low": 300, "high": 800, "step": 100},
        # step=0.02 so the catalogue default 0.10 is reachable.
        {"name": "validation_fraction", "type": "float", "low": 0.08, "high": 0.20, "step": 0.02},
        {"name": "n_iter_no_change", "type": "int", "low": 15, "high": 35, "step": 5},
    ],
}


def get_default_search_space(model_short: str) -> list[dict[str, Any]]:
    """Return default HP search space for a model based on its algo."""
    if model_short not in MODEL_CATALOGUE:
        return []
    algo = MODEL_CATALOGUE[model_short]["algo"]
    return HP_SEARCH_SPACES.get(algo, [])


def build_hp_model(model_short: str, params: dict[str, Any]):
    """Instantiate an untrained model with given hyperparameters.

    Returns a sklearn estimator or PyTorch nn.Module (untrained).
    """
    if model_short not in MODEL_CATALOGUE:
        raise ValueError(f"Unknown model: {model_short}")

    cat = MODEL_CATALOGUE[model_short]
    algo = cat["algo"]
    # Merge catalogue defaults with trial params (trial overrides)
    merged = {**cat["params"], **params}

    if algo == "RandomForest":
        if not merged.get("bootstrap", True):
            merged.pop("max_samples", None)
        merged.setdefault("random_state", 42)
        merged.setdefault("n_jobs", -1)
        return RandomForestClassifier(**merged)

    if algo == "LGBM":
        if LGBMClassifier is None:
            raise ImportError("lightgbm not installed")
        merged.setdefault("random_state", 42)
        merged.setdefault("verbose", -1)
        return LGBMClassifier(**merged)

    if algo == "MLP":
        hls = merged.get("hidden_layer_sizes")
        if isinstance(hls, list):
            merged["hidden_layer_sizes"] = tuple(hls)
        merged.setdefault("solver", "adam")
        merged.setdefault("max_iter", 500)
        merged.setdefault("early_stopping", True)
        merged.setdefault("validation_fraction", 0.1)
        merged.setdefault("n_iter_no_change", 20)
        merged.setdefault("random_state", 42)
        return MLPClassifier(**merged)

    if algo == "SVM":
        merged.setdefault("probability", True)
        merged.setdefault("random_state", 42)
        return SVC(**merged)

    if algo == "DeepMLP":
        from ufc_core.models.pytorch_arch import DeepMLP

        hidden_dims = merged.get("hidden_dims", [128, 64])
        if isinstance(hidden_dims, tuple):
            hidden_dims = list(hidden_dims)
        dropout = merged.get("dropout", 0.25)
        return DeepMLP(merged["_n_features"], hidden_dims, dropout)

    if algo == "TabularResNet":
        from ufc_core.models.pytorch_arch import TabularResNet

        return TabularResNet(
            merged["_n_features"],
            merged.get("hidden_dim", 128),
            merged.get("n_blocks", 5),
            merged.get("dropout", 0.25),
        )

    if algo == "XGBoost":
        if XGBClassifier is None:
            raise ImportError("xgboost not installed")
        merged.setdefault("random_state", 42)
        merged.setdefault("eval_metric", "logloss")
        merged.setdefault("verbosity", 0)
        return XGBClassifier(**merged)

    if algo == "CatBoost":
        if CatBoostClassifier is None:
            raise ImportError("catboost not installed")
        merged.setdefault("random_seed", 42)
        merged.setdefault("verbose", 0)
        return CatBoostClassifier(**merged)

    if algo == "LogisticRegression":
        merged.setdefault("penalty", "elasticnet")
        merged.setdefault("solver", "saga")
        merged.setdefault("random_state", 42)
        merged.setdefault("max_iter", 1000)
        return LogisticRegression(**merged)

    if algo == "MLPShallow":
        hls = merged.get("hidden_layer_sizes")
        if isinstance(hls, list):
            merged["hidden_layer_sizes"] = tuple(hls)
        merged.setdefault("solver", "adam")
        merged.setdefault("max_iter", 500)
        merged.setdefault("early_stopping", True)
        merged.setdefault("validation_fraction", 0.1)
        merged.setdefault("n_iter_no_change", 20)
        merged.setdefault("random_state", 42)
        return MLPClassifier(**merged)

    raise ValueError(f"Unknown algo: {algo}")


def get_disabled_models() -> list[str]:
    """Get the list of disabled model short names."""
    reg = load_model_registry()
    return reg.get("disabled_models", [])
