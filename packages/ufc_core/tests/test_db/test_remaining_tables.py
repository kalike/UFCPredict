from ufc_core.db import Base, models


def test_remaining_tables_smoke(test_engine, db_session):
    Base.metadata.create_all(test_engine)
    u = models.User(cognito_sub="abc", email="x@y.com")
    db_session.add(u)
    db_session.flush()
    bc = models.BetConfig(user_id=u.id, name="default", params={"kelly": 0.5})
    db_session.add(bc)
    db_session.flush()
    lp = models.LabPreference(key="theme", value={"v": "dark"})
    db_session.add(lp)
    db_session.flush()
    sr = models.ScrapingRun(source="ufcstats", new_count=10, updated_count=2)
    db_session.add(sr)
    db_session.flush()
    al = models.AppLog(level="info", module="test", message="hello", context={"k": 1})
    db_session.add(al)
    db_session.flush()
    assert all(o.id is not None for o in (u, bc, lp, sr, al))
