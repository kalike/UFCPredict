"""
UFC Predictor — Schemas for the predictions router.
"""

from pydantic import BaseModel

from .tapology import TapologyCommunityPicks


class FightInput(BaseModel):
    fighter_1: str
    fighter_2: str
    odds_f1_american: int | None = None
    odds_f2_american: int | None = None
    community_picks: TapologyCommunityPicks | None = None


class EventPredictionRequest(BaseModel):
    event_name: str = ""
    fights: list[FightInput]


class ModelPrediction(BaseModel):
    full_name: str
    predicted_winner: str
    probability_f1: float
    confidence: float


class ConsensusResult(BaseModel):
    fighter_1_votes: int
    fighter_2_votes: int
    total_models: int
    consensus_winner: str
    consensus_pct: float


class FightPrediction(BaseModel):
    fighter_1: str
    fighter_2: str
    event: str = ""
    odds_f1_american: int | None = None
    odds_f2_american: int | None = None
    models: dict[str, ModelPrediction] = {}
    consensus: ConsensusResult | None = None
    fighter_1_has_history: bool = True
    fighter_2_has_history: bool = True
    fighter_1_n_fights: int | None = None
    fighter_2_n_fights: int | None = None
    community_picks: TapologyCommunityPicks | None = None


class PredictionResponse(BaseModel):
    event: str = ""
    n_fights: int
    n_models: int
    fights: list[FightPrediction]
    skipped: list[str] = []


class SaveSessionRequest(BaseModel):
    event: str
    fights: list[dict]  # full fight prediction data from frontend


class MarkResultRequest(BaseModel):
    fight_index: int
    real_winner: str | None = None


class PromoteRequest(BaseModel):
    event_date: str | None = None
    event_location: str | None = None


class PastEventSummary(BaseModel):
    name: str
    n_fights: int
    date: str | None


class ModelAccuracyItem(BaseModel):
    full_name: str
    accuracy: float | None
    correct: int
    total: int


class PastEventDetailResponse(BaseModel):
    event: str
    n_fights: int
    n_fights_valid: int
    accuracy: dict[str, ModelAccuracyItem]
    fights: list[FightPrediction]
    skipped: list[str]


class SaveSessionResponse(BaseModel):
    ok: bool
    id: str


class SessionFightData(BaseModel):
    """Structure of a fight within a saved session."""

    fighter_1: str
    fighter_2: str
    consensus_winner: str | None = None
    consensus_pct: float | None = None
    real_winner: str | None = None
    fighter_1_has_history: bool = True
    fighter_2_has_history: bool = True
    models: dict = {}
    community_picks: TapologyCommunityPicks | None = None

    model_config = {"extra": "allow"}


class SessionSummary(BaseModel):
    id: str
    event: str
    created_at: str
    n_fights: int
    n_results: int
    n_correct: int
    accuracy: float | None
    promoted: bool


class SessionDetailResponse(BaseModel):
    id: str
    event: str
    created_at: str
    n_fights: int
    promoted: bool
    fights: list[SessionFightData]

    model_config = {"extra": "allow"}


class MarkResultResponse(BaseModel):
    ok: bool
    n_results: int
    n_correct: int
    accuracy: float | None


class PromoteSessionResponse(BaseModel):
    ok: bool
    event: str
    n_fights: int
    message: str


# ── Parlay persistence ────────────────────────────────────────────────────

class ParlayInstanceSave(BaseModel):
    """One strategy instance (original or copy) to persist."""
    instance_id: str          # e.g. "safe-0", "safe-1"
    strategy_type: str        # e.g. "safe"
    picks: list[dict]         # serialised ParlayPick objects
    combined_odds: float | None = None
    combined_prob: float = 0.0
    ev: float | None = None
    kelly_pct: float | None = None


class SaveParlaysRequest(BaseModel):
    instances: list[ParlayInstanceSave]


class ParlayInstanceResponse(ParlayInstanceSave):
    id: int
    created_at: str
