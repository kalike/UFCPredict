"""UFC Predictor — Centralized feature imputation.

Replaces fillna(0) with statistically-sound imputation:
- fit() on training data to learn medians
- transform() on any data using stored medians
- Serializable via joblib for inference consistency
"""

import numpy as np
import pandas as pd
import joblib
from pathlib import Path


# Fallback medians for features with known problematic fillna(0).
# Used when no fitted imputer is available (legacy model compatibility).
# Source: Feature Report V2, medians of 14,050-row dataset.
KNOWN_DEFAULTS = {
    "days_inactive": 175.0,
    "reach_in": 72.0,
    "age": 30.5,
    "height_in": 70.0,
}


class FeatureImputer:
    """Fit-transform imputer that stores medians from training set."""

    def __init__(self):
        self._medians: dict[str, float] = {}
        self._fitted = False

    def fit(self, df: pd.DataFrame, feature_cols: list[str]) -> "FeatureImputer":
        """Compute medians from training data for each feature column."""
        self._medians = {}
        for col in feature_cols:
            if col in df.columns:
                med = df[col].median()
                if np.isnan(med):
                    suffix = col.replace("f1_", "").replace("f2_", "").replace("delta_", "")
                    med = KNOWN_DEFAULTS.get(suffix, 0.0)
                self._medians[col] = float(med)
        self._fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Impute NaN values using stored medians."""
        if not self._fitted:
            raise RuntimeError("FeatureImputer.fit() must be called first")
        df = df.copy()
        for col, med in self._medians.items():
            if col in df.columns:
                df[col] = df[col].fillna(med)
        return df

    def save(self, path: Path) -> None:
        joblib.dump({"medians": self._medians}, path)

    @classmethod
    def load(cls, path: Path) -> "FeatureImputer":
        data = joblib.load(path)
        imp = cls()
        imp._medians = data["medians"]
        imp._fitted = True
        return imp

    @classmethod
    def from_defaults(cls, feature_cols: list[str]) -> "FeatureImputer":
        """Create imputer with known defaults (legacy model compat)."""
        imp = cls()
        for col in feature_cols:
            matched = False
            for suffix, default in KNOWN_DEFAULTS.items():
                if col.endswith(suffix):
                    imp._medians[col] = default
                    matched = True
                    break
            if not matched:
                imp._medians[col] = 0.0
        imp._fitted = True
        return imp

    @property
    def medians(self) -> dict[str, float]:
        return dict(self._medians)
