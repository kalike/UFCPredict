def test_publish_dry_run_requires_target_or_all(client):
    r = client.post("/api/publish/dry-run", json={})
    assert r.status_code == 400


def test_publish_dry_run_empty_active(client):
    r = client.post("/api/publish/dry-run", json={"all_active": True})
    assert r.status_code == 200
    body = r.json()
    assert body["rc"] == 0


def test_publish_runs_empty(client):
    r = client.get("/api/publish/runs")
    assert r.status_code == 200
    assert r.json() == []
