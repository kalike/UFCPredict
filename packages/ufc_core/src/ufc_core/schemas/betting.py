"""
UFC Predictor — Schemas for the betting router.
"""

from pydantic import BaseModel, Field


class BettingConfig(BaseModel):
    """Configurable parameters for betting strategies."""

    min_consensus_pct: float = Field(100, ge=50, le=100)
    min_model_prob: float = Field(0.52, ge=0.50, le=0.80)
    max_parlay_legs: int = Field(3, ge=2, le=3)
    kelly_fraction: float = Field(0.25, ge=0.10, le=0.50)
    max_event_exposure_pct: float = Field(0.16, ge=0.05, le=0.30)
    max_picks_per_event: int = Field(8, ge=3, le=12)
    bankroll: float = Field(3000, ge=100, le=1_000_000)
    stake_per_combo: float = Field(30, ge=1, le=10_000)
    compound_mode: bool = Field(False)
    bankroll_floor: float = Field(500, ge=0, le=100000)
    parlay_stake_pct: float = Field(0.01, ge=0.001, le=0.05)
    min_pit_fights: int = Field(0, ge=0, le=20)
    # Per-type thresholds (default 0.0 = neutral, no extra filter).
    min_prob_leg_double: float = Field(0.0, ge=0.0, le=0.95)
    min_prob_leg_triple: float = Field(0.0, ge=0.0, le=0.95)
    min_combined_prob_double: float = Field(0.0, ge=0.0, le=0.95)
    min_combined_prob_triple: float = Field(0.0, ge=0.0, le=0.95)
    min_combo_ev: float = Field(0.0, ge=0.0, le=1.0)
    # Per-type exposure caps (fraction of bankroll). 0.0 = disabled for that type
    # → only the global `max_event_exposure_pct` applies (legacy behaviour).
    exposure_pct_singles: float = Field(0.0, ge=0.0, le=0.30)
    exposure_pct_doubles: float = Field(0.0, ge=0.0, le=0.30)
    exposure_pct_triples: float = Field(0.0, ge=0.0, le=0.30)
    excluded_picks: list[str] = Field(default_factory=list)


class QualifiedPick(BaseModel):
    fighter_1: str
    fighter_2: str
    pick: str
    pick_odds_american: int
    model_prob: float
    decimal_odds: float
    implied_prob: float
    edge: float
    ev_per_unit: float
    kelly_full: float
    kelly_quarter: float
    score: float
    consensus_pct: float
    excluded: bool = False
    hit: bool | None = None  # null = pending


class BetCombo(BaseModel):
    type: str  # "single", "double", "triple"
    picks: list[QualifiedPick]
    combined_prob: float
    combined_odds: float
    ev: float
    stake: float
    potential_return: float
    hit: bool | None = None


class RecommendSummary(BaseModel):
    total_stake: float
    exposure_pct: float
    n_singles: int
    n_doubles: int
    n_triples: int
    expected_return: float


class RecommendResponse(BaseModel):
    event_name: str
    config: BettingConfig
    all_qualified_picks: list[QualifiedPick]
    qualified_picks: list[QualifiedPick]
    singles: list[BetCombo]
    doubles: list[BetCombo]
    triples: list[BetCombo]
    summary: RecommendSummary
    effective_bankroll: float | None = None


class ComboDetail(BaseModel):
    """Lightweight combo representation for backtest event details."""

    type: str  # "double", "triple"
    pick_names: list[str]
    combined_odds: float
    combined_prob: float
    ev: float
    stake: float
    potential_return: float
    hit: bool | None = None


class EventBacktestDetail(BaseModel):
    event_name: str
    date: str
    n_qualified: int
    n_bets: int
    stake: float
    returned: float
    profit: float
    picks_hit_rate: float
    picks: list[dict]
    combos: list[ComboDetail] = []
    working_bankroll: float = 0.0


class StrategyResult(BaseModel):
    total_bets: int
    total_stake: float
    total_return: float
    profit: float
    roi_pct: float
    hit_rate_picks: float
    hit_rate_parlays: float
    max_drawdown: float
    sharpe_ratio: float
    events: list[EventBacktestDetail]
    cumulative_pnl: list[float]
    bankroll_history: list[float] = []


class BacktestResponse(BaseModel):
    config: BettingConfig
    strategies: dict[str, StrategyResult]  # keys: singles, doubles, triples, baseline
    best_strategy: str
    total_events: int


class CompareRequest(BaseModel):
    configs: list[BettingConfig]


class CompareResponse(BaseModel):
    results: list[BacktestResponse]
