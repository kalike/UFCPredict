"""Tests for TapologyPicksRepo using mocked SQLAlchemy session.

A real DB integration test is covered by the smoke test (Task 14) against
PostgreSQL. These tests validate the upsert logic in isolation.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from ufc_core.tapology.picks_repo import PickRow, TapologyPicksRepo
from ufc_core.db.models import TapologyPicks


def _make_session_with_existing(existing_row: TapologyPicks | None) -> MagicMock:
    """Build a MagicMock session whose .query().filter().one_or_none() returns the row."""
    session = MagicMock()
    chain = session.query.return_value.filter.return_value
    chain.one_or_none.return_value = existing_row
    return session


def _row(**overrides) -> PickRow:
    base = dict(
        fight_id=1, fighter_a_id=10, fighter_b_id=20, total_picks=100,
        fighter_a_win_pct=60.0, fighter_b_win_pct=40.0,
    )
    base.update(overrides)
    return PickRow(**base)


def test_upsert_inserts_when_no_existing_row():
    session = _make_session_with_existing(None)
    repo = TapologyPicksRepo(session)
    written = repo.upsert(_row())
    assert written is True
    session.add.assert_called_once()
    added = session.add.call_args.args[0]
    assert isinstance(added, TapologyPicks)
    assert added.fight_id == 1
    assert added.total_picks == 100


def test_upsert_skips_when_existing_is_recent():
    existing = TapologyPicks(
        fight_id=1, fighter_a_id=10, fighter_b_id=20, total_picks=50,
        scraped_at=datetime.now(UTC),  # fresh
    )
    session = _make_session_with_existing(existing)
    repo = TapologyPicksRepo(session)
    written = repo.upsert(_row(total_picks=999))
    assert written is False
    session.add.assert_not_called()
    assert existing.total_picks == 50  # unchanged


def test_upsert_writes_when_existing_is_old():
    old_ts = datetime.now(UTC) - timedelta(days=40)
    existing = TapologyPicks(
        fight_id=1, fighter_a_id=10, fighter_b_id=20, total_picks=50,
        scraped_at=old_ts,
    )
    session = _make_session_with_existing(existing)
    repo = TapologyPicksRepo(session)
    written = repo.upsert(_row(total_picks=999))
    assert written is True
    assert existing.total_picks == 999
    assert existing.scraped_at > old_ts


def test_upsert_force_overwrites_recent():
    existing = TapologyPicks(
        fight_id=1, fighter_a_id=10, fighter_b_id=20, total_picks=50,
        scraped_at=datetime.now(UTC),
    )
    session = _make_session_with_existing(existing)
    repo = TapologyPicksRepo(session)
    written = repo.upsert(_row(total_picks=999), force=True)
    assert written is True
    assert existing.total_picks == 999


def test_upsert_writes_when_existing_has_no_scraped_at():
    """Defensive: if a row was inserted without scraped_at, treat as stale."""
    existing = TapologyPicks(
        fight_id=1, fighter_a_id=10, fighter_b_id=20, total_picks=50,
        scraped_at=None,
    )
    session = _make_session_with_existing(existing)
    repo = TapologyPicksRepo(session)
    written = repo.upsert(_row(total_picks=999))
    assert written is True


def test_all_recent_empty_set_is_true():
    session = MagicMock()
    repo = TapologyPicksRepo(session)
    assert repo.all_recent(set()) is True
    session.query.assert_not_called()


def test_all_recent_returns_true_when_all_recent():
    fresh = datetime.now(UTC) - timedelta(days=1)
    rows = [
        MagicMock(fight_id=1, scraped_at=fresh),
        MagicMock(fight_id=2, scraped_at=fresh),
    ]
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rows
    repo = TapologyPicksRepo(session)
    assert repo.all_recent({1, 2}) is True


def test_all_recent_returns_false_when_one_missing():
    fresh = datetime.now(UTC) - timedelta(days=1)
    rows = [MagicMock(fight_id=1, scraped_at=fresh)]
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rows
    repo = TapologyPicksRepo(session)
    assert repo.all_recent({1, 2}) is False


def test_all_recent_returns_false_when_one_stale():
    stale = datetime.now(UTC) - timedelta(days=60)
    fresh = datetime.now(UTC) - timedelta(days=1)
    rows = [
        MagicMock(fight_id=1, scraped_at=fresh),
        MagicMock(fight_id=2, scraped_at=stale),
    ]
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rows
    repo = TapologyPicksRepo(session)
    assert repo.all_recent({1, 2}) is False
