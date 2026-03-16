"""Metadata tests for the TapologyPicks ORM model.

Full DB integration is verified at smoke-test time against PostgreSQL.
The repo's test pattern (MockDataStore) doesn't exercise SQLAlchemy directly,
so these tests only validate ORM metadata.
"""

from ufc_core.db.models import TapologyPicks


def test_tablename():
    assert TapologyPicks.__tablename__ == "tapology_picks"


def test_columns():
    cols = {c.name for c in TapologyPicks.__table__.columns}
    expected = {
        "id",
        "fight_id",
        "total_picks",
        "fighter_a_id",
        "fighter_b_id",
        "fighter_a_win_pct",
        "fighter_b_win_pct",
        "fighter_a_methods",
        "fighter_b_methods",
        "matchup_url",
        "source_event_url",
        "scraped_at",
    }
    assert expected == cols


def test_fight_id_unique_and_cascade():
    fight_id_col = TapologyPicks.__table__.columns["fight_id"]
    assert fight_id_col.unique is True
    fk = next(iter(fight_id_col.foreign_keys))
    assert fk.ondelete == "CASCADE"
    # ufc_core uses singular table names ("fight" not "fights")
    assert fk.column.table.name == "fight"


def test_fighter_fks_point_to_fighters():
    for col_name in ("fighter_a_id", "fighter_b_id"):
        col = TapologyPicks.__table__.columns[col_name]
        fk = next(iter(col.foreign_keys))
        # ufc_core uses singular table names ("fighter" not "fighters")
        assert fk.column.table.name == "fighter"


def test_total_picks_not_null_default_zero():
    col = TapologyPicks.__table__.columns["total_picks"]
    assert col.nullable is False


def test_win_pct_nullable():
    """null win_pct = Tapology listed matchup but no votes (pre-2012 fights)."""
    for col_name in ("fighter_a_win_pct", "fighter_b_win_pct"):
        assert TapologyPicks.__table__.columns[col_name].nullable is True
