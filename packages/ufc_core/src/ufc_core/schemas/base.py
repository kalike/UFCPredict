"""
UFC Predictor — Base schemas: reusable types shared across domains.
"""

from pydantic import BaseModel


class OkResponse(BaseModel):
    ok: bool


class FighterPhysicalStats(BaseModel):
    """Pydantic form of fighters.stats JSONB."""

    height: str = ""
    weight: str = ""
    reach: str = ""
    stance: str = ""
    dob: str = ""
    slpm: float = 0.0
    striking_accuracy: float = 0.0
    sapm: float = 0.0
    striking_defense: float = 0.0
    tdd: float = 0.0
    td_accuracy: float = 0.0
    td_defense: float = 0.0
    sub_avg: float = 0.0

    model_config = {"extra": "allow"}


class CareerStats(BaseModel):
    """Aggregated career stats computed by feature_engine."""

    n_fights: int = 0
    n_wins: int = 0
    n_losses: int = 0
    n_draws: int = 0
    avg_kd_landed: float = 0.0
    avg_kd_received: float = 0.0
    avg_sig_str_landed: float = 0.0
    avg_sig_str_attempted: float = 0.0
    avg_td_landed: float = 0.0
    avg_td_attempted: float = 0.0
    avg_sub_att: float = 0.0
    avg_ctrl_seconds: float = 0.0

    model_config = {"extra": "allow"}


class FightRawStats(BaseModel):
    """Raw stats for one fighter in one fight (matchup endpoint)."""

    kd: int = 0
    sig_str_landed: int = 0
    sig_str_attempted: int = 0
    sig_str_received: int = 0
    td_landed: int = 0
    td_attempted: int = 0
    td_received: int = 0
    sub_att: int = 0
    reversals: int = 0
    ctrl_seconds: int = 0
    head_landed: int = 0
    body_landed: int = 0
    leg_landed: int = 0
    distance_landed: int = 0
    clinch_landed: int = 0
    ground_landed: int = 0

    model_config = {"extra": "allow"}
