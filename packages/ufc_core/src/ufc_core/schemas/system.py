"""
UFC Predictor — Schemas for the system router.
"""

from pydantic import BaseModel


class ModelInfo(BaseModel):
    name: str
    short: str
    features: str
    type: str
    n_features: int


class SystemStatus(BaseModel):
    data_loaded: bool
    models_loaded: bool
    n_fighters: int
    n_events: int
    n_models: int
    n_fight_cards: int
    data_source: str = "files"  # 'files' | 'postgresql'
