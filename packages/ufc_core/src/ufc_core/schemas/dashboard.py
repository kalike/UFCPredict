"""
UFC Predictor — Schemas for the dashboard router.
"""

from pydantic import BaseModel

from .predictions import FightPrediction


class EventFightResult(BaseModel):
    event: str
    date: str | None
    fighter_1: str
    fighter_2: str
    predicted_winner: str
    real_winner: str
    correct: bool
    consensus_pct: float


class ModelAverageAccuracy(BaseModel):
    avg_accuracy: float | None
    n_events: int
    total_correct: int
    total_fights: int


class EventAccuracySummary(BaseModel):
    event: str
    date: str | None
    location: str
    n_fights: int
    n_fights_valid: int
    is_past: bool
    accuracy_by_model: dict[str, dict]
    overall_accuracy: float | None


class DashboardSummaryResponse(BaseModel):
    all_event_results: list[EventAccuracySummary]
    avg_by_model: dict[str, ModelAverageAccuracy]
    recent_fights: list[EventFightResult]
    model_shorts: list[str]
    n_past_events: int
    n_predicted_events: int
    n_fighters: int


class InvalidateCacheResponse(BaseModel):
    ok: bool


class EventFightsResponse(BaseModel):
    event: str
    fights: list[FightPrediction]
