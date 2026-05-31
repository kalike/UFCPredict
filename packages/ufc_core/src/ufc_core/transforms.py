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
#
# Why this matters: the default clip_0_6 is asymmetric, so for delta_win_streak
# it (a) clamps every negative delta to 0 — discarding the half of the signal
# where fighter_2 has the longer streak — and (b) is not an odd function, so it
# breaks the negation symmetry that TTA relies on (training augments by negating
# the RAW delta then transforming; TTA negates the TRANSFORMED value). clip_sym_6
# is odd, fixing both. Enabled per-instance via delta_overrides=True; the flag is
# pickled with the transformer so inference reuses exactly what training applied.
#
# Only NEW 35f models opt in (delta_overrides=True). Legacy 35f artifacts and the
# legacy predictor path keep delta_overrides=False, preserving the clip_0_6 they
# were trained with. 52f models never have delta_ columns, so the flag is a no-op.
DELTA_TRANSFORM_OVERRIDES = {
    "win_streak": "clip_sym_6",
}


class FeatureTransformer:
    """Applies configured transforms to feature columns.

    Stateless — no fitting needed. Transform config is fixed.
    Applied identically in training and inference.

    delta_overrides: when True, delta_ columns whose suffix is in
    DELTA_TRANSFORM_OVERRIDES use the override transform instead of the default
    registry one (see the module note above). Off by default for backward
    compatibility with existing artifacts.
    """

    def __init__(self, enabled: bool = True, delta_overrides: bool = False):
        self.enabled = enabled
        self.delta_overrides = delta_overrides

    def _fn_name_for(self, prefix: str, suffix: str, default: str) -> str:
        """Resolve the effective transform fn name for one prefixed column."""
        # getattr guards artifacts pickled before delta_overrides existed.
        if (getattr(self, "delta_overrides", False)
                and prefix == "delta_"
                and suffix in DELTA_TRANSFORM_OVERRIDES):
            return DELTA_TRANSFORM_OVERRIDES[suffix]
        return default

    def transform_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.enabled:
            return df
        df = df.copy()
        for suffix, fn_name in TRANSFORM_REGISTRY.items():
            for prefix in ("f1_", "f2_", "delta_"):
                col = f"{prefix}{suffix}"
                if col in df.columns:
                    fn = _FN_MAP[self._fn_name_for(prefix, suffix, fn_name)]
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
                    prefix = "delta_" if col.startswith("delta_") else col[:3]
                    X[:, i] = _FN_MAP[self._fn_name_for(prefix, suffix, fn_name)](X[:, i])
                    break
        return X
