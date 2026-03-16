"""Backtest engine: runs betting strategies over historical promoted sessions."""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

from ufc_core.schemas.betting import (
    BacktestResponse,
    BettingConfig,
    ComboDetail,
    EventBacktestDetail,
    StrategyResult,
)
from ufc_core.betting.engine import american_to_decimal, generate_event_plan

if TYPE_CHECKING:
    from ufc_core.betting._stubs import PredictionSessionService  # TODO(F1.T15): sessions not ported yet


class BacktestEngine:
    """Run backtests over promoted sessions with real results."""

    def __init__(self, session_service: PredictionSessionService) -> None:
        """
        Parameters
        ----------
        session_service:
            PredictionSessionService instance. Uses .list_all() for summaries
            and .get(id) for full session detail.
        """
        self._sessions = session_service

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_promoted_sessions(self) -> list[dict]:
        """Return full session dicts for all promoted sessions that have at least
        one fight with real_winner set."""
        summaries = self._sessions.list_all()
        promoted = [s for s in summaries if s.get("promoted", False)]

        sessions_data = []
        for s in promoted:
            detail = self._sessions.get(s["id"])
            if not detail:
                continue
            fights = detail.get("fights", [])
            if any(f.get("real_winner") for f in fights):
                sessions_data.append(detail)

        return sessions_data

    @staticmethod
    def _normalise_fights(fights: list) -> list[dict]:
        """Convert fight items to plain dicts regardless of source type."""
        result = []
        for f in fights:
            if hasattr(f, "model_dump"):
                result.append(f.model_dump())
            elif isinstance(f, dict):
                result.append(f)
            else:
                result.append(dict(f))
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_backtest(self, config: BettingConfig) -> BacktestResponse:
        """Run a full backtest with the given config over all promoted sessions.

        For every promoted session the engine:
        1. Generates a betting plan via generate_event_plan (singles/doubles/triples).
        2. Resolves each combo using the stored real_winner values.
        3. Tracks cumulative PnL, hit rates, drawdown, and Sharpe per strategy.
        4. Computes a flat-$10 baseline over every fight that has consensus data.

        Returns a BacktestResponse with per-strategy StrategyResult objects and
        the best non-baseline strategy by ROI.
        """
        raw = self._get_promoted_sessions()
        sessions = [
            {**s, "fights": self._normalise_fights(s.get("fights", []))}
            for s in raw
        ]
        return self._backtest_over_sessions(sessions, config)

    def _backtest_over_sessions(
        self,
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
            best_strategy=best_strategy,
            total_events=len(sessions),
        )


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


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
