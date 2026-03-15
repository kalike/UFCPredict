"""Shared orchestration helpers for the Tapology backfill CLI and the
UFCStats incremental hook. Lives in core/ so both consumers (scripts/ and
scrapperUFCStats.py) can import without creating cycles.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ufc_core.db.models import Event, Fight, Fighter
from ufc_core.tapology.alias_map import AliasMap
from ufc_core.tapology.event_resolver import resolve_event_url
from ufc_core.tapology.matcher import (
    FightCandidate,
    FightMatcher,
    FighterCandidate,
    FighterMatcher,
)
from ufc_core.tapology.paths import (
    fighter_aliases_path,
    retry_queue_path,
    unmatched_events_path,
    unmatched_fighters_path,
    unmatched_fights_path,
)
from ufc_core.tapology.picks_repo import PickRow, TapologyPicksRepo
from ufc_core.tapology.unmatched import RetryQueue, UnmatchedLogger


def _lazy_scraper():
    """Lazy import of TapologyHistoricalScraper — T10 not yet in ufc_core."""
    from ufc_core.scrapers.tapology_historical import (  # noqa: PLC0415
        MatchupPicksDto,
        TapologyHistoricalScraper,
    )
    return MatchupPicksDto, TapologyHistoricalScraper


def discover_db_events(
    session: Session, since: date, until: date
) -> list[tuple[int, str, date]]:
    """Return [(event_id, event_name, event_date)] for UFC events in [since, until]."""
    rows = (
        session.query(Event.id, Event.name, Event.date)
        .filter(Event.date.isnot(None))
        .all()
    )
    out = []
    for eid, name, dt in rows:
        ev_date = dt.date() if hasattr(dt, "date") else dt
        if since <= ev_date <= until:
            out.append((eid, name, ev_date))
    out.sort(key=lambda x: x[2], reverse=True)
    return out


def build_matchers(
    session: Session, restrict_event_ids: set[int] | None = None
) -> tuple[FighterMatcher, FightMatcher, AliasMap]:
    aliases = AliasMap(fighter_aliases_path())
    fighter_cands = [
        FighterCandidate(id=f.id, canonical_name=f.name)
        for f in session.query(Fighter).all()
    ]
    fight_q = session.query(Fight).filter(
        Fight.event_id.isnot(None), Fight.opponent_id.isnot(None)
    )
    if restrict_event_ids:
        fight_q = fight_q.filter(Fight.event_id.in_(restrict_event_ids))
    fight_cands = [
        FightCandidate(
            id=fi.id,
            event_id=fi.event_id,
            fighter_id=fi.fighter_id,
            opponent_id=fi.opponent_id,
        )
        for fi in fight_q.all()
    ]
    return FighterMatcher(fighter_cands, aliases), FightMatcher(fight_cands), aliases


async def process_matchup_dto(
    dto: MatchupPicksDto,
    *,
    db_event_id: int,
    event_url: str,
    session: Session,
    fighter_m: FighterMatcher,
    fight_m: FightMatcher,
    repo: TapologyPicksRepo,
    unmatched: UnmatchedLogger,
    retry_q: RetryQueue,
    force: bool,
) -> tuple[bool, str]:
    """Match a DTO to a fight row and persist. Returns (inserted, status)."""
    a_id = fighter_m.match(dto.fighter_a_name)
    b_id = fighter_m.match(dto.fighter_b_name)
    if a_id is None:
        unmatched.add_fighter(
            dto.fighter_a_name,
            context={"event_url": event_url, "opponent_name": dto.fighter_b_name},
        )
    if b_id is None:
        unmatched.add_fighter(
            dto.fighter_b_name,
            context={"event_url": event_url, "opponent_name": dto.fighter_a_name},
        )
    if a_id is None or b_id is None:
        retry_q.add(
            dto.matchup_url,
            "unmatched_fighter",
            context={
                "a": dto.fighter_a_name,
                "b": dto.fighter_b_name,
                "event_url": event_url,
                "db_event_id": db_event_id,
            },
        )
        return False, "unmatched_fighter"

    fight_db_id = fight_m.match(db_event_id, a_id, b_id)
    if fight_db_id is None:
        unmatched.add_fight(
            event_url=event_url,
            fighter_a=dto.fighter_a_name,
            fighter_b=dto.fighter_b_name,
            reason="fight_not_in_db",
        )
        retry_q.add(
            dto.matchup_url,
            "unmatched_fight",
            context={"db_event_id": db_event_id},
        )
        return False, "unmatched_fight"

    repo.upsert(
        PickRow(
            fight_id=fight_db_id,
            fighter_a_id=a_id,
            fighter_b_id=b_id,
            total_picks=dto.total_picks,
            fighter_a_win_pct=dto.fighter_a_win_pct,
            fighter_b_win_pct=dto.fighter_b_win_pct,
            fighter_a_methods=dto.fighter_a_methods,
            fighter_b_methods=dto.fighter_b_methods,
            matchup_url=dto.matchup_url,
            source_event_url=event_url,
        ),
        force=force,
    )
    session.commit()
    retry_q.remove(dto.matchup_url)
    return True, "ok"


async def tapology_hook_for_event_names(event_names: set[str] | None = None) -> dict[str, int]:
    """Resolve + scrape + persist Tapology picks for recent events.

    Selects candidate events directly from the DB (date >= today - 90 days,
    fights present), independent of which fighters the JSON scrape touched.
    Reason: a fighter whose record didn't change won't appear in
    ``new + updated``, so events from a previous JSON snapshot that were
    only just ingested into the DB would be invisible to the hook.

    The optional ``event_names`` argument is accepted for backwards
    compatibility but ignored — the DB query supersedes it.

    Errors per event are logged but never propagated; one Cloudflare block
    cannot kill the rest of the queue.

    Returns {events_resolved, picks_inserted, unresolved, skipped_recent,
    event_failures}.
    """
    from playwright.async_api import async_playwright

    from ufc_core.db.engine import SessionLocal as SyncSessionLocal

    summary = {
        "events_resolved": 0,
        "picks_inserted": 0,
        "unresolved": 0,
        "skipped_recent": 0,
        "event_failures": 0,
    }
    # NOTE: event_names is intentionally unused; kept in signature so existing
    # callers (api/scraping.py, scripts/) work without modification.
    del event_names

    unmatched = UnmatchedLogger(
        fighters_path=unmatched_fighters_path(),
        events_path=unmatched_events_path(),
        fights_path=unmatched_fights_path(),
    )
    retry_q = RetryQueue(retry_queue_path())
    _, TapologyHistoricalScraper = _lazy_scraper()
    scraper = TapologyHistoricalScraper(concurrency=2, delay=0.5)

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=user_agent)
        try:
            with SyncSessionLocal() as session:
                # Source of truth: events recent enough to plausibly need picks.
                from datetime import date as _date, timedelta as _timedelta

                date_floor = _date.today() - _timedelta(days=90)

                event_rows = (
                    session.query(Event.id, Event.name, Event.date)
                    .filter(
                        Event.date.isnot(None),
                        Event.date >= date_floor,
                    )
                    .all()
                )
                if not event_rows:
                    return summary

                # Incremental skip: filter out events whose every fight already
                # has recent picks. The expensive web work (Tapology resolve +
                # matchup scrape) is what we want to avoid; repo.upsert already
                # has a per-row recency check, but reaching it requires the full
                # scrape. Pre-filter here so we hit Tapology only for events
                # that actually need it.
                repo = TapologyPicksRepo(session)
                pending_events: list = []
                skipped_recent = 0
                for row in event_rows:
                    fight_ids = {
                        fid for (fid,) in session.query(Fight.id)
                        .filter(Fight.event_id == row.id, Fight.opponent_id.isnot(None))
                        .all()
                    }
                    if not fight_ids:
                        # Event has no fights yet → nothing to attach picks to;
                        # skip but don't count as recent (truly nothing to do).
                        continue
                    if repo.all_recent(fight_ids):
                        skipped_recent += 1
                        continue
                    pending_events.append(row)

                summary["skipped_recent"] = skipped_recent
                summary["candidates"] = len(event_rows)
                summary["pending"] = len(pending_events)
                if not pending_events:
                    return summary

                fighter_m, fight_m, _ = build_matchers(
                    session, restrict_event_ids={r.id for r in pending_events}
                )

                event_failures = 0
                for eid, name, dt in pending_events:
                    # Per-event try/except so a single Cloudflare block or
                    # parser error doesn't kill the rest of the queue. The
                    # original behaviour was to bubble up and abort everything.
                    try:
                        ev_date = dt.date() if hasattr(dt, "date") else dt
                        event_url = await resolve_event_url(context, name, ev_date)
                        if event_url is None:
                            unmatched.add_event(name, str(ev_date), url="")
                            summary["unresolved"] += 1
                            continue
                        summary["events_resolved"] += 1
                        _, dtos = await scraper.scrape_event_matchups(context, event_url)
                        for dto in dtos:
                            ok, _ = await process_matchup_dto(
                                dto,
                                db_event_id=eid,
                                event_url=event_url,
                                session=session,
                                fighter_m=fighter_m,
                                fight_m=fight_m,
                                repo=repo,
                                unmatched=unmatched,
                                retry_q=retry_q,
                                force=False,
                            )
                            if ok:
                                summary["picks_inserted"] += 1
                    except Exception as ev_exc:
                        event_failures += 1
                        retry_q.add(
                            matchup_url="",
                            reason=f"event_error: {type(ev_exc).__name__}: {ev_exc}",
                            context={"event_name": name, "event_date": str(ev_date) if ev_date else ""},
                        )

                summary["event_failures"] = event_failures
                unmatched.flush()
                retry_q.save()
        finally:
            await browser.close()

    return summary
