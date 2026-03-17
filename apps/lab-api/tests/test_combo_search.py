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
