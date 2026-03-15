import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


EXPECTED_TABLES = {
    "event", "fighter", "fight", "fighter_raw", "fight_features",
    "tapology_picks", "tapology_event_match",
    "model", "model_version", "active_model", "training_session",
    "prediction_session", "prediction", "prediction_cache",
    "user", "user_bet", "parlay", "bet_config",
    "user_preference", "user_view_state",
    "lab_preference", "lab_bet_config",
    "hp_search_study", "hp_search_trial",
    "combo_search_study", "combo_search_trial", "backtest_run",
    "scraping_run", "publish_run", "app_log",
    "alembic_version",
}


def test_alembic_upgrade_creates_all_tables(test_engine):
    """`alembic upgrade head` against a fresh DB creates the full schema.

    Uses a dedicated `ufc_lab_alembic_test` DB (drop+create) so that prior
    tests in the session — which call `Base.metadata.create_all(test_engine)`
    on `ufc_lab_test` — don't leak tables and cause DuplicateTable on the
    migration's `op.create_table()`.
    """
    pkg_root = Path(__file__).resolve().parents[2]  # packages/ufc_core/
    db_user = os.environ.get("UFC_LAB_DB_USER", "ufc")
    db_pass = os.environ.get("UFC_LAB_DB_PASS", "ufc_secret")
    db_host = os.environ.get("UFC_LAB_DB_HOST", "localhost")
    db_port = os.environ.get("UFC_LAB_DB_PORT", "5432")
    mig_db = "ufc_lab_alembic_test"

    admin_url = (
        f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/postgres"
    )
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {mig_db}"))
        c.execute(text(f"CREATE DATABASE {mig_db}"))
    admin.dispose()

    url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{mig_db}"
    try:
        subprocess.check_call(
            ["alembic", "-x", f"db_url={url}", "upgrade", "head"],
            cwd=str(pkg_root),
        )

        target = create_engine(url)
        tables = set(inspect(target).get_table_names())
        target.dispose()
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Tables missing after migration: {missing}"
    finally:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {mig_db}"))
        admin.dispose()
