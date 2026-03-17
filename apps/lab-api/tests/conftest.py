import os

# Set env vars BEFORE any ufc_core import can happen at collection time.
os.environ.setdefault("UFC_LAB_DB_NAME", "ufc_lab_test")
os.environ["UFC_LAB_DB_NAME"] = os.environ.get("UFC_LAB_DB_NAME", "ufc_lab_test")

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
    """Ensure a clean ufc_lab_test database exists with all tables created."""
    db_name = os.environ["UFC_LAB_DB_NAME"]
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
    engine.dispose()

    # Teardown
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
    admin.dispose()


@pytest.fixture
def client(test_engine):
    from lab_api.main import app
    return TestClient(app)
