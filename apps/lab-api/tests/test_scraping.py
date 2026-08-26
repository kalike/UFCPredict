def test_scraping_status_idle(client):
    r = client.get("/api/scraping/status")
    assert r.status_code == 200
    body = r.json()
    assert body["is_running"] is False


def test_scraping_runs_initially_empty(client):
    r = client.get("/api/scraping/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_photo_status_idle(client):
    r = client.get("/api/scraping/photos/status")
    assert r.status_code == 200
    assert r.json()["is_running"] is False


def test_photo_scrape_start_empty_db(client):
    # No fighters in the test DB → 0 names → download skipped, no network.
    r = client.post("/api/scraping/photos")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert "0 fighters" in body["message"]


# ── Post-scrape auto-refresh + recalc hook ──────────────────────────────


def test_refresh_and_recalc_after_scrape_triggers_all(monkeypatch):
    """The hook drops the DataStore singleton, invalidates both dashboard
    caches, and starts a recalc when none is running."""
    import lab_api.deps as deps
    import lab_api.services.dashboard as dsvc
    import lab_api.services.dashboard_realworld as rwsvc
    import lab_api.services.recalculation as recalc_svc
    from lab_api.routers.scraping import _refresh_and_recalc_after_scrape

    calls: list = []
    monkeypatch.setattr(deps.get_data_store, "cache_clear",
                        lambda: calls.append("ds_clear"))
    monkeypatch.setattr(dsvc, "invalidate", lambda: calls.append("dsvc"))
    monkeypatch.setattr(rwsvc, "invalidate", lambda: calls.append("rwsvc"))
    monkeypatch.setattr(recalc_svc, "get_status", lambda: {"is_running": False})
    monkeypatch.setattr(recalc_svc, "start_recalculation",
                        lambda ev: calls.append(("recalc", ev)) or {"started": True})

    _refresh_and_recalc_after_scrape(3)

    assert "ds_clear" in calls
    assert "dsvc" in calls and "rwsvc" in calls
    assert ("recalc", None) in calls  # default scope = RealWorld window


def test_refresh_and_recalc_skips_recalc_when_running(monkeypatch):
    """A recalc already in flight must not be double-started, but caches are
    still refreshed so the dashboard picks up the new data."""
    import lab_api.deps as deps
    import lab_api.services.dashboard as dsvc
    import lab_api.services.dashboard_realworld as rwsvc
    import lab_api.services.recalculation as recalc_svc
    from lab_api.routers.scraping import _refresh_and_recalc_after_scrape

    calls: list = []
    monkeypatch.setattr(deps.get_data_store, "cache_clear",
                        lambda: calls.append("ds_clear"))
    monkeypatch.setattr(dsvc, "invalidate", lambda: calls.append("dsvc"))
    monkeypatch.setattr(rwsvc, "invalidate", lambda: calls.append("rwsvc"))
    monkeypatch.setattr(recalc_svc, "get_status", lambda: {"is_running": True})
    monkeypatch.setattr(recalc_svc, "start_recalculation",
                        lambda ev: calls.append(("recalc", ev)))

    _refresh_and_recalc_after_scrape(1)

    assert "ds_clear" in calls and "dsvc" in calls and "rwsvc" in calls
    assert not any(isinstance(c, tuple) for c in calls)  # recalc NOT started


# ── Tapology hook on empty incremental runs ─────────────────────────────


def test_tapology_hook_runs_when_scrape_finds_nothing_new(
    client, monkeypatch, tmp_path
):
    """The Tapology hook selects pending events from the DB itself, so it must
    run even when the incremental scrape ingests no new/updated fighters —
    otherwise events ingested while the hook was broken never get picks."""
    import time

    import ufc_core.config as cfg
    import ufc_core.scrapers.ufcstats as ufcstats
    import ufc_core.tapology as tap
    from lab_api.routers import scraping

    monkeypatch.setattr(cfg, "SCRAPE_DUMPS_DIR", tmp_path / "dumps")
    # Incremental scrape returns nothing new, without touching the network.
    monkeypatch.setattr(
        ufcstats, "process_letter_incremental", lambda *a, **k: ([], [], {}, [])
    )

    hook_calls: list = []

    async def fake_hook(event_names=None, progress_cb=None):
        hook_calls.append(event_names)
        return {"events_resolved": 0, "picks_inserted": 0}

    monkeypatch.setattr(tap, "tapology_hook_for_event_names", fake_hook)
    monkeypatch.setattr(scraping, "_refresh_and_recalc_after_scrape",
                        lambda n: None)

    r = client.post("/api/scraping/start", params={"letters": "a"})
    assert r.status_code == 200

    for _ in range(100):
        with scraping._lock:
            running = scraping._state["is_running"]
        if not running:
            break
        time.sleep(0.1)
    assert not running
    assert scraping._state["error"] is None
    assert hook_calls, "tapology hook must run even with no new fighters"


def test_tapology_progress_reaches_monitor(client, monkeypatch, tmp_path):
    """Per-event progress reported by the tapology hook must land in the
    monitor state the frontend polls (step/progress bar/log console), and the
    closing summary line must use the hook's real summary keys."""
    import time

    import ufc_core.config as cfg
    import ufc_core.scrapers.ufcstats as ufcstats
    import ufc_core.tapology as tap
    from lab_api.routers import scraping

    monkeypatch.setattr(cfg, "SCRAPE_DUMPS_DIR", tmp_path / "dumps")
    monkeypatch.setattr(
        ufcstats, "process_letter_incremental", lambda *a, **k: ([], [], {}, [])
    )

    async def fake_hook(event_names=None, progress_cb=None):
        progress_cb(1, 3, "event 'UFC Wired Night': 4 picks inserted (5 matchups)")
        return {
            "events_resolved": 1, "picks_inserted": 4, "unresolved": 0,
            "skipped_recent": 2, "event_failures": 0, "pending": 1,
        }

    monkeypatch.setattr(tap, "tapology_hook_for_event_names", fake_hook)
    monkeypatch.setattr(scraping, "_refresh_and_recalc_after_scrape",
                        lambda n: None)

    r = client.post("/api/scraping/start", params={"letters": "a"})
    assert r.status_code == 200

    for _ in range(100):
        with scraping._lock:
            running = scraping._state["is_running"]
        if not running:
            break
        time.sleep(0.1)
    assert not running
    assert scraping._state["error"] is None

    logs = "\n".join(scraping._state["log_lines"])
    assert "UFC Wired Night" in logs
    assert "tapology 1/3" in logs
    # Progress bar values survive in state (frontend shows current/total).
    assert scraping._state["progress_total"] == 3
    # Closing summary reflects what the hook actually did.
    assert "resolved=1" in logs and "picks=4" in logs


# ── Reingest from a surviving scrape dump ───────────────────────────────


def test_reingest_404_when_no_dumps(client, monkeypatch, tmp_path):
    import ufc_core.config as cfg
    monkeypatch.setattr(cfg, "SCRAPE_DUMPS_DIR", tmp_path / "dumps")
    r = client.post("/api/scraping/reingest")
    assert r.status_code == 404


def test_reingest_replays_dump(client, monkeypatch, tmp_path):
    """A surviving .jsonl dump is replayed into the DB without any network
    call, and deleted once fully ingested."""
    import json
    import time

    import ufc_core.config as cfg
    from lab_api.routers import scraping

    dumps = tmp_path / "dumps"
    dumps.mkdir()
    dump = dumps / "ufcstats_20260101_000000.jsonl"
    fighter = {
        "name": "Reingest Guy", "url": "http://ufcstats.com/fighter-details/reing1",
        "record": "Record: 1-0-0",
        "fights": [{
            "event": "UFC Reingest Night", "event_date": "2026-01-01",
            "opponent": "Reingest Rival",
            "opponent_url": "http://ufcstats.com/fighter-details/reing2",
            "result": "win", "method": "KO", "round": 1, "time": "1:00",
        }],
    }
    dump.write_text(json.dumps(fighter) + "\n")
    monkeypatch.setattr(cfg, "SCRAPE_DUMPS_DIR", dumps)
    # The post-ingest cache refresh would kick off a real recalculation.
    monkeypatch.setattr(scraping, "_refresh_and_recalc_after_scrape",
                        lambda n: None)

    r = client.post("/api/scraping/reingest")
    assert r.status_code == 200
    assert r.json()["started"] is True

    for _ in range(100):
        with scraping._lock:
            running = scraping._state["is_running"]
        if not running:
            break
        time.sleep(0.1)
    assert not running
    assert scraping._state["error"] is None
    assert scraping._state["counts"]["fighters_new"] == 2  # scraped + stub rival
    assert not dump.exists()  # consumed on success

    from ufc_core.db import models as m
    from ufc_core.db.engine import SessionLocal
    db = SessionLocal()
    try:
        assert db.query(m.Fighter).filter_by(name="Reingest Guy").count() == 1
        assert db.query(m.Event).filter_by(name="UFC Reingest Night").count() == 1
    finally:
        db.close()
