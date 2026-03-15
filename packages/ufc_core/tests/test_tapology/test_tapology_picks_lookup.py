"""Tests for build_picks_lookup_by_event_pair and orient_picks_for_fight helpers."""

from ufc_core.tapology.picks_repo import (
    _orient_picks,
    orient_picks_for_fight,
)


def test_orient_picks_target_is_fighter_a():
    """When target_f1 == fighter_a, fighter_1_win_pct = fighter_a_pct."""
    out = _orient_picks(
        fighter_a_name="Alice",
        fighter_b_name="Bob",
        fighter_a_pct=0.7,
        fighter_b_pct=0.3,
        target_f1="Alice",
    )
    assert out["fighter_1_win_pct"] == 0.7
    assert out["fighter_2_win_pct"] == 0.3


def test_orient_picks_target_is_fighter_b():
    """When target_f1 == fighter_b, percentages are swapped."""
    out = _orient_picks(
        fighter_a_name="Alice",
        fighter_b_name="Bob",
        fighter_a_pct=0.7,
        fighter_b_pct=0.3,
        target_f1="Bob",
    )
    assert out["fighter_1_win_pct"] == 0.3
    assert out["fighter_2_win_pct"] == 0.7


def test_orient_picks_target_unknown_fallback_alphabetical():
    """When target_f1 matches neither, fall back to alphabetical orientation."""
    out = _orient_picks(
        fighter_a_name="Bob",
        fighter_b_name="Alice",
        fighter_a_pct=0.6,
        fighter_b_pct=0.4,
        target_f1="Charlie",
    )
    # Alphabetical: Alice first → fighter_1_win_pct = 0.4 (b's pct since b="Alice")
    assert out["fighter_1_win_pct"] == 0.4
    assert out["fighter_2_win_pct"] == 0.6


def test_orient_picks_handles_none_pct():
    """None pct values become 0.5 (neutral)."""
    out = _orient_picks(
        fighter_a_name="Alice",
        fighter_b_name="Bob",
        fighter_a_pct=None,
        fighter_b_pct=None,
        target_f1="Alice",
    )
    assert out["fighter_1_win_pct"] == 0.5
    assert out["fighter_2_win_pct"] == 0.5


def test_orient_picks_for_fight_returns_pre_oriented_dict():
    """Wrapper produces dict in pre-oriented format expected by compute_fight_features."""
    entry = {
        "total_picks": 200,
        "fighter_a_name": "Alice",
        "fighter_b_name": "Bob",
        "fighter_a_win_pct": 0.6,
        "fighter_b_win_pct": 0.4,
    }
    out = orient_picks_for_fight(entry, fighter_1_name="Bob")
    assert out == {
        "total_picks": 200,
        "fighter_1_win_pct": 0.4,
        "fighter_2_win_pct": 0.6,
    }


def test_orient_picks_for_fight_returns_none_on_zero_picks():
    """zero total_picks → None (let caller apply neutral imputation)."""
    entry = {
        "total_picks": 0,
        "fighter_a_name": "Alice",
        "fighter_b_name": "Bob",
        "fighter_a_win_pct": 0.5,
        "fighter_b_win_pct": 0.5,
    }
    assert orient_picks_for_fight(entry, fighter_1_name="Alice") is None


def test_orient_picks_for_fight_returns_none_on_missing_pct():
    """When pct values are None → None."""
    entry = {
        "total_picks": 200,
        "fighter_a_name": "Alice",
        "fighter_b_name": "Bob",
        "fighter_a_win_pct": None,
        "fighter_b_win_pct": None,
    }
    assert orient_picks_for_fight(entry, fighter_1_name="Alice") is None


def test_orient_picks_for_fight_returns_none_on_none_input():
    assert orient_picks_for_fight(None, fighter_1_name="Alice") is None
