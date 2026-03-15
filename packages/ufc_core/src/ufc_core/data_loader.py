"""
UFC Predictor — DataStoreDB: PostgreSQL-backed data store.

The only data loader in ufc_core (no file-based mode). Loads all data from
PostgreSQL into RAM once at startup via load(); subsequent calls use the
in-memory cache.

This is a DB-only module: there is no USE_DB env var toggle here. The
file-based DataStore from the legacy backend is not copied into this package.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ufc_core.db.engine import SessionLocal as SyncSessionLocal
from ufc_core.db.models import Event, Fighter
from ufc_core.data_loader_base import BaseDataStore
from ufc_core.features.engine import build_fighter_histories
from ufc_core.parsers import american_to_decimal

logger = logging.getLogger("ufc-predictor")


class DataStoreDB(BaseDataStore):
    """PostgreSQL-backed data store with the same interface as DataStore.

    All heavy data is cached in RAM after ``load()``; the DB is only hit once
    at startup (just like the file-based version reads from disk once).
    """

    def load(self) -> None:
        """Read everything from PostgreSQL into RAM."""
        db: Session = SyncSessionLocal()
        try:
            self._load_fighters(db)
            self._load_event_dates(db)
            self._load_fight_cards(db)
            self.fighter_histories = build_fighter_histories(self.fighters_raw)
            self._build_name_index()
            self._loaded = True
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Internal loaders (from PostgreSQL)
    # ------------------------------------------------------------------

    def _load_fighters(self, db: Session) -> None:
        """Load all fighters from the ``fighter`` table."""
        rows = db.execute(select(Fighter).order_by(Fighter.name)).scalars().all()

        self.fighters_raw = []
        self.fighter_lookup = {}
        for f in rows:
            # ufc_core Fighter has no raw_data/stats/url/sex/num_fights fields;
            # build a minimal dict from the columns that do exist.
            fdict = {
                "name": f.name,
                "record": f.record or "",
                "sex": None,
                "stats": {
                    "Stance": f.stance or "",
                    "Height": str(f.height_cm) if f.height_cm else "",
                    "Reach": str(f.reach_cm) if f.reach_cm else "",
                },
                "url": f.ufcstats_url or "",
                "fights": [],
                "num_fights": 0,
            }
            self.fighters_raw.append(fdict)
            self.fighter_lookup[f.name] = fdict

        logger.info(f"  DB -> {len(self.fighters_raw)} fighters loaded")

    def _load_event_dates(self, db: Session) -> None:
        """Load events from the ``event`` table -> event_dates + event_locations."""
        rows = db.execute(select(Event).order_by(Event.date.desc().nulls_last())).scalars().all()

        self.event_dates = {}
        self.event_locations = {}
        for ev in rows:
            if ev.date:
                self.event_dates[ev.name] = ev.date.replace(tzinfo=None)
            if ev.location:
                self.event_locations[ev.name] = ev.location

        logger.info(f"  DB -> {len(self.event_dates)} event dates loaded")

    def _load_fight_cards(self, db: Session) -> None:
        """Load saved fight cards.

        TEMPORARILY a stub during F1: re-implementation against PredictionSession/
        Prediction tables is deferred to a later task (recalc/backtest in T15).
        For the lab MVP, fight_cards and predicted_events stay empty; predictions
        are computed on demand from ``Fight`` rows directly.
        """
        self.fight_cards = []
        self.predicted_events = []
