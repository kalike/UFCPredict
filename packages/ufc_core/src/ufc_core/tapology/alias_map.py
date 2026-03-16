"""Manual alias map: Tapology fighter name -> canonical DB fighter name."""

import json
from pathlib import Path


class AliasMap:
    """In-memory cache of fighter_aliases.json with resolve() and add()."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        try:
            with self._path.open(encoding="utf-8") as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def resolve(self, tapology_name: str) -> str | None:
        """Return the canonical DB name for a Tapology name, or None."""
        return self._data.get(tapology_name)

    def add(self, tapology_name: str, canonical_name: str) -> None:
        """Add a new alias entry (in-memory)."""
        self._data[tapology_name] = canonical_name

    def save(self) -> None:
        """Persist the current map to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2, sort_keys=True)
