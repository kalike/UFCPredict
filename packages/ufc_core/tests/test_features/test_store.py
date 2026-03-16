from datetime import datetime

from ufc_core.db import Base, models
from ufc_core.features.store import (
    upsert_fight_features, get_features_for_fight, bulk_load_feature_vectors,
)


def _seed_fight(db_session):
    ev = models.Event(name="X", status="completed")
    f1 = models.Fighter(name="A", slug="a", ufcstats_url="u/a")
    f2 = models.Fighter(name="B", slug="b", ufcstats_url="u/b")
    db_session.add_all([ev, f1, f2])
    db_session.flush()
    fight = models.Fight(event_id=ev.id, fighter_1_id=f1.id, fighter_2_id=f2.id)
    db_session.add(fight)
    db_session.flush()
    return fight


def test_store_upsert_replaces_same_set(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    fight = _seed_fight(db_session)

    upsert_fight_features(db_session, fight.id, "v7", {"x": 1.0},
                          before_event_date=datetime(2024, 4, 13))
    upsert_fight_features(db_session, fight.id, "v7", {"x": 2.0},
                          before_event_date=datetime(2024, 4, 13))
    db_session.flush()

    assert db_session.query(models.FightFeatures).filter_by(fight_id=fight.id).count() == 1
    vec = get_features_for_fight(db_session, fight.id, "v7")
    assert vec["x"] == 2.0


def test_bulk_load_feature_vectors(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    fight = _seed_fight(db_session)
    upsert_fight_features(db_session, fight.id, "v7", {"a": 0.5})
    db_session.flush()

    vectors = bulk_load_feature_vectors(db_session, [fight.id], "v7")
    assert vectors == {fight.id: {"a": 0.5}}
