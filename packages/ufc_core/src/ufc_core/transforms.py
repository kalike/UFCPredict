"""UFC Predictor — Feature transformations for skew reduction.

Applied AFTER imputation, BEFORE scaling.
Stateless — no fitting, same transforms in training and inference.
"""

import numpy as np
import pandas as pd


# Transform registry: suffix -> transform function name
# Applied to all columns ending with the suffix (f1_X, f2_X, delta_X)
TRANSFORM_REGISTRY = {
    "days_inactive": "signed_log1p",       # skew=5.8
    "chin_damage_score": "signed_log1p",   # skew=2.7
    "win_streak": "clip_0_6",              # skew=5.2
    "ctrl_time_differential": "clip_300",  # rango [-728, 535]
}


def _signed_log1p(x: np.ndarray) -> np.ndarray:
    """log1p preserving sign: log1p(|x|) * sign(x)."""
    return np.log1p(np.abs(x)) * np.sign(x)


def _clip_0_6(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0, 6)


def _clip_sym_6(x: np.ndarray) -> np.ndarray:
    """Symmetric clip [-6, 6] for delta features where sign carries meaning."""
    return np.clip(x, -6, 6)


def _clip_300(x: np.ndarray) -> np.ndarray:
    return np.clip(x, -300, 300)


_FN_MAP = {
    "signed_log1p": _signed_log1p,
    "clip_0_6": _clip_0_6,
    "clip_sym_6": _clip_sym_6,
    "clip_300": _clip_300,
}

# Overrides for delta_ prefix — when a delta needs a different transform
# than the individual f1_/f2_ features (e.g. win_streak can be negative
# as a delta but never negative as an individual stat).
# Only used during training of NEW models (via use_delta_overrides=True).
# Prediction of existing models uses the default transforms they were trained with.
DELTA_TRANSFORM_OVERRIDES = {
    "win_streak": "clip_sym_6",
}


class FeatureTransformer:
    """Applies configured transforms to feature columns.

    Stateless — no fitting needed. Transform config is fixed.
    Applied identically in training and inference.

    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def transform_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.enabled:
            return df
        df = df.copy()
        for suffix, fn_name in TRANSFORM_REGISTRY.items():
            fn = _FN_MAP[fn_name]
            for prefix in ("f1_", "f2_", "delta_"):
                col = f"{prefix}{suffix}"
                if col in df.columns:
                    df[col] = fn(df[col].values)
        return df

    def transform_array(
        self, X: np.ndarray, feature_cols: list[str]
    ) -> np.ndarray:
        if not self.enabled:
            return X
        X = X.copy()
        for i, col in enumerate(feature_cols):
            for suffix, fn_name in TRANSFORM_REGISTRY.items():
                if col.endswith(suffix):
                    X[:, i] = _FN_MAP[fn_name](X[:, i])
                    break
        return X
