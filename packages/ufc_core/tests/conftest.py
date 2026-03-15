import os

# Fix 1: Set env var BEFORE any ufc_core import can happen at collection time.
TEST_DB_NAME = os.environ.get("UFC_LAB_TEST_DB_NAME", "ufc_lab_test")
os.environ["UFC_LAB_DB_NAME"] = TEST_DB_NAME

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session


# Fix 3: _admin_url() honours port + password.
def _admin_url():
    user = os.environ.get("UFC_LAB_DB_USER", os.environ.get("USER", "postgres"))
    host = os.environ.get("UFC_LAB_DB_HOST", "localhost")
    port = os.environ.get("UFC_LAB_DB_PORT", "5432")
    pwd  = os.environ.get("UFC_LAB_DB_PASS", "")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql+psycopg2://{auth}{host}:{port}/postgres"


@pytest.fixture(scope="session")
def test_engine():
    """Ensure a clean ufc_lab_test database and return an engine bound to it."""
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        c.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin.dispose()

    from ufc_core.db.engine import engine
    yield engine
    engine.dispose()

    # Teardown: drop the test DB so parallel/repeated runs are clean.
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
    admin.dispose()


# Fix 2: SAVEPOINT-based db_session rollback — immune to inner commits.
@pytest.fixture
def db_session(test_engine):
    """Per-test session with SAVEPOINT-based rollback (immune to inner commits)."""
    connection = test_engine.connect()
    transaction = connection.begin()
    SessionMaker = sessionmaker(
        bind=connection, autoflush=False, autocommit=False,
        join_transaction_mode="create_savepoint",
    )
    session = SessionMaker()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
