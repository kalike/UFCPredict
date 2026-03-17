def test_events_list_empty(client):
    r = client.get("/api/predictions/events")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_events_filter_by_status(client):
    r = client.get("/api/predictions/events?status=scheduled")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_event_cache_unknown_event_returns_404(client):
    r = client.get("/api/predictions/cache/999999")
    assert r.status_code == 404
