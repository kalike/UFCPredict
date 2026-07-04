import numpy as np

from ufc_core.tta import build_tta_flip


def test_52f_clean_swaps_f1_f2_pairs():
    # feat_cols = sorted f1 block then f2 block (no symmetric cols).
    feat_cols = ["f1_age", "f1_reach", "f2_age", "f2_reach"]
    X = np.array([[20.0, 70.0, 30.0, 75.0]], dtype=np.float32)
    flip = build_tta_flip(X, feat_cols)
    # f1_age <-> f2_age, f1_reach <-> f2_reach
    np.testing.assert_array_equal(flip, np.array([[30.0, 75.0, 20.0, 70.0]]))


def test_52f_clean_matches_legacy_half_swap():
    # The shared helper must be a strict generalization of the old contiguous
    # half-swap on a clean 52f layout (no symmetric columns).
    feat_cols = ["f1_a", "f1_b", "f1_c", "f2_a", "f2_b", "f2_c"]
    X = np.arange(6, dtype=np.float32).reshape(1, 6)
    n_half = 3
    legacy = np.hstack([X[:, n_half:], X[:, :n_half]])
    np.testing.assert_array_equal(build_tta_flip(X, feat_cols), legacy)


def test_35f_delta_negates():
    feat_cols = ["delta_age", "delta_reach"]
    X = np.array([[5.0, -3.0]], dtype=np.float32)
    np.testing.assert_array_equal(build_tta_flip(X, feat_cols), np.array([[-5.0, 3.0]]))


def test_v7_52f_leaves_symmetric_columns_in_place():
    # V7 appends symmetric fight-level columns (no f1_/f2_/delta_ prefix).
    # The buggy half-swap scrambled these; the fix must keep them untouched
    # while still swapping the f1_/f2_ pairs (incl. asymmetric f*_tap_win_pct).
    feat_cols = [
        "f1_age", "f1_tap_win_pct",
        "f2_age", "f2_tap_win_pct",
        "tap_consensus_strength", "tap_log_volume", "tap_has_data",
    ]
    X = np.array([[20.0, 0.7, 30.0, 0.3, 0.2, 8.7, 1.0]], dtype=np.float32)
    flip = build_tta_flip(X, feat_cols)
    # f1<->f2 pairs swapped; the 3 symmetric tap columns unchanged.
    np.testing.assert_array_equal(
        flip, np.array([[30.0, 0.3, 20.0, 0.7, 0.2, 8.7, 1.0]], dtype=np.float32)
    )


def test_v7_35f_negates_deltas_keeps_symmetric():
    feat_cols = ["delta_age", "delta_tap_win_pct",
                 "tap_consensus_strength", "tap_log_volume", "tap_has_data"]
    X = np.array([[5.0, 0.4, 0.2, 8.7, 1.0]], dtype=np.float32)
    flip = build_tta_flip(X, feat_cols)
    np.testing.assert_array_equal(
        flip, np.array([[-5.0, -0.4, 0.2, 8.7, 1.0]], dtype=np.float32)
    )


def test_does_not_mutate_input():
    feat_cols = ["f1_a", "f2_a", "tap_has_data"]
    X = np.array([[1.0, 2.0, 1.0]], dtype=np.float32)
    X_copy = X.copy()
    build_tta_flip(X, feat_cols)
    np.testing.assert_array_equal(X, X_copy)
