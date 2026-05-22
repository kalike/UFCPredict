import os

# Set env vars BEFORE any ufc_core import can happen at collection time.
# Honours root conftest's UFC_LAB_DB_NAME if already set (monorepo combined run).
_LAB_DB = os.environ.get("UFC_LAB_DB_NAME") or os.environ.get("LAB_API_TEST_DB_NAME", "ufc_lab_test")
os.environ["UFC_LAB_DB_NAME"] = _LAB_DB

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient


def _admin_url():
    user = os.environ.get("UFC_LAB_DB_USER", os.environ.get("USER", "postgres"))
    host = os.environ.get("UFC_LAB_DB_HOST", "localhost")
    port = os.environ.get("UFC_LAB_DB_PORT", "5432")
    pwd  = os.environ.get("UFC_LAB_DB_PASS", "")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql+psycopg2://{auth}{host}:{port}/postgres"


@pytest.fixture(scope="session", autouse=True)
def test_engine():
    """Ensure a clean test database exists with all tables created.

    In monorepo combined runs, the root conftest.py autouse test_engine has
    already created the DB; this fixture detects that and reuses it.
    """
    db_name = _LAB_DB

    # Check if DB already exists (root conftest may have created it).
    try:
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            result = c.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": db_name},
            )
            db_exists = result.fetchone() is not None
        admin.dispose()
    except Exception:
        db_exists = False

    if not db_exists:
        # Solo run: create the DB.
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
            c.execute(text(f"CREATE DATABASE {db_name}"))
        admin.dispose()

    from ufc_core.db.engine import engine
    from ufc_core.db.base import Base
    # Import all models so their metadata is registered
    import ufc_core.db.models  # noqa: F401
    Base.metadata.create_all(engine)
    yield engine

    if not db_exists:
        # Solo run: tear down.
        engine.dispose()
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        admin.dispose()


@pytest.fixture
def client(test_engine):
    from lab_api.main import app
    return TestClient(app)


def _wait_workers_idle(timeout: float) -> list[str]:
    """Poll every background worker until is_running=False. Returns the names
    of workers still busy after the timeout (empty list = all idle)."""
    import time
    from lab_api.services import combo_search, hp_search, recalculation, training
    from lab_api.routers import scraping

    # Services expose get_status(); the scraping router keeps its scrape/photo
    # job state as module-level dicts. Both spawn daemon threads that hold a DB
    # connection, so a test that starts one and returns without waiting blocks
    # the next test's DROP DATABASE ("being accessed by other users").
    checks = {
        "training": lambda: training.get_status()["is_running"],
        "hp_search": lambda: hp_search.get_status()["is_running"],
        "combo_search": lambda: combo_search.get_status()["is_running"],
        "recalculation": lambda: recalculation.get_status()["is_running"],
        "scraping": lambda: scraping._state["is_running"],
        "photos": lambda: scraping._photo_state["is_running"],
    }
    deadline = time.time() + timeout
    busy = [n for n, c in checks.items() if c()]
    while busy and time.time() < deadline:
        time.sleep(0.2)
        busy = [n for n, c in checks.items() if c()]
    return busy


@pytest.fixture(autouse=True)
def workers_idle():
    """Workers are module-level singletons with daemon threads — a test that
    starts a job and returns without waiting poisons every later test
    ("A training job is already running"). Wait defensively before each test,
    and fail the leaking test (not its victim) if it leaves a worker busy."""
    _wait_workers_idle(timeout=60.0)
    yield
    busy = _wait_workers_idle(timeout=60.0)
    assert not busy, (
        f"Test left background worker(s) still running after 60s: {busy}. "
        "Poll the worker's status endpoint until is_running=False before returning."
    )
