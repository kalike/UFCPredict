"""FeatureTransformer delta-override (clip_sym_6) behaviour for 35f.

Guards the fix for delta_win_streak: the default clip_0_6 is asymmetric, which
both destroys the sign of negative deltas and breaks TTA's negation symmetry.
The delta_overrides flag swaps in the odd clip_sym_6 for delta_ columns only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ufc_core.transforms import FeatureTransformer


def _row(**deltas) -> pd.DataFrame:
    base = {
        "delta_win_streak": 3.0,
        "delta_days_inactive": 50.0,            # signed_log1p (odd)
        "delta_ctrl_time_differential": 400.0,  # clip_300 (odd)
    }
    base.update(deltas)
    return pd.DataFrame([base])


def test_override_keeps_sign_of_negative_delta_win_streak():
    """clip_sym_6 preserves a negative delta that clip_0_6 would zero out."""
    df = _row(delta_win_streak=-3.0)
    default = FeatureTransformer().transform_df(df)
    override = FeatureTransformer(delta_overrides=True).transform_df(df)
    assert default["delta_win_streak"].iloc[0] == 0.0      # clip_0_6 destroys it
    assert override["delta_win_streak"].iloc[0] == -3.0    # clip_sym_6 keeps it


def test_override_makes_transform_odd_for_tta_symmetry():
    """With the override, transform(-d) == -transform(d) for every delta col.

    This is exactly the invariant TTA's `X_flip = -X` relies on.
    """
    cols = ["delta_win_streak", "delta_days_inactive", "delta_ctrl_time_differential"]
    pos = _row()
    neg = _row(**{c: -pos[c].iloc[0] for c in cols})
    tf = FeatureTransformer(delta_overrides=True)
    t_pos = tf.transform_df(pos)[cols].values[0]
    t_neg = tf.transform_df(neg)[cols].values[0]
    np.testing.assert_allclose(t_neg, -t_pos, atol=1e-9)


def test_default_is_not_odd_for_win_streak():
    """Sanity: without the override the symmetry genuinely fails (the bug)."""
    tf = FeatureTransformer()  # delta_overrides defaults False
    t_pos = tf.transform_df(_row(delta_win_streak=3.0))["delta_win_streak"].iloc[0]
    t_neg = tf.transform_df(_row(delta_win_streak=-3.0))["delta_win_streak"].iloc[0]
    assert t_pos == 3.0 and t_neg == 0.0
    assert t_neg != -t_pos


def test_override_is_noop_for_f1_f2_columns():
    """The override only touches delta_ columns; f1_/f2_ keep clip_0_6."""
    df = pd.DataFrame([{"f1_win_streak": 3.0, "f2_win_streak": 5.0}])
    default = FeatureTransformer().transform_df(df)
    override = FeatureTransformer(delta_overrides=True).transform_df(df)
    pd.testing.assert_frame_equal(default, override)


def test_transform_array_matches_transform_df():
    """transform_array honours the override identically to transform_df."""
    cols = ["delta_win_streak", "delta_days_inactive"]
    df = _row(delta_win_streak=-4.0)
    tf = FeatureTransformer(delta_overrides=True)
    via_df = tf.transform_df(df)[cols].values[0]
    via_arr = tf.transform_array(df[cols].values.astype(float).copy(), cols)[0]
    np.testing.assert_allclose(via_arr, via_df, atol=1e-9)


def test_backward_compat_pickled_without_flag():
    """Artifacts pickled before the flag existed must still transform (clip_0_6)."""
    tf = FeatureTransformer()
    del tf.delta_overrides  # simulate an instance unpickled from an old artifact
    out = tf.transform_df(_row(delta_win_streak=-3.0))
    assert out["delta_win_streak"].iloc[0] == 0.0  # falls back to default
