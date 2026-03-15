import os
import subprocess
from pathlib import Path

from sqlalchemy import inspect


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
    """`alembic upgrade head` against ufc_lab_test creates the full schema."""
    pkg_root = Path(__file__).resolve().parents[2]  # packages/ufc_core/
    db_name = os.environ.get("UFC_LAB_TEST_DB_NAME", "ufc_lab_test")
    db_user = os.environ.get("UFC_LAB_DB_USER", "ufc")
    db_pass = os.environ.get("UFC_LAB_DB_PASS", "ufc_secret")
    url = f"postgresql+psycopg2://{db_user}:{db_pass}@localhost/{db_name}"

    subprocess.check_call(
        ["alembic", "-x", f"db_url={url}", "upgrade", "head"],
        cwd=str(pkg_root),
    )

    tables = set(inspect(test_engine).get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Tables missing after migration: {missing}"
