"""
UFC Predictor — Abstract base class for data stores.

Eliminates duplicated code between DataStore (file-based)
and DataStoreDB (PostgreSQL-backed).
"""

import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime


def _normalize_name(name: str) -> str:
    """Strip accent marks, smart quotes, hyphens, and lowercase for matching."""
    name = name.replace("\u2018", "'").replace("\u2019", "'").replace("\u2032", "'")
    name = name.replace("-", " ")
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


class BaseDataStore(ABC):
    """Abstract base for file-based and DB-backed data stores.

    Subclasses must implement load() and the three private loaders.
    All public attributes and shared methods are defined here.
    """

    def __init__(self):
        self.fighters_raw: list[dict] = []
        self.fighter_lookup: dict[str, dict] = {}
        self.fighter_histories: dict[str, list[dict]] = {}
        self.event_dates: dict[str, datetime] = {}
        self.event_locations: dict[str, str] = {}
        self.fight_cards: list[dict] = []
        self.predicted_events: list[dict] = []
        self._loaded = False
        self._name_index: dict[str, str] = {}

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def load(self) -> None:
        """Load all data into RAM (from files or DB)."""
        ...

    def resolve_name(self, name: str) -> str:
        """Return canonical fighter name, matching accent-insensitively.

        E.g. 'Edgar Cháirez' → 'Edgar Chairez'. Falls back to the
        original name if no match is found.
        """
        if name in self.fighter_lookup:
            return name
        norm = _normalize_name(name)
        if norm in self._name_index:
            return self._name_index[norm]
        return name

    def _build_name_index(self) -> None:
        """Build accent-insensitive name index. Called at end of load()."""
        self._name_index = {_normalize_name(n): n for n in self.fighter_lookup}

    def get_fighter(self, name: str) -> dict | None:
        """Get fighter data by exact name."""
        return self.fighter_lookup.get(name)

    def search_fighters(self, query: str, limit: int = 20) -> list[dict]:
        """Search fighters by partial name match (case-insensitive)."""
        q = query.lower()
        results = []
        for name, ftr in self.fighter_lookup.items():
            if q in name.lower():
                results.append(
                    {
                        "name": name,
                        "record": ftr.get("stats", {}).get("Record", ""),
                        "height": ftr.get("stats", {}).get("Height", ""),
                        "weight": ftr.get("stats", {}).get("Weight", ""),
                        "reach": ftr.get("stats", {}).get("Reach", ""),
                        "n_fights": len(ftr.get("fights", [])),
                    }
                )
                if len(results) >= limit:
                    break
        return results

    def get_events(self) -> list[str]:
        """Get unique event names from predicted events (preserves order)."""
        return [ev["canonical_name"] for ev in self.predicted_events]

    def get_predicted_events(self) -> list[dict]:
        """Get full predicted event info, sorted by date (most recent first)."""
        events = sorted(
            self.predicted_events,
            key=lambda e: e["date"] or datetime.min,
            reverse=True,
        )
        return events

    def get_fights_by_event(self, event: str) -> list[dict]:
        """Get fights for a specific event (matches canonical or pred name)."""
        return [f for f in self.fight_cards if f["event"] == event]

    def get_fighter_photo_filename(self, name: str) -> str | None:
        """Get the photo filename for a fighter (e.g. 'Jon_Jones.png')."""
        return name.replace(" ", "_") + ".png"

    def get_all_fighter_names(self) -> list[str]:
        """Return all fighter names sorted alphabetically."""
        return sorted(self.fighter_lookup.keys())
