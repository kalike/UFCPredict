"""Playwright must never run on the server's event loop.

Under `uvicorn --reload` on Windows the server loop is a SelectorEventLoop,
which cannot spawn subprocesses — Playwright's browser launch dies with
NotImplementedError. Both Tapology-scraping endpoints must therefore execute
the scrape on a worker thread with its own fresh event loop.
"""

import asyncio
import threading
from types import SimpleNamespace

from ufc_core.db import models
from ufc_core.scrapers.tapology import TapologyScraper
from lab_api.routers import predictions


def _fake_scrape(seen: dict, fights: list | None = None):
    async def fake(self, url):
        seen["scrape_thread"] = threading.get_ident()
        seen["scrape_loop"] = asyncio.get_running_loop()
        return SimpleNamespace(
            model_dump=lambda: {"event_name": "X", "n_fights": 0, "fights": []},
            fights=fights or [],
        )
    return fake


def test_tapology_scrape_runs_off_the_server_loop(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(TapologyScraper, "scrape_event", _fake_scrape(seen))

    async def server_side():
        seen["server_thread"] = threading.get_ident()
        seen["server_loop"] = asyncio.get_running_loop()
        return await predictions.tapology_scrape(
            predictions.TapologyScrapeIn(
                url="https://www.tapology.com/fightcenter/events/x"
            )
        )

    body = asyncio.run(server_side())

    assert body == {"event_name": "X", "n_fights": 0, "fights": []}
    assert seen["scrape_thread"] != seen["server_thread"]
    assert seen["scrape_loop"] is not seen["server_loop"]


def test_import_odds_runs_off_the_server_loop(client, monkeypatch):
    from ufc_core.db.engine import SessionLocal

    db = SessionLocal()
    # Idempotent setup: a previous failed run may have left the event behind
    # (deleting the Event cascades to its PredictionSession at the DB level).
    stale = db.query(models.Event).filter_by(name="UFC Offloop Night").one_or_none()
    if stale is not None:
        db.delete(stale)
        db.commit()
    ev = models.Event(name="UFC Offloop Night", status="scheduled")
    db.add(ev)
    db.flush()
    s = models.PredictionSession(event_id=ev.id, source="lab_preview")
    db.add(s)
    db.commit()

    seen: dict = {}
    monkeypatch.setattr(TapologyScraper, "scrape_event", _fake_scrape(seen))

    try:
        async def server_side():
            seen["server_thread"] = threading.get_ident()
            seen["server_loop"] = asyncio.get_running_loop()
            return await predictions.import_odds(
                s.id,
                predictions.ImportOddsRequest(
                    tapology_url="https://www.tapology.com/fightcenter/events/x"
                ),
                db=db,
            )

        resp = asyncio.run(server_side())

        assert resp.ok is True
        assert seen["scrape_thread"] != seen["server_thread"]
        assert seen["scrape_loop"] is not seen["server_loop"]
    finally:
        db.rollback()
        db.query(models.Event).filter_by(name="UFC Offloop Night").delete()
        db.commit()
        db.close()
