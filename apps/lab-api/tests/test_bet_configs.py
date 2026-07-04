def test_bet_config_crud(client):
    payload = {"name": "agresiva", "is_default": True,
               "params": {"config": {"min_model_prob": 0.6}, "combo": {"XGB": 3}}}
    r = client.post("/api/betting/configs", json=payload)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["params"]["config"]["min_model_prob"] == 0.6

    r = client.get("/api/betting/configs")
    assert any(c["name"] == "agresiva" for c in r.json())

    # upsert por name (mismo nombre actualiza, no duplica)
    r = client.post("/api/betting/configs",
                    json={"name": "agresiva", "params": {"config": {"min_model_prob": 0.7}, "combo": None}})
    assert r.status_code == 200
    assert len([c for c in client.get("/api/betting/configs").json() if c["name"] == "agresiva"]) == 1

    r = client.delete(f"/api/betting/configs/{cid}")
    assert r.status_code == 200
    assert not any(c["name"] == "agresiva" for c in client.get("/api/betting/configs").json())
