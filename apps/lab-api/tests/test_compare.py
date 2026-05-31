def test_compare_unknown_returns_404(client):
    r = client.get("/api/compare?a=999998&b=999999")
    assert r.status_code == 404


def test_compare_by_name_unknown_returns_404(client):
    r = client.get("/api/compare/by-name?f1=No%20Existe&f2=Tampoco%20Existe")
    assert r.status_code == 404
