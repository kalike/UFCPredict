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
