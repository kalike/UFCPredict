"""Backtest engine: runs betting strategies over promoted lab sessions."""
from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from lab_api.schemas.betting import (
    BacktestResponse,
    BettingConfig,
    ComboDetail,
    EventBacktestDetail,
    StrategyResult,
)
from lab_api.services.betting_engine import american_to_decimal, generate_event_plan
from lab_api.services.lab_session_provider import list_promoted_sessions


def run_backtest(db: Session, config: BettingConfig) -> BacktestResponse:
    """Run a full backtest over all promoted lab sessions with real results."""
    sessions = list_promoted_sessions(db)
    return _backtest_over_sessions(sessions, config)


def _backtest_over_sessions(
    sessions: list[dict],
    config: BettingConfig,
) -> BacktestResponse:
    """Core backtest loop. Assumes `sessions` is the list of dicts ready
    to iterate: each session has keys `event`, `created_at`, `fights` (list of dicts).
    """
    # Per-strategy accumulators
    strategy_keys = ("singles", "doubles", "triples", "baseline")
    strategies_data: dict[str, dict] = {k: {"bets": [], "events": []} for k in strategy_keys}
    pnl_history: dict[str, list[float]] = {k: [0.0] for k in strategy_keys}

    # Compound bankroll tracking (single shared bankroll across strategies)
    working_bankroll = config.bankroll
    bankroll_history: list[float] = [config.bankroll]

    for session in sessions:
        event_name = session.get("event", "Unknown")
        created_at = session.get("created_at", "")
        fight_dicts = session.get("fights", [])

        # ── Generate plan for this event ─────────────────────────────────
        plan = generate_event_plan(
            fight_dicts,
            config,
            event_name,
            effective_bankroll=working_bankroll if config.compound_mode else None,
        )
        date_str = created_at[:10] if created_at else ""

        # Track total event PnL for compound bankroll update
        total_event_profit = 0.0

        # ── singles / doubles / triples ──────────────────────────────────
        for strategy_key, combos in (
            ("singles", plan.singles),
            ("doubles", plan.doubles),
            ("triples", plan.triples),
        ):
            event_stake = sum(c.stake for c in combos)
            event_return = 0.0
            n_hit = 0
            n_resolved = 0

            for combo in combos:
                if combo.hit is not None:
                    n_resolved += 1
                    if combo.hit:
                        event_return += combo.potential_return
                        n_hit += 1
                strategies_data[strategy_key]["bets"].append(combo)

            event_profit = event_return - event_stake
            total_event_profit += event_profit
            hit_rate = n_hit / n_resolved if n_resolved > 0 else 0.0

            # Map each qualified pick to the stake of its single bet (when
            # this strategy is "singles"). Doubles/triples don't assign a
            # per-pick stake, so we leave it as None.
            single_stake_by_pick: dict[str, float] = {}
            if strategy_key == "singles":
                for c in combos:
                    if c.type == "single" and c.picks:
                        single_stake_by_pick[c.picks[0].pick] = round(c.stake, 2)

            # Build combo details for doubles/triples
            combo_details = [
                ComboDetail(
                    type=c.type,
                    pick_names=[p.pick for p in c.picks],
                    combined_odds=round(c.combined_odds, 4),
                    combined_prob=round(c.combined_prob, 4),
                    ev=round(c.ev, 4),
                    stake=round(c.stake, 2),
                    potential_return=round(c.potential_return, 2),
                    hit=c.hit,
                )
                for c in combos
                if c.type in ("double", "triple")
            ]

            strategies_data[strategy_key]["events"].append(
                EventBacktestDetail(
                    event_name=event_name,
                    date=date_str,
                    n_qualified=len(plan.qualified_picks),
                    n_bets=len(combos),
                    stake=round(event_stake, 2),
                    returned=round(event_return, 2),
                    profit=round(event_profit, 2),
                    picks_hit_rate=round(hit_rate, 4),
                    picks=[
                        {
                            "pick": p.pick,
                            "fighter_1": p.fighter_1,
                            "fighter_2": p.fighter_2,
                            "odds": p.decimal_odds,
                            "prob": p.model_prob,
                            "hit": p.hit,
                            "stake": single_stake_by_pick.get(p.pick),
                        }
                        for p in plan.qualified_picks
                    ],
                    combos=combo_details,
                    working_bankroll=round(working_bankroll, 2),
                )
            )

            pnl_history[strategy_key].append(
                round(pnl_history[strategy_key][-1] + event_profit, 2)
            )

        # ── Baseline: flat bet on every consensus pick with odds ──────────
        baseline_bet = (
            10.0 * (working_bankroll / config.bankroll)
            if config.compound_mode and config.bankroll > 0
            else 10.0
        )
        baseline_stake = 0.0
        baseline_return = 0.0
        baseline_hits = 0
        baseline_total = 0

        for f in fight_dicts:
            cw = f.get("consensus_winner")
            rw = f.get("real_winner")
            if not cw or not rw:
                continue

            odds_am = (
                f.get("odds_f1_american")
                if cw == f.get("fighter_1")
                else f.get("odds_f2_american")
            )
            if not odds_am:
                continue

            baseline_total += 1
            baseline_stake += baseline_bet
            dec_odds = american_to_decimal(odds_am)
            if dec_odds is None:
                baseline_total -= 1
                baseline_stake -= baseline_bet
                continue
            if cw == rw:
                baseline_return += baseline_bet * dec_odds
                baseline_hits += 1

        baseline_profit = baseline_return - baseline_stake
        strategies_data["baseline"]["events"].append(
            EventBacktestDetail(
                event_name=event_name,
                date=date_str,
                n_qualified=baseline_total,
                n_bets=baseline_total,
                stake=round(baseline_stake, 2),
                returned=round(baseline_return, 2),
                profit=round(baseline_profit, 2),
                picks_hit_rate=(
                    round(baseline_hits / baseline_total, 4) if baseline_total > 0 else 0.0
                ),
                picks=[],
                working_bankroll=round(working_bankroll, 2),
            )
        )
        pnl_history["baseline"].append(round(pnl_history["baseline"][-1] + baseline_profit, 2))

        # ── Update bankroll history after event ──────────────────────────
        if config.compound_mode:
            working_bankroll += total_event_profit
            working_bankroll = max(working_bankroll, config.bankroll_floor)
            bankroll_history.append(round(working_bankroll, 2))
        else:
            # Flat staking: track bankroll evolution without reinvestment.
            bankroll_history.append(round(bankroll_history[-1] + total_event_profit, 2))

    # ── Build StrategyResult for each strategy ────────────────────────────
    strategy_results: dict[str, StrategyResult] = {}
    best_roi = float("-inf")
    best_strategy = "singles"

    for key in strategy_keys:
        events = strategies_data[key]["events"]
        total_stake = sum(e.stake for e in events)
        total_return = sum(e.returned for e in events)
        profit = total_return - total_stake
        roi_pct = (profit / total_stake * 100) if total_stake > 0 else 0.0

        # Hit rates
        if key == "baseline":
            total_bets = sum(e.n_bets for e in events)
            weighted_hits = sum(e.n_bets * e.picks_hit_rate for e in events)
            hit_rate_picks = weighted_hits / total_bets if total_bets > 0 else 0.0
            hit_rate_parlays = hit_rate_picks
        else:
            bets = strategies_data[key]["bets"]
            resolved = [b for b in bets if b.hit is not None]
            hit_rate_parlays = (
                sum(1 for b in resolved if b.hit) / len(resolved) if resolved else 0.0
            )
            # Individual pick hit rate across all qualified picks in events
            pick_hit_flags: list[bool] = []
            for e in events:
                for p in e.picks:
                    if p.get("hit") is not None:
                        pick_hit_flags.append(bool(p["hit"]))
            hit_rate_picks = (
                sum(pick_hit_flags) / len(pick_hit_flags) if pick_hit_flags else 0.0
            )

        max_dd = _max_drawdown(pnl_history[key])

        event_roi_series: list[float] = [e.profit / e.stake for e in events if e.stake > 0]
        sharpe = _sharpe_ratio(event_roi_series)

        total_bets_count = sum(e.n_bets for e in events)

        strategy_results[key] = StrategyResult(
            total_bets=total_bets_count,
            total_stake=round(total_stake, 2),
            total_return=round(total_return, 2),
            profit=round(profit, 2),
            roi_pct=round(roi_pct, 2),
            hit_rate_picks=round(hit_rate_picks, 4),
            hit_rate_parlays=round(hit_rate_parlays, 4),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 4),
            events=events,
            cumulative_pnl=pnl_history[key],
            bankroll_history=bankroll_history,
        )

        if key != "baseline" and roi_pct > best_roi:
            best_roi = roi_pct
            best_strategy = key

    return BacktestResponse(
        config=config,
        strategies=strategy_results,
        total=_aggregate_total(strategies_data, pnl_history, bankroll_history),
        best_strategy=best_strategy,
        total_events=len(sessions),
    )


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


def _aggregate_total(strategies_data: dict, pnl_history: dict,
                     bankroll_history: list[float]) -> StrategyResult:
    """Aggregate singles+doubles+triples (excludes baseline) into one StrategyResult.

    Per-event stake/return/profit are summed across the three bet types. The
    `max_drawdown` and `sharpe_ratio` are computed over the COMBINED cumulative
    PnL series (point-by-point sum of the three per-strategy series), so Max DD
    represents the largest continuous loss of the whole three-type portfolio.
    """
    comp = ("singles", "doubles", "triples")
    comp_events = [strategies_data[k]["events"] for k in comp]
    n_ev = len(comp_events[0]) if comp_events[0] else 0

    total_events: list[EventBacktestDetail] = []
    for i in range(n_ev):
        evs = [ce[i] for ce in comp_events]
        base = evs[0]
        stake = sum(e.stake for e in evs)
        returned = sum(e.returned for e in evs)
        total_events.append(EventBacktestDetail(
            event_name=base.event_name,
            date=base.date,
            n_qualified=base.n_qualified,
            n_bets=sum(e.n_bets for e in evs),
            stake=round(stake, 2),
            returned=round(returned, 2),
            profit=round(returned - stake, 2),
            picks_hit_rate=base.picks_hit_rate,
            picks=base.picks,
            combos=[c for e in evs for c in e.combos],
            working_bankroll=base.working_bankroll,
        ))

    # Combined cumulative PnL: point-by-point sum of the three series.
    comp_pnl = [pnl_history[k] for k in comp]
    length = len(comp_pnl[0])
    pnl_total = [round(sum(series[i] for series in comp_pnl), 2) for i in range(length)]

    total_stake = sum(e.stake for e in total_events)
    total_return = sum(e.returned for e in total_events)
    profit = total_return - total_stake
    roi_pct = (profit / total_stake * 100) if total_stake > 0 else 0.0

    all_bets = [b for k in comp for b in strategies_data[k]["bets"]]
    resolved = [b for b in all_bets if b.hit is not None]
    hit_parlays = (sum(1 for b in resolved if b.hit) / len(resolved)) if resolved else 0.0
    pick_flags = [bool(p["hit"]) for e in total_events for p in e.picks if p.get("hit") is not None]
    hit_picks = (sum(pick_flags) / len(pick_flags)) if pick_flags else 0.0
    roi_series = [e.profit / e.stake for e in total_events if e.stake > 0]

    return StrategyResult(
        total_bets=sum(e.n_bets for e in total_events),
        total_stake=round(total_stake, 2),
        total_return=round(total_return, 2),
        profit=round(profit, 2),
        roi_pct=round(roi_pct, 2),
        hit_rate_picks=round(hit_picks, 4),
        hit_rate_parlays=round(hit_parlays, 4),
        max_drawdown=round(_max_drawdown(pnl_total), 2),
        sharpe_ratio=round(_sharpe_ratio(roi_series), 4),
        events=total_events,
        cumulative_pnl=pnl_total,
        bankroll_history=bankroll_history,
    )


def _max_drawdown(pnl: list[float]) -> float:
    """Return maximum drawdown from a cumulative PnL series as a non-positive number.

    Example: [0, 10, 5, 12, 3] -> peak=12, trough=3, drawdown=-9.
    """
    if len(pnl) < 2:
        return 0.0
    peak = pnl[0]
    max_dd = 0.0
    for val in pnl[1:]:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    return -max_dd  # negative by convention


def _sharpe_ratio(returns: list[float]) -> float:
    """Annualised Sharpe ratio from per-event ROI values (mean / stdev).

    Returns 0.0 when fewer than two observations or zero variance.
    """
    if len(returns) < 2:
        return 0.0
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns)
    if std_r == 0.0:
        return 0.0
    return mean_r / std_r
