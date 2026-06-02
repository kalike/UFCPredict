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


def test_opponent_resolved_by_url_not_name(test_engine, db_session):
    """If the opponent already exists (by URL), the truncated display name in
    another fighter's history must NOT create a duplicate placeholder."""
    Base.metadata.create_all(test_engine)
    # Real fighter ingested from his own page (full name + real URL).
    db_session.add(models.Fighter(
        name="Jack Della Maddalena", slug="jack-della-maddalena",
        ufcstats_url="http://ufcstats.com/fighter-details/jdm",
    ))
    db_session.flush()
    payload = [{
        "name": "Belal Muhammad",
        "url": "http://ufcstats.com/fighter-details/belal",
        "fights": [{
            "event": "UFC 315", "date": "May. 10, 2025",
            "opponent": "Della Maddalena",  # truncated display name
            "opponent_url": "http://ufcstats.com/fighter-details/jdm",
            "result": "loss", "method": "U-DEC", "round": 5, "time": "5:00",
        }],
    }]
    ingest_fighters_payload(db_session, payload)
    # No placeholder created; opponent is the existing real fighter.
    assert db_session.query(models.Fighter).filter(
        models.Fighter.ufcstats_url.like("placeholder://%")).count() == 0
    jdm = db_session.query(models.Fighter).filter_by(
        ufcstats_url="http://ufcstats.com/fighter-details/jdm").one()
    assert db_session.query(models.Fight).count() == 1
    f = db_session.query(models.Fight).one()
    assert jdm.id in (f.fighter_1_id, f.fighter_2_id)


def test_stub_uses_real_url_and_is_reconciled_later(test_engine, db_session):
    """An as-yet-unseen opponent becomes a stub keyed by the REAL url, so when
    his own page is scraped he is updated (name reconciled), not duplicated."""
    Base.metadata.create_all(test_engine)
    # First: opponent appears only in someone else's history, truncated.
    ingest_fighters_payload(db_session, [{
        "name": "Davey Grant",
        "url": "http://ufcstats.com/fighter-details/davey",
        "fights": [{
            "event": "DWCS 9.9", "date": "Jun. 1, 2025",
            "opponent": "Luna Martinetti",
            "opponent_url": "http://ufcstats.com/fighter-details/adrian",
            "result": "win", "method": "U-DEC", "round": 3, "time": "5:00",
        }],
    }])
    stub = db_session.query(models.Fighter).filter_by(
        ufcstats_url="http://ufcstats.com/fighter-details/adrian").one()
    assert stub.name == "Luna Martinetti"          # truncated for now
    assert not stub.ufcstats_url.startswith("placeholder://")
    # Later: the opponent's own page is scraped with his full name.
    ingest_fighters_payload(db_session, [{
        "name": "Adrian Luna Martinetti",
        "url": "http://ufcstats.com/fighter-details/adrian",
        "fights": [],
    }])
    db_session.refresh(stub)
    assert stub.name == "Adrian Luna Martinetti"    # reconciled
    assert db_session.query(models.Fighter).filter_by(
        ufcstats_url="http://ufcstats.com/fighter-details/adrian").count() == 1


def test_falls_back_to_placeholder_without_url(test_engine, db_session):
    """No opponent_url (opponent has no UFCStats page) → legacy placeholder."""
    Base.metadata.create_all(test_engine)
    ingest_fighters_payload(db_session, [{
        "name": "Mridul Saikia",
        "url": "http://ufcstats.com/fighter-details/mridul",
        "fights": [{
            "event": "Road to UFC 4.1 + 4.2", "date": "May. 22, 2025",
            "opponent": "Saikia Agulali", "opponent_url": None,
            "result": "win", "method": "U-DEC", "round": 3, "time": "5:00",
        }],
    }])
    opp = db_session.query(models.Fighter).filter_by(name="Saikia Agulali").one()
    assert opp.ufcstats_url == "placeholder://Saikia Agulali"
