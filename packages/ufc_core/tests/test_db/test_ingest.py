from ufc_core.db import Base, models
from ufc_core.db.ingest import ingest_fighters_payload


SAMPLE = [{
    "name": "Conor McGregor",
    "url": "http://ufcstats.com/fighter-details/abc",
    "record": "22-6-0",
    "stance": "southpaw",
    "height_cm": 175.0,
    "reach_cm": 188.0,
    "dob": "1988-07-14",
    "fights": [
        {"event": "UFC 300", "date": "Apr. 13, 2024", "opponent": "Test Test",
         "result": "win", "method": "U-DEC", "round": 3, "time": "5:00",
         "weight_class": "Lightweight"},
    ],
}]


def test_ingest_idempotent(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    counts1 = ingest_fighters_payload(db_session, SAMPLE)
    counts2 = ingest_fighters_payload(db_session, SAMPLE)
    assert counts1["fighters_new"] >= 1
    assert counts2["fighters_new"] == 0
    assert db_session.query(models.Fighter).count() >= 1
    assert db_session.query(models.Event).count() == 1
    assert db_session.query(models.Fight).count() == 1
