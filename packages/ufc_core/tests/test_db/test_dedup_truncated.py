import importlib.util
from pathlib import Path

# Load the script module by path (scripts/ is not a package).
_spec = importlib.util.spec_from_file_location(
    "dedup_truncated",
    Path(__file__).resolve().parents[4] / "scripts" / "dedup-truncated-fighters.py",
)
dedup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dedup)


class _F:
    """Lightweight stand-in for a Fight row."""
    def __init__(self, **kw):
        self.fighter_1_id = kw["f1"]
        self.fighter_2_id = kw["f2"]
        self.odds_f1_american = kw.get("o1")
        self.odds_f2_american = kw.get("o2")
        self.real_winner = kw.get("real_winner")
        self.result = kw.get("result")
        self.method = kw.get("method")
        self.round = kw.get("round")
        self.time = kw.get("time")
        self.weight_class = kw.get("weight_class")
        self.card_position = kw.get("card_position")
        self.scheduled_rounds = kw.get("scheduled_rounds")
        self.fight_order = kw.get("fight_order")


def test_odds_for_fighter_maps_by_position():
    f = _F(f1=10, f2=20, o1=105, o2=-125)
    assert dedup.odds_for_fighter(f, 10) == 105
    assert dedup.odds_for_fighter(f, 20) == -125
    assert dedup.odds_for_fighter(f, 99) is None


def test_consolidate_fills_only_missing_and_reorients_odds():
    # twin: real_X(10) vs real_target(30), no odds yet.
    twin = _F(f1=10, f2=30)
    # phantom: real_X(10) vs placeholder(==30 logically), odds present.
    phantom = _F(f1=10, f2=40, o1=105, o2=-125, method="U-DEC", result="win")
    updates = dedup.consolidate_updates(twin, phantom, real_target_id=30)
    # real_X(10) keeps its odd; the placeholder's odd goes to real_target(30=f2).
    assert updates["odds_f1_american"] == 105
    assert updates["odds_f2_american"] == -125
    assert updates["method"] == "U-DEC"
    assert updates["result"] == "win"


def test_consolidate_reorients_when_positions_swapped():
    # twin has real_target as f1 and shared real as f2 (opposite of phantom).
    twin = _F(f1=30, f2=10)
    phantom = _F(f1=10, f2=40, o1=105, o2=-125)  # shared=10 -> 105, placeholder=40 -> -125
    updates = dedup.consolidate_updates(twin, phantom, real_target_id=30)
    # f1 is real_target(30) -> gets the placeholder odd (-125); f2 is shared(10) -> 105.
    assert updates["odds_f1_american"] == -125
    assert updates["odds_f2_american"] == 105


def test_consolidate_does_not_overwrite_existing_odds():
    twin = _F(f1=10, f2=30, o1=200, o2=-250)
    phantom = _F(f1=10, f2=40, o1=105, o2=-125)
    updates = dedup.consolidate_updates(twin, phantom, real_target_id=30)
    assert "odds_f1_american" not in updates
    assert "odds_f2_american" not in updates


from datetime import datetime, timezone
from ufc_core.db import models, Base


def _seed_dup(db):
    """Event with the Sterling-vs-Zalal shape: real-vs-real twin + a phantom dup."""
    ev = models.Event(name="UFC FN: Sterling vs. Zalal",
                       date=datetime(2026, 4, 25, tzinfo=timezone.utc),
                       source="promoted")
    adrian = models.Fighter(name="Adrian Luna Martinetti", slug="adrian-luna-martinetti",
                            ufcstats_url="http://ufcstats.com/fighter-details/adrian")
    davey = models.Fighter(name="Davey Grant", slug="davey-grant",
                           ufcstats_url="http://ufcstats.com/fighter-details/davey")
    phantom = models.Fighter(name="Luna Martinetti", slug="luna-martinetti",
                             ufcstats_url="placeholder://Luna Martinetti")
    db.add_all([ev, adrian, davey, phantom]); db.flush()
    twin = models.Fight(event_id=ev.id, fighter_1_id=adrian.id, fighter_2_id=davey.id,
                        odds_f1_american=105, odds_f2_american=-125, result="loss")
    dup = models.Fight(event_id=ev.id, fighter_1_id=davey.id, fighter_2_id=phantom.id,
                       odds_f1_american=-125, odds_f2_american=105)
    db.add_all([twin, dup]); db.flush()
    sess = models.PredictionSession(event_id=ev.id, source="production", status="open")
    db.add(sess); db.flush()
    db.add(models.Prediction(session_id=sess.id, fight_id=dup.id, model_short="mlp",
                             version_idx=1, prob_f1=0.5, prob_f2=0.5))
    db.flush()
    return {"ev": ev, "adrian": adrian, "davey": davey, "phantom": phantom,
            "twin": twin, "dup": dup}


def test_find_and_merge_removes_duplicate(test_engine, db_session_real_commit):
    db = db_session_real_commit
    Base.metadata.create_all(test_engine)
    s = _seed_dup(db); db.commit()
    twin_id, dup_id, phantom_id = s["twin"].id, s["dup"].id, s["phantom"].id

    pairs = dedup.find_duplicate_pairs(db, window="all")
    assert len(pairs) == 1
    p = pairs[0]
    assert p["phantom_fight_id"] == dup_id
    assert p["twin_fight_id"] == twin_id
    assert p["real_target_id"] == s["adrian"].id

    dedup.merge_pair(db, p)
    db.commit()
    # Duplicate fight + its prediction gone; twin remains with its odds intact.
    assert db.query(models.Fight).filter_by(id=dup_id).first() is None
    assert db.query(models.Prediction).count() == 0
    twin = db.query(models.Fight).filter_by(id=twin_id).one()
    assert twin.odds_f1_american == 105 and twin.odds_f2_american == -125

    removed = dedup.delete_orphan_placeholders(db, [phantom_id]); db.commit()
    assert removed == 1
    assert db.query(models.Fighter).filter_by(id=phantom_id).first() is None


def _seed_dup_with_bet(db):
    """Like _seed_dup but adds a UserBet on the phantom fight and a real fightless fighter.

    Returns the seed dict extended with: user, bet, real_fightless.
    """
    s = _seed_dup(db)
    # A real (non-placeholder) fighter with no fights — must NOT be deleted by orphan cleanup.
    real_fightless = models.Fighter(name="Fightless Real", slug="fightless-real",
                                    ufcstats_url="http://ufcstats.com/fighter-details/fightless")
    db.add(real_fightless)
    db.flush()
    # A user to satisfy the FK on user_bet.
    user = models.User(cognito_sub="test-sub-dedup-001")
    db.add(user); db.flush()
    bet = models.UserBet(
        user_id=user.id,
        fight_id=s["dup"].id,
        stake=10,
        predicted_pick="Davey Grant",
        odds_taken_american=-125,
        status="open",
    )
    db.add(bet); db.flush()
    s.update({"user": user, "bet": bet, "real_fightless": real_fightless})
    return s


def test_merge_pair_repoints_user_bets_and_delete_orphan_scoped(test_engine, db_session_real_commit):
    """Fix 1 + Fix 2: user_bet is re-pointed to twin; real fightless fighter not touched."""
    db = db_session_real_commit
    Base.metadata.create_all(test_engine)
    s = _seed_dup_with_bet(db); db.commit()

    twin_id = s["twin"].id
    dup_id = s["dup"].id
    phantom_fighter_id = s["phantom"].id
    real_fightless_id = s["real_fightless"].id
    bet_id = s["bet"].id

    pairs = dedup.find_duplicate_pairs(db, window="all")
    assert len(pairs) == 1
    p = pairs[0]

    result = dedup.merge_pair(db, p)
    db.commit()

    # Fix 1: user_bet re-pointed to twin, not deleted.
    bet = db.query(models.UserBet).filter_by(id=bet_id).one()
    assert bet.fight_id == twin_id, "user_bet must be re-pointed to the twin fight"

    # Fix 1: phantom prediction deleted, not re-pointed (recalculable).
    assert db.query(models.Prediction).count() == 0

    # Fix 1: repointed_bets in return value.
    assert result.get("repointed_bets") == 1

    # Fix 2: delete_orphan_placeholders scoped to candidate_ids only.
    # phantom fighter should be removed (it is a placeholder and has no fights).
    removed = dedup.delete_orphan_placeholders(db, [phantom_fighter_id]); db.commit()
    assert removed == 1
    assert db.query(models.Fighter).filter_by(id=phantom_fighter_id).first() is None

    # Fix 2: real fightless fighter is NOT deleted even though it has no fights.
    assert db.query(models.Fighter).filter_by(id=real_fightless_id).one() is not None
