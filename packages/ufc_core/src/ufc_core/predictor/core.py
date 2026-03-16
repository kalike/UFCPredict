"""
UFC Predictor — Prediction engine with TTA (Test-Time Augmentation).

Runs all 11 PRO models with symmetric TTA on a feature DataFrame
and returns per-model and ensemble predictions.
"""

import numpy as np
import pandas as pd

from ufc_core.config import TEMPERATURE
from ufc_core.models.registry import ModelRegistry
from ufc_core.trainer.core import get_disabled_models


def _temperature_scale(proba: np.ndarray, temperature: float | None = None) -> np.ndarray:
    t = TEMPERATURE if temperature is None else temperature
    if t == 1.0:
        return proba

    proba = np.clip(proba, 1e-10, 1 - 1e-10)
    logits = np.log(proba / (1 - proba))
    return 1 / (1 + np.exp(-logits / t))


def _prepare_inputs(df: pd.DataFrame, registry: ModelRegistry) -> dict:
    """Prepare all input matrices (original + TTA flipped) for every model."""
    from ufc_core.transforms import FeatureTransformer

    transformer = FeatureTransformer(enabled=True)

    X_35 = df[registry.feats_35].values.astype(np.float32)
    X_52 = df[registry.feats_52].values.astype(np.float32)

    X_35 = transformer.transform_array(X_35, registry.feats_35)
    X_52 = transformer.transform_array(X_52, registry.feats_52)

    X_35_scaled = registry.nn_scaler.transform(X_35)
    X_35_svm_std = registry.svm_std_scaler.transform(X_35)
    X_35_svm_rob = registry.svm_rob_scaler.transform(X_35)

    # TTA: negated features for 35f, column-swapped for 52f
    X_35_neg = -X_35
    X_35_flip = -X_35  # flip for RF/LGBM (no scaler)
    X_35_flip_scaled = registry.nn_scaler.transform(X_35_neg)  # flip for MLP/NNs
    X_35_svm_std_flip = registry.svm_std_scaler.transform(X_35_neg)
    X_35_svm_rob_flip = registry.svm_rob_scaler.transform(X_35_neg)

    # 52f flip: swap f1_* ↔ f2_* columns (26 + 26)
    X_52_flip = np.hstack([X_52[:, 26:], X_52[:, :26]])

    return {
        "X_35": X_35,
        "X_35_neg": X_35_neg,
        "X_52": X_52,
        "X_35_scaled": X_35_scaled,
        "X_35_svm_std": X_35_svm_std,
        "X_35_svm_rob": X_35_svm_rob,
        "X_35_flip": X_35_flip,
        "X_52_flip": X_52_flip,
        "X_35_flip_scaled": X_35_flip_scaled,
        "X_35_svm_std_flip": X_35_svm_std_flip,
        "X_35_svm_rob_flip": X_35_svm_rob_flip,
    }


# Mapping: model name → (X_key, X_flip_key)
_SKLEARN_INPUT_MAP = {
    "RF (35f) PRO": ("X_35", "X_35_flip"),
    "RF D+Aug (35f) PRO": ("X_35", "X_35_flip"),
    "LGBM D+Aug (35f) PRO": ("X_35", "X_35_flip"),
    "RF D+Aug (52f) PRO": ("X_52", "X_52_flip"),
    "MLP sklearn (35f) PRO": ("X_35_scaled", "X_35_flip_scaled"),
    "SVM Base (35f) PRO": ("X_35_svm_std", "X_35_svm_std_flip"),
    "SVM GSearch (35f) PRO": ("X_35_svm_std", "X_35_svm_std_flip"),
    "SVM Robust (35f) PRO": ("X_35_svm_rob", "X_35_svm_rob_flip"),
    "XGB D+Aug (35f) PRO": ("X_35", "X_35_flip"),
    "XGB D+Aug (52f) PRO": ("X_52", "X_52_flip"),
    "CB D+Aug (35f) PRO": ("X_35", "X_35_flip"),
    "CB D+Aug (52f) PRO": ("X_52", "X_52_flip"),
    "LR ElasticNet (35f) PRO": ("X_35_svm_std", "X_35_svm_std_flip"),
    "LR ElasticNet (52f) PRO": ("X_52", "X_52_flip"),
    "MLP Shallow (35f) PRO": ("X_35_scaled", "X_35_flip_scaled"),
    "MLP Shallow (52f) PRO": ("X_52", "X_52_flip"),
}


def _get_model_inputs(
    model_name: str, df: pd.DataFrame, inputs: dict, registry: ModelRegistry,
) -> tuple[np.ndarray, np.ndarray]:
    """Get X and X_flip for a model, using per-model feat_cols and scaler if available."""
    from ufc_core.transforms import FeatureTransformer

    feat_cols = registry.model_feat_cols.get(model_name)
    per_scaler = registry.model_scalers.get(model_name)

    if feat_cols is not None:
        # Custom feature columns: extract from DataFrame
        transformer = FeatureTransformer(enabled=True)
        for c in feat_cols:
            if c not in df.columns:
                df[c] = 0

        # Apply per-model imputer (fills NaN with training medians)
        per_imputer = registry.model_imputers.get(model_name)
        if per_imputer is not None:
            df = per_imputer.transform(df)

        X = df[feat_cols].values.astype(np.float32)
        # Fallback: fill any remaining NaN with 0
        np.nan_to_num(X, copy=False, nan=0.0)
        X = transformer.transform_array(X, feat_cols)

        # TTA flip: swap f1/f2 halves for 52f, negate for 35f (deltas)
        is_52f = any(c.startswith("f1_") for c in feat_cols)
        if is_52f:
            n_half = sum(1 for c in feat_cols if c.startswith("f1_"))
            X_flip = np.hstack([X[:, n_half:], X[:, :n_half]])
        else:
            X_flip = -X

        if per_scaler is not None:
            return per_scaler.transform(X), per_scaler.transform(X_flip)
        return X, X_flip

    # No custom feat_cols: use pre-computed inputs
    if per_scaler is not None:
        X_raw = inputs["X_35"] if "52f" not in model_name else inputs["X_52"]
        X_neg = inputs["X_35_neg"] if "52f" not in model_name else inputs["X_52_flip"]
        return per_scaler.transform(X_raw), per_scaler.transform(X_neg)

    x_key, xf_key = _SKLEARN_INPUT_MAP.get(model_name, ("X_35", "X_35_flip"))
    return inputs[x_key], inputs[xf_key]


def run_predictions(
    df: pd.DataFrame,
    registry: ModelRegistry,
    temperature: float | None = None,
    disabled_override: set[str] | None = None,
) -> dict[str, dict]:
    """Run all 11 models with TTA on the feature DataFrame.

    Returns dict of model_name → {y_proba, y_pred} for each model,
    including the Ensemble 3 NN in position 11.

    Handles imputation internally:
    - Global imputer (or fillna(0) fallback) for shared/PRO model inputs
    - Per-model imputers for retrained models with custom feat_cols

    `disabled_override` lets callers (like the combo-search cache warmup)
    bypass the registry's disabled_models list so every model present in
    `registry` gets predicted regardless of its current active/disabled flag.
    """
    # Keep raw df for per-model imputers (before global imputation)
    df_raw = df

    # Apply global imputation for shared/PRO model inputs
    if registry.imputer is not None:
        df_imputed = registry.imputer.transform(df)
    else:
        df_imputed = df.copy()
        for col in df_imputed.columns:
            if col.startswith(("delta_", "f1_", "f2_")):
                df_imputed[col] = df_imputed[col].fillna(0)

    inputs = _prepare_inputs(df_imputed, registry)
    results: dict[str, dict] = {}
    disabled = disabled_override if disabled_override is not None else set(get_disabled_models())

    # --- sklearn / joblib models ---
    for model_name, model in registry.sklearn_models.items():
        short = registry._get_short_name(model_name)
        if short in disabled:
            continue

        X, X_flip = _get_model_inputs(model_name, df_raw, inputs, registry)

        p_orig = model.predict_proba(X)[:, 1]
        p_flip = model.predict_proba(X_flip)[:, 1]
        y_proba = (p_orig + (1 - p_flip)) / 2  # TTA
        y_proba = _temperature_scale(y_proba, temperature)
        y_pred = (y_proba >= 0.5).astype(int)

        results[model_name] = {"y_proba": y_proba, "y_pred": y_pred}

    # --- DeepMLP (PyTorch) ---
    import torch
    deep_model = registry.pytorch_models.get("DeepMLP (35f) PRO")
    if deep_model is not None and "Deep" not in disabled:
        X, X_flip = _get_model_inputs("DeepMLP (35f) PRO", df_raw, inputs, registry)
        X_t = torch.FloatTensor(X)
        X_t_flip = torch.FloatTensor(X_flip)
        with torch.no_grad():
            proba_orig = torch.sigmoid(deep_model(X_t).squeeze(-1)).numpy()
            proba_flip = torch.sigmoid(deep_model(X_t_flip).squeeze(-1)).numpy()
        proba_orig = np.atleast_1d(proba_orig)
        proba_flip = np.atleast_1d(proba_flip)
        proba_deep = (proba_orig + (1 - proba_flip)) / 2
        proba_deep = _temperature_scale(proba_deep, temperature)

        results["DeepMLP (35f) PRO"] = {
            "y_proba": proba_deep,
            "y_pred": (proba_deep >= 0.5).astype(int),
        }

    # --- ResNet (PyTorch) ---
    resnet_model = registry.pytorch_models.get("ResNet (35f) PRO")
    if resnet_model is not None and "RNet" not in disabled:
        X, X_flip = _get_model_inputs("ResNet (35f) PRO", df_raw, inputs, registry)
        X_t = torch.FloatTensor(X)
        X_t_flip = torch.FloatTensor(X_flip)
        with torch.no_grad():
            proba_orig = torch.sigmoid(resnet_model(X_t).squeeze(-1)).numpy()
            proba_flip = torch.sigmoid(resnet_model(X_t_flip).squeeze(-1)).numpy()
        proba_orig = np.atleast_1d(proba_orig)
        proba_flip = np.atleast_1d(proba_flip)
        proba_resnet = (proba_orig + (1 - proba_flip)) / 2
        proba_resnet = _temperature_scale(proba_resnet, temperature)

        results["ResNet (35f) PRO"] = {
            "y_proba": proba_resnet,
            "y_pred": (proba_resnet >= 0.5).astype(int),
        }

    # --- Ensemble 3 NN ---
    if "Ens3" not in disabled:
        nn_names = ["MLP sklearn (35f) PRO", "DeepMLP (35f) PRO", "ResNet (35f) PRO"]
        nn_probas = [np.atleast_1d(results[n]["y_proba"]) for n in nn_names if n in results]
        if len(nn_probas) == 3:
            proba_ens = np.mean(np.stack(nn_probas), axis=0)
            results["Ensemble 3 NN PRO"] = {
                "y_proba": proba_ens,
                "y_pred": (proba_ens >= 0.5).astype(int),
            }

    return results


def format_predictions_table(
    df: pd.DataFrame,
    results: dict[str, dict],
    registry: ModelRegistry,
) -> list[dict]:
    """Format predictions into a list of fight dicts with per-model results.

    Returns list of dicts, one per fight, with structure:
    {
        fighter_1, fighter_2, event, odds_f1_american, odds_f2_american,
        models: {model_short: {predicted_winner, probability, confidence}}
    }
    """
    output = []
    for i, row in df.iterrows():
        fight = {
            "fighter_1": row["fighter_1"],
            "fighter_2": row["fighter_2"],
            "event": row.get("event", ""),
            "odds_f1_american": row.get("odds_f1_american"),
            "odds_f2_american": row.get("odds_f2_american"),
            "models": {},
        }

        for model_name, res in results.items():
            idx = i if isinstance(i, int) else df.index.get_loc(i)
            proba = float(res["y_proba"][idx])
            pred = int(res["y_pred"][idx])
            winner = row["fighter_1"] if pred == 1 else row["fighter_2"]
            confidence = proba if pred == 1 else 1 - proba
            short = registry._get_short_name(model_name)

            fight["models"][short] = {
                "full_name": model_name,
                "predicted_winner": winner,
                "probability_f1": round(proba, 4),
                "confidence": round(confidence, 4),
            }

        # Consensus (tie-break by average probability)
        votes_f1 = sum(
            1 for m in fight["models"].values() if m["predicted_winner"] == row["fighter_1"]
        )
        total = len(fight["models"])
        if votes_f1 * 2 == total:
            avg_prob = float(np.mean([m["probability_f1"] for m in fight["models"].values()]))
            cons_winner = row["fighter_1"] if avg_prob >= 0.5 else row["fighter_2"]
        else:
            cons_winner = row["fighter_1"] if votes_f1 > total / 2 else row["fighter_2"]
        fight["consensus"] = {
            "fighter_1_votes": votes_f1,
            "fighter_2_votes": total - votes_f1,
            "total_models": total,
            "consensus_winner": cons_winner,
            "consensus_pct": round(max(votes_f1, total - votes_f1) / total * 100, 1),
        }

        output.append(fight)

    return output
