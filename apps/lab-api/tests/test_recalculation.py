def test_recalc_status_endpoint(client):
    r = client.get("/api/recalculation/status")
    assert r.status_code == 200
    assert "is_running" in r.json()


def test_recalc_runs_empty(client):
    r = client.get("/api/recalculation/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_recalc_run_with_no_events(client):
    import time
    r = client.post("/api/recalculation/run", json={"event_ids": [999999]})
    assert r.status_code == 200
    for _ in range(30):
        time.sleep(0.1)
        s = client.get("/api/recalculation/status").json()
        if not s["is_running"]:
            break
    final = client.get("/api/recalculation/status").json()
    assert final["is_running"] is False
