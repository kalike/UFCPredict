from lab_api.services.training import _build_realworld_df


class _DS:
    """Minimal DataStore double: one realworld fight F1 vs F2 at event E."""
    def __init__(self, ev_date):
        self.fighters_raw = [
            {"name": "F1", "fights": [{"opponent": "F2", "event": "E", "result": "win"}]},
            {"name": "F2", "fights": [{"opponent": "F1", "event": "E", "result": "loss"}]},
        ]
        self.event_dates = {"E": ev_date}
        self.fighter_histories = {}
        self.fighter_lookup = {}


def test_build_realworld_df_assigns_odds_by_fighter(monkeypatch):
    from lab_api.services import training as T
    from ufc_core.config import REALWORLD_CUTOFF_DT

    ev_date = REALWORLD_CUTOFF_DT.replace(year=2025, month=6, day=1)

    # Stub feature computation so the test stays unit-level (no ELO/PIT machinery).
    monkeypatch.setattr(T, "compute_fight_features",
                        lambda **kw: {"delta_x": 0.0}, raising=False)
    monkeypatch.setattr(T, "load_db_picks_lookup", lambda: {}, raising=False)

    lookup = {("E", frozenset({"F1", "F2"})): {"F1": -150, "F2": 130}}
    df = _build_realworld_df(_DS(ev_date), {}, {}, 1500.0, odds_lookup=lookup)

    assert len(df) == 1
    row = df.iloc[0]
    # Odds must follow the fighter, not the column position (positions are random).
    f1_name = row["fighter_1"]
    expected_f1 = -150 if f1_name == "F1" else 130
    expected_f2 = 130 if f1_name == "F1" else -150
    assert row["odds_f1_american"] == expected_f1
    assert row["odds_f2_american"] == expected_f2


def test_build_realworld_df_without_lookup_has_no_odds_cols():
    from ufc_core.config import REALWORLD_CUTOFF_DT
    ev_date = REALWORLD_CUTOFF_DT.replace(year=2025, month=6, day=1)
    df = _build_realworld_df(_DS(ev_date), {}, {}, 1500.0)
    assert "odds_f1_american" not in df.columns
