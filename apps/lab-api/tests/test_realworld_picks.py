"""Regression tests for Tapology picks in the realworld held-out builder.

The bug: `_build_realworld_df` called `compute_fight_features` WITHOUT
`tapology_picks`, so every held-out fight got neutral tap_* imputation while
training rows had the real values. A model trained with feature_set='v7' then
lost its strongest signal at eval time and realworld_accuracy collapsed (good
CV, bad realworld). These tests pin the wiring so it can't silently regress.
"""

from datetime import datetime
from unittest.mock import patch

import lab_api.services.training as training_svc


def _make_ds(event: str, ev_date: datetime, fa: str, fb: str):
    """Minimal data store: one realworld fight (fa beat fb)."""
    class _DS:
        fighters_raw = [
            {"name": fa, "fights": [{"opponent": fb, "event": event, "result": "win"}]},
        ]
        fighter_histories: dict = {}
        fighter_lookup: dict = {}
        event_dates = {event: ev_date}

    return _DS()


def test_realworld_df_feeds_tapology_picks_when_present():
    # event_date must be on/after REALWORLD_CUTOFF (default 2025-05-01).
    ev, ev_date = "UFC RW Test", datetime(2025, 6, 1)
    fa, fb = "Alice RWTest", "Bob RWTest"
    ds = _make_ds(ev, ev_date, fa, fb)
    lookup = {
        (ev, frozenset({fa, fb})): {
            "total_picks": 100,
            "fighter_a_name": fa, "fighter_b_name": fb,
            # DB stores percentages in the 0-100 range.
            "fighter_a_win_pct": 80.0, "fighter_b_win_pct": 20.0,
        }
    }
    captured: dict = {}

    def _spy(**kwargs):
        captured.update(kwargs)
        return {"delta_dummy": 0.0}

    # Patch where the names are looked up (training imports them at module level).
    with patch("lab_api.services.training.load_db_picks_lookup", return_value=lookup), \
         patch("lab_api.services.training.compute_fight_features", side_effect=_spy):
        df = training_svc._build_realworld_df(ds, {}, {})

    assert len(df) == 1
    picks = captured.get("tapology_picks")
    assert picks is not None, "tapology_picks was not forwarded to the feature engine"
    # Normalized 0-100 -> 0-1 and oriented to whoever landed in fighter_1.
    expected = 0.8 if captured["f1_name"] == fa else 0.2
    assert picks["fighter_1_win_pct"] == expected


def test_realworld_df_neutral_when_no_picks():
    # Control: empty lookup -> engine receives None (neutral imputation), so the
    # value tracks the DB rather than being hard-wired on or off.
    ev, ev_date = "UFC RW Test2", datetime(2025, 6, 1)
    fa, fb = "Carol RWTest", "Dave RWTest"
    ds = _make_ds(ev, ev_date, fa, fb)
    captured: dict = {}

    def _spy(**kwargs):
        captured.update(kwargs)
        return {"delta_dummy": 0.0}

    with patch("lab_api.services.training.load_db_picks_lookup", return_value={}), \
         patch("lab_api.services.training.compute_fight_features", side_effect=_spy):
        training_svc._build_realworld_df(ds, {}, {})

    assert captured.get("tapology_picks") is None
