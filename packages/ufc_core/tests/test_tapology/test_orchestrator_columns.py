"""build_matchers must read the lab Fight schema (fighter_1_id/fighter_2_id),
not the legacy backend's fighter_id/opponent_id columns."""

from ufc_core.db import Base, models
from ufc_core.tapology.orchestrator import build_matchers


def test_build_matchers_maps_fight_columns(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    ev = models.Event(name="E1", status="completed")
    a = models.Fighter(name="A", slug="a-x", ufcstats_url="u-a")
    b = models.Fighter(name="B", slug="b-x", ufcstats_url="u-b")
    db_session.add_all([ev, a, b])
    db_session.flush()
    fight = models.Fight(event_id=ev.id, fighter_1_id=a.id, fighter_2_id=b.id)
    db_session.add(fight)
    db_session.flush()

    # Must not raise AttributeError: type object 'Fight' has no attribute 'opponent_id'
    _fighter_m, fight_m, _aliases = build_matchers(db_session)
    # And the bout must be indexed by its real fighter columns (either order).
    assert fight_m.match(ev.id, a.id, b.id) == fight.id
    assert fight_m.match(ev.id, b.id, a.id) == fight.id
