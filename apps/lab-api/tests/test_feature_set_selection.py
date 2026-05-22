"""Unit tests for feature-set/feat-type column selection.

Regression for: training and HP search ignored the requested feature_set —
every run trained on "all numeric columns", so different feature sets
produced identical Test Acc. Selection must delegate to ufc_core's
_get_feature_cols (single source of truth for set definitions).
"""

import pandas as pd
import pytest

from lab_api.services.training import _select_feat_cols


def _make_df() -> pd.DataFrame:
    """One-row frame with representative column families."""
    row = {
        # core stats (present in every set)
        "f1_elo": 1500.0, "f2_elo": 1480.0, "delta_elo": 20.0,
        "f1_win_rate": 0.6, "f2_win_rate": 0.5, "delta_win_rate": 0.1,
        # V2 feature — excluded in "legacy"
        "f1_chin_damage_score": 0.1, "f2_chin_damage_score": 0.2,
        "delta_chin_damage_score": -0.1,
        # excluded from v3 onwards (importance < 0.001)
        "f1_height_in": 70.0, "f2_height_in": 72.0, "delta_height_in": -2.0,
        # tapology asymmetric — only v7
        "f1_tap_win_pct": 0.6, "f2_tap_win_pct": 0.4, "delta_tap_win_pct": 0.2,
        # tapology symmetric bare-name — only v7
        "tap_consensus_strength": 0.3, "tap_log_volume": 2.0, "tap_has_data": 1.0,
        # metadata — never a feature
        "result": 1, "fighter_1": "A", "fighter_2": "B",
    }
    return pd.DataFrame([row])


def test_52f_selects_only_prefixed_fighter_cols():
    cols = _select_feat_cols(_make_df(), feat_type="52f", feature_set="v2")
    assert cols, "selection must not be empty"
    assert all(c.startswith(("f1_", "f2_")) for c in cols)
    assert not any(c.startswith("delta_") for c in cols)


def test_delta_feat_type_selects_only_delta_cols():
    cols = _select_feat_cols(_make_df(), feat_type="delta", feature_set="v2")
    assert cols, "selection must not be empty"
    assert all(c.startswith("delta_") for c in cols)


def test_v7_includes_tapology_v6_excludes_it():
    v7 = _select_feat_cols(_make_df(), feat_type="52f", feature_set="v7")
    v6 = _select_feat_cols(_make_df(), feat_type="52f", feature_set="v6")
    assert "f1_tap_win_pct" in v7
    assert "tap_consensus_strength" in v7
    assert "f1_tap_win_pct" not in v6
    assert "tap_consensus_strength" not in v6


def test_legacy_excludes_v2_features():
    legacy = _select_feat_cols(_make_df(), feat_type="52f", feature_set="legacy")
    assert "f1_chin_damage_score" not in legacy
    v2 = _select_feat_cols(_make_df(), feat_type="52f", feature_set="v2")
    assert "f1_chin_damage_score" in v2


def test_different_feature_sets_select_different_columns():
    """The user-visible regression: v2 vs v7 must NOT train on the same columns."""
    v2 = _select_feat_cols(_make_df(), feat_type="52f", feature_set="v2")
    v7 = _select_feat_cols(_make_df(), feat_type="52f", feature_set="v7")
    assert set(v2) != set(v7)


def test_metadata_never_selected():
    for fs in ("legacy", "v2", "v5", "v7"):
        cols = _select_feat_cols(_make_df(), feat_type="52f", feature_set=fs)
        assert "result" not in cols
        assert "fighter_1" not in cols


def test_empty_selection_raises():
    df = pd.DataFrame([{"result": 1, "unrelated": 3.0}])
    with pytest.raises(ValueError, match="No feature columns"):
        _select_feat_cols(df, feat_type="52f", feature_set="v7")


def test_unknown_feature_set_raises():
    """Free-text UI field: a typo must fail loudly, not train the superset."""
    with pytest.raises(ValueError, match="Unknown feature_set"):
        _select_feat_cols(_make_df(), feat_type="52f", feature_set="v99")
