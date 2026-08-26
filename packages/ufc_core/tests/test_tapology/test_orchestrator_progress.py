"""tapology_hook_for_event_names must report per-event progress through the
optional progress_cb callback so callers (the lab-api scraping monitor) can
show which event is being processed instead of going silent for minutes."""

import asyncio
from datetime import date, timedelta

from ufc_core.db import models
import ufc_core.tapology.orchestrator as orch


class _FakeContext:
    async def close(self):
        pass


class _FakeBrowser:
    async def new_context(self, **kwargs):
        return _FakeContext()

    async def close(self):
        pass


class _FakeEngine:
    async def launch(self, headless=True):
        return _FakeBrowser()


class _FakePlaywright:
    webkit = _FakeEngine()


class _FakeAsyncPlaywrightCM:
    async def __aenter__(self):
        return _FakePlaywright()

    async def __aexit__(self, *exc):
        return False


def test_hook_reports_per_event_progress(
    db_session_real_commit, monkeypatch, tmp_path
):
    session = db_session_real_commit
    ev = models.Event(
        name="UFC Progress Night",
        status="completed",
        date=date.today() - timedelta(days=5),
    )
    a = models.Fighter(name="Prog A", slug="prog-a", ufcstats_url="u-prog-a")
    b = models.Fighter(name="Prog B", slug="prog-b", ufcstats_url="u-prog-b")
    session.add_all([ev, a, b])
    session.flush()
    session.add(
        models.Fight(event_id=ev.id, fighter_1_id=a.id, fighter_2_id=b.id)
    )
    session.commit()

    # Keep scraper state files out of the real data dir.
    for fn in (
        "unmatched_fighters_path", "unmatched_events_path",
        "unmatched_fights_path", "retry_queue_path", "fighter_aliases_path",
    ):
        monkeypatch.setattr(orch, fn, lambda fn=fn: tmp_path / f"{fn}.json")

    # No browser, no network: playwright is faked and the Tapology URL
    # resolver finds nothing, so the event ends as unresolved after one
    # full progress cycle.
    monkeypatch.setattr(
        "playwright.async_api.async_playwright", lambda: _FakeAsyncPlaywrightCM()
    )

    async def _no_url(context, name, ev_date):
        return None

    monkeypatch.setattr(orch, "resolve_event_url", _no_url)

    calls: list[tuple[int, int, str]] = []
    summary = asyncio.run(
        orch.tapology_hook_for_event_names(
            progress_cb=lambda done, total, msg: calls.append((done, total, msg))
        )
    )

    assert summary["unresolved"] == 1
    assert calls, "progress_cb was never invoked"
    assert any("UFC Progress Night" in msg for _, _, msg in calls)
    # The last report closes the loop: every pending event accounted for.
    done, total, _ = calls[-1]
    assert done == total == 1
