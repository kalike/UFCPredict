from lab_api.services import dashboard as dsvc


def test_predicted_winner_picks_f1_when_prob_ge_half():
    assert dsvc._predicted_winner(0.5, "A", "B") == "A"
    assert dsvc._predicted_winner(0.51, "A", "B") == "A"
    assert dsvc._predicted_winner(0.49, "A", "B") == "B"


def test_consensus_majority_3_1():
    votes = [("A", 0.8), ("A", 0.7), ("A", 0.6), ("B", 0.3)]
    winner, n_for, n_total, prob = dsvc._consensus(votes, "A", "B")
    assert winner == "A"
    assert n_for == 3
    assert n_total == 4
    assert round(prob, 4) == 0.6


def test_consensus_split_2_2_resolved_by_mean_prob():
    votes = [("A", 0.9), ("A", 0.8), ("B", 0.3), ("B", 0.2)]
    winner, n_for, n_total, prob = dsvc._consensus(votes, "A", "B")
    assert winner == "A"
    assert n_for == 2
    assert n_total == 4


def test_consensus_tier_labels_for_four_models():
    assert dsvc._consensus_tier(4, 4) == "unanimous"
    assert dsvc._consensus_tier(3, 4) == "majority"
    assert dsvc._consensus_tier(2, 4) == "split"


def test_probability_tier_bins():
    assert dsvc._probability_tier(0.52) == "low"
    assert dsvc._probability_tier(0.58) == "medium"
    assert dsvc._probability_tier(0.62) == "high"
    assert dsvc._probability_tier(0.68) == "very_high"
    assert dsvc._probability_tier(0.80) == "extreme"
