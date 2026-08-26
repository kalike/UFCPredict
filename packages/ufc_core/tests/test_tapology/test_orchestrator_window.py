"""The tapology hook must cover the whole RealWorld window (not just the
last 90 days), while never re-crawling completed events whose picks were
already captured after the event took place (final snapshot)."""

import asyncio
from datetime import UTC, datetime, timedelta

from ufc_core.db import models
import ufc_core.tapology.orchestrator as orch

from .test_orchestrator_progress import _FakeAsyncPlaywrightCM


def _patch_no_network(monkeypatch, tmp_path):
    for fn in (
        "unmatched_fighters_path", "unmatched_events_path",
        "unmatched_fights_path", "retry_queue_path", "fighter_aliases_path",
    ):
        monkeypatch.setattr(orch, fn, lambda fn=fn: tmp_path / f"{fn}.json")
    monkeypatch.setattr(
        "playwright.async_api.async_playwright", lambda: _FakeAsyncPlaywrightCM()
    )

    async def _no_url(context, name, ev_date):
        return None

    monkeypatch.setattr(orch, "resolve_event_url", _no_url)


def _add_event(session, name, days_ago, slug):
    # Summary counts are DB-global: start from a clean slate so leftovers
    # from sibling tests (pytest-randomly reorders them) can't skew counts.
    session.query(models.TapologyPicks).delete()
    session.query(models.Fight).delete()
    session.query(models.Event).delete()
    session.query(models.Fighter).delete()
    session.flush()
    ev = models.Event(
        name=name,
        status="completed",
        date=datetime.now(UTC) - timedelta(days=days_ago),
    )
    a = models.Fighter(name=f"{slug} A", slug=f"{slug}-a", ufcstats_url=f"u-{slug}-a")
    b = models.Fighter(name=f"{slug} B", slug=f"{slug}-b", ufcstats_url=f"u-{slug}-b")
    session.add_all([ev, a, b])
    session.flush()
    fight = models.Fight(event_id=ev.id, fighter_1_id=a.id, fighter_2_id=b.id)
    session.add(fight)
    session.flush()
    return ev, fight, a, b


def test_window_covers_realworld_not_just_90_days(
    db_session_real_commit, monkeypatch, tmp_path
):
    """An event inside the RealWorld window but older than 90 days must be
    queued (initial loads would otherwise never get picks nor odds)."""
    session = db_session_real_commit
    _add_event(session, "UFC Old RealWorld Night", days_ago=300, slug="oldrw")
    session.commit()

    _patch_no_network(monkeypatch, tmp_path)

    summary = asyncio.run(orch.tapology_hook_for_event_names())

    assert summary["pending"] == 1
    assert summary["unresolved"] == 1


def test_completed_event_with_final_snapshot_is_skipped(
    db_session_real_commit, monkeypatch, tmp_path
):
    """A completed event whose picks were scraped AFTER the event date is
    covered forever — the 30-day recency re-scrape only applies to upcoming
    events, otherwise every pass would re-crawl the whole history."""
    session = db_session_real_commit
    ev, fight, a, b = _add_event(
        session, "UFC Final Snapshot Night", days_ago=60, slug="finsnap"
    )
    session.add(models.TapologyPicks(
        fight_id=fight.id, fighter_a_id=a.id, fighter_b_id=b.id,
        total_picks=10, fighter_a_win_pct=60.0, fighter_b_win_pct=40.0,
        matchup_url="https://www.tapology.com/x", source_event_url="https://www.tapology.com/e",
        scraped_at=datetime.now(UTC) - timedelta(days=40),  # after the event
    ))
    session.commit()

    _patch_no_network(monkeypatch, tmp_path)

    summary = asyncio.run(orch.tapology_hook_for_event_names())

    assert summary["pending"] == 0
    assert summary["skipped_recent"] == 1


def test_completed_event_with_preevent_snapshot_is_rescraped(
    db_session_real_commit, monkeypatch, tmp_path
):
    """Picks captured BEFORE the event are a provisional snapshot: the event
    must be re-queued once to capture the final numbers."""
    session = db_session_real_commit
    ev, fight, a, b = _add_event(
        session, "UFC Preevent Snapshot Night", days_ago=60, slug="presnap"
    )
    session.add(models.TapologyPicks(
        fight_id=fight.id, fighter_a_id=a.id, fighter_b_id=b.id,
        total_picks=10, fighter_a_win_pct=60.0, fighter_b_win_pct=40.0,
        matchup_url="https://www.tapology.com/y", source_event_url="https://www.tapology.com/e2",
        scraped_at=datetime.now(UTC) - timedelta(days=70),  # before the event
    ))
    session.commit()

    _patch_no_network(monkeypatch, tmp_path)

    summary = asyncio.run(orch.tapology_hook_for_event_names())

    assert summary["pending"] == 1
