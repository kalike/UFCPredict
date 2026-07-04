from datetime import datetime, UTC
from ufc_core.db import models as m


def test_lab_user_bet_roundtrip(db_session):
    ev = m.Event(name="UFC LUB Test", source="promoted", status="completed")
    db_session.add(ev)
    db_session.flush()
    bet = m.LabUserBet(
        event_id=ev.id, bet_type="single",
        picks=[{"pick": "Alice", "fighter_1": "Alice", "fighter_2": "Bob"}],
        combo_key="single:Alice", combined_odds=1.8, stake=30.0,
        potential_return=54.0, status="pending",
    )
    db_session.add(bet)
    db_session.commit()
    got = db_session.query(m.LabUserBet).filter_by(event_id=ev.id).one()
    assert got.status == "pending"
    assert got.picks[0]["pick"] == "Alice"
    assert got.combo_key == "single:Alice"
