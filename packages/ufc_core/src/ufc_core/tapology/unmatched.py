"""Persistent loggers for unmatched names/events/fights and retry queue."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_MAX_SAMPLE_CONTEXT = 10  # cap per fighter to keep file size bounded


class UnmatchedLogger:
    """Aggregates unmatched fighters/events/fights and flushes them as JSON."""

    def __init__(
        self, fighters_path: Path, events_path: Path, fights_path: Path
    ) -> None:
        self._fighters_path = Path(fighters_path)
        self._events_path = Path(events_path)
        self._fights_path = Path(fights_path)
        self._fighters: dict[str, dict[str, Any]] = self._load_dict(self._fighters_path)
        self._events: list[dict[str, Any]] = self._load_list(self._events_path)
        self._fights: list[dict[str, Any]] = self._load_list(self._fights_path)

    @staticmethod
    def _load_dict(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _load_list(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def add_fighter(self, name: str, context: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        if name not in self._fighters:
            self._fighters[name] = {
                "occurrences": 0,
                "first_seen": now,
                "last_seen": now,
                "sample_context": [],
            }
        entry = self._fighters[name]
        entry["occurrences"] += 1
        entry["last_seen"] = now
        if len(entry["sample_context"]) < _MAX_SAMPLE_CONTEXT:
            entry["sample_context"].append(context)

    def add_event(self, name: str, date: str | None, url: str) -> None:
        # Dedupe by (name, date) so reruns don't accumulate duplicates
        for e in self._events:
            if e.get("name") == name and e.get("date") == date:
                e["last_seen"] = datetime.now(UTC).isoformat()
                e["occurrences"] = e.get("occurrences", 1) + 1
                return
        self._events.append(
            {
                "name": name,
                "date": date,
                "url": url,
                "first_seen": datetime.now(UTC).isoformat(),
                "last_seen": datetime.now(UTC).isoformat(),
                "occurrences": 1,
            }
        )

    def add_fight(
        self,
        event_url: str,
        fighter_a: str,
        fighter_b: str,
        reason: str,
    ) -> None:
        for e in self._fights:
            if (
                e.get("event_url") == event_url
                and e.get("fighter_a") == fighter_a
                and e.get("fighter_b") == fighter_b
            ):
                e["last_seen"] = datetime.now(UTC).isoformat()
                e["occurrences"] = e.get("occurrences", 1) + 1
                return
        self._fights.append(
            {
                "event_url": event_url,
                "fighter_a": fighter_a,
                "fighter_b": fighter_b,
                "reason": reason,
                "first_seen": datetime.now(UTC).isoformat(),
                "last_seen": datetime.now(UTC).isoformat(),
                "occurrences": 1,
            }
        )

    def flush(self) -> None:
        self._fighters_path.parent.mkdir(parents=True, exist_ok=True)
        for path, data in (
            (self._fighters_path, self._fighters),
            (self._events_path, self._events),
            (self._fights_path, self._fights),
        ):
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)


class RetryQueue:
    """Persistent queue of matchups that failed and should be retried later."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._entries = data
        except (json.JSONDecodeError, OSError):
            self._entries = []

    def add(
        self,
        matchup_url: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._entries.append(
            {
                "matchup_url": matchup_url,
                "reason": reason,
                "context": context or {},
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )

    def remove(self, matchup_url: str) -> None:
        self._entries = [e for e in self._entries if e["matchup_url"] != matchup_url]

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)
