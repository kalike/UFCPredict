def test_list_fighters_empty(client):
    r = client.get("/api/fighters/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_fighter_detail_unknown_returns_404(client):
    r = client.get("/api/fighters/999999")
    assert r.status_code == 404


def test_list_fighters_search_param(client):
    r = client.get("/api/fighters/?q=test")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
