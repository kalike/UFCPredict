"""
UFC Predictor — Schemas for the compare router.
"""

from pydantic import BaseModel

from .base import CareerStats, FighterPhysicalStats
from .predictions import FightPrediction


class CompareRequest(BaseModel):
    fighter_1: str
    fighter_2: str


class StatComparison(BaseModel):
    f1_value: float | str | None = None
    f2_value: float | str | None = None
    delta: float | None = None
    advantage: str | None = None  # "fighter_1" | "fighter_2" | "equal"


class FighterCompareStats(BaseModel):
    name: str
    stats: FighterPhysicalStats = FighterPhysicalStats()
    career: CareerStats = CareerStats()
    elo: float = 1500
    photo_url: str = ""


class CompareResponse(BaseModel):
    fighter_1: FighterCompareStats
    fighter_2: FighterCompareStats
    stat_comparison: dict[str, StatComparison] = {}
    prediction: FightPrediction | None = None
