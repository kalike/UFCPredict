"""Tests for V7 tapology_picks features in compute_fight_features."""

import pytest
from datetime import datetime

from ufc_core.features.engine import compute_fight_features


def _minimal_args(picks=None):
    """Minimal valid args for compute_fight_features. Both fighters need >=1 fight."""
    histories = {
        "Alice": [{
            "result": 1, "opponent": "Bob", "event": "UFC X", "method": "KO",
            "kd_landed": 1, "kd_received": 0,
            "sig_str_landed": 50, "sig_str_attempted": 100,
            "sig_str_received": 30, "sig_str_received_attempted": 80,
            "td_landed": 1, "td_attempted": 3, "td_received": 0, "td_received_attempted": 2,
            "ctrl_seconds": 60, "opp_ctrl_seconds": 0,
            "sub_att": 0, "reversals": 0,
            "head_landed": 20, "body_landed": 15, "leg_landed": 15,
            "distance_landed": 30, "clinch_landed": 10, "ground_landed": 10,
        }],
        "Bob": [{
            "result": 0, "opponent": "Alice", "event": "UFC X", "method": "KO",
            "kd_landed": 0, "kd_received": 1,
            "sig_str_landed": 30, "sig_str_attempted": 80,
            "sig_str_received": 50, "sig_str_received_attempted": 100,
            "td_landed": 0, "td_attempted": 2, "td_received": 1, "td_received_attempted": 3,
            "ctrl_seconds": 0, "opp_ctrl_seconds": 60,
            "sub_att": 0, "reversals": 0,
            "head_landed": 15, "body_landed": 10, "leg_landed": 5,
            "distance_landed": 20, "clinch_landed": 5, "ground_landed": 5,
        }],
    }
    return dict(
        f1_name="Alice",
        f2_name="Bob",
        fighter_histories=histories,
        fighter_lookup={"Alice": {}, "Bob": {}},
        event_dates={"UFC X": datetime(2020, 1, 1)},
        event="UFC Y",
        event_date=datetime(2024, 1, 1),
        tapology_picks=picks,
    )


def test_v7_columns_present_with_picks():
    picks = {"total_picks": 1000, "fighter_1_win_pct": 0.7, "fighter_2_win_pct": 0.3}
    row = compute_fight_features(**_minimal_args(picks))
    assert row is not None
    # Asimétricas
    assert row["f1_tap_win_pct"] == 0.7
    assert row["f2_tap_win_pct"] == 0.3
    assert abs(row["delta_tap_win_pct"] - 0.4) < 1e-9
    # Simétricas (bare names)
    assert abs(row["tap_consensus_strength"] - 0.2) < 1e-9  # |0.5 - 0.7|
    assert row["tap_log_volume"] > 0  # log1p(1000)
    assert row["tap_has_data"] == 1


def test_v7_columns_neutral_without_picks():
    row = compute_fight_features(**_minimal_args(picks=None))
    assert row is not None
    assert row["f1_tap_win_pct"] == 0.5
    assert row["f2_tap_win_pct"] == 0.5
    assert row["delta_tap_win_pct"] == 0.0
    assert row["tap_consensus_strength"] == 0.0
    assert row["tap_log_volume"] == 0.0
    assert row["tap_has_data"] == 0


def test_v7_columns_neutral_when_zero_picks():
    picks = {"total_picks": 0, "fighter_1_win_pct": 0.5, "fighter_2_win_pct": 0.5}
    row = compute_fight_features(**_minimal_args(picks))
    assert row["tap_has_data"] == 0
    assert row["tap_log_volume"] == 0.0


def test_v7_consensus_symmetric():
    picks = {"total_picks": 500, "fighter_1_win_pct": 0.3, "fighter_2_win_pct": 0.7}
    row = compute_fight_features(**_minimal_args(picks))
    # consensus es simétrica: |0.5 - 0.3| == |0.5 - 0.7| = 0.2
    assert row["tap_consensus_strength"] == 0.2


def test_compute_features_for_fights_passes_picks():
    """Pre-oriented picks dict is passed through to compute_fight_features."""
    from ufc_core.features.engine import compute_features_for_fights

    histories = {
        "Alice": [{
            "result": 1, "opponent": "Bob", "event": "UFC X", "method": "KO",
            "kd_landed": 1, "kd_received": 0,
            "sig_str_landed": 50, "sig_str_attempted": 100,
            "sig_str_received": 30, "sig_str_received_attempted": 80,
            "td_landed": 1, "td_attempted": 3, "td_received": 0, "td_received_attempted": 2,
            "ctrl_seconds": 60, "opp_ctrl_seconds": 0,
            "sub_att": 0, "reversals": 0,
            "head_landed": 20, "body_landed": 15, "leg_landed": 15,
            "distance_landed": 30, "clinch_landed": 10, "ground_landed": 10,
        }],
        "Bob": [{
            "result": 0, "opponent": "Alice", "event": "UFC X", "method": "KO",
            "kd_landed": 0, "kd_received": 1,
            "sig_str_landed": 30, "sig_str_attempted": 80,
            "sig_str_received": 50, "sig_str_received_attempted": 100,
            "td_landed": 0, "td_attempted": 2, "td_received": 1, "td_received_attempted": 3,
            "ctrl_seconds": 0, "opp_ctrl_seconds": 60,
            "sub_att": 0, "reversals": 0,
            "head_landed": 15, "body_landed": 10, "leg_landed": 5,
            "distance_landed": 20, "clinch_landed": 5, "ground_landed": 5,
        }],
    }
    fights = [{"fighter_1": "Alice", "fighter_2": "Bob", "event": "UFC Y"}]
    picks_by_key = {
        ("UFC Y", frozenset({"Alice", "Bob"})): {
            "total_picks": 200, "fighter_1_win_pct": 0.6, "fighter_2_win_pct": 0.4,
        }
    }
    df, _ = compute_features_for_fights(
        fights=fights,
        fighter_histories=histories,
        fighter_lookup={"Alice": {}, "Bob": {}},
        event_dates={"UFC X": datetime(2020, 1, 1)},
        event_date=datetime(2024, 1, 1),
        tapology_picks_by_key=picks_by_key,
    )
    assert len(df) == 1
    assert df.iloc[0]["f1_tap_win_pct"] == 0.6
    assert df.iloc[0]["tap_has_data"] == 1


def test_compute_features_for_fights_handles_missing_picks():
    """When tapology_picks_by_key is empty, neutral imputation is applied."""
    from ufc_core.features.engine import compute_features_for_fights

    histories = {
        "Alice": [{
            "result": 1, "opponent": "Bob", "event": "UFC X", "method": "KO",
            "kd_landed": 1, "kd_received": 0,
            "sig_str_landed": 50, "sig_str_attempted": 100,
            "sig_str_received": 30, "sig_str_received_attempted": 80,
            "td_landed": 1, "td_attempted": 3, "td_received": 0, "td_received_attempted": 2,
            "ctrl_seconds": 60, "opp_ctrl_seconds": 0,
            "sub_att": 0, "reversals": 0,
            "head_landed": 20, "body_landed": 15, "leg_landed": 15,
            "distance_landed": 30, "clinch_landed": 10, "ground_landed": 10,
        }],
        "Bob": [{
            "result": 0, "opponent": "Alice", "event": "UFC X", "method": "KO",
            "kd_landed": 0, "kd_received": 1,
            "sig_str_landed": 30, "sig_str_attempted": 80,
            "sig_str_received": 50, "sig_str_received_attempted": 100,
            "td_landed": 0, "td_attempted": 2, "td_received": 1, "td_received_attempted": 3,
            "ctrl_seconds": 0, "opp_ctrl_seconds": 60,
            "sub_att": 0, "reversals": 0,
            "head_landed": 15, "body_landed": 10, "leg_landed": 5,
            "distance_landed": 20, "clinch_landed": 5, "ground_landed": 5,
        }],
    }
    fights = [{"fighter_1": "Alice", "fighter_2": "Bob", "event": "UFC NoPicks"}]
    df, _ = compute_features_for_fights(
        fights=fights,
        fighter_histories=histories,
        fighter_lookup={"Alice": {}, "Bob": {}},
        event_dates={"UFC X": datetime(2020, 1, 1)},
        event_date=datetime(2024, 1, 1),
        tapology_picks_by_key={},
    )
    assert df.iloc[0]["tap_has_data"] == 0
    assert df.iloc[0]["f1_tap_win_pct"] == 0.5


def test_compute_features_for_fights_default_arg_works():
    """Wrapper still works without the new tapology_picks_by_key kwarg (default None)."""
    from ufc_core.features.engine import compute_features_for_fights

    histories = {
        "Alice": [{
            "result": 1, "opponent": "Bob", "event": "UFC X", "method": "KO",
            "kd_landed": 1, "kd_received": 0,
            "sig_str_landed": 50, "sig_str_attempted": 100,
            "sig_str_received": 30, "sig_str_received_attempted": 80,
            "td_landed": 1, "td_attempted": 3, "td_received": 0, "td_received_attempted": 2,
            "ctrl_seconds": 60, "opp_ctrl_seconds": 0,
            "sub_att": 0, "reversals": 0,
            "head_landed": 20, "body_landed": 15, "leg_landed": 15,
            "distance_landed": 30, "clinch_landed": 10, "ground_landed": 10,
        }],
        "Bob": [{
            "result": 0, "opponent": "Alice", "event": "UFC X", "method": "KO",
            "kd_landed": 0, "kd_received": 1,
            "sig_str_landed": 30, "sig_str_attempted": 80,
            "sig_str_received": 50, "sig_str_received_attempted": 100,
            "td_landed": 0, "td_attempted": 2, "td_received": 1, "td_received_attempted": 3,
            "ctrl_seconds": 0, "opp_ctrl_seconds": 60,
            "sub_att": 0, "reversals": 0,
            "head_landed": 15, "body_landed": 10, "leg_landed": 5,
            "distance_landed": 20, "clinch_landed": 5, "ground_landed": 5,
        }],
    }
    fights = [{"fighter_1": "Alice", "fighter_2": "Bob", "event": "UFC Z"}]
    df, _ = compute_features_for_fights(
        fights=fights,
        fighter_histories=histories,
        fighter_lookup={"Alice": {}, "Bob": {}},
        event_dates={"UFC X": datetime(2020, 1, 1)},
        event_date=datetime(2024, 1, 1),
    )
    assert df.iloc[0]["tap_has_data"] == 0


@pytest.mark.skip(reason="Deferred — depends on ufc_core.tapology (T12)")
def test_compute_features_for_fights_orients_repo_format():
    """Repo-format entries get oriented based on the fight's fighter_1."""
    from ufc_core.features.engine import compute_features_for_fights

    histories = {
        "Alice": [{
            "result": 1, "opponent": "Bob", "event": "UFC X", "method": "KO",
            "kd_landed": 1, "kd_received": 0,
            "sig_str_landed": 50, "sig_str_attempted": 100,
            "sig_str_received": 30, "sig_str_received_attempted": 80,
            "td_landed": 1, "td_attempted": 3, "td_received": 0, "td_received_attempted": 2,
            "ctrl_seconds": 60, "opp_ctrl_seconds": 0,
            "sub_att": 0, "reversals": 0,
            "head_landed": 20, "body_landed": 15, "leg_landed": 15,
            "distance_landed": 30, "clinch_landed": 10, "ground_landed": 10,
        }],
        "Bob": [{
            "result": 0, "opponent": "Alice", "event": "UFC X", "method": "KO",
            "kd_landed": 0, "kd_received": 1,
            "sig_str_landed": 30, "sig_str_attempted": 80,
            "sig_str_received": 50, "sig_str_received_attempted": 100,
            "td_landed": 0, "td_attempted": 2, "td_received": 1, "td_received_attempted": 3,
            "ctrl_seconds": 0, "opp_ctrl_seconds": 60,
            "sub_att": 0, "reversals": 0,
            "head_landed": 15, "body_landed": 10, "leg_landed": 5,
            "distance_landed": 20, "clinch_landed": 5, "ground_landed": 5,
        }],
    }
    fights = [{"fighter_1": "Bob", "fighter_2": "Alice", "event": "UFC Y"}]
    # Repo format: picks stored with fighter_a=Alice (alphabetical), fighter_a_pct=0.6
    picks_by_key = {
        ("UFC Y", frozenset({"Alice", "Bob"})): {
            "total_picks": 200,
            "fighter_a_name": "Alice",
            "fighter_b_name": "Bob",
            "fighter_a_win_pct": 0.6,
            "fighter_b_win_pct": 0.4,
        }
    }
    df, _ = compute_features_for_fights(
        fights=fights,
        fighter_histories=histories,
        fighter_lookup={"Alice": {}, "Bob": {}},
        event_dates={"UFC X": datetime(2020, 1, 1)},
        event_date=datetime(2024, 1, 1),
        tapology_picks_by_key=picks_by_key,
    )
    # fighter_1=Bob → Bob's win_pct (0.4) goes to f1_tap_win_pct
    assert abs(df.iloc[0]["f1_tap_win_pct"] - 0.4) < 1e-9
    assert abs(df.iloc[0]["f2_tap_win_pct"] - 0.6) < 1e-9
