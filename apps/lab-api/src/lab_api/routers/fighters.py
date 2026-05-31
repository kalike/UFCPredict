"""Fighters router — list, search, detail, ranking, history, matchup."""

import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ufc_core.config import BASE_ELO, FOTOS_DIR
from ufc_core.scrapers.fotos import sanitize_filename
from ufc_core.db import models as db_models
from ufc_core.parsers import aggregate_stats, extract_fight_stats
from ufc_core.schemas.fighters import (
    FighterDetail as FighterDetailFull,
    FightMatchupResponse,
    FightStatsRecord,
)
from ufc_core.trainer.core import recalculate_elo

from lab_api.deps import get_data_store, get_db

router = APIRouter(prefix="/api/fighters", tags=["fighters"])

_FIGHT_STAT_KEYS = [
    "kd_landed",
    "kd_received",
    "sig_str_landed",
    "sig_str_attempted",
    "sig_str_received",
    "sig_str_received_attempted",
    "td_landed",
    "td_attempted",
    "td_received",
    "td_received_attempted",
    "sub_att",
    "reversals",
    "ctrl_seconds",
    "opp_ctrl_seconds",
    "head_landed",
    "body_landed",
    "leg_landed",
    "distance_landed",
    "clinch_landed",
    "ground_landed",
]


@lru_cache(maxsize=1)
def _get_elo_ratings() -> dict[str, float]:
    """ELO ratings recomputed once from the loaded DataStore (cached)."""
    ds = get_data_store()
    elo_ratings, _ = recalculate_elo(ds, base_elo=BASE_ELO, save_to_disk=False)
    return elo_ratings


def _local_photo_path(name: str):
    """Path to a readable on-disk headshot PNG, or None.

    Returns None not just when the file is missing but also when it cannot be
    read (e.g. macOS TCC blocks access to a Documents-backed FOTOS_DIR), so the
    UI degrades to initials instead of the endpoint 500ing mid-stream.
    """
    path = FOTOS_DIR / sanitize_filename(name)
    try:
        if path.is_file() and os.access(path, os.R_OK):
            return path
    except OSError:
        pass
    return None


def _resolve_photo_url(name: str, db_photo_url: str | None) -> str:
    """Prefer the locally scraped PNG; fall back to the DB photo_url column."""
    if _local_photo_path(name) is not None:
        return f"/api/fighters/by-name/{quote(name)}/photo"
    return db_photo_url or ""


def _photo_url_map(db: Session, names: list[str]) -> dict[str, str | None]:
    if not names:
        return {}
    rows = (
        db.query(db_models.Fighter.name, db_models.Fighter.photo_url)
        .filter(db_models.Fighter.name.in_(names))
        .all()
    )
    return {name: url for name, url in rows}


class FighterSummary(BaseModel):
    id: int
    name: str
    slug: str
    record: str | None
    stance: str | None
    height_cm: float | None
    reach_cm: float | None
    photo_url: str | None


class FighterDetail(FighterSummary):
    ufcstats_url: str
    tapology_url: str | None
    fight_count: int


class FighterRankingEntry(BaseModel):
    rank: int
    name: str
    elo: float
    has_photo: bool
    photo_url: str


@router.get("/", response_model=list[FighterSummary])
def list_fighters(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[FighterSummary]:
    """List fighters; optional `q` filters by name (case-insensitive substring)."""
    query = db.query(db_models.Fighter)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db_models.Fighter.name.ilike(like))
    rows = query.order_by(db_models.Fighter.name).offset(offset).limit(limit).all()
    return [FighterSummary(
        id=f.id, name=f.name, slug=f.slug, record=f.record,
        stance=f.stance, height_cm=f.height_cm, reach_cm=f.reach_cm,
        photo_url=f.photo_url,
    ) for f in rows]


@router.get("/names", response_model=list[str])
def list_fighter_names() -> list[str]:
    """All fighter names, for autocomplete."""
    return get_data_store().get_all_fighter_names()


@router.get("/ranking", response_model=list[FighterRankingEntry])
def fighter_ranking(
    limit: int = 20,
    active_months: int = 18,
    db: Session = Depends(get_db),
) -> list[FighterRankingEntry]:
    """Top-N fighters by ELO, filtered to those active in the last N months.

    A fighter counts as "active" if their most recent fight's event has a
    known date >= today - active_months * 30 days. Fighters without history
    or with no resolvable last-event date are skipped.
    """
    ds = get_data_store()
    elo_ratings = _get_elo_ratings()
    cutoff = date.today() - timedelta(days=active_months * 30)

    candidates: list[tuple[str, float]] = []
    for name, elo in elo_ratings.items():
        history = ds.fighter_histories.get(name, [])
        if not history:
            continue
        last_event = history[0].get("event", "")
        last_dt = ds.event_dates.get(last_event)
        if last_dt is None:
            continue
        last_d = last_dt.date() if isinstance(last_dt, datetime) else last_dt
        if last_d < cutoff:
            continue
        candidates.append((name, float(elo)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    top = candidates[:limit]

    photos = _photo_url_map(db, [name for name, _ in top])
    entries = []
    for i, (name, elo) in enumerate(top):
        photo_url = _resolve_photo_url(name, photos.get(name))
        entries.append(
            FighterRankingEntry(
                rank=i + 1,
                name=name,
                elo=elo,
                has_photo=bool(photo_url),
                photo_url=photo_url,
            )
        )
    return entries


@router.get("/by-name/{name}", response_model=FighterDetailFull)
def get_fighter_by_name(name: str, db: Session = Depends(get_db)) -> FighterDetailFull:
    """Rich fighter profile: physical stats, career aggregates, ELO, recent fights."""
    ds = get_data_store()
    ftr = ds.get_fighter(name)
    if ftr is None:
        raise HTTPException(404, f"Fighter '{name}' not found")

    canonical = ftr.get("name", name)
    history = ds.fighter_histories.get(canonical, [])
    career = aggregate_stats(history) if history else {}
    if career:
        # Aliases the profile UI reads directly.
        career["avg_kd"] = career.get("avg_kd_landed", 0)
        career["ctrl_minutes_per_fight"] = career.get("avg_ctrl_time", 0) / 60

    photo_url = _resolve_photo_url(canonical, _photo_url_map(db, [canonical]).get(canonical))
    elo = _get_elo_ratings().get(canonical, BASE_ELO)

    # The scraper stores the record at the payload top level, not inside stats,
    # prefixed like "Record: 28-1-0".
    stats = dict(ftr.get("stats", {}))
    record = (ftr.get("record") or "").strip()
    if record.lower().startswith("record:"):
        record = record.split(":", 1)[1].strip()
    if record and "Record" not in stats:
        stats["Record"] = record

    recent_fights = []
    for f in ftr.get("fights", [])[:10]:
        method = " ".join((f.get("method") or "").strip().split())
        ev_name = f.get("event", "")
        ev_dt = ds.event_dates.get(ev_name)
        recent_fights.append(
            {
                "result": f.get("result", ""),
                "opponent": f.get("opponent", ""),
                "method": method,
                "round": str(f.get("round", "")),
                "event": ev_name,
                "event_date": ev_dt.strftime("%b %d, %Y") if ev_dt else "",
            }
        )

    return FighterDetailFull(
        name=canonical,
        stats=stats,
        n_fights=len(ftr.get("fights", [])),
        career_stats=career,
        elo=elo,
        has_photo=bool(photo_url),
        photo_url=photo_url or "",
        recent_fights=recent_fights,
    )


@router.get("/by-name/{name}/photo")
def get_fighter_photo(name: str) -> Response:
    """Serve the locally downloaded headshot PNG (see ufc_core.scrapers.fotos).

    Reads the bytes eagerly so an unreadable file yields a clean 404 instead of
    crashing the ASGI app while FileResponse streams (macOS TCC raises EPERM on
    open() even when stat() succeeds).
    """
    path = _local_photo_path(name)
    if path is None:
        raise HTTPException(404, f"No photo for '{name}'")
    try:
        data = path.read_bytes()
    except OSError:
        raise HTTPException(404, f"Photo for '{name}' is not readable")
    return Response(content=data, media_type="image/png")


@router.get("/by-name/{name}/fight-history-stats", response_model=list[FightStatsRecord])
def get_fight_history_stats(name: str) -> list[FightStatsRecord]:
    """Per-fight raw stats for every fight in the fighter's history."""
    ds = get_data_store()
    ftr = ds.get_fighter(name)
    if ftr is None:
        raise HTTPException(404, f"Fighter '{name}' not found")

    records = []
    for i, fight in enumerate(ftr.get("fights", [])):
        try:
            stats = extract_fight_stats(fight, ftr.get("name", name))
        except Exception:
            stats = {}
        method = " ".join((fight.get("method") or "").strip().split())
        ev_name = fight.get("event", "")
        ev_dt = ds.event_dates.get(ev_name)
        records.append(
            FightStatsRecord(
                fight_index=i,
                result=fight.get("result", ""),
                opponent=fight.get("opponent", ""),
                method=method,
                round=str(fight.get("round", "")),
                event=ev_name,
                event_date=ev_dt.strftime("%b %d, %Y") if ev_dt else "",
                **{k: stats.get(k, 0) for k in _FIGHT_STAT_KEYS},
            )
        )
    return records


@router.get("/by-name/{name}/fight-matchup/{fight_index}", response_model=FightMatchupResponse)
def get_fight_matchup(name: str, fight_index: int) -> FightMatchupResponse:
    """Both fighters' raw stats from one specific fight of the fighter's history."""
    ds = get_data_store()
    ftr = ds.get_fighter(name)
    if ftr is None:
        raise HTTPException(404, f"Fighter '{name}' not found")

    canonical = ftr.get("name", name)
    raw_fights = ftr.get("fights", [])
    if fight_index < 0 or fight_index >= len(raw_fights):
        raise HTTPException(400, f"Fight index {fight_index} out of range")

    fight = raw_fights[fight_index]
    opponent_name = fight.get("opponent", "")

    try:
        fighter_stats = extract_fight_stats(fight, canonical)
    except Exception:
        fighter_stats = {}

    # Build opponent stats by mirroring (received <-> landed)
    opponent_stats = {
        "kd_landed": fighter_stats.get("kd_received", 0),
        "kd_received": fighter_stats.get("kd_landed", 0),
        "sig_str_landed": fighter_stats.get("sig_str_received", 0),
        "sig_str_attempted": fighter_stats.get("sig_str_received_attempted", 0),
        "sig_str_received": fighter_stats.get("sig_str_landed", 0),
        "sig_str_received_attempted": fighter_stats.get("sig_str_attempted", 0),
        "td_landed": fighter_stats.get("td_received", 0),
        "td_attempted": fighter_stats.get("td_received_attempted", 0),
        "td_received": fighter_stats.get("td_landed", 0),
        "td_received_attempted": fighter_stats.get("td_attempted", 0),
        "sub_att": 0,
        "reversals": 0,
        "ctrl_seconds": fighter_stats.get("opp_ctrl_seconds", 0),
        "opp_ctrl_seconds": fighter_stats.get("ctrl_seconds", 0),
        "head_landed": 0,
        "body_landed": 0,
        "leg_landed": 0,
        "distance_landed": 0,
        "clinch_landed": 0,
        "ground_landed": 0,
    }

    # Try to find actual opponent stats from their fight history
    opp_ftr = ds.get_fighter(opponent_name)
    resolved_opp_name = opponent_name
    if not opp_ftr:
        opp_lower = opponent_name.lower()
        for fn in ds.get_all_fighter_names():
            if fn.lower() == opp_lower or fn.lower().endswith(opp_lower):
                opp_ftr = ds.get_fighter(fn)
                resolved_opp_name = fn
                break

    if opp_ftr:
        event_name = fight.get("event", "")
        for opp_fight in opp_ftr.get("fights", []):
            opp_opponent = opp_fight.get("opponent", "")
            if opp_fight.get("event", "") == event_name and (
                opp_opponent == canonical or canonical.lower().endswith(opp_opponent.lower())
            ):
                try:
                    opponent_stats = extract_fight_stats(opp_fight, resolved_opp_name)
                except Exception:
                    pass
                break

    method = " ".join((fight.get("method") or "").strip().split())
    return FightMatchupResponse(
        fighter=canonical,
        opponent=opponent_name,
        event=fight.get("event", ""),
        result=fight.get("result", ""),
        method=method,
        round=str(fight.get("round", "")),
        fighter_stats=fighter_stats,
        opponent_stats=opponent_stats,
    )


@router.get("/{fighter_id}", response_model=FighterDetail)
def get_fighter(fighter_id: int, db: Session = Depends(get_db)) -> FighterDetail:
    f = db.query(db_models.Fighter).filter_by(id=fighter_id).one_or_none()
    if f is None:
        raise HTTPException(404, f"Fighter {fighter_id} not found")
    fight_count = (
        db.query(db_models.Fight)
          .filter(or_(db_models.Fight.fighter_1_id == f.id,
                      db_models.Fight.fighter_2_id == f.id))
          .count()
    )
    return FighterDetail(
        id=f.id, name=f.name, slug=f.slug, record=f.record,
        stance=f.stance, height_cm=f.height_cm, reach_cm=f.reach_cm,
        photo_url=f.photo_url, ufcstats_url=f.ufcstats_url,
        tapology_url=f.tapology_url, fight_count=fight_count,
    )
