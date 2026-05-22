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
