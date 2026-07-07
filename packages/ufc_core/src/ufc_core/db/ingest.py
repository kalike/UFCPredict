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


def _unique_slug(name: str, ufcstats_url: str, taken: set[str]) -> str:
    """A slug not present in `taken`.

    `fighter.slug` is UNIQUE but derived from the name, and UFC has homonyms
    (two distinct 'Mike Davis'). When the plain slug is taken, disambiguate with
    a stable token from the canonical URL (the fighter-details id), so
    re-ingesting the same fighter yields the same slug (idempotent). Falls back
    to a numeric suffix only if even that collides.
    """
    base = _slug(name)
    if base not in taken:
        return base
    tail = (ufcstats_url or "").rstrip("/").rsplit("/", 1)[-1][:8]
    candidate = f"{base}-{tail}" if tail else base
    i = 2
    while candidate in taken:
        candidate = f"{base}-{tail}-{i}" if tail else f"{base}-{i}"
        i += 1
    return candidate


def is_road_to_ufc(name: str | None) -> bool:
    """True if an event is part of the 'Road to UFC' qualifier series.

    These events are excluded from every calculation (ELO, training, RealWorld
    evaluation, dashboard) via Event.source='road_to_ufc' — they are not part of
    the UFC universe we model. Single source of truth for the detector.
    """
    return "road to ufc" in (name or "").lower()


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
        dict with counters: fighters_new, fighters_updated, events_new,
        fights_new, fights_updated.
    """
    fighters_new = 0
    fighters_updated = 0
    events_new = 0
    fights_new = 0
    fights_updated = 0

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
    # All slugs currently in use, kept in sync as we create/rename fighters so
    # _unique_slug never collides with the UNIQUE(slug) constraint.
    slugs_taken: set[str] = {f.slug for f in fighter_by_url.values()}

    for item in payload:
        url = item["url"]
        fields = _extract_fighter_fields(item)
        existing = fighter_by_url.get(url)
        if existing is None:
            slug = _unique_slug(item["name"], url, slugs_taken)
            slugs_taken.add(slug)
            fighter = models.Fighter(
                name=item["name"],
                slug=slug,
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
            # Reconcile name from the fighter's own page (the canonical source):
            # a stub created earlier with a truncated opponent name gets fixed
            # here. Guard the unique slug against collisions.
            payload_name = (item.get("name") or "").strip()
            if payload_name and payload_name != existing.name:
                existing.name = payload_name
                # Re-slug to the canonical name, disambiguating against every
                # other slug in use (its own current slug is freed first).
                new_slug = _unique_slug(
                    payload_name, existing.ufcstats_url,
                    slugs_taken - {existing.slug},
                )
                if new_slug != existing.slug:
                    slugs_taken.discard(existing.slug)
                    existing.slug = new_slug
                    slugs_taken.add(new_slug)
            fighter = existing
            fighters_updated += 1

        # Always append a raw payload audit row (audit log — intentional duplicate).
        db.add(models.FighterRaw(fighter_id=fighter.id, payload=item))

        for fight in item.get("fights", []):
            ev_name = fight.get("event")
            if not ev_name:
                continue

            # The scraper emits the per-fight date under "event_date"; keep a
            # "date" fallback for any legacy payload shape.
            ev_date = _parse_date_loose(fight.get("event_date") or fight.get("date"))
            # Road to UFC events are excluded from every calculation via a
            # dedicated source; everything else keeps the default "scraped".
            ev_source = "road_to_ufc" if is_road_to_ufc(ev_name) else "scraped"
            event = event_by_name.get(ev_name)
            if event is None:
                event = models.Event(
                    name=ev_name,
                    date=ev_date,
                    status="completed",
                    is_dwcs=is_dwcs_event(ev_name),
                    source=ev_source,
                )
                db.add(event)
                db.flush()
                event_by_name[ev_name] = event
                events_new += 1
            else:
                if event.is_dwcs != is_dwcs_event(ev_name):
                    # Keep the flag correct for events created before this was wired.
                    event.is_dwcs = is_dwcs_event(ev_name)
                # Stamp the excluded source onto a Road to UFC row created before
                # this was wired (never downgrade a promoted event).
                if ev_source == "road_to_ufc" and event.source != "road_to_ufc":
                    event.source = "road_to_ufc"
                # A promoted (pre-fight) card that now shows up in a fighter's
                # scraped history has actually happened, so promote it to a real
                # scraped event. UFCStats only lists completed fights in a
                # history, so its presence here means results are available.
                elif ev_source == "scraped" and event.source == "promoted":
                    event.source = "scraped"
                # Backfill a missing date once a payload carries it (rows created
                # before event_date was read correctly have date=NULL).
                if event.date is None and ev_date is not None:
                    event.date = ev_date

            opp_name = fight.get("opponent")
            if not opp_name:
                continue

            # Resolve the opponent by canonical URL first (covers truncated
            # display names that UFCStats uses in other fighters' histories),
            # then by exact name, and only then create a stub. The stub is keyed
            # by the REAL url when known, so scraping the opponent's own page
            # later updates it (reconciliation) instead of duplicating.
            opp_url = fight.get("opponent_url")
            opp = fighter_by_url.get(opp_url) if opp_url else None
            if opp is None:
                # Residual fallback: opponent_url absent or not scraped yet.
                # When opponent_url is missing but the opponent has a real UFCStats
                # page, this path can still create a placeholder:// stub on the next
                # scrape, regenerating a duplicate fight — re-run dedup-truncated-fighters
                # after any scrape that adds new fighters.
                opp = fighter_by_name.get(opp_name)
            if opp is None:
                stub_url = opp_url or f"placeholder://{opp_name}"
                opp = fighter_by_url.get(stub_url)
            if opp is None:
                opp_slug = _unique_slug(opp_name, stub_url, slugs_taken)
                slugs_taken.add(opp_slug)
                opp = models.Fighter(
                    name=opp_name,
                    slug=opp_slug,
                    ufcstats_url=stub_url,
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
                # Backfill a placeholder fight (created by the promote flow with
                # result=NULL) once the scrape brings the real outcome. Never
                # overwrite an already-populated field — the scraped history is
                # the source of truth only for what was missing.
                res = fight.get("result")
                if res and not existing_fight.result:
                    # `res` is the owner (`fighter`) perspective; orient it to the
                    # stored fighter_1 in case the placeholder was inserted with
                    # the opposite fighter order.
                    if existing_fight.fighter_1_id == fighter.id:
                        existing_fight.result = res
                    else:
                        existing_fight.result = {"win": "loss", "loss": "win"}.get(res, res)
                    fights_updated += 1
                if not existing_fight.method and fight.get("method"):
                    existing_fight.method = fight.get("method")
                if not existing_fight.round and fight.get("round"):
                    existing_fight.round = fight.get("round")
                if not existing_fight.time and fight.get("time"):
                    existing_fight.time = fight.get("time")
                if not existing_fight.weight_class and fight.get("weight_class"):
                    existing_fight.weight_class = fight.get("weight_class")
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
        "fights_updated": fights_updated,
    }
