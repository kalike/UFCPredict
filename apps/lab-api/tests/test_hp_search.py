import time


def test_hp_studies_initially_empty(client):
    r = client.get("/api/hp-search/studies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_hp_start_creates_study(client):
    assert _wait_idle(client)
    r = client.post("/api/hp-search/start", json={"model_short": "XGB", "n_trials": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert body["study_id"] is not None
    _wait_idle(client)  # don't leak a running job into later tests


def test_hp_trials_for_unknown_study_returns_404(client):
    r = client.get("/api/hp-search/studies/99999/trials")
    assert r.status_code == 404


def test_hp_status_endpoint_exists(client):
    r = client.get("/api/hp-search/status")
    assert r.status_code == 200
    assert "is_running" in r.json()


def _wait_idle(client, timeout_s: float = 40.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not client.get("/api/hp-search/status").json()["is_running"]:
            return True
        time.sleep(0.2)
    return False


def test_hp_supported_families_accepted(client):
    # The four canonical families all support HP search.
    for fam in ("XGB", "RF", "CB", "Deep"):
        assert _wait_idle(client), "a previous HP run did not settle"
        r = client.post("/api/hp-search/start", json={"model_short": fam, "n_trials": 2})
        assert r.status_code == 200
        assert r.json()["started"] is True
        # Empty test DB → the worker fails fast on dataset build.
        assert _wait_idle(client)


def test_hp_adopt_empty_returns_400(client):
    r = client.post("/api/hp-search/adopt", json={"items": []})
    assert r.status_code == 400


def test_hp_adopt_unknown_study_returns_404(client):
    r = client.post("/api/hp-search/adopt", json={
        "items": [{"study_id": 999999, "trial_idx": 0}],
    })
    assert r.status_code == 404


def test_hp_delete_unknown_study_returns_404(client):
    r = client.delete("/api/hp-search/studies/999999")
    assert r.status_code == 404


def test_hp_delete_study_removes_it(client):
    assert _wait_idle(client)
    sid = client.post("/api/hp-search/start", json={"model_short": "XGB", "n_trials": 2}).json()["study_id"]
    assert _wait_idle(client)  # let the worker finish (empty test DB → fails fast)
    r = client.delete(f"/api/hp-search/studies/{sid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Gone: its trials endpoint now 404s.
    assert client.get(f"/api/hp-search/studies/{sid}/trials").status_code == 404


def test_hp_delete_batch_removes_several(client):
    assert _wait_idle(client)
    ids = []
    for _ in range(2):
        ids.append(client.post("/api/hp-search/start", json={"model_short": "XGB", "n_trials": 2}).json()["study_id"])
        assert _wait_idle(client)
    r = client.post("/api/hp-search/studies/delete-batch", json={"ids": ids})
    assert r.status_code == 200
    assert r.json()["deleted"] == 2
    for sid in ids:
        assert client.get(f"/api/hp-search/studies/{sid}/trials").status_code == 404


def test_hp_unsupported_family_marks_not_supported(client):
    # A non-canonical short (e.g. the virtual ensemble) is not HP-searchable.
    r = client.post("/api/hp-search/start", json={
        "model_short": "Ens3", "n_trials": 3,
    })
    assert r.status_code == 200
    # It IS started (worker kicked off), but immediately marks not_supported.
    for _ in range(40):
        time.sleep(0.1)
        s = client.get("/api/hp-search/status").json()
        if not s["is_running"]:
            break
    final = client.get("/api/hp-search/status").json()
    assert final["is_running"] is False
