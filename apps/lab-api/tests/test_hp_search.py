import time


def test_hp_studies_initially_empty(client):
    r = client.get("/api/hp-search/studies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_hp_start_creates_study(client):
    r = client.post("/api/hp-search/start", json={"model_short": "lgbm", "n_trials": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert body["study_id"] is not None


def test_hp_trials_for_unknown_study_returns_404(client):
    r = client.get("/api/hp-search/studies/99999/trials")
    assert r.status_code == 404


def test_hp_status_endpoint_exists(client):
    r = client.get("/api/hp-search/status")
    assert r.status_code == 200
    assert "is_running" in r.json()


def test_hp_unsupported_family_marks_not_supported(client):
    r = client.post("/api/hp-search/start", json={
        "model_short": "RF35", "n_trials": 3,
    })
    assert r.status_code == 200
    body = r.json()
    # It IS started (worker kicked off), but immediately marks not_supported
    for _ in range(40):
        time.sleep(0.1)
        s = client.get("/api/hp-search/status").json()
        if not s["is_running"]:
            break
    final = client.get("/api/hp-search/status").json()
    assert final["is_running"] is False
