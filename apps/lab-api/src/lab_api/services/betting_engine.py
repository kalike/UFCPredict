from itertools import combinations

from lab_api.schemas.betting import (
    BettingConfig,
    QualifiedPick,
    BetCombo,
    RecommendSummary,
    RecommendResponse,
    EventBacktestDetail,
)


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds."""
    if american == 0:
        return None
    if american > 0:
        return 1 + american / 100
    else:
        return 1 + 100 / abs(american)


def qualify_picks(fights: list[dict], config: BettingConfig) -> list[QualifiedPick]:
    """
    Filter and score fights to produce qualified picks.

    For each fight:
    1. Check consensus_pct >= min_consensus_pct
    2. Determine the pick (consensus_winner)
    3. Get the correct odds for the picked fighter
    4. Calculate model_prob: if consensus_winner == fighter_1, model_prob = avg_prob_f1, else 1 - avg_prob_f1
    5. Check model_prob >= min_model_prob
    6. Check odds are available (not null)
    7. Calculate: decimal_odds, implied_prob, edge, ev_per_unit, kelly_full, kelly_quarter, score
    8. Determine hit: if real_winner is set, hit = (pick == real_winner)

    Score formula:
      consensus_factor = 1.0 if consensus_pct == 100, 0.5 if >= 80, else 0.0
      score = model_prob * 0.7 + consensus_factor * 0.3

    Sort by score descending, take top max_picks_per_event.
    """
    qualified = []
    for f in fights:
        consensus_pct = f.get("consensus_pct") or 0
        if consensus_pct < config.min_consensus_pct:
            continue

        # Filter by minimum point-in-time (PIT) career fights for both fighters.
        # If data is missing and a threshold is set, exclude the fight (safer default).
        if config.min_pit_fights > 0:
            f1_n = f.get("fighter_1_n_fights")
            f2_n = f.get("fighter_2_n_fights")
            if f1_n is None or f2_n is None:
                continue
            if f1_n < config.min_pit_fights or f2_n < config.min_pit_fights:
                continue

        consensus_winner = f.get("consensus_winner")
        if not consensus_winner:
            continue

        avg_prob_f1 = f.get("avg_prob_f1")
        if avg_prob_f1 is None:
            continue

        # Determine model_prob for the picked fighter
        if consensus_winner == f.get("fighter_1"):
            model_prob = avg_prob_f1
            odds_american = f.get("odds_f1_american")
        else:
            model_prob = 1 - avg_prob_f1
            odds_american = f.get("odds_f2_american")

        # Per-type probability thresholds are applied later in
        # `generate_event_plan`, so each bet type (singles/doubles/triples)
        # can be tuned independently. Here we only require odds + consensus.
        if not odds_american:
            continue

        decimal_odds = american_to_decimal(odds_american)
        if decimal_odds is None:
            continue
        implied_prob = 1 / decimal_odds
        edge = model_prob - implied_prob
        ev_per_unit = model_prob * decimal_odds - 1
        kelly_full = ev_per_unit / (decimal_odds - 1) if ev_per_unit > 0 else 0.0
        kelly_quarter = kelly_full * config.kelly_fraction

        consensus_factor = 1.0 if consensus_pct >= 100 else (0.5 if consensus_pct >= 80 else 0.0)
        score = model_prob * 0.7 + consensus_factor * 0.3

        real_winner = f.get("real_winner")
        hit = (consensus_winner == real_winner) if real_winner else None

        qualified.append(
            QualifiedPick(
                fighter_1=f["fighter_1"],
                fighter_2=f["fighter_2"],
                pick=consensus_winner,
                pick_odds_american=odds_american,
                model_prob=round(model_prob, 4),
                decimal_odds=round(decimal_odds, 4),
                implied_prob=round(implied_prob, 4),
                edge=round(edge, 4),
                ev_per_unit=round(ev_per_unit, 4),
                kelly_full=round(kelly_full, 4),
                kelly_quarter=round(kelly_quarter, 4),
                score=round(score, 4),
                consensus_pct=consensus_pct,
                hit=hit,
            )
        )

    qualified.sort(key=lambda p: (p.score, p.ev_per_unit), reverse=True)
    return qualified


def generate_singles(picks: list[QualifiedPick], config: BettingConfig) -> list[BetCombo]:
    """
    Generate single bets with Kelly-weighted stakes.

    Stake = bankroll * kelly_quarter, capped:
      - min: stake_per_combo
      - max: 5% of bankroll
    """
    combos = []
    for p in picks:
        stake = config.bankroll * p.kelly_quarter
        stake = max(stake, config.stake_per_combo)
        stake = min(stake, config.bankroll * 0.05)

        potential_return = stake * p.decimal_odds

        combos.append(
            BetCombo(
                type="single",
                picks=[p],
                combined_prob=round(p.model_prob, 4),
                combined_odds=round(p.decimal_odds, 4),
                ev=round(p.ev_per_unit, 4),
                stake=round(stake, 2),
                potential_return=round(potential_return, 2),
                hit=p.hit,
            )
        )
    return combos


def generate_round_robin(
    picks: list[QualifiedPick],
    n_legs: int,
    config: BettingConfig,
    min_combined_prob: float = 0.0,
    min_combo_ev: float = 0.0,
) -> list[BetCombo]:
    """
    Generate round-robin combos of n_legs from qualified picks.
    For doubles: n_legs=2, all C(N,2) combinations.
    For triples: n_legs=3, all C(N,3) combinations, only if len(picks) >= 5.

    Stake: config.stake_per_combo (fixed per combo).
    Combined odds: product of decimal_odds.
    Combined prob: product of model_prob.
    EV: combined_prob * combined_odds - 1.
    Hit: all picks hit (if all resolved), else None.

    Combos below `min_combined_prob` or `min_combo_ev` are discarded.
    Defaults (0.0) keep the legacy behaviour (no combo-level filtering).
    """
    if n_legs == 3 and len(picks) < 5:
        return []
    if len(picks) < n_legs:
        return []

    combos = []
    for combo_picks in combinations(picks, n_legs):
        combined_odds = 1.0
        combined_prob = 1.0
        all_resolved = True
        all_hit = True

        for p in combo_picks:
            combined_odds *= p.decimal_odds
            combined_prob *= p.model_prob
            if p.hit is None:
                all_resolved = False
            elif not p.hit:
                all_hit = False

        ev = combined_prob * combined_odds - 1

        # Combo-level filters (per bet type).
        # `min_combined_prob == 0` and `min_combo_ev == 0` both mean "no filter"
        # — so negative-EV combos still pass at defaults (legacy behaviour).
        if min_combined_prob > 0 and combined_prob < min_combined_prob:
            continue
        if min_combo_ev > 0 and ev < min_combo_ev:
            continue

        potential_return = config.stake_per_combo * combined_odds
        hit = all_hit if all_resolved else None

        combo_type = "double" if n_legs == 2 else "triple"
        combos.append(
            BetCombo(
                type=combo_type,
                picks=list(combo_picks),
                combined_prob=round(combined_prob, 4),
                combined_odds=round(combined_odds, 4),
                ev=round(ev, 4),
                stake=round(config.stake_per_combo, 2),
                potential_return=round(potential_return, 2),
                hit=hit,
            )
        )
    return combos


def _scale_bucket(combos: list[BetCombo], scale: float) -> None:
    for c in combos:
        c.stake = round(c.stake * scale, 2)
        c.potential_return = round(c.stake * c.combined_odds, 2)


def apply_exposure_cap(
    singles: list[BetCombo],
    doubles: list[BetCombo],
    triples: list[BetCombo],
    config: BettingConfig,
) -> None:
    """
    Two-stage exposure control (modifies combos in-place):

    1) Per-type cap — if `exposure_pct_<type>` > 0, that bucket is scaled down
       so its aggregate stake does not exceed `bankroll * weight`. Each bucket
       is independent: a blow-up in triples will not cannibalise singles/doubles.
       Defaults (0.0) leave the bucket unaffected.

    2) Global cap — finally, if the TOTAL stake still exceeds
       `bankroll * max_event_exposure_pct`, everything is scaled proportionally
       (legacy behaviour). This acts as a hard overall ceiling.
    """
    # Stage 1: per-bucket cap.
    buckets: list[tuple[list[BetCombo], float]] = [
        (singles, config.exposure_pct_singles),
        (doubles, config.exposure_pct_doubles),
        (triples, config.exposure_pct_triples),
    ]
    for combos, weight in buckets:
        if weight <= 0:
            continue
        bucket_stake = sum(c.stake for c in combos)
        bucket_cap = config.bankroll * weight
        if bucket_stake > bucket_cap and bucket_stake > 0:
            _scale_bucket(combos, bucket_cap / bucket_stake)

    # Stage 2: global cap across all buckets.
    total_stake = (
        sum(c.stake for c in singles)
        + sum(c.stake for c in doubles)
        + sum(c.stake for c in triples)
    )
    max_allowed = config.bankroll * config.max_event_exposure_pct
    if total_stake > max_allowed and total_stake > 0:
        scale = max_allowed / total_stake
        for combo_list in (singles, doubles, triples):
            _scale_bucket(combo_list, scale)


def generate_event_plan(
    fights: list[dict],
    config: BettingConfig,
    event_name: str = "",
    effective_bankroll: float | None = None,
) -> RecommendResponse:
    """
    Full pipeline: qualify picks -> generate all bet types -> apply exposure cap -> return response.

    If effective_bankroll is provided (compound mode), overrides config.bankroll and
    computes parlay stake dynamically from parlay_stake_pct.
    """
    if effective_bankroll is not None:
        combo_stake = (
            effective_bankroll * config.parlay_stake_pct
            if config.compound_mode
            else config.stake_per_combo
        )
        working_config = config.model_copy(
            update={"bankroll": effective_bankroll, "stake_per_combo": combo_stake}
        )
    else:
        working_config = config

    all_picks = qualify_picks(fights, working_config)

    exclusion_set = set(working_config.excluded_picks)
    for p in all_picks:
        key = f"{p.fighter_1} vs {p.fighter_2}"
        p.excluded = key in exclusion_set

    available = [p for p in all_picks if not p.excluded]

    # Independent per-type probability thresholds.
    # - Singles always use `min_model_prob`.
    # - Doubles/triples use their per-leg threshold when > 0; otherwise they
    #   fall back to `min_model_prob` (preserves legacy/default behaviour).
    thr_single = working_config.min_model_prob
    thr_double = working_config.min_prob_leg_double or working_config.min_model_prob
    thr_triple = working_config.min_prob_leg_triple or working_config.min_model_prob

    cap = working_config.max_picks_per_event
    singles_pool = [p for p in available if p.model_prob >= thr_single][:cap]
    doubles_pool = [p for p in available if p.model_prob >= thr_double][:cap]
    triples_pool = [p for p in available if p.model_prob >= thr_triple][:cap]

    singles = generate_singles(singles_pool, working_config)
    doubles = (
        generate_round_robin(
            doubles_pool,
            2,
            working_config,
            min_combined_prob=working_config.min_combined_prob_double,
            min_combo_ev=working_config.min_combo_ev,
        )
        if working_config.max_parlay_legs >= 2
        else []
    )
    triples = (
        generate_round_robin(
            triples_pool,
            3,
            working_config,
            min_combined_prob=working_config.min_combined_prob_triple,
            min_combo_ev=working_config.min_combo_ev,
        )
        if working_config.max_parlay_legs >= 3
        else []
    )

    # Representative pool shown in the response (used by the UI's qualified picks list).
    picks = singles_pool

    apply_exposure_cap(singles, doubles, triples, working_config)

    total_stake = (
        sum(c.stake for c in singles)
        + sum(c.stake for c in doubles)
        + sum(c.stake for c in triples)
    )
    expected_return = (
        sum(c.combined_prob * c.potential_return for c in singles)
        + sum(c.combined_prob * c.potential_return for c in doubles)
        + sum(c.combined_prob * c.potential_return for c in triples)
    )

    summary = RecommendSummary(
        total_stake=round(total_stake, 2),
        exposure_pct=round(total_stake / working_config.bankroll, 4) if working_config.bankroll > 0 else 0,
        n_singles=len(singles),
        n_doubles=len(doubles),
        n_triples=len(triples),
        expected_return=round(expected_return, 2),
    )

    return RecommendResponse(
        event_name=event_name,
        config=config,
        all_qualified_picks=all_picks,
        qualified_picks=picks,
        singles=singles,
        doubles=doubles,
        triples=triples,
        summary=summary,
        effective_bankroll=effective_bankroll,
    )
