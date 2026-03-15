from datetime import datetime

from ufc_core.db import Base, models


def test_event_fighter_fight_round_trip(test_engine, db_session):
    Base.metadata.create_all(test_engine)

    ev = models.Event(name="UFC 300", date=datetime(2024, 4, 13), location="Las Vegas, USA",
                     status="completed", is_dwcs=False, source_url="http://ufcstats.com/e/1")
    f1 = models.Fighter(name="A B", slug="a-b", ufcstats_url="http://ufcstats.com/f/1",
                        record="10-0-0", stance="orthodox")
    f2 = models.Fighter(name="C D", slug="c-d", ufcstats_url="http://ufcstats.com/f/2",
                        record="5-2-0", stance="southpaw")
    db_session.add_all([ev, f1, f2])
    db_session.flush()

    fight = models.Fight(event_id=ev.id, fighter_1_id=f1.id, fighter_2_id=f2.id,
                        weight_class="Lightweight", card_position="main",
                        scheduled_rounds=5, fight_order=12)
    db_session.add(fight)
    db_session.flush()

    assert fight.id is not None
    assert fight.event.name == "UFC 300"
    assert fight.fighter_1.name == "A B"
