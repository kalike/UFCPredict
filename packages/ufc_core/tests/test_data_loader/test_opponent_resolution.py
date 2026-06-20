"""_load_fighters must resolve each fight's opponent by opponent_url to the
canonical fighter name, repairing garbled scraper-stored opponent names
(owner+opponent concatenated) without re-scraping."""

from ufc_core.db import Base, models
from ufc_core.data_loader import DataStoreDB


def test_load_fighters_resolves_opponent_by_url(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    a = models.Fighter(name="Fares Ziam", slug="fares-ziam",
                       ufcstats_url="http://ufcstats.com/fighter-details/a")
    b = models.Fighter(name="Tom Nolan", slug="tom-nolan",
                       ufcstats_url="http://ufcstats.com/fighter-details/b")
    db_session.add_all([a, b])
    db_session.flush()
    db_session.add(models.FighterRaw(fighter_id=a.id, payload={
        "name": "Fares Ziam",
        "url": "http://ufcstats.com/fighter-details/a",
        "fights": [{
            "event": "UFC X",
            "opponent": "Fares Ziam\n      \n\n   Tom Nolan",   # corrupt
            "opponent_url": "http://ufcstats.com/fighter-details/b",
            "result": "win",
        }],
    }))
    db_session.flush()

    ds = DataStoreDB()
    ds._load_fighters(db_session)

    fz = next(f for f in ds.fighters_raw if f["name"] == "Fares Ziam")
    assert fz["fights"][0]["opponent"] == "Tom Nolan"   # clean, resolved by URL


def test_load_fighters_keeps_opponent_without_url(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    a = models.Fighter(name="Solo Guy", slug="solo-guy",
                       ufcstats_url="http://ufcstats.com/fighter-details/solo")
    db_session.add(a)
    db_session.flush()
    db_session.add(models.FighterRaw(fighter_id=a.id, payload={
        "name": "Solo Guy",
        "url": "http://ufcstats.com/fighter-details/solo",
        "fights": [{"event": "UFC Y", "opponent": "Some Debutant",
                    "opponent_url": None, "result": "win"}],
    }))
    db_session.flush()

    ds = DataStoreDB()
    ds._load_fighters(db_session)
    sg = next(f for f in ds.fighters_raw if f["name"] == "Solo Guy")
    assert sg["fights"][0]["opponent"] == "Some Debutant"   # unchanged


def test_load_fighters_resolves_opponent_by_alias_without_url(test_engine, db_session):
    """Sin opponent_url, repara el oponente vía la tabla fight (alias id+evento)."""
    import datetime as _dt
    Base.metadata.create_all(test_engine)
    a = models.Fighter(name="Owner Guy", slug="owner-guy",
                       ufcstats_url="http://ufcstats.com/fighter-details/own")
    b = models.Fighter(name="Canonical Opp", slug="canonical-opp",
                       ufcstats_url="http://ufcstats.com/fighter-details/cop")
    db_session.add_all([a, b])
    db_session.flush()
    ev = models.Event(name="UFC Z", date=_dt.datetime(2025, 6, 1),
                      status="completed", is_dwcs=False)
    db_session.add(ev)
    db_session.flush()
    db_session.add(models.Fight(event_id=ev.id, fighter_1_id=a.id,
                                fighter_2_id=b.id, result="win"))
    db_session.add(models.FighterRaw(fighter_id=a.id, payload={
        "name": "Owner Guy", "url": "http://ufcstats.com/fighter-details/own",
        "fights": [{"event": "UFC Z", "opponent": "Garbled Asian Name",
                    "opponent_url": None, "result": "win"}],
    }))
    db_session.flush()

    ds = DataStoreDB()
    ds._load_fighters(db_session)

    og = next(f for f in ds.fighters_raw if f["name"] == "Owner Guy")
    assert og["fights"][0]["opponent"] == "Canonical Opp"  # repaired by alias

