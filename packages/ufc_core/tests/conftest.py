import os

# Fix 1: Set env var BEFORE any ufc_core import can happen at collection time.
# Honours root conftest's UFC_LAB_DB_NAME if already set (monorepo combined run).
# Fallback chain: UFC_CORE_TEST_DB_NAME > UFC_LAB_TEST_DB_NAME > ufc_lab_test.
if not os.environ.get("UFC_LAB_DB_NAME"):
    TEST_DB_NAME = os.environ.get(
        "UFC_CORE_TEST_DB_NAME",
        os.environ.get("UFC_LAB_TEST_DB_NAME", "ufc_lab_test"),
    )
    os.environ["UFC_LAB_DB_NAME"] = TEST_DB_NAME
else:
    TEST_DB_NAME = os.environ["UFC_LAB_DB_NAME"]

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
    """Ensure a clean test database and return an engine bound to it.

    In monorepo combined runs (pytest packages/ufc_core/tests/ apps/lab-api/tests/),
    the root conftest.py's autouse test_engine already creates the DB; this
    fixture reuses the existing DB without dropping/recreating it.
    """
    # Check if the DB already exists (created by root conftest or a prior run).
    try:
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            result = c.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": TEST_DB_NAME},
            )
            db_exists = result.fetchone() is not None
        admin.dispose()
    except Exception:
        db_exists = False

    if not db_exists:
        # Solo run: create the DB ourselves.
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
            c.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
        admin.dispose()

    from ufc_core.db.engine import engine
    from ufc_core.db.base import Base
    import ufc_core.db.models  # noqa: F401
    Base.metadata.create_all(engine)
    yield engine

    if not db_exists:
        # Solo run: tear down.
        engine.dispose()
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


@pytest.fixture
def db_session_real_commit(test_engine):
    """Per-test session that performs real commits; truncates all tables after.

    Use this fixture when the test needs data to be visible to independent
    connections (e.g. CLI code that opens its own session via session_scope).
    """
    from ufc_core.db import Base
    Base.metadata.create_all(test_engine)

    SessionMaker = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = SessionMaker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        # Truncate all known tables in reverse dependency order so FK constraints hold.
        with test_engine.begin() as conn:
            for tbl in reversed(Base.metadata.sorted_tables):
                conn.execute(tbl.delete())
