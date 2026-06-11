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
from ufc_core.db.models import Event, Fighter, FighterRaw
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
        """Load all fighters from the ``fighter`` table.

        When a ``fighter_raw`` payload exists for a fighter (written by
        ingest_fighters_payload after scraping), we use it as the primary
        source so that full fight history is available for feature engineering.
        Otherwise we fall back to the basic Fighter table columns.
        """
        rows = db.execute(select(Fighter).order_by(Fighter.name)).scalars().all()

        # Build a map: fighter_id → latest raw payload (if any).
        # Only load the latest row per fighter to keep memory bounded.
        latest_raw: dict[int, dict] = {}
        raw_rows = (
            db.execute(
                select(FighterRaw)
                .order_by(FighterRaw.fighter_id, FighterRaw.scraped_at.desc())
            )
            .scalars()
            .all()
        )
        for rr in raw_rows:
            if rr.fighter_id not in latest_raw and isinstance(rr.payload, dict):
                latest_raw[rr.fighter_id] = rr.payload

        # Canonical name per UFCStats URL — used to repair garbled opponent
        # names. The scraper stores the opponent as the whole "Fighter" cell
        # text (owner + opponent concatenated); opponent_url is reliable, so we
        # resolve the display name from it without re-scraping.
        url_to_name = {f.ufcstats_url: f.name for f in rows if f.ufcstats_url}

        self.fighters_raw = []
        self.fighter_lookup = {}
        for f in rows:
            payload = latest_raw.get(f.id)
            if payload and "fights" in payload:
                # Full payload from scraper: use as-is, only override name to
                # keep canonical casing from the fighter table.
                fdict = dict(payload)
                fdict["name"] = f.name
                fdict["fights"] = [
                    ({**ft, "opponent": url_to_name[ou]}
                     if (ou := ft.get("opponent_url")) and ou in url_to_name
                     else ft)
                    for ft in fdict.get("fights", [])
                ]
            else:
                # Fallback: minimal dict from fighter table columns (no history).
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

        logger.info(
            "  DB -> %d fighters loaded (%d with raw payload)",
            len(self.fighters_raw),
            len(latest_raw),
        )

    def _load_event_dates(self, db: Session) -> None:
        """Load events from the ``event`` table -> event_dates + event_locations.

        Non-UFC events (``source == "fighter_history"``: PRIDE, Strikeforce, ONE,
        ...) are excluded from ``event_dates`` so the ELO/training universe is
        UFC-only, matching the legacy backend. Because ``event_dates`` is the
        single gate consulted by recalculate_elo and _build_dataset (a fight whose
        event is absent here is skipped), excluding them here makes ELO, the
        ranking and the training datasets all UFC-only in one place.
        """
        rows = db.execute(select(Event).order_by(Event.date.desc().nulls_last())).scalars().all()

        self.event_dates = {}
        self.event_locations = {}
        excluded_non_ufc = 0
        for ev in rows:
            # preview = ad-hoc user matchups not yet promoted; no real results.
            # road_to_ufc = the Asian qualifier series, excluded from every
            # calculation. None must leak into PIT date lookups or the
            # ELO/training universe. This is the central gatekeeper.
            if ev.source in ("fighter_history", "preview", "road_to_ufc"):
                excluded_non_ufc += 1
                continue
            if ev.date:
                self.event_dates[ev.name] = ev.date.replace(tzinfo=None)
            if ev.location:
                self.event_locations[ev.name] = ev.location

        logger.info(
            "  DB -> %d event dates loaded (%d non-UFC events excluded)",
            len(self.event_dates), excluded_non_ufc,
        )

    def _load_fight_cards(self, db: Session) -> None:
        """Load saved fight cards.

        TEMPORARILY a stub during F1: re-implementation against PredictionSession/
        Prediction tables is deferred to a later task (recalc/backtest in T15).
        For the lab MVP, fight_cards and predicted_events stay empty; predictions
        are computed on demand from ``Fight`` rows directly.
        """
        self.fight_cards = []
        self.predicted_events = []
