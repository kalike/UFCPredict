from datetime import datetime, UTC
from unittest.mock import patch

from ufc_core.db import Base, models
from ufc_core.data_loader import DataStoreDB


class _NoCloseSession:
    """Thin wrapper that delegates everything to `session` but suppresses close()."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def close(self):
        pass  # do NOT close the outer test-transaction session


def test_datastore_loads_event(test_engine, db_session, monkeypatch):
    Base.metadata.create_all(test_engine)

    ev = models.Event(name="UFC 300", date=datetime(2024, 4, 13, tzinfo=UTC),
                      status="completed")
    db_session.add(ev)
    db_session.flush()  # make row visible within the savepoint transaction

    # Redirect SyncSessionLocal() to return a wrapper around the in-transaction
    # db_session so DataStoreDB.load() sees the row without a separate connection,
    # and without closing the shared session in the finally block.
    monkeypatch.setattr(
        "ufc_core.data_loader.SyncSessionLocal",
        lambda: _NoCloseSession(db_session),
    )

    ds = DataStoreDB()
    ds.load()

    assert "UFC 300" in ds.event_dates
    assert ds.event_dates["UFC 300"].year == 2024
    assert ds.fight_cards == []  # stub is empty for F1
    assert ds.predicted_events == []


def test_non_ufc_events_excluded_from_event_dates(test_engine, db_session, monkeypatch):
    """Regression: fighter_history (non-UFC) events must not enter event_dates.

    event_dates is the single gate consulted by recalculate_elo and _build_dataset,
    so excluding non-UFC events here keeps the lab's ELO/training universe UFC-only,
    matching the legacy backend (PRIDE/Strikeforce/ONE fights are dropped).
    """
    Base.metadata.create_all(test_engine)

    db_session.add_all([
        models.Event(name="UFC 295", date=datetime(2023, 11, 11, tzinfo=UTC),
                     status="completed", source="scraped"),
        models.Event(name="UFC 320", date=datetime(2025, 10, 4, tzinfo=UTC),
                     status="scheduled", source="promoted"),
        models.Event(name="PRIDE 23: Championship Chaos 2",
                     date=datetime(2002, 11, 24, tzinfo=UTC),
                     status="completed", source="fighter_history"),
    ])
    db_session.flush()

    monkeypatch.setattr(
        "ufc_core.data_loader.SyncSessionLocal",
        lambda: _NoCloseSession(db_session),
    )

    ds = DataStoreDB()
    ds.load()

    assert "UFC 295" in ds.event_dates       # UFC card → kept
    assert "UFC 320" in ds.event_dates       # upcoming UFC card → kept
    assert "PRIDE 23: Championship Chaos 2" not in ds.event_dates  # non-UFC → dropped
