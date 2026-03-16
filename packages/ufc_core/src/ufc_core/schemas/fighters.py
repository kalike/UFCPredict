"""
UFC Predictor — Schemas for the fighters router.
"""

from pydantic import BaseModel

from .base import CareerStats, FighterPhysicalStats, FightRawStats


class FighterSummary(BaseModel):
    name: str
    record: str = ""
    height: str = ""
    weight: str = ""
    reach: str = ""
    n_fights: int = 0
    has_photo: bool = False


class RecentFightRecord(BaseModel):
    result: str = ""
    opponent: str = ""
    method: str = ""
    round: str = ""
    event: str = ""
    event_date: str = ""


class FightStatsRecord(BaseModel):
    """Per-fight raw statistics for one fighter."""

    fight_index: int = 0
    result: str = ""
    opponent: str = ""
    method: str = ""
    round: str = ""
    event: str = ""
    event_date: str = ""
    kd_landed: int = 0
    kd_received: int = 0
    sig_str_landed: int = 0
    sig_str_attempted: int = 0
    sig_str_received: int = 0
    sig_str_received_attempted: int = 0
    td_landed: int = 0
    td_attempted: int = 0
    td_received: int = 0
    td_received_attempted: int = 0
    sub_att: int = 0
    reversals: int = 0
    ctrl_seconds: int = 0
    opp_ctrl_seconds: int = 0
    head_landed: int = 0
    body_landed: int = 0
    leg_landed: int = 0
    distance_landed: int = 0
    clinch_landed: int = 0
    ground_landed: int = 0


class FightMatchupResponse(BaseModel):
    """Both fighters' raw stats from a specific fight."""

    fighter: str = ""
    opponent: str = ""
    event: str = ""
    result: str = ""
    method: str = ""
    round: str = ""
    fighter_stats: FightRawStats = FightRawStats()
    opponent_stats: FightRawStats = FightRawStats()


class FighterDetail(BaseModel):
    name: str
    stats: FighterPhysicalStats = FighterPhysicalStats()
    n_fights: int = 0
    career_stats: CareerStats = CareerStats()
    elo: float = 1500.0
    has_photo: bool = False
    photo_url: str = ""
    recent_fights: list[RecentFightRecord] = []


class FighterStatsResponse(BaseModel):
    """Response for GET /api/fighters/{name}/stats."""

    name: str
    n_fights: int = 0
    career: CareerStats = CareerStats()
    elo: float = 1500.0
    recent_fights: list[RecentFightRecord] = []
