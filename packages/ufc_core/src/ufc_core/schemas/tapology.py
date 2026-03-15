"""
UFC Predictor — Schemas for the Tapology scraping router.
"""

from pydantic import BaseModel


class TapologyMethodBreakdown(BaseModel):
    ko_tko_pct: float = 0.0
    submission_pct: float = 0.0
    decision_pct: float = 0.0


class TapologyCommunityPicks(BaseModel):
    total_picks: int = 0
    fighter_1_win_pct: float = 0.0
    fighter_2_win_pct: float = 0.0
    fighter_1_methods: TapologyMethodBreakdown = TapologyMethodBreakdown()
    fighter_2_methods: TapologyMethodBreakdown = TapologyMethodBreakdown()


class TapologyFight(BaseModel):
    fighter_1: str
    fighter_2: str
    matchup_url: str = ""
    odds_f1_american: int | None = None
    odds_f2_american: int | None = None
    community_picks: TapologyCommunityPicks | None = None


class TapologyScrapeRequest(BaseModel):
    url: str


class TapologyScrapeResponse(BaseModel):
    event_name: str
    n_fights: int
    fights: list[TapologyFight]
    errors: list[str] = []
