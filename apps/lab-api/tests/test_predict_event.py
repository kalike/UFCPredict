from ufc_core.db import Base, models as db_models
from ufc_core.db.engine import SessionLocal


def test_predict_unknown_event_returns_404(client):
    r = client.post("/api/predictions/event/999999/predict")
    assert r.status_code == 404


def test_predict_event_without_fights_returns_400(client, test_engine):
    Base.metadata.create_all(test_engine)
    db = SessionLocal()
    try:
        ev = db_models.Event(name="Empty Event", status="scheduled")
        db.add(ev); db.commit()
        ev_id = ev.id
    finally:
        db.close()
    r = client.post(f"/api/predictions/event/{ev_id}/predict")
    assert r.status_code == 400
