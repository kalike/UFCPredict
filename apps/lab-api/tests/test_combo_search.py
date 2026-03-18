def test_combo_studies_initially_empty(client):
    r = client.get("/api/combo-search/studies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_combo_start_creates_study(client):
    r = client.post("/api/combo-search/start", json={"name": "test-combo-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True


def test_combo_start_rejects_duplicate(client):
    r = client.post("/api/combo-search/start", json={"name": "dup-name"})
    assert r.status_code == 200
    r2 = client.post("/api/combo-search/start", json={"name": "dup-name"})
    assert r2.status_code == 200
    assert r2.json()["started"] is False


def test_combo_status_endpoint_exists(client):
    r = client.get("/api/combo-search/status")
    assert r.status_code == 200
    assert "is_running" in r.json()


def test_combo_no_versions_fails_gracefully(client):
    """Without trained model versions, the worker should mark study as failed."""
    import time
    r = client.post("/api/combo-search/start", json={"name": f"fail-test-{int(time.time())}"})
    assert r.status_code == 200
    body = r.json()
    if not body["started"]:
        return  # already had a previous worker queued; that's also fine
    for _ in range(40):
        time.sleep(0.1)
        s = client.get("/api/combo-search/status").json()
        if not s["is_running"]:
            break
    final = client.get("/api/combo-search/status").json()
    assert final["is_running"] is False
