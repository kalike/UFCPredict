"""Dependency injection — lazy-loaded singletons of DataStore + ModelRegistry."""

from functools import lru_cache

from sqlalchemy.orm import Session
from ufc_core.data_loader import DataStoreDB
from ufc_core.db.engine import SessionLocal
from ufc_core.models.registry import ModelRegistry


@lru_cache(maxsize=1)
def get_data_store() -> DataStoreDB:
    """Singleton DataStore loaded once at first request."""
    ds = DataStoreDB()
    ds.load()
    return ds


def get_db() -> Session:
    """Per-request DB session. Use as FastAPI Depends()."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_registry(db: Session) -> ModelRegistry:
    """ModelRegistry bound to the request's session."""
    return ModelRegistry(db)
