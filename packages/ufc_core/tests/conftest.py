import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Use a separate test DB so we never touch ufc_lab production data.
TEST_DB_NAME = os.environ.get("UFC_LAB_TEST_DB_NAME", "ufc_lab_test")


def _admin_url():
    user = os.environ.get("UFC_LAB_DB_USER", os.environ.get("USER", "postgres"))
    host = os.environ.get("UFC_LAB_DB_HOST", "localhost")
    return f"postgresql+psycopg2://{user}@{host}:5432/postgres"


@pytest.fixture(scope="session")
def test_engine():
    """Ensure a clean ufc_lab_test database and return an engine bound to it."""
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        c.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin.dispose()

    os.environ["UFC_LAB_DB_NAME"] = TEST_DB_NAME
    from ufc_core.db.engine import engine
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Per-test transactional session, rolled back at the end."""
    Session = sessionmaker(bind=test_engine, autoflush=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.rollback()
        s.close()
