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


def test_homonym_fighters_get_distinct_slugs(test_engine, db_session):
    """Two different people named 'Mike Davis' (distinct UFCStats URLs) must
    both persist with distinct unique slugs — no UniqueViolation on fighter_slug_key."""
    Base.metadata.create_all(test_engine)
    payload = [
        {"name": "Mike Davis", "url": "http://ufcstats.com/fighter-details/aaa111", "fights": []},
        {"name": "Mike Davis", "url": "http://ufcstats.com/fighter-details/bbb222", "fights": []},
    ]
    ingest_fighters_payload(db_session, payload)
    davises = db_session.query(models.Fighter).filter_by(name="Mike Davis").all()
    assert len(davises) == 2
    slugs = {f.slug for f in davises}
    assert len(slugs) == 2          # distinct → no unique-constraint violation
    assert "mike-davis" in slugs    # first one keeps the clean slug


def test_homonym_ingest_is_idempotent(test_engine, db_session):
    """Re-ingesting the same homonym payload yields the SAME slugs and no new rows."""
    Base.metadata.create_all(test_engine)
    payload = [
        {"name": "Mike Davis", "url": "http://ufcstats.com/fighter-details/aaa111", "fights": []},
        {"name": "Mike Davis", "url": "http://ufcstats.com/fighter-details/bbb222", "fights": []},
    ]
    ingest_fighters_payload(db_session, payload)
    before = {f.ufcstats_url: f.slug for f in db_session.query(models.Fighter).all()}
    ingest_fighters_payload(db_session, payload)
    after = {f.ufcstats_url: f.slug for f in db_session.query(models.Fighter).all()}
    assert before == after
    assert db_session.query(models.Fighter).filter_by(name="Mike Davis").count() == 2


def test_event_date_read_from_event_date_key(test_engine, db_session):
    """The scraper emits the per-fight date under 'event_date'; ingest must read
    that key (not 'date') so new events get a non-NULL date."""
    Base.metadata.create_all(test_engine)
    ingest_fighters_payload(db_session, [{
        "name": "X", "url": "http://ufcstats.com/fighter-details/xkey",
        "fights": [{
            "event": "UFC New Card", "event_date": "2026-06-06", "opponent": "Y",
            "opponent_url": None, "result": "win", "method": "KO", "round": 1, "time": "1:00",
        }],
    }])
    ev = db_session.query(models.Event).filter_by(name="UFC New Card").one()
    assert ev.date is not None
    assert (ev.date.year, ev.date.month, ev.date.day) == (2026, 6, 6)


def test_existing_event_null_date_is_backfilled(test_engine, db_session):
    """An event row that already exists with date=NULL gets its date filled in
    once a payload carries the event_date."""
    Base.metadata.create_all(test_engine)
    db_session.add(models.Event(name="UFC Old Card", date=None, status="completed"))
    db_session.flush()
    ingest_fighters_payload(db_session, [{
        "name": "Z", "url": "http://ufcstats.com/fighter-details/zkey",
        "fights": [{
            "event": "UFC Old Card", "event_date": "2026-05-20", "opponent": "W",
            "opponent_url": None, "result": "loss", "method": "DEC", "round": 3, "time": "5:00",
        }],
    }])
    ev = db_session.query(models.Event).filter_by(name="UFC Old Card").one()
    assert ev.date is not None
    assert (ev.date.month, ev.date.day) == (5, 20)


def test_is_road_to_ufc_detector():
    from ufc_core.db.ingest import is_road_to_ufc
    assert is_road_to_ufc("Road To UFC 5.1")
    assert is_road_to_ufc("Road to UFC 4.3 + 4.4")
    assert not is_road_to_ufc("UFC Fight Night: Muhammad vs. Bonfim")
    assert not is_road_to_ufc("UFC Freedom 250")
    assert not is_road_to_ufc(None)


def test_road_to_ufc_event_gets_excluded_source(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    ingest_fighters_payload(db_session, [{
        "name": "R", "url": "http://ufcstats.com/fighter-details/rkey",
        "fights": [{
            "event": "Road To UFC 5.1", "event_date": "2026-05-28", "opponent": "S",
            "opponent_url": None, "result": "win", "method": "DEC", "round": 3, "time": "5:00",
        }],
    }])
    ev = db_session.query(models.Event).filter_by(name="Road To UFC 5.1").one()
    assert ev.source == "road_to_ufc"


def test_normal_event_keeps_scraped_source(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    ingest_fighters_payload(db_session, [{
        "name": "U", "url": "http://ufcstats.com/fighter-details/ukey",
        "fights": [{
            "event": "UFC Freedom 250", "event_date": "2026-06-14", "opponent": "V",
            "opponent_url": None, "result": "win", "method": "KO", "round": 1, "time": "1:00",
        }],
    }])
    ev = db_session.query(models.Event).filter_by(name="UFC Freedom 250").one()
    assert ev.source == "scraped"


def test_existing_road_to_ufc_source_corrected(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    db_session.add(models.Event(name="Road to UFC 4.3", date=None, status="completed", source="scraped"))
    db_session.flush()
    ingest_fighters_payload(db_session, [{
        "name": "R2", "url": "http://ufcstats.com/fighter-details/r2key",
        "fights": [{
            "event": "Road to UFC 4.3", "event_date": "2025-06-01", "opponent": "S",
            "opponent_url": None, "result": "win", "method": "DEC", "round": 3, "time": "5:00",
        }],
    }])
    ev = db_session.query(models.Event).filter_by(name="Road to UFC 4.3").one()
    assert ev.source == "road_to_ufc"


def test_promoted_placeholder_fight_backfilled_by_scrape(test_engine, db_session):
    """Reproduces the Fiziev bug: an event promoted before it happened has
    placeholder fights (result=NULL, source='promoted'). When the scrape later
    brings the real results, ingest must backfill the result (oriented to the
    stored fighter_1), flip source promoted->scraped, and count fights_updated —
    instead of skipping the existing fight."""
    Base.metadata.create_all(test_engine)
    # Two real fighters + a promoted event with ONE placeholder fight (no result).
    a = models.Fighter(name="Rafael Fiziev", slug="rafael-fiziev",
                        ufcstats_url="http://ufcstats.com/fighter-details/fiziev")
    b = models.Fighter(name="Manuel Torres", slug="manuel-torres",
                        ufcstats_url="http://ufcstats.com/fighter-details/torres")
    db_session.add_all([a, b]); db_session.flush()
    ev = models.Event(name="UFC Fight Night: Fiziev vs. Torres",
                      date=None, status="completed", source="promoted")
    db_session.add(ev); db_session.flush()
    # Placeholder stored with Torres as fighter_1 (opposite of the scraped owner).
    db_session.add(models.Fight(event_id=ev.id, fighter_1_id=b.id,
                                fighter_2_id=a.id, result=None))
    db_session.commit()

    # Scrape brings Fiziev's page: he WON. Owner perspective = 'win'.
    counts = ingest_fighters_payload(db_session, [{
        "name": "Rafael Fiziev",
        "url": "http://ufcstats.com/fighter-details/fiziev",
        "fights": [{
            "event": "UFC Fight Night: Fiziev vs. Torres",
            "event_date": "2026-06-27", "opponent": "Manuel Torres",
            "opponent_url": "http://ufcstats.com/fighter-details/torres",
            "result": "win", "method": "KO/TKO", "round": 2, "time": "3:11",
            "weight_class": "Lightweight",
        }],
    }])

    db_session.refresh(ev)
    assert ev.source == "scraped"                 # promoted -> scraped
    assert db_session.query(models.Fight).count() == 1   # no duplicate row
    f = db_session.query(models.Fight).one()
    # Stored fighter_1 is Torres, so his oriented result is 'loss' (Fiziev won).
    assert f.fighter_1_id == b.id
    assert f.result == "loss"
    assert f.method == "KO/TKO" and f.weight_class == "Lightweight"
    assert counts["fights_updated"] == 1
    assert counts["fights_new"] == 0


def test_backfill_never_overwrites_existing_result(test_engine, db_session):
    """A fight that already carries a result must not be rewritten by a later
    scrape (backfill is fill-only)."""
    Base.metadata.create_all(test_engine)
    a = models.Fighter(name="AA", slug="aa", ufcstats_url="http://ufcstats.com/fighter-details/aa")
    b = models.Fighter(name="BB", slug="bb", ufcstats_url="http://ufcstats.com/fighter-details/bb")
    db_session.add_all([a, b]); db_session.flush()
    ev = models.Event(name="UFC Settled", date=None, status="completed", source="scraped")
    db_session.add(ev); db_session.flush()
    db_session.add(models.Fight(event_id=ev.id, fighter_1_id=a.id, fighter_2_id=b.id,
                                result="win", method="U-DEC"))
    db_session.commit()
    counts = ingest_fighters_payload(db_session, [{
        "name": "AA", "url": "http://ufcstats.com/fighter-details/aa",
        "fights": [{
            "event": "UFC Settled", "event_date": "2026-06-27", "opponent": "BB",
            "opponent_url": "http://ufcstats.com/fighter-details/bb",
            "result": "loss", "method": "KO", "round": 1, "time": "1:00",
        }],
    }])
    f = db_session.query(models.Fight).one()
    assert f.result == "win" and f.method == "U-DEC"   # untouched
    assert counts["fights_updated"] == 0
