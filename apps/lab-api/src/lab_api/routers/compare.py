"""Compare router — head-to-head between two fighters (basic stats)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

router = APIRouter(prefix="/api/compare", tags=["compare"])


class FighterStats(BaseModel):
    id: int
    name: str
    record: str | None
    stance: str | None
    height_cm: float | None
    reach_cm: float | None
    fight_count: int


class CompareResponse(BaseModel):
    fighter_a: FighterStats
    fighter_b: FighterStats


def _stats(db: Session, f: db_models.Fighter) -> FighterStats:
    from sqlalchemy import or_
    fight_count = (
        db.query(db_models.Fight)
          .filter(or_(db_models.Fight.fighter_1_id == f.id,
                      db_models.Fight.fighter_2_id == f.id))
          .count()
    )
    return FighterStats(
        id=f.id, name=f.name, record=f.record, stance=f.stance,
        height_cm=f.height_cm, reach_cm=f.reach_cm, fight_count=fight_count,
    )


@router.get("", response_model=CompareResponse)
def compare(a: int, b: int, db: Session = Depends(get_db)) -> CompareResponse:
    """Compare two fighters by id."""
    fa = db.query(db_models.Fighter).filter_by(id=a).one_or_none()
    fb = db.query(db_models.Fighter).filter_by(id=b).one_or_none()
    if fa is None:
        raise HTTPException(404, f"Fighter {a} not found")
    if fb is None:
        raise HTTPException(404, f"Fighter {b} not found")
    return CompareResponse(fighter_a=_stats(db, fa), fighter_b=_stats(db, fb))
