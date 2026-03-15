"""
UFC Predictor — Combo Search schemas (Pydantic v2).

Used by Phase A warmup endpoint and reused in Phases C/D for the full search.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComboWarmupRequest(BaseModel):
    top_k: int = Field(3, ge=1, le=50)
    shorts: list[str] | None = None


class ComboWarmupStatus(BaseModel):
    active: bool
    processed: int
    total: int
    message: str
    error: str | None = None


class ComboSearchStartRequest(BaseModel):
    n_trials: int = Field(200, ge=10, le=50000)
    top_k: int = Field(3, ge=1, le=50)
    weighting: Literal["stake", "equal", "max", "min", "geometric"] = "min"
    cv_split: int = Field(10, ge=1, le=50)
    study_name: str | None = None
    # Minimum bets per strategy for a trial to count — below this the trial is
    # pruned. Forces Optuna to explore combos where singles/doubles/triples all
    # produce enough volume instead of "turning off" hard strategies.
    min_bets_per_strategy: int = Field(5, ge=0, le=100)
    # Minimum total stake (in dollars) per strategy. Complements min_bets: a
    # trial can only satisfy both if each strategy has real volume AND real
    # money committed — prevents Optuna from routing all stake to singles
    # while keeping doubles/triples alive with $1 bets.
    min_stake_per_strategy: float = Field(0.0, ge=0.0, le=1_000_000.0)
    # Optional subset of model shorts to include in the pool. None = all 19.
    shorts: list[str] | None = None
    # Discard the N oldest promoted events before splitting train/test. Useful
    # when early events sit in a low-rentability regime (cold model) and drag
    # the optimisation towards the wrong baseline. 0 = use everything.
    skip_first_n_events: int = Field(0, ge=0, le=200)
    # Seed the optimiser with a known-good starting point so TPE converges
    # around it instead of exploring from scratch. When enabled with
    # `warm_start_config`/`warm_start_combo`, trial #0 runs those values
    # exactly; otherwise falls back to the live registry + BettingConfig().
    warm_start: bool = False
    warm_start_config: dict | None = None
    warm_start_combo: dict[str, int] | None = None


class ComboSearchTrialResult(BaseModel):
    trial_number: int
    combo: dict[str, int]
    config: dict
    sharpe_global_train: float
    sharpe_global_test: float
    sharpe_singles: float
    sharpe_doubles: float
    sharpe_triples: float
    roi_pct_best: float
    max_drawdown_worst: float
    duration_secs: float
    is_best: bool = False


class ComboSearchStatus(BaseModel):
    active: bool
    study_id: str | None = None
    study_name: str | None = None
    trial_current: int = 0
    n_trials: int = 0
    top_k: int = 0
    weighting: str = "min"
    cv_split: int = 0
    min_bets_per_strategy: int = 5
    min_stake_per_strategy: float = 0.0
    shorts: list[str] | None = None
    skip_first_n_events: int = 0
    best_trial: ComboSearchTrialResult | None = None
    trials: list[ComboSearchTrialResult] = []
    error: str | None = None
    version_pool: dict[str, list[int]] = {}


class ComboSearchStartResponse(BaseModel):
    ok: bool
    study_id: str
    n_trials: int
    message: str


class ComboSearchEvaluateRequest(BaseModel):
    """Evaluate a specific (combo, config) with the same pipeline as the search.

    Lets you compare your manually calibrated setup against Optuna's best
    trial on equal footing (same cv_split, same skip, same weighting).
    """
    # None = read from the live model_registry (disabled_models + active_version).
    combo: dict[str, int] | None = None
    # None = BettingConfig() defaults. Pass your `calibrated_v1` dict here.
    config: dict | None = None
    weighting: Literal["stake", "equal", "max", "min", "geometric"] = "min"
    cv_split: int = Field(10, ge=1, le=50)
    skip_first_n_events: int = Field(0, ge=0, le=200)


class ComboSearchStudyAnalysis(BaseModel):
    """Analytical summary of a completed combo search study.

    Meant to answer the usual questions a human asks after a run:
    which models appear consistently in the top trials, which parameter
    ranges converged, and whether the best trial is a real improvement
    over the baseline or an overfit artefact.
    """
    study_id: str
    study_name: str | None = None
    n_trials_total: int
    n_trials_valid: int           # not null sharpe_global_train
    top_k_analysed: int           # how many trials fed the model/param stats
    # Scores
    baseline_train: float | None = None        # if caller supplied baseline
    best_trial_number: int | None = None
    best_sharpe_train: float | None = None
    best_sharpe_test: float | None = None
    best_combo: dict[str, int] | None = None
    best_config: dict | None = None
    # Model frequency in top-K trials
    model_frequency: dict[str, float]       # short -> fraction in [0.0, 1.0]
    version_frequency: dict[str, dict[int, float]]   # short -> {v_idx -> fraction}
    # Config parameter convergence in top-K
    param_ranges: dict[str, dict[str, float]]     # param -> {mean, std, min, max}
    # Overfit diagnostic
    mean_gap_train_minus_test: float | None = None
    # Recommendation
    recommendation: str           # APPLY | HOLD | OVERFIT | INCONCLUSIVE
    recommendation_reason: str


class ComboSearchEvaluateResponse(BaseModel):
    combo: dict[str, int]
    config: dict
    weighting: str
    # Scores
    sharpe_global_train: float
    sharpe_global_test: float
    # Per-strategy, per-split
    sharpe_singles_train: float
    sharpe_singles_test: float
    sharpe_doubles_train: float
    sharpe_doubles_test: float
    sharpe_triples_train: float
    sharpe_triples_test: float
    # Volume
    n_train_events: int
    n_test_events: int
    train_bets: dict   # {singles: int, doubles: int, triples: int}
    test_bets: dict
    train_roi_pct: dict
    test_roi_pct: dict
    # Diagnostics
    missing_cache_pairs: list[list]   # [[short, version_idx], ...]
