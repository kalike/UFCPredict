from datetime import datetime, UTC
from typing import Iterable

from sqlalchemy.orm import Session

from ufc_core.db import models


def upsert_fight_features(
    db: Session,
    fight_id: int,
    feature_set: str,
    vector: dict,
    before_event_date: datetime | None = None,
) -> models.FightFeatures:
    """Insert or replace the feature vector for (fight_id, feature_set)."""
    existing = (
        db.query(models.FightFeatures)
          .filter_by(fight_id=fight_id, feature_set=feature_set)
          .one_or_none()
    )
    if existing is None:
        existing = models.FightFeatures(
            fight_id=fight_id,
            feature_set=feature_set,
            vector=vector,
            computed_at=datetime.now(UTC),
            before_event_date=before_event_date,
        )
        db.add(existing)
        db.flush()  # make row visible to subsequent queries in the same session
    else:
        existing.vector = vector
        existing.computed_at = datetime.now(UTC)
        existing.before_event_date = before_event_date
    return existing


def get_features_for_fight(db: Session, fight_id: int, feature_set: str) -> dict | None:
    row = (
        db.query(models.FightFeatures)
          .filter_by(fight_id=fight_id, feature_set=feature_set)
          .one_or_none()
    )
    return row.vector if row else None


def bulk_load_feature_vectors(
    db: Session, fight_ids: Iterable[int], feature_set: str
) -> dict[int, dict]:
    rows = (
        db.query(models.FightFeatures)
          .filter(
              models.FightFeatures.fight_id.in_(list(fight_ids)),
              models.FightFeatures.feature_set == feature_set,
          )
          .all()
    )
    return {r.fight_id: r.vector for r in rows}
