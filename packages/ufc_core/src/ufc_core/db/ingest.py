"""Idempotent ingest of raw fighter payloads into the ufc_core DB.

The contract: callers pass a list of fighter dicts (shape produced by
ufc_core.scrapers.ufcstats.parse_fighter_page / run_incremental_scrape).
ingest_fighters_payload upserts them into `fighter`, `event`, `fight`,
and `fighter_raw` tables, returning counters for audit.

Designed to be safe under repeat execution: re-running with the same
payload performs no writes after the first call (except fighter_raw audit
rows, which are always appended — audit history is the whole point).
"""

import re
from datetime import datetime, UTC
from typing import Iterable

from sqlalchemy.orm import Session

from ufc_core.db import models


def _parse_date_loose(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%b. %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def is_dwcs_event(name: str | None) -> bool:
    """True if an event name denotes Dana White's Contender Series.

    Single source of truth for the DWCS flag (parity with the legacy backend's
    the legacy dashboard helper). Used both at ingest time
    (to stamp Event.is_dwcs) and by a backfill script.
    """
    e = (name or "").lower()
    return "dwcs" in e or "contender series" in e


_RECORD_TRIPLET_RE = re.compile(r"(\d+)-(\d+)-(\d+)")


def _normalise_record(record: str | None) -> str | None:
    """Extract canonical 'W-L-D' triplet from UFCStats record strings.

    Strips the 'Record: ' prefix and any '(N NC)' suffix.  Returns None
    if no triplet is found.
    """
    if not record:
        return None
    m = _RECORD_TRIPLET_RE.search(record)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _ht_to_cm(s: str | None) -> float | None:
    """Parse '5\\' 9\"' / '5\\'9\"' into cm. Returns None on garbage."""
    if not s or s == "--":
        return None
    m = re.match(r"\s*(\d+)\s*'\s*(\d+)\s*\"?\s*", s)
    if not m:
        return None
    feet = int(m.group(1))
    inches = int(m.group(2))
    return round((feet * 12 + inches) * 2.54, 1)


def _reach_to_cm(s: str | None) -> float | None:
    """Parse '72\"' / '72' into cm. Returns None on garbage."""
    if not s or s == "--":
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*\"?\s*", s)
    if not m:
        return None
    return round(float(m.group(1)) * 2.54, 1)


def _extract_fighter_fields(item: dict) -> dict:
    """Flatten parse_fighter_page output into Fighter column values.

    `parse_fighter_page` returns {name, record, url, fights, stats:{Height, Weight,
    Reach, STANCE, DOB, ...}}. Map those into our column shape.
    """
    stats = item.get("stats") or {}
    return {
        "record": _normalise_record(item.get("record")),
        "stance": (stats.get("STANCE") or item.get("stance") or "").strip() or None,
        "height_cm": _ht_to_cm(stats.get("Height") or item.get("height")),
        "reach_cm": _reach_to_cm(stats.get("Reach") or item.get("reach")),
        "dob": _parse_date_loose(stats.get("DOB") or item.get("dob")),
        "photo_url": item.get("photo_url"),
    }


def ingest_fighters_payload(db: Session, payload: Iterable[dict]) -> dict[str, int]:
    """Upsert raw fighter dicts into fighter/event/fight tables.

    Returns:
        dict with counters: fighters_new, fighters_updated, events_new, fights_new.
    """
    fighters_new = 0
    fighters_updated = 0
    events_new = 0
    fights_new = 0

    # Bootstrap caches from the DB so repeat calls are fully idempotent.
    fighter_by_url: dict[str, models.Fighter] = {
        f.ufcstats_url: f for f in db.query(models.Fighter).all()
    }
    # Secondary lookup by name for placeholder resolution (name is unique per fighter).
    fighter_by_name: dict[str, models.Fighter] = {
        f.name: f for f in fighter_by_url.values()
    }
    event_by_name: dict[str, models.Event] = {
        e.name: e for e in db.query(models.Event).all()
    }

    for item in payload:
        url = item["url"]
        fields = _extract_fighter_fields(item)
        existing = fighter_by_url.get(url)
        if existing is None:
            fighter = models.Fighter(
                name=item["name"],
                slug=_slug(item["name"]),
                ufcstats_url=url,
                record=fields["record"],
                stance=fields["stance"],
                height_cm=fields["height_cm"],
                reach_cm=fields["reach_cm"],
                dob=fields["dob"],
                photo_url=fields["photo_url"],
                last_scraped_at=datetime.now(UTC),
            )
            db.add(fighter)
            db.flush()
            fighter_by_url[url] = fighter
            fighter_by_name[fighter.name] = fighter
            fighters_new += 1
        else:
            # Update only the fields we actually parsed; never blank out
            # a previously-known value with None.
            if fields["record"]:
                existing.record = fields["record"]
            if fields["stance"]:
                existing.stance = fields["stance"]
            if fields["height_cm"]:
                existing.height_cm = fields["height_cm"]
            if fields["reach_cm"]:
                existing.reach_cm = fields["reach_cm"]
            if fields["dob"]:
                existing.dob = fields["dob"]
            existing.last_scraped_at = datetime.now(UTC)
            fighter = existing
            fighters_updated += 1

        # Always append a raw payload audit row (audit log — intentional duplicate).
        db.add(models.FighterRaw(fighter_id=fighter.id, payload=item))

        for fight in item.get("fights", []):
            ev_name = fight.get("event")
            if not ev_name:
                continue

            event = event_by_name.get(ev_name)
            if event is None:
                event = models.Event(
                    name=ev_name,
                    date=_parse_date_loose(fight.get("date")),
                    status="completed",
                    is_dwcs=is_dwcs_event(ev_name),
                )
                db.add(event)
                db.flush()
                event_by_name[ev_name] = event
                events_new += 1
            elif event.is_dwcs != is_dwcs_event(ev_name):
                # Keep the flag correct for events created before this was wired.
                event.is_dwcs = is_dwcs_event(ev_name)

            opp_name = fight.get("opponent")
            if not opp_name:
                continue

            # Look up opponent by name first (covers both real fighters and placeholders).
            opp = fighter_by_name.get(opp_name)
            if opp is None:
                # Placeholder fighter to satisfy the FK; filled in when their page is scraped.
                opp = models.Fighter(
                    name=opp_name,
                    slug=_slug(opp_name),
                    ufcstats_url=f"placeholder://{opp_name}",
                )
                db.add(opp)
                db.flush()
                fighter_by_url[opp.ufcstats_url] = opp
                fighter_by_name[opp.name] = opp
                fighters_new += 1

            # Idempotent fight check: same event + same pair (order-insensitive).
            existing_fight = (
                db.query(models.Fight)
                  .filter_by(event_id=event.id, fighter_1_id=fighter.id,
                             fighter_2_id=opp.id)
                  .first()
                or
                db.query(models.Fight)
                  .filter_by(event_id=event.id, fighter_1_id=opp.id,
                             fighter_2_id=fighter.id)
                  .first()
            )
            if existing_fight is not None:
                continue

            db.add(models.Fight(
                event_id=event.id,
                fighter_1_id=fighter.id,
                fighter_2_id=opp.id,
                weight_class=fight.get("weight_class"),
                result=fight.get("result"),
                method=fight.get("method"),
                round=fight.get("round"),
                time=fight.get("time"),
            ))
            fights_new += 1

    db.commit()
    return {
        "fighters_new": fighters_new,
        "fighters_updated": fighters_updated,
        "events_new": events_new,
        "fights_new": fights_new,
    }
