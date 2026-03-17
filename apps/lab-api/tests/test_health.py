def test_health_returns_ok(client):
    r = client.get("/api/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_registry_listing(client):
    r = client.get("/api/system/registry")
    assert r.status_code == 200
    body = r.json()
    assert "models" in body
