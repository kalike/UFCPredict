def test_current_combo_returns_mapping(client):
    r = client.get("/api/models/current-combo")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)  # {} when no active models seeded


def test_apply_combo_skips_unknown_model(client):
    r = client.post("/api/models/apply-combo", json={"combo": {"NOPE": 0}})
    assert r.status_code == 200
    assert "NOPE" in [s["short"] for s in r.json()["skipped"]]
