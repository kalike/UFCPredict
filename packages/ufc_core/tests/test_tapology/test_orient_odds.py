"""_orient_odds maps Tapology's (fighter_a, fighter_b) odds onto a Fight row's
(fighter_1, fighter_2) positions, regardless of which side matched fighter_a."""

from ufc_core.tapology.orchestrator import _orient_odds


def test_orient_odds_same_order():
    # fighter_a (a_id=10) is the row's fighter_1 -> odds keep their order.
    assert _orient_odds(fight_f1_id=10, a_id=10, odds_a=-150, odds_b=130) == (-150, 130)


def test_orient_odds_swapped():
    # fighter_a (a_id=10) is the row's fighter_2 -> odds swap.
    assert _orient_odds(fight_f1_id=20, a_id=10, odds_a=-150, odds_b=130) == (130, -150)
