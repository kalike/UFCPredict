"""End-to-end smoke: seed → train LGBM → predict the seeded event.

Offline test — no network.  Builds a synthetic fight history wide enough
to satisfy the training worker's "≥100 rows" guard and the train/test
split (TEST_CUTOFF_DT = 2024-01-01).

Seed strategy: insert Fighter + Event + Fight rows directly, then attach
FighterRaw rows with full payloads (fight history in the scraper-native
format).  DataStoreDB._load_fighters() uses the latest FighterRaw payload
per fighter to populate fighters_raw[i]["fights"], which is required by:

  - recalculate_elo        (iterates fighters_raw[i]["fights"])
  - build_fighter_histories (same)
  - _build_dataset_simple   (same → feature rows → training)
"""

import time
from datetime import datetime, timedelta, UTC
from pathlib import Path

from ufc_core.db.base import Base
from ufc_core.db.engine import SessionLocal
from ufc_core.db import models as db_models


# ─── Synthetic data config ────────────────────────────────────────────────────

# Keep it modest: 20 fighters, 22 train events × 5 fights = 110 train rows,
# 3 test events × 5 fights = 15 test rows.
N_FIGHTERS = 20
N_TRAIN_EVENTS = 22
N_TEST_EVENTS = 3
N_FUTURE_FIGHTS = 4


# ─── Helper builders ─────────────────────────────────────────────────────────


def _make_fight_detail(fighter_name: str, opponent_name: str) -> dict:
    """Minimal fight detail dict in the UFCStats scraper format.

    The 'Fighter' totals field starts with *fighter_name* so that
    extract_fight_stats() uses idx=0 (is_first=True) for this fighter.
    """
    return {
        "details": {
            "tables": {
                "totals": [
                    {
                        "Fighter": f"{fighter_name} {opponent_name}",
                        "KD": "1 0",
                        "Sig. str.": "20 of 40 15 of 35",
                        "Td": "2 of 4 1 of 3",
                        "Sub. att": "1 0",
                        "Rev.": "0 0",
                        "Ctrl": "1:30 0:45",
                    }
                ],
                "significant_strikes": [
                    {
                        "Fighter": f"{fighter_name} {opponent_name}",
                        "Head": "10 of 20 8 of 18",
                        "Body": "5 of 10 4 of 9",
                        "Leg": "5 of 10 3 of 8",
                        "Distance": "15 of 30 12 of 28",
                        "Clinch": "3 of 5 2 of 4",
                        "Ground": "2 of 5 1 of 3",
                    }
                ],
            }
        }
    }


def _date_str(dt: datetime) -> str:
    """'Jan. 1, 2022' format used by UFCStats scraper."""
    return dt.strftime("%b. %-d, %Y")


class _Seeder:
    """Seed synthetic fighters, events, fights, and FighterRaw payloads.

    All names are prefixed 'E2E_' so cleanup is unambiguous.
    """

    PREFIX = "E2E_"

    def __init__(self, db):
        self.db = db
        self.fighter_objs: list[db_models.Fighter] = []
        self.fighter_names: list[str] = []
        # name → list of fight dicts (for FighterRaw payload)
        self._fight_history: dict[str, list[dict]] = {}

    def cleanup(self) -> None:
        """Remove all E2E_ prefixed rows. Safe to call on a fresh DB too."""
        db = self.db

        # Future + test events
        for prefix in (f"{self.PREFIX}Future", f"{self.PREFIX}Train", f"{self.PREFIX}Test"):
            ev_ids = [
                e.id for e in db.query(db_models.Event)
                .filter(db_models.Event.name.like(f"{prefix}%")).all()
            ]
            if ev_ids:
                db.query(db_models.Fight).filter(
                    db_models.Fight.event_id.in_(ev_ids)
                ).delete(synchronize_session=False)
                db.query(db_models.Event).filter(
                    db_models.Event.id.in_(ev_ids)
                ).delete(synchronize_session=False)

        # Fighters
        fighters = db.query(db_models.Fighter).filter(
            db_models.Fighter.name.like(f"{self.PREFIX}%")
        ).all()
        if fighters:
            fids = [f.id for f in fighters]
            db.query(db_models.Fight).filter(
                db_models.Fight.fighter_1_id.in_(fids)
                | db_models.Fight.fighter_2_id.in_(fids)
            ).delete(synchronize_session=False)
            db.query(db_models.FighterRaw).filter(
                db_models.FighterRaw.fighter_id.in_(fids)
            ).delete(synchronize_session=False)
            for f in fighters:
                db.delete(f)

        db.commit()

    def seed_fighters(self) -> None:
        """Insert N_FIGHTERS Fighter rows."""
        for i in range(N_FIGHTERS):
            name = f"{self.PREFIX}F{i:02d}"
            f = db_models.Fighter(
                name=name,
                slug=f"e2e-f{i:02d}",
                ufcstats_url=f"http://ufcstats.e2e/f{i:02d}",
                record="0-0-0",
                stance="Orthodox" if i % 2 == 0 else "Southpaw",
                height_cm=170.0 + (i % 15),
                reach_cm=175.0 + (i % 15),
            )
            self.db.add(f)
            self.fighter_names.append(name)
            self._fight_history[name] = []
        self.db.flush()
        self.fighter_objs = (
            self.db.query(db_models.Fighter)
            .filter(db_models.Fighter.name.like(f"{self.PREFIX}%"))
            .order_by(db_models.Fighter.name)
            .all()
        )

    def _lookup(self, name: str) -> db_models.Fighter:
        for f in self.fighter_objs:
            if f.name == name:
                return f
        raise KeyError(name)

    def seed_events(self) -> int:
        """Seed train + test events and return the ID of the future event.

        Pairings are round-robin using a global fight counter to ensure
        uniqueness within each event.  We track pairs-per-event to avoid
        the unique constraint violation (event_id, f1_id, f2_id).
        """
        # Generate all events + their pairings before touching the DB so we
        # can guarantee uniqueness.
        all_events: list[tuple[str, datetime, str, list[tuple[int,int,str,str]]]] = []
        # (ev_name, ev_dt, status, [(f1_idx, f2_idx, f1_result, f2_result), ...])

        global_fight_idx = 0

        def _gen_pairs(ev_idx_global: int, n_pairs: int) -> list[tuple[int,int,str,str]]:
            nonlocal global_fight_idx
            used: set[frozenset] = set()
            pairs: list[tuple[int,int,str,str]] = []
            attempts = 0
            while len(pairs) < n_pairs and attempts < 200:
                attempts += 1
                f1_i = (global_fight_idx * 3 + 1) % N_FIGHTERS
                f2_i = (global_fight_idx * 3 + 1 + 7) % N_FIGHTERS
                global_fight_idx += 1
                if f1_i == f2_i:
                    f2_i = (f2_i + 1) % N_FIGHTERS
                key = frozenset({f1_i, f2_i})
                if key in used:
                    continue
                used.add(key)
                if global_fight_idx % 2 == 0:
                    f1_res, f2_res = "win", "loss"
                else:
                    f1_res, f2_res = "loss", "win"
                pairs.append((f1_i, f2_i, f1_res, f2_res))
            return pairs

        ev_counter = 0
        base_train = datetime(2020, 1, 15, tzinfo=UTC)
        for ev_idx in range(N_TRAIN_EVENTS):
            ev_dt = base_train + timedelta(days=ev_idx * 55)
            pairs = _gen_pairs(ev_counter, 5)
            all_events.append((f"{self.PREFIX}Train{ev_idx:03d}", ev_dt, "completed", pairs))
            ev_counter += 1

        base_test = datetime(2024, 3, 1, tzinfo=UTC)
        for ev_idx in range(N_TEST_EVENTS):
            ev_dt = base_test + timedelta(days=ev_idx * 90)
            pairs = _gen_pairs(ev_counter, 5)
            all_events.append((f"{self.PREFIX}Test{ev_idx:03d}", ev_dt, "completed", pairs))
            ev_counter += 1

        # Insert events one by one (flush each so we get the id before adding fights)
        for ev_name, ev_dt, ev_status, pairs in all_events:
            ev = db_models.Event(name=ev_name, date=ev_dt, status=ev_status)
            self.db.add(ev)
            self.db.flush()
            self._insert_fights(ev, ev_dt, pairs)
            self.db.flush()

        # Future event
        future_dt = datetime(2026, 6, 1, tzinfo=UTC)
        future_ev = db_models.Event(
            name=f"{self.PREFIX}Future Card",
            date=future_dt,
            status="scheduled",
        )
        self.db.add(future_ev)
        self.db.flush()
        for fi in range(N_FUTURE_FIGHTS):
            f1 = self.fighter_objs[fi * 2]
            f2 = self.fighter_objs[fi * 2 + 1]
            self.db.add(db_models.Fight(
                event_id=future_ev.id,
                fighter_1_id=f1.id,
                fighter_2_id=f2.id,
                weight_class="Bantamweight",
                fight_order=fi,
            ))

        self.db.commit()
        return future_ev.id

    def _insert_fights(
        self,
        ev: db_models.Event,
        ev_dt: datetime,
        pairs: list[tuple[int, int, str, str]],
    ) -> None:
        """Insert fight rows and update in-memory fight history."""
        ev_dt_naive = ev_dt.replace(tzinfo=None)
        ev_date_str = _date_str(ev_dt_naive)
        for order, (f1_idx, f2_idx, f1_result, f2_result) in enumerate(pairs):
            f1_obj = self.fighter_objs[f1_idx]
            f2_obj = self.fighter_objs[f2_idx]
            f1_name = f1_obj.name
            f2_name = f2_obj.name
            winner = f1_name if f1_result == "win" else f2_name

            self.db.add(db_models.Fight(
                event_id=ev.id,
                fighter_1_id=f1_obj.id,
                fighter_2_id=f2_obj.id,
                weight_class="Lightweight",
                result=f1_result,
                method="U-DEC",
                round=3,
                time="5:00",
                real_winner=winner,
                fight_order=order,
            ))

            # Fight history entries (UFCStats scraper format)
            self._fight_history[f1_name].append({
                "event": ev.name,
                "date": ev_date_str,
                "opponent": f2_name,
                "result": f1_result,
                "method": "U-DEC",
                "round": 3,
                "time": "5:00",
                "weight_class": "Lightweight",
                **_make_fight_detail(f1_name, f2_name),
            })
            self._fight_history[f2_name].append({
                "event": ev.name,
                "date": ev_date_str,
                "opponent": f1_name,
                "result": f2_result,
                "method": "U-DEC",
                "round": 3,
                "time": "5:00",
                "weight_class": "Lightweight",
                **_make_fight_detail(f2_name, f1_name),
            })

    def attach_fighter_raw(self) -> None:
        """Insert FighterRaw rows with full fight history payloads."""
        for f_obj in self.fighter_objs:
            name = f_obj.name
            fights = self._fight_history.get(name, [])
            wins = sum(1 for fh in fights if fh["result"] == "win")
            losses = len(fights) - wins
            payload = {
                "name": name,
                "url": f_obj.ufcstats_url,
                "record": f"{wins}-{losses}-0",
                "stance": f_obj.stance or "Orthodox",
                "height_cm": f_obj.height_cm,
                "reach_cm": f_obj.reach_cm,
                "dob": None,
                "photo_url": None,
                "fights": fights,
            }
            self.db.add(db_models.FighterRaw(
                fighter_id=f_obj.id,
                payload=payload,
            ))
        self.db.commit()


# ─── Poll helper ─────────────────────────────────────────────────────────────


def _wait_idle(client, timeout_seconds: float = 120.0) -> dict:
    """Poll /api/models/train/status until is_running=False or timeout."""
    deadline = time.time() + timeout_seconds
    status = client.get("/api/models/train/status").json()
    while status["is_running"] and time.time() < deadline:
        time.sleep(0.5)
        status = client.get("/api/models/train/status").json()
    return status


# ─── Test ────────────────────────────────────────────────────────────────────


def test_e2e_train_lgbm_then_predict_event(client, test_engine):
    """Offline e2e: seed synthetic data → train LGBM → predict future event."""
    Base.metadata.create_all(test_engine)

    db = SessionLocal()
    seeder = _Seeder(db)
    try:
        # ── Step 0: clean + seed ────────────────────────────────────────────
        seeder.cleanup()
        seeder.seed_fighters()
        future_event_id = seeder.seed_events()
        seeder.attach_fighter_raw()

        # Ensure LGBM model catalog row
        if db.query(db_models.Model).filter_by(short="LGBM").one_or_none() is None:
            db.add(db_models.Model(
                short="LGBM", family="sklearn", default_feat_type="35f",
                description="LightGBM — e2e smoke test",
            ))
            db.commit()
    finally:
        db.close()

    # ── Step 1: Start training ───────────────────────────────────────────────
    r = client.post(
        "/api/models/train",
        json={"model_short": "LGBM", "feature_set": "v7", "dataset": "since2010"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["started"] is True, f"Training did not start: {body}"

    # ── Step 2: Wait for completion ──────────────────────────────────────────
    final = _wait_idle(client, timeout_seconds=120.0)
    assert not final["is_running"], f"Training did not finish in time: {final}"
    assert "failed" not in (final.get("step") or "").lower(), (
        f"Training step reported failure: {final}"
    )
    assert final.get("result_version_id") is not None, (
        f"No version registered after training. "
        f"step={final.get('step')!r}, error={final.get('error')!r}"
    )

    # ── Step 3: Verify version + artifact ────────────────────────────────────
    db = SessionLocal()
    try:
        m = db.query(db_models.Model).filter_by(short="LGBM").one()
        v = (
            db.query(db_models.ModelVersion)
              .filter_by(model_id=m.id)
              .order_by(db_models.ModelVersion.version_idx.desc())
              .first()
        )
        assert v is not None, "No ModelVersion row found after training"
        assert v.artifact_uri.startswith("file://"), (
            f"Unexpected artifact URI: {v.artifact_uri!r}"
        )
        artifact_path = Path(v.artifact_uri[len("file://"):])
        assert artifact_path.exists(), f"Artifact missing on disk: {artifact_path}"

        assert v.metrics_json is not None, "metrics_json is None"
        assert v.metrics_json.get("accuracy") is not None, (
            f"accuracy not in metrics_json: {v.metrics_json}"
        )
        version_idx = v.version_idx
    finally:
        db.close()

    # ── Step 4: Activate the trained version ─────────────────────────────────
    r = client.post(f"/api/models/LGBM/versions/{version_idx}/activate")
    assert r.status_code == 200, r.text

    # ── Step 5: Predict the future event ─────────────────────────────────────
    r = client.post(f"/api/predictions/event/{future_event_id}/predict")
    assert r.status_code == 200, (
        f"Predict endpoint returned {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body["event_id"] == future_event_id, (
        f"event_id mismatch: {body['event_id']} vs {future_event_id}"
    )
    # At least 1 fight should produce a prediction
    assert len(body["predictions"]) >= 1, (
        f"No predictions produced. notes={body.get('notes')!r}"
    )
    for pred in body["predictions"]:
        assert 0.0 <= pred["prob_f1"] <= 1.0, f"prob_f1 out of range: {pred}"
        assert 0.0 <= pred["prob_f2"] <= 1.0, f"prob_f2 out of range: {pred}"
        assert abs(pred["prob_f1"] + pred["prob_f2"] - 1.0) < 1e-5, (
            f"prob_f1 + prob_f2 != 1.0: {pred}"
        )
        assert "LGBM" in pred["contributing_models"], (
            f"LGBM not in contributing_models: {pred['contributing_models']}"
        )


def test_e2e_train_rf_and_mlp(client, test_engine):
    """Confirm RF35 and MLP can be trained on the same synthetic dataset.

    Reuses the seed from the LGBM e2e — synthetic data is idempotent so
    re-seeding produces the same rows (or skips if already present).
    """
    Base.metadata.create_all(test_engine)

    db = SessionLocal()
    seeder = _Seeder(db)
    try:
        # Register the two model families if not present
        for short, family in [("RF35", "sklearn"), ("MLP", "sklearn")]:
            if db.query(db_models.Model).filter_by(short=short).one_or_none() is None:
                db.add(db_models.Model(
                    short=short, family=family,
                    default_feat_type="35f",
                    description=f"Test {short}",
                ))
        db.commit()

        # Seed only if no E2E fighters are present (previous test already seeded)
        existing = (
            db.query(db_models.Fighter)
            .filter(db_models.Fighter.name.like(f"{_Seeder.PREFIX}%"))
            .first()
        )
        if existing is None:
            seeder.seed_fighters()
            seeder.seed_events()
            seeder.attach_fighter_raw()
    finally:
        db.close()

    for short in ("RF35", "MLP"):
        r = client.post(
            "/api/models/train",
            json={"model_short": short, "feature_set": "v7", "dataset": "since2010"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["started"] is True

        final = _wait_idle(client, timeout_seconds=90)
        assert not final["is_running"], f"Training for {short} did not finish: {final}"
        assert "failed" not in (final.get("step") or "").lower(), (
            f"Training for {short} failed: {final}"
        )
        assert final.get("result_version_id") is not None, (
            f"{short} trained but no version_id. step={final.get('step')} err={final.get('error')}"
        )
