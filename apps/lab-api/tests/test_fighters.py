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


def test_fighter_names_returns_list(client):
    r = client.get("/api/fighters/names")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_fighter_ranking_returns_list(client):
    r = client.get("/api/fighters/ranking?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_fighter_by_name_unknown_returns_404(client):
    r = client.get("/api/fighters/by-name/No%20Existe")
    assert r.status_code == 404


def test_fight_history_unknown_returns_404(client):
    r = client.get("/api/fighters/by-name/No%20Existe/fight-history-stats")
    assert r.status_code == 404


def test_fight_matchup_unknown_returns_404(client):
    r = client.get("/api/fighters/by-name/No%20Existe/fight-matchup/0")
    assert r.status_code == 404


def test_fighter_photo_unknown_returns_404(client):
    r = client.get("/api/fighters/by-name/No%20Existe/photo")
    assert r.status_code == 404
