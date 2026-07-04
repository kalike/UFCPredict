import numpy as np
import pandas as pd
from ufc_core.trainer.core import evaluate_realworld


class _DummyClf:
    """predict_proba constante: P(f1)=0.6 para toda fila."""
    def predict_proba(self, X):
        n = X.shape[0]
        return np.column_stack([np.full(n, 0.4), np.full(n, 0.6)])


class _IdImputer:
    def transform(self, df):
        return df.copy()


def _rw_df():
    # 2 peleas con odds y fechas separadas para forzar el split sel/val.
    return pd.DataFrame({
        "delta_a": [1.0, -1.0],
        "delta_b": [0.5, -0.5],
        "rw_label": [1.0, 0.0],
        "event": ["UFC A", "UFC B"],
        "event_date": pd.to_datetime(["2025-06-01", "2025-12-01"]),
        "fighter_1": ["X", "P"],
        "fighter_2": ["Y", "Q"],
        "rw_real_winner": ["X", "Q"],
        "odds_f1_american": [200.0, -250.0],
        "odds_f2_american": [-250.0, 200.0],
    })


def test_evaluate_realworld_emits_roi_fields():
    out = evaluate_realworld(
        _DummyClf(), None, _IdImputer(),
        feat_cols=["delta_a", "delta_b"],
        realworld_df=_rw_df(),
        is_pytorch=False, min_fights=0,
    )
    rv = out["realworld_value"]
    assert rv is not None
    assert "roi_ev" in rv
    assert "roi_ev_sel" in rv and "roi_ev_val" in rv
    assert rv["split_date"] is not None
    assert rv["n_picks_ev"] >= 1
