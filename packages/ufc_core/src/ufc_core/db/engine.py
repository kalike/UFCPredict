import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

DB_HOST = os.environ.get("UFC_LAB_DB_HOST", "localhost")
DB_PORT = os.environ.get("UFC_LAB_DB_PORT", "5432")
DB_USER = os.environ.get("UFC_LAB_DB_USER", os.environ.get("USER", "postgres"))
DB_PASS = os.environ.get("UFC_LAB_DB_PASS", "")
DB_NAME = os.environ.get("UFC_LAB_DB_NAME", "ufc_lab")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
