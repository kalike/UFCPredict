"""Paths for Tapology scraper state files (under $UFC_DATA_DIR/tapology/)."""

from pathlib import Path

from ufc_core.config import DATA_DIR


def tapology_state_dir() -> Path:
    """Return the Tapology state directory, creating it if missing."""
    p = DATA_DIR / "tapology"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fighter_aliases_path() -> Path:
    return tapology_state_dir() / "fighter_aliases.json"


def unmatched_fighters_path() -> Path:
    return tapology_state_dir() / "unmatched_fighters.json"


def unmatched_events_path() -> Path:
    return tapology_state_dir() / "unmatched_events.json"


def unmatched_fights_path() -> Path:
    return tapology_state_dir() / "unmatched_fights.json"


def retry_queue_path() -> Path:
    return tapology_state_dir() / "retry_queue.json"


def events_listing_cache_path() -> Path:
    return tapology_state_dir() / "events_listing_cache.html"
