def test_compare_unknown_returns_404(client):
    r = client.get("/api/compare?a=999998&b=999999")
    assert r.status_code == 404
