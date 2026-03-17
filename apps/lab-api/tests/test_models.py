def test_list_models_empty(client):
    r = client.get("/api/models/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_versions_for_unknown_model_returns_404(client):
    r = client.get("/api/models/doesnotexist/versions")
    assert r.status_code == 404


def test_disable_unknown_model_returns_404(client):
    r = client.post("/api/models/doesnotexist/disable")
    assert r.status_code == 404


def test_train_status_idle(client):
    r = client.get("/api/models/train/status")
    assert r.status_code == 200
    body = r.json()
    assert body["is_running"] is False


def test_train_starts(client):
    r = client.post("/api/models/train", json={"model_short": "lgbm"})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] in (True, False)
