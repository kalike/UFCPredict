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
