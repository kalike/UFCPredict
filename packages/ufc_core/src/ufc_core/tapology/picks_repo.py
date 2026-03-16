"""Repository for tapology_picks rows: idempotent upsert with recency check."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ufc_core.db.models import TapologyPicks


_RECENCY_DAYS = 30


@dataclass
class PickRow:
    fight_id: int
    fighter_a_id: int
    fighter_b_id: int
    total_picks: int = 0
    fighter_a_win_pct: float | None = None
    fighter_b_win_pct: float | None = None
    fighter_a_methods: dict[str, float] | None = None
    fighter_b_methods: dict[str, float] | None = None
    matchup_url: str | None = None
    source_event_url: str | None = None


class TapologyPicksRepo:
    """Insert/upsert tapology_picks rows with skip-when-recent semantics."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, row: PickRow, force: bool = False) -> bool:
        """Upsert a row. Returns True if a row was written, False if skipped."""
        existing = (
            self._session.query(TapologyPicks)
            .filter(TapologyPicks.fight_id == row.fight_id)
            .one_or_none()
        )
        now = datetime.now(UTC)
        if existing is not None:
            if not force and existing.scraped_at:
                age = now - existing.scraped_at
                if age < timedelta(days=_RECENCY_DAYS):
                    return False
            for k, v in self._row_dict(row).items():
                setattr(existing, k, v)
            existing.scraped_at = now
            return True

        new_row = TapologyPicks(**self._row_dict(row), scraped_at=now)
        self._session.add(new_row)
        return True

    def all_recent(self, fight_ids: set[int]) -> bool:
        """True if every fight_id has a row with scraped_at < RECENCY_DAYS."""
        if not fight_ids:
            return True
        cutoff = datetime.now(UTC) - timedelta(days=_RECENCY_DAYS)
        rows = (
            self._session.query(TapologyPicks.fight_id, TapologyPicks.scraped_at)
            .filter(TapologyPicks.fight_id.in_(fight_ids))
            .all()
        )
        recent_ids = {
            r.fight_id for r in rows if r.scraped_at is not None and r.scraped_at >= cutoff
        }
        return recent_ids == fight_ids

    @staticmethod
    def _row_dict(row: PickRow) -> dict[str, Any]:
        return {
            "fight_id": row.fight_id,
            "fighter_a_id": row.fighter_a_id,
            "fighter_b_id": row.fighter_b_id,
            "total_picks": row.total_picks,
            "fighter_a_win_pct": row.fighter_a_win_pct,
            "fighter_b_win_pct": row.fighter_b_win_pct,
            "fighter_a_methods": row.fighter_a_methods,
            "fighter_b_methods": row.fighter_b_methods,
            "matchup_url": row.matchup_url,
            "source_event_url": row.source_event_url,
        }


def _normalize_pct(pct: float | None) -> float:
    """Normalize a percentage to the 0..1 range expected by the feature engine.

    The DB stores Tapology percentages in the 0-100 range (e.g. 56.0 for 56%),
    but ``compute_fight_features`` expects 0..1 (e.g. 0.56) — the same range
    used by the imputed neutral value (0.5). Without this conversion, training
    rows with picks have ``f1_tap_win_pct ∈ [0, 100]`` while imputed rows have
    ``f1_tap_win_pct = 0.5``, creating a bimodal distribution that LR/MLP
    models latch onto and that doesn't generalise to held-out (RW) data.

    None becomes 0.5 (neutral). Values already <= 1.0 are passed through so
    callers that pre-normalize don't double-scale.
    """
    if pct is None:
        return 0.5
    p = float(pct)
    if p > 1.0:
        p = p / 100.0
    return p


def _orient_picks(
    fighter_a_name: str,
    fighter_b_name: str,
    fighter_a_pct: float | None,
    fighter_b_pct: float | None,
    target_f1: str,
) -> dict:
    """Orient picks so fighter_1_win_pct corresponds to target_f1.

    If target_f1 matches neither fighter, falls back to alphabetical orientation.
    Values are normalized to 0..1 (DB stores them as 0-100).
    """
    fa_pct = _normalize_pct(fighter_a_pct)
    fb_pct = _normalize_pct(fighter_b_pct)
    if target_f1 == fighter_a_name:
        return {"fighter_1_win_pct": fa_pct, "fighter_2_win_pct": fb_pct}
    if target_f1 == fighter_b_name:
        return {"fighter_1_win_pct": fb_pct, "fighter_2_win_pct": fa_pct}
    # Alphabetical fallback
    if fighter_a_name <= fighter_b_name:
        return {"fighter_1_win_pct": fa_pct, "fighter_2_win_pct": fb_pct}
    return {"fighter_1_win_pct": fb_pct, "fighter_2_win_pct": fa_pct}


def orient_picks_for_fight(picks_entry: dict | None, fighter_1_name: str) -> dict | None:
    """Convert a repo-format lookup entry into pre-oriented format for the engine.

    Returns a dict {total_picks, fighter_1_win_pct, fighter_2_win_pct} oriented to
    `fighter_1_name`, or None if the entry has no usable picks (zero votes or None pct).
    """
    if picks_entry is None:
        return None
    total = int(picks_entry.get("total_picks") or 0)
    if total == 0:
        return None
    fa_pct = picks_entry.get("fighter_a_win_pct")
    fb_pct = picks_entry.get("fighter_b_win_pct")
    if fa_pct is None or fb_pct is None:
        return None
    oriented = _orient_picks(
        picks_entry["fighter_a_name"],
        picks_entry["fighter_b_name"],
        fa_pct,
        fb_pct,
        fighter_1_name,
    )
    return {
        "total_picks": total,
        "fighter_1_win_pct": oriented["fighter_1_win_pct"],
        "fighter_2_win_pct": oriented["fighter_2_win_pct"],
    }


def build_picks_lookup_by_event_pair(session: Session) -> dict[tuple[str, frozenset], dict]:
    """Build a lookup dict for all tapology_picks rows in the DB.

    Returns dict keyed by (event_name, frozenset({fighter_a_name, fighter_b_name})).
    Each value is a "repo-format" dict containing fighter_a_name/fighter_b_name and
    fighter_a_win_pct/fighter_b_win_pct. Use orient_picks_for_fight() to convert
    each value into the pre-oriented format expected by compute_fight_features.
    """
    from ufc_core.db.models import Event, Fight, Fighter, TapologyPicks

    rows = (
        session.query(
            Event.name.label("event_name"),
            TapologyPicks.total_picks,
            TapologyPicks.fighter_a_win_pct,
            TapologyPicks.fighter_b_win_pct,
            TapologyPicks.fighter_a_id,
            TapologyPicks.fighter_b_id,
        )
        .join(Fight, Fight.id == TapologyPicks.fight_id)
        .join(Event, Event.id == Fight.event_id)
        .all()
    )

    fighter_ids = {r.fighter_a_id for r in rows} | {r.fighter_b_id for r in rows}
    name_by_id: dict[int, str] = {
        f.id: f.name
        for f in session.query(Fighter.id, Fighter.name)
        .filter(Fighter.id.in_(fighter_ids))
        .all()
    }

    lookup: dict[tuple[str, frozenset], dict] = {}
    for r in rows:
        fa = name_by_id.get(r.fighter_a_id)
        fb = name_by_id.get(r.fighter_b_id)
        if fa is None or fb is None:
            continue
        key = (r.event_name, frozenset({fa, fb}))
        lookup[key] = {
            "total_picks": int(r.total_picks or 0),
            "fighter_a_name": fa,
            "fighter_b_name": fb,
            "fighter_a_win_pct": r.fighter_a_win_pct,
            "fighter_b_win_pct": r.fighter_b_win_pct,
        }
    return lookup


def load_db_picks_lookup() -> dict[tuple[str, frozenset], dict]:
    """Convenience helper: open a DB session and return the picks lookup.

    Returns an empty dict on any failure (DB unavailable, file mode, etc).
    Used by training/inference call sites to feed V7 features without
    repeating the try/except boilerplate.
    """
    import logging
    logger = logging.getLogger("ufc-predictor")
    try:
        from ufc_core.db.engine import SessionLocal as SyncSessionLocal
        with SyncSessionLocal() as session:
            return build_picks_lookup_by_event_pair(session)
    except Exception as exc:
        logger.info(
            "load_db_picks_lookup unavailable (%s); V7 features will use neutral imputation",
            exc,
        )
        return {}
