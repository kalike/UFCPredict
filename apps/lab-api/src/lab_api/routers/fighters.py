"""Fighters router — list, search, detail."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

router = APIRouter(prefix="/api/fighters", tags=["fighters"])


class FighterSummary(BaseModel):
    id: int
    name: str
    slug: str
    record: str | None
    stance: str | None
    height_cm: float | None
    reach_cm: float | None
    photo_url: str | None


class FighterDetail(FighterSummary):
    ufcstats_url: str
    tapology_url: str | None
    fight_count: int


@router.get("/", response_model=list[FighterSummary])
def list_fighters(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[FighterSummary]:
    """List fighters; optional `q` filters by name (case-insensitive substring)."""
    query = db.query(db_models.Fighter)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db_models.Fighter.name.ilike(like))
    rows = query.order_by(db_models.Fighter.name).offset(offset).limit(limit).all()
    return [FighterSummary(
        id=f.id, name=f.name, slug=f.slug, record=f.record,
        stance=f.stance, height_cm=f.height_cm, reach_cm=f.reach_cm,
        photo_url=f.photo_url,
    ) for f in rows]


@router.get("/{fighter_id}", response_model=FighterDetail)
def get_fighter(fighter_id: int, db: Session = Depends(get_db)) -> FighterDetail:
    f = db.query(db_models.Fighter).filter_by(id=fighter_id).one_or_none()
    if f is None:
        raise HTTPException(404, f"Fighter {fighter_id} not found")
    fight_count = (
        db.query(db_models.Fight)
          .filter(or_(db_models.Fight.fighter_1_id == f.id,
                      db_models.Fight.fighter_2_id == f.id))
          .count()
    )
    return FighterDetail(
        id=f.id, name=f.name, slug=f.slug, record=f.record,
        stance=f.stance, height_cm=f.height_cm, reach_cm=f.reach_cm,
        photo_url=f.photo_url, ufcstats_url=f.ufcstats_url,
        tapology_url=f.tapology_url, fight_count=fight_count,
    )
