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
