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
