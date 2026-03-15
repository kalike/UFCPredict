from datetime import datetime

from ufc_core.db import Base, models


def _seed_fight(db_session):
    ev = models.Event(name="UFC X", status="completed")
    f1 = models.Fighter(name="A", slug="a", ufcstats_url="u/a")
    f2 = models.Fighter(name="B", slug="b", ufcstats_url="u/b")
    db_session.add_all([ev, f1, f2])
    db_session.flush()
    fight = models.Fight(event_id=ev.id, fighter_1_id=f1.id, fighter_2_id=f2.id)
    db_session.add(fight)
    db_session.flush()
    return fight


def test_fight_features_unique_per_feature_set(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    fight = _seed_fight(db_session)

    ff = models.FightFeatures(
        fight_id=fight.id, feature_set="v7",
        vector={"f1_winrate": 0.7, "delta_age": 3.0},
        computed_at=datetime.utcnow(),
        before_event_date=datetime(2024, 4, 13),
    )
    db_session.add(ff)
    db_session.flush()
    assert ff.id is not None
    assert ff.vector["f1_winrate"] == 0.7
