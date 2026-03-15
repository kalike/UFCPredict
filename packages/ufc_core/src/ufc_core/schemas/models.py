"""
UFC Predictor — Schemas for the model_management router.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ToggleRequest(BaseModel):
    active: bool


class AcceptRequest(BaseModel):
    version_index: int


class RetrainRequest(BaseModel):
    models: list[str]
    dataset: str = "since2010"
    augment: bool | None = None
    test_cutoff: int | str = 2024
    min_fights: int = 0
    use_pit: bool = False
    feature_set: str = "legacy"  # legacy | v2 | v3 | v4 | v5 | v6 | v7
    feat_type: str = "auto"  # "auto" (per model catalogue), "35f", or "52f"


class TrainJobConfig(BaseModel):
    """One model + one specific training configuration."""
    model: str
    dataset: str = "since2010"
    augment: bool | None = None
    test_cutoff: int | str = 2024
    min_fights: int = 0
    use_pit: bool = False
    feature_set: str = "legacy"  # legacy | v2 | v3 | v4 | v5 | v6 | v7
    feat_type: str = "auto"


class BatchRetrainRequest(BaseModel):
    """A list of training jobs to execute sequentially."""
    jobs: list[TrainJobConfig]


class ModelMetrics(BaseModel):
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    auc: float | None = None
    train_accuracy: float | None = None
    test_cutoff: int | None = None
    n_train: int | None = None
    n_test: int | None = None

    model_config = {"extra": "allow"}


class ModelVersion(BaseModel):
    version: int
    trained_at: str
    metrics: ModelMetrics
    is_active: bool
    dataset: str | None = None


class ModelListItem(BaseModel):
    name: str
    short: str
    model_type: str  # sklearn | pytorch | virtual
    n_features: int
    active: bool
    n_versions: int
    current_version: int | None
    test_accuracy: float | None
    real_accuracy: float | None


class ModelDetailResponse(BaseModel):
    name: str
    short: str
    model_type: str
    n_features: int
    active: bool
    params: dict = {}
    feature_list: list[str] = []
    metrics: ModelMetrics = ModelMetrics()
    feature_importance: dict[str, float] | None = None
    versions: list[ModelVersion] = []


class ToggleModelResponse(BaseModel):
    ok: bool
    short: str
    active: bool


class AcceptVersionResponse(BaseModel):
    ok: bool
    short: str
    active_version: int


class DeleteVersionResponse(BaseModel):
    ok: bool
    short: str
    deleted_index: int


class MarkVersionRequest(BaseModel):
    """Update user-owned annotations on a version.

    starred=None leaves the flag untouched; pass True/False to change.
    note=None leaves the note untouched; pass "" to clear it.
    """
    starred: bool | None = None
    note: str | None = None


class MarkVersionResponse(BaseModel):
    ok: bool
    short: str
    version_index: int
    starred: bool
    note: str | None = None


class BatchDeleteVersionsRequest(BaseModel):
    indices: list[int]


class BatchDeleteVersionsResponse(BaseModel):
    ok: bool
    short: str
    deleted_indices: list[int]
    errors: list[str] = []


class RetrainStartResponse(BaseModel):
    ok: bool
    message: str
    models: list[str]
    n_jobs: int = 0


class TrainingResult(BaseModel):
    model: str
    short: str
    accuracy: float | None
    status: str  # completed | error | skipped


class TrainingStatusResponse(BaseModel):
    active: bool
    model_short: str | None
    step: str
    pct: float
    message: str
    error: str | None
    metrics: ModelMetrics | None
    results: list[TrainingResult]


# ---------------------------------------------------------------------------
# HP Search (Optuna)
# ---------------------------------------------------------------------------


class HyperparamSpec(BaseModel):
    """Definition of a hyperparameter to optimize."""
    name: str
    type: Literal["int", "float", "categorical"]
    low: float | None = None
    high: float | None = None
    step: float | None = None
    log: bool = False
    choices: list[Any] | None = None


class HpObjective(BaseModel):
    """A single optimization objective."""
    metric: str  # accuracy, logloss, brier, auc, f1, overfit
    direction: str = "auto"  # maximize, minimize, auto


class HpSearchRequest(BaseModel):
    """Request to launch hyperparameter search."""
    model: str
    version_index: int
    n_trials: int = 50
    metric: str = "accuracy"  # legacy single-metric (ignored if objectives set)
    objectives: list[HpObjective] | None = None
    search_space: list[HyperparamSpec]


class HpSearchStartResponse(BaseModel):
    ok: bool
    message: str
    model: str
    n_trials: int


class HpTrialResult(BaseModel):
    """Result of a single Optuna trial."""
    trial_number: int
    params: dict[str, Any]
    mean_accuracy: float | None = None
    mean_auc: float | None = None
    mean_f1: float | None = None
    mean_logloss: float | None = None
    mean_brier: float | None = None
    mean_overfit: float | None = None
    prod_accuracy: float | None = None
    prod_brier: float | None = None
    std_score: float | None = None
    fold_scores: list[float] | None = None
    is_best: bool = False
    is_pareto: bool = False
    best_value: float | None = None
    duration_secs: float


class HpAdoptRequest(BaseModel):
    """Request to adopt best HP search params — retrain with them."""
    model: str
    params: dict[str, Any]
    expected_accuracy: float | None = None
    dataset: str = "since2010"
    augment: bool | None = None
    test_cutoff: int | str = 2024
    min_fights: int = 0
    use_pit: bool = False
    feature_set: str = "legacy"  # legacy | v2 | v3 | v4 | v5 | v6 | v7
    feat_type: str = "auto"


class HpAdoptBatchRequest(BaseModel):
    """Adopt multiple HP trials at once — retrain each with its params."""
    model: str
    trials: list[dict[str, Any]]  # each dict has "params": {...}
    dataset: str = "since2010"
    augment: bool | None = None
    test_cutoff: int | str = 2024
    min_fights: int = 0
    use_pit: bool = False
    feature_set: str = "legacy"  # legacy | v2 | v3 | v4 | v5 | v6 | v7
    feat_type: str = "auto"


class HpAdoptMultiItem(BaseModel):
    """One adoption item: model + params + config."""
    model: str
    params: dict[str, Any]
    mean_accuracy: float | None = None
    dataset: str = "since2010"
    augment: bool | None = None
    min_fights: int = 2
    use_pit: bool = True
    feature_set: str = "v5"
    feat_type: str = "auto"


class HpAdoptMultiRequest(BaseModel):
    """Adopt trials from multiple models/jobs at once."""
    items: list[HpAdoptMultiItem]


class HpSearchJobConfig(BaseModel):
    """Config for a single HP search job in a batch queue."""
    model: str
    n_trials: int = 50
    objectives: list[HpObjective] | None = None
    search_space: list[dict[str, Any]] | None = None  # None = use model default
    dataset: str = "since2010"
    augment: bool | None = None
    min_fights: int = 2
    use_pit: bool = True
    feature_set: str = "v5"
    feat_type: str = "auto"


class HpSearchBatchRequest(BaseModel):
    """Queue of HP search jobs to run sequentially."""
    jobs: list[HpSearchJobConfig]


class HpSearchJobStatus(BaseModel):
    """Status of one job in the queue."""
    model: str
    feature_set: str
    min_fights: int
    n_trials: int
    status: str = "pending"  # pending | running | done | error
    baselines: dict[str, float] = {}
    best_trial: HpTrialResult | None = None
    trials: list[HpTrialResult] = []
    error: str | None = None


class HpSearchStatus(BaseModel):
    active: bool
    model_short: str | None = None
    trial_current: int = 0
    n_trials: int = 0
    metric: str = "accuracy"  # legacy compat
    objectives: list[HpObjective] = []
    baseline_value: float | None = None  # legacy compat
    baselines: dict[str, float] = {}
    best_trial: HpTrialResult | None = None
    trials: list[HpTrialResult] = []
    error: str | None = None
    version_config: dict[str, Any] | None = None
    # Queue fields
    queue_index: int = 0      # current job (0-indexed)
    queue_total: int = 0      # total jobs in queue
    queue_jobs: list[HpSearchJobStatus] = []  # status of each job


class BiasTestDetail(BaseModel):
    pass_rate: float | None = None
    n_tests: int = 0
    details: dict = {}


class ModelBiasResult(BaseModel):
    short: str
    tests: dict[str, BiasTestDetail]
    pass_all: bool


class BiasReportResponse(BaseModel):
    ran_at: str
    n_fights: int
    n_swapped: int
    models: dict[str, ModelBiasResult]


# ---------------------------------------------------------------------------
# Model combinations (presets of active models + active versions)
# ---------------------------------------------------------------------------


class ModelComboEntry(BaseModel):
    active: bool
    active_version: int | None = None


class ModelCombination(BaseModel):
    name: str
    description: str | None = None
    created_at: str
    updated_at: str
    models: dict[str, ModelComboEntry]


class SaveCombinationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=280)
    overwrite: bool = False

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class ApplyCombinationResponse(BaseModel):
    ok: bool
    name: str
    applied: list[str]
    skipped_unknown: list[str]
    clamped_versions: list[str] = []
    recalculation_started: bool = False
    recalculation_reason: str | None = None


class DeleteCombinationResponse(BaseModel):
    ok: bool
    name: str
