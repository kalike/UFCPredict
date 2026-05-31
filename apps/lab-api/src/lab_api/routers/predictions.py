"""Predictions router — serve cached predictions per event.

Supports listing events, reading caches, and running real ensemble inference
against all active models for a given event.
"""

from datetime import datetime, UTC
import numpy as np

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_data_store, get_db
from lab_api.routers.predictions_artifacts import load_artifact as _load_artifact

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class EventSummary(BaseModel):
    id: int
    name: str
    date: str | None
    status: str
    fight_count: int


class CacheEntry(BaseModel):
    event_id: int
    model_version_id: int
    computed_at: str
    expires_at: str | None
    payload: dict


@router.get("/events", response_model=list[EventSummary])
def list_events(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[EventSummary]:
    """List events filtered by status."""
    q = db.query(db_models.Event)
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(db_models.Event.date.desc().nullslast()).limit(limit).all()
    out = []
    for e in rows:
        fc = db.query(db_models.Fight).filter_by(event_id=e.id).count()
        out.append(EventSummary(
            id=e.id, name=e.name,
            date=e.date.isoformat() if e.date else None,
            status=e.status, fight_count=fc,
        ))
    return out


@router.get("/cache/{event_id}", response_model=list[CacheEntry])
def event_cache(event_id: int, db: Session = Depends(get_db)) -> list[CacheEntry]:
    if db.query(db_models.Event).filter_by(id=event_id).one_or_none() is None:
        raise HTTPException(404, f"Event {event_id} not found")
    rows = (
        db.query(db_models.PredictionCache)
          .filter_by(event_id=event_id)
          .order_by(db_models.PredictionCache.computed_at.desc())
          .all()
    )
    return [CacheEntry(
        event_id=c.event_id, model_version_id=c.model_version_id,
        computed_at=c.computed_at.isoformat() if c.computed_at else "",
        expires_at=c.expires_at.isoformat() if c.expires_at else None,
        payload=c.payload,
    ) for c in rows]


# ─── Real predict endpoint ────────────────────────────────────────────────────


class FightPrediction(BaseModel):
    fight_id: int
    fighter_1: str
    fighter_2: str
    prob_f1: float
    prob_f2: float
    contributing_models: list[str]


class PredictionRunResponse(BaseModel):
    session_id: int
    event_id: int
    event_name: str
    predictions: list[FightPrediction]
    notes: str | None = None


@router.post("/event/{event_id}/predict", response_model=PredictionRunResponse)
def predict_event(event_id: int, db: Session = Depends(get_db)) -> PredictionRunResponse:
    """Run inference against all active models with TTA + weighted ensemble.

    TTA (Test-Time Augmentation): each fight is predicted twice — once in
    normal order and once with fighter_1 / fighter_2 swapped.  The TTA
    probability for fighter_1 is ``(p_normal + (1 - p_swapped)) / 2``.

    Weighted ensemble: each model is weighted by its ``metrics_json.accuracy``
    (falls back to 1.0 if the field is absent).  Weights are normalised to
    sum to 1 before aggregation.

    Idempotent-ish: each call creates a new prediction_session row and writes
    one prediction row per (model, fight).  The latest cache row per
    (event_id, model_version_id) is overwritten with the new payload.
    """
    ev = db.query(db_models.Event).filter_by(id=event_id).one_or_none()
    if ev is None:
        raise HTTPException(404, f"Event {event_id} not found")

    fights = (
        db.query(db_models.Fight)
          .filter_by(event_id=ev.id)
          .order_by(db_models.Fight.fight_order.asc().nullslast())
          .all()
    )
    if not fights:
        raise HTTPException(400, f"Event {event_id} has no fights")

    # Find every active model + its active version
    active_rows = db.query(db_models.ActiveModel).all()
    if not active_rows:
        raise HTTPException(400, "No active models registered. Train and activate at least one first.")

    versions: list[tuple[db_models.Model, db_models.ModelVersion, dict, float]] = []
    skipped: list[str] = []
    for am in active_rows:
        m = db.query(db_models.Model).filter_by(id=am.model_id).one()
        v = db.query(db_models.ModelVersion).filter_by(id=am.version_id).one()
        try:
            art = _load_artifact(v.artifact_uri)
        except Exception as e:
            skipped.append(f"{m.short}: {e!r}")
            continue
        weight = 1.0
        if v.metrics_json and isinstance(v.metrics_json, dict):
            weight = float(v.metrics_json.get("accuracy", 1.0) or 1.0)
        versions.append((m, v, art, weight))

    if not versions:
        raise HTTPException(400, f"No loadable active models. Skipped: {skipped}")

    # Normalize weights so they sum to 1
    total_w = sum(entry[3] for entry in versions) or 1.0
    weights = [entry[3] / total_w for entry in versions]

    # Build feature inputs for this event's fights (normal + swapped)
    from ufc_core.data_loader import DataStoreDB
    from ufc_core.features.engine import compute_features_for_fights

    ds = DataStoreDB()
    ds.load()

    fight_inputs: list[dict] = []
    fight_inputs_swapped: list[dict] = []
    fight_id_map: dict[int, db_models.Fight] = {}
    fighter_names: list[tuple[str, str]] = []
    for f in fights:
        f1 = db.query(db_models.Fighter).filter_by(id=f.fighter_1_id).one()
        f2 = db.query(db_models.Fighter).filter_by(id=f.fighter_2_id).one()
        fight_inputs.append({
            "event": ev.name,
            "fighter_1": f1.name,
            "fighter_2": f2.name,
            "odds_f1_american": f.odds_f1_american,
            "odds_f2_american": f.odds_f2_american,
        })
        fight_inputs_swapped.append({
            "event": ev.name,
            "fighter_1": f2.name,
            "fighter_2": f1.name,
            "odds_f1_american": f.odds_f2_american,
            "odds_f2_american": f.odds_f1_american,
        })
        fight_id_map[len(fight_inputs) - 1] = f
        fighter_names.append((f1.name, f2.name))

    # Strip timezone so comparisons with event_dates (naive) don't raise TypeError.
    ev_date_naive = ev.date.replace(tzinfo=None) if ev.date else None

    feats_normal, _ = compute_features_for_fights(
        fights=fight_inputs,
        fighter_histories=ds.fighter_histories,
        fighter_lookup=ds.fighter_lookup,
        event_dates=ds.event_dates,
        base_elo=1500.0,
        event_date=ev_date_naive,
        before_event_date=ev_date_naive,
    )
    feats_swapped, _ = compute_features_for_fights(
        fights=fight_inputs_swapped,
        fighter_histories=ds.fighter_histories,
        fighter_lookup=ds.fighter_lookup,
        event_dates=ds.event_dates,
        base_elo=1500.0,
        event_date=ev_date_naive,
        before_event_date=ev_date_naive,
    )

    if len(feats_normal) == 0:
        raise HTTPException(
            400,
            "Feature computation produced no rows (one or both fighters lack history). "
            "Make sure scraping ran first.",
        )

    # Create prediction_session
    sess = db_models.PredictionSession(
        event_id=ev.id, source="lab_preview", status="open",
    )
    db.add(sess)
    db.flush()

    # For each (model, version), run TTA inference and collect weighted probs.
    # per_fight_probs[i] = [(model_short, p_tta_f1, weight), ...]
    per_fight_probs: list[list[tuple[str, float, float]]] = [[] for _ in fight_inputs]
    for (m, v, art, _raw_w), w in zip(versions, weights):
        clf = art["clf"]
        feat_cols = art["feat_cols"]
        # Fill columns missing in the current feature frame with 0.0
        for c in feat_cols:
            if c not in feats_normal.columns:
                feats_normal[c] = 0.0
            if c not in feats_swapped.columns:
                feats_swapped[c] = 0.0

        # Apply the same preprocessing used at training time (impute → transform
        # → scale) so inference matches the model. Artifacts trained before this
        # was added carry no imputer/transformer and fall back to raw features.
        def _prepare(frame):
            imputer = art.get("imputer")
            transformer = art.get("transformer")
            scaler = art.get("scaler")
            df = imputer.transform(frame) if imputer is not None else frame
            if transformer is not None:
                df = transformer.transform_df(df)
            X = df[feat_cols].values.astype("float32")
            np.nan_to_num(X, copy=False, nan=0.0)
            if scaler is not None:
                X = scaler.transform(X)
            return X

        X_n = _prepare(feats_normal)
        X_s = _prepare(feats_swapped)
        try:
            p_n = clf.predict_proba(X_n)[:, 1].astype(float)
            p_s = clf.predict_proba(X_s)[:, 1].astype(float)
        except Exception:
            p_n = clf.predict(X_n).astype(float)
            p_s = clf.predict(X_s).astype(float)

        # TTA: average of (normal P(f1 wins), 1 - swapped P(f1 wins))
        p_tta = (p_n + (1.0 - p_s)) / 2.0
        p_tta = np.clip(p_tta, 0.0, 1.0)

        for i in range(len(feats_normal)):
            p1 = float(p_tta[i])
            p2 = 1.0 - p1
            per_fight_probs[i].append((m.short, p1, w))

            # Persist per-model prediction row
            db.add(db_models.Prediction(
                session_id=sess.id,
                fight_id=fight_id_map[i].id,
                model_short=m.short,
                version_idx=v.version_idx,
                prob_f1=p1,
                prob_f2=p2,
                method_pred=None,
                raw_response={
                    "prob_f1": p1,
                    "prob_f2": p2,
                    "tta": {"normal": float(p_n[i]), "swapped": float(p_s[i])},
                    "weight": w,
                },
            ))

    # Aggregate (weighted mean) + assemble response
    out: list[FightPrediction] = []
    cache_payload = {"event_id": ev.id, "predictions": []}
    for i in range(len(fight_inputs)):
        rows_i = per_fight_probs[i]
        if not rows_i:
            continue
        total_w_local = sum(r[2] for r in rows_i) or 1.0
        p1 = sum(r[1] * r[2] for r in rows_i) / total_w_local
        p2 = 1.0 - p1
        fp = FightPrediction(
            fight_id=fight_id_map[i].id,
            fighter_1=fighter_names[i][0],
            fighter_2=fighter_names[i][1],
            prob_f1=float(p1),
            prob_f2=float(p2),
            contributing_models=[r[0] for r in rows_i],
        )
        out.append(fp)
        cache_payload["predictions"].append(fp.model_dump())

    # Persist cache: one row per active version, with same aggregate payload.
    for m, v, _art, _w in versions:
        existing_cache = (
            db.query(db_models.PredictionCache)
              .filter_by(event_id=ev.id, model_version_id=v.id)
              .one_or_none()
        )
        if existing_cache is None:
            db.add(db_models.PredictionCache(
                event_id=ev.id,
                model_version_id=v.id,
                payload=cache_payload,
                computed_at=datetime.now(UTC),
                expires_at=None,
            ))
        else:
            existing_cache.payload = cache_payload
            existing_cache.computed_at = datetime.now(UTC)

    sess.status = "completed"
    db.commit()

    note = None
    if skipped:
        note = "Skipped models: " + "; ".join(skipped)
    return PredictionRunResponse(
        session_id=sess.id, event_id=ev.id, event_name=ev.name,
        predictions=out, notes=note,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Rich predictions: arbitrary matchups, past events, sessions
#  Port of the legacy backend's predictions page, adapted to the DB-only lab.
# ══════════════════════════════════════════════════════════════════════════════

import unicodedata
import re as _re


# ─── Rich response schemas ────────────────────────────────────────────────────


class ModelPredictionOut(BaseModel):
    full_name: str
    predicted_winner: str
    probability_f1: float
    confidence: float


class ConsensusOut(BaseModel):
    fighter_1_votes: int
    fighter_2_votes: int
    total_models: int
    consensus_winner: str
    consensus_pct: float


class MethodBreakdownOut(BaseModel):
    wins: int = 0
    losses: int = 0
    ko_wins: int = 0
    sub_wins: int = 0
    dec_wins: int = 0
    ko_losses: int = 0
    sub_losses: int = 0
    dec_losses: int = 0


class CommunityMethodOut(BaseModel):
    ko_tko_pct: float = 0.0
    submission_pct: float = 0.0
    decision_pct: float = 0.0


class CommunityPicksOut(BaseModel):
    total_picks: int = 0
    fighter_1_win_pct: float = 0.0
    fighter_2_win_pct: float = 0.0
    fighter_1_methods: CommunityMethodOut = CommunityMethodOut()
    fighter_2_methods: CommunityMethodOut = CommunityMethodOut()


class RichFightPrediction(BaseModel):
    fighter_1: str
    fighter_2: str
    event: str
    odds_f1_american: int | None = None
    odds_f2_american: int | None = None
    models: dict[str, ModelPredictionOut]
    consensus: ConsensusOut | None = None
    prob_f1: float
    prob_f2: float
    fighter_1_has_history: bool
    fighter_2_has_history: bool
    fighter_1_n_fights: int = 0
    fighter_2_n_fights: int = 0
    fighter_1_methods: MethodBreakdownOut = MethodBreakdownOut()
    fighter_2_methods: MethodBreakdownOut = MethodBreakdownOut()
    community_picks: CommunityPicksOut | None = None
    real_winner: str | None = None
    fight_id: int | None = None
    # Concluded without a winner: "nc" (No Contest / Overturned) or "draw".
    outcome: str | None = None


class FightInputIn(BaseModel):
    fighter_1: str
    fighter_2: str
    odds_f1_american: int | None = None
    odds_f2_american: int | None = None
    community_picks: CommunityPicksOut | None = None


class PredictRequest(BaseModel):
    event_name: str
    fights: list[FightInputIn]


class PredictResponse(BaseModel):
    event: str
    n_fights: int
    n_models: int
    fights: list[RichFightPrediction]
    skipped: list[str] = []


# ─── Conversion helpers ───────────────────────────────────────────────────────


def _methods_out(mb) -> MethodBreakdownOut:
    return MethodBreakdownOut(
        wins=mb.wins, losses=mb.losses,
        ko_wins=mb.ko_wins, sub_wins=mb.sub_wins, dec_wins=mb.dec_wins,
        ko_losses=mb.ko_losses, sub_losses=mb.sub_losses, dec_losses=mb.dec_losses,
    )


def _community_out(cp) -> CommunityPicksOut | None:
    if cp is None:
        return None
    if isinstance(cp, CommunityPicksOut):
        return cp
    if isinstance(cp, dict):
        return CommunityPicksOut(**cp)
    return None


def _fr_to_rich(
    fr, real_winner: str | None = None, fight_id: int | None = None,
    outcome: str | None = None,
) -> RichFightPrediction:
    """Convert a predict_engine.FightResult into the API response shape."""
    models = {
        short: ModelPredictionOut(
            full_name=mv.full_name,
            predicted_winner=mv.predicted_winner,
            probability_f1=mv.probability_f1,
            confidence=mv.confidence,
        )
        for short, mv in fr.models.items()
    }
    consensus = None
    if fr.consensus is not None:
        c = fr.consensus
        consensus = ConsensusOut(
            fighter_1_votes=c.fighter_1_votes,
            fighter_2_votes=c.fighter_2_votes,
            total_models=c.total_models,
            consensus_winner=c.consensus_winner,
            consensus_pct=c.consensus_pct,
        )
    return RichFightPrediction(
        fighter_1=fr.fighter_1,
        fighter_2=fr.fighter_2,
        event=fr.event,
        odds_f1_american=fr.odds_f1_american,
        odds_f2_american=fr.odds_f2_american,
        models=models,
        consensus=consensus,
        prob_f1=fr.prob_f1,
        prob_f2=fr.prob_f2,
        fighter_1_has_history=fr.fighter_1_has_history,
        fighter_2_has_history=fr.fighter_2_has_history,
        fighter_1_n_fights=fr.fighter_1_n_fights,
        fighter_2_n_fights=fr.fighter_2_n_fights,
        fighter_1_methods=_methods_out(fr.fighter_1_methods),
        fighter_2_methods=_methods_out(fr.fighter_2_methods),
        community_picks=_community_out(fr.community_picks),
        real_winner=real_winner,
        fight_id=fight_id,
        outcome=outcome,
    )


def _norm_name(s: str) -> str:
    """Accent/case-insensitive normalisation for fuzzy name matching."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return _re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


# ─── POST /  — predict arbitrary matchups (stateless) ─────────────────────────


@router.post("/", response_model=PredictResponse)
def predict_fights(req: PredictRequest, db: Session = Depends(get_db)) -> PredictResponse:
    """Run inference over an arbitrary list of matchups, without persisting.

    Fighters are resolved by name. A fight where both fighters lack history is
    reported under ``skipped``. Use ``POST /sessions`` afterwards to persist the
    result as a saved session.
    """
    from lab_api.services import predict_engine

    ds = get_data_store()
    versions, vskipped = predict_engine.build_versions(db)
    if not versions:
        raise HTTPException(400, f"No loadable active models. Skipped: {vskipped}")

    fights_input = [{
        "event": req.event_name,
        "fighter_1": f.fighter_1,
        "fighter_2": f.fighter_2,
        "odds_f1_american": f.odds_f1_american,
        "odds_f2_american": f.odds_f2_american,
        "community_picks": f.community_picks.model_dump() if f.community_picks else None,
    } for f in req.fights]

    result = predict_engine.run_inference(
        db, ds, fights_input, versions=versions, versions_skipped=vskipped,
    )
    return PredictResponse(
        event=req.event_name,
        n_fights=len(result.fights),
        n_models=result.n_models,
        fights=[_fr_to_rich(fr) for fr in result.fights],
        skipped=result.skipped,
    )


# ─── Past events ──────────────────────────────────────────────────────────────


class PastEventSummary(BaseModel):
    name: str
    n_fights: int
    date: str | None = None


class ModelAccuracyOut(BaseModel):
    full_name: str
    accuracy: float
    correct: int
    total: int


class PastEventResponse(BaseModel):
    event: str
    n_fights: int
    n_fights_valid: int
    accuracy: dict[str, ModelAccuracyOut]
    fights: list[RichFightPrediction]
    skipped: list[str] = []


@router.get("/past-events", response_model=list[PastEventSummary])
def list_past_events(db: Session = Depends(get_db)) -> list[PastEventSummary]:
    """Realworld held-out events: completed UFC events with
    ``event_date >= REALWORLD_CUTOFF_DT`` (the same partition the trainer holds
    out for realworld evaluation). Non-UFC (``fighter_history``) and ad-hoc
    ``preview`` events are excluded.
    """
    from sqlalchemy import func, or_
    from ufc_core.config import REALWORLD_CUTOFF_DT

    rows = (
        db.query(
            db_models.Event.name,
            db_models.Event.date,
            func.count(db_models.Fight.id),
        )
        .join(db_models.Fight, db_models.Fight.event_id == db_models.Event.id)
        .filter(db_models.Event.date.isnot(None))
        .filter(db_models.Event.date >= REALWORLD_CUTOFF_DT)
        .filter(db_models.Event.status == "completed")
        # NULL source means a legacy scraped event → include it (treat NULL as UFC).
        .filter(or_(
            db_models.Event.source.is_(None),
            db_models.Event.source.notin_(["fighter_history", "preview"]),
        ))
        .group_by(db_models.Event.id, db_models.Event.name, db_models.Event.date)
        .order_by(db_models.Event.date.desc().nullslast())
        .all()
    )
    return [
        PastEventSummary(
            name=name,
            n_fights=int(cnt),
            date=date.isoformat() if date else None,
        )
        for name, date, cnt in rows
    ]


def _fight_real_winner(name1: str, name2: str, result: str | None, real_winner: str | None) -> str | None:
    """Resolve a completed fight's winner. Scraped fights store the outcome in
    ``Fight.result`` (win/loss relative to fighter_1); promoted sessions use the
    ``real_winner`` column set via mark-result."""
    if real_winner:
        return real_winner
    if result == "win":
        return name1
    if result == "loss":
        return name2
    return None


def _fight_outcome(result: str | None, method: str | None) -> str | None:
    """Classify a concluded fight that has no winner: "nc" (No Contest /
    Overturned) or "draw". Returns None for win/loss or not-yet-fought."""
    r = (result or "").strip().lower()
    m = (method or "").strip().lower()
    if r in ("nc", "no contest") or "overturn" in m or "no contest" in m:
        return "nc"
    if r == "draw" or "draw" in m:
        return "draw"
    return None


@router.get("/past-events/{event_name}", response_model=PastEventResponse)
def predict_past_event(event_name: str, db: Session = Depends(get_db)) -> PastEventResponse:
    """Re-run inference on a historical event and score each model vs the result."""
    from lab_api.services import predict_engine

    ev = db.query(db_models.Event).filter_by(name=event_name).one_or_none()
    if ev is None:
        raise HTTPException(404, f"Event '{event_name}' not found")

    fights = (
        db.query(db_models.Fight)
          .filter_by(event_id=ev.id)
          .order_by(db_models.Fight.fight_order.asc().nullslast())
          .all()
    )
    if not fights:
        raise HTTPException(400, f"Event '{event_name}' has no fights")

    ds = get_data_store()
    versions, vskipped = predict_engine.build_versions(db)
    if not versions:
        raise HTTPException(400, f"No loadable active models. Skipped: {vskipped}")

    # Build inputs keyed back to their Fight row (for real_winner + fight_id).
    fight_by_pair: dict[tuple[str, str], db_models.Fight] = {}
    real_by_pair: dict[tuple[str, str], str | None] = {}
    outcome_by_pair: dict[tuple[str, str], str | None] = {}
    fights_input: list[dict] = []
    for f in fights:
        f1 = db.query(db_models.Fighter).filter_by(id=f.fighter_1_id).one()
        f2 = db.query(db_models.Fighter).filter_by(id=f.fighter_2_id).one()
        fights_input.append({
            "event": ev.name,
            "fighter_1": f1.name,
            "fighter_2": f2.name,
            "odds_f1_american": f.odds_f1_american,
            "odds_f2_american": f.odds_f2_american,
            "community_picks": _community_picks_for_fight(db, f.id),
        })
        fight_by_pair[(f1.name, f2.name)] = f
        real_by_pair[(f1.name, f2.name)] = _fight_real_winner(
            f1.name, f2.name, f.result, f.real_winner,
        )
        outcome_by_pair[(f1.name, f2.name)] = _fight_outcome(f.result, f.method)

    ev_date_naive = ev.date.replace(tzinfo=None) if ev.date else None
    result = predict_engine.run_inference(
        db, ds, fights_input,
        event_date=ev_date_naive, before_event_date=ev_date_naive,
        versions=versions, versions_skipped=vskipped,
    )

    # Per-model accuracy across fights that have a real winner.
    correct: dict[str, int] = {}
    total: dict[str, int] = {}
    full_names: dict[str, str] = {}
    n_valid = 0
    rich: list[RichFightPrediction] = []
    for fr in result.fights:
        frow = fight_by_pair.get((fr.fighter_1, fr.fighter_2))
        real = real_by_pair.get((fr.fighter_1, fr.fighter_2))
        outcome = outcome_by_pair.get((fr.fighter_1, fr.fighter_2))
        fid = frow.id if frow else None
        rich.append(_fr_to_rich(fr, real_winner=real, fight_id=fid, outcome=outcome))
        if not real:
            continue
        n_valid += 1
        real_resolved = ds.resolve_name(real)
        for short, mv in fr.models.items():
            full_names[short] = mv.full_name
            total[short] = total.get(short, 0) + 1
            if ds.resolve_name(mv.predicted_winner) == real_resolved:
                correct[short] = correct.get(short, 0) + 1

    accuracy = {
        short: ModelAccuracyOut(
            full_name=full_names.get(short, short),
            accuracy=round(correct.get(short, 0) / total[short], 4) if total[short] else 0.0,
            correct=correct.get(short, 0),
            total=total[short],
        )
        for short in total
    }

    return PastEventResponse(
        event=ev.name,
        n_fights=len(result.fights),
        n_fights_valid=n_valid,
        accuracy=accuracy,
        fights=rich,
        skipped=result.skipped,
    )


def _community_picks_for_fight(db: Session, fight_id: int) -> dict | None:
    """Load community picks for a DB fight, oriented to its fighter_1/fighter_2."""
    tp = db.query(db_models.TapologyPicks).filter_by(fight_id=fight_id).one_or_none()
    if tp is None:
        return None
    f = db.query(db_models.Fight).filter_by(id=fight_id).one()
    # tapology_picks stores fighter_a/b; orient to the fight's fighter_1/2.
    a_is_f1 = tp.fighter_a_id == f.fighter_1_id
    pa, pb = tp.fighter_a_win_pct or 0.0, tp.fighter_b_win_pct or 0.0
    ma, mb = tp.fighter_a_methods or {}, tp.fighter_b_methods or {}
    f1_pct, f2_pct = (pa, pb) if a_is_f1 else (pb, pa)
    f1_m, f2_m = (ma, mb) if a_is_f1 else (mb, ma)
    return {
        "total_picks": tp.total_picks or 0,
        "fighter_1_win_pct": f1_pct,
        "fighter_2_win_pct": f2_pct,
        "fighter_1_methods": f1_m,
        "fighter_2_methods": f2_m,
    }


# ─── Sessions: save / list / detail / mark / delete / promote / import-odds ────


class SessionFightIn(BaseModel):
    fighter_1: str
    fighter_2: str
    odds_f1_american: int | None = None
    odds_f2_american: int | None = None
    models: dict[str, ModelPredictionOut] = {}
    consensus_winner: str | None = None
    consensus_pct: float | None = None
    avg_prob_f1: float | None = None
    community_picks: CommunityPicksOut | None = None


class SaveSessionRequest(BaseModel):
    event: str
    event_date: str | None = None
    fights: list[SessionFightIn]


class SaveSessionResponse(BaseModel):
    ok: bool
    id: int
    skipped: list[str] = []


class SessionSummary(BaseModel):
    id: int
    event: str
    created_at: str
    event_date: str | None = None
    n_fights: int
    n_results: int
    n_correct: int
    accuracy: float | None = None
    promoted: bool = False


class SessionDetailResponse(BaseModel):
    id: int
    event: str
    created_at: str
    event_date: str | None = None
    n_fights: int
    promoted: bool = False
    fights: list[RichFightPrediction]


class MarkResultRequest(BaseModel):
    fight_index: int
    real_winner: str | None = None


class MarkResultResponse(BaseModel):
    ok: bool
    n_results: int
    n_correct: int
    accuracy: float | None = None


class PromoteRequest(BaseModel):
    event_date: str | None = None
    event_location: str | None = None


class PromoteResponse(BaseModel):
    ok: bool
    event: str
    n_fights: int
    message: str


class ImportOddsRequest(BaseModel):
    tapology_url: str


class ImportOddsResponse(BaseModel):
    ok: bool
    updated: int = 0
    updated_fights: list[str] = []
    not_matched: list[str] = []
    error: str | None = None


def _parse_event_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _resolve_fighter_row(db: Session, ds, name: str) -> db_models.Fighter | None:
    canonical = ds.resolve_name(name)
    row = db.query(db_models.Fighter).filter_by(name=canonical).first()
    if row is None and canonical != name:
        row = db.query(db_models.Fighter).filter_by(name=name).first()
    return row


def _get_or_create_fight(
    db: Session, event_id: int, f1_id: int, f2_id: int, order: int,
    odds1: int | None, odds2: int | None,
) -> db_models.Fight:
    from sqlalchemy import or_, and_
    fight = (
        db.query(db_models.Fight)
          .filter(
              db_models.Fight.event_id == event_id,
              or_(
                  and_(db_models.Fight.fighter_1_id == f1_id,
                       db_models.Fight.fighter_2_id == f2_id),
                  and_(db_models.Fight.fighter_1_id == f2_id,
                       db_models.Fight.fighter_2_id == f1_id),
              ),
          )
          .first()
    )
    if fight is None:
        fight = db_models.Fight(
            event_id=event_id, fighter_1_id=f1_id, fighter_2_id=f2_id,
            fight_order=order, odds_f1_american=odds1, odds_f2_american=odds2,
        )
        db.add(fight)
        db.flush()
    else:
        if odds1 is not None:
            fight.odds_f1_american = odds1
        if odds2 is not None:
            fight.odds_f2_american = odds2
    return fight


def _active_version_idx_map(db: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    for am in db.query(db_models.ActiveModel).all():
        m = db.query(db_models.Model).filter_by(id=am.model_id).one()
        v = db.query(db_models.ModelVersion).filter_by(id=am.version_id).one()
        out[m.short] = v.version_idx
    return out


@router.post("/sessions", response_model=SaveSessionResponse)
def save_session(req: SaveSessionRequest, db: Session = Depends(get_db)) -> SaveSessionResponse:
    """Persist a prediction session.

    Materialises a preview ``Event`` (``source='preview'``) plus its ``Fight``
    rows — resolving fighter names to DB ids — then stores one ``Prediction``
    per (model, fight). Fights whose fighters can't be resolved are skipped.
    """
    ds = get_data_store()
    ev = db.query(db_models.Event).filter_by(name=req.event).one_or_none()
    if ev is None:
        ev = db_models.Event(
            name=req.event, source="preview", status="scheduled",
            date=_parse_event_date(req.event_date),
        )
        db.add(ev)
        db.flush()
    elif req.event_date and ev.date is None:
        ev.date = _parse_event_date(req.event_date)

    version_map = _active_version_idx_map(db)
    sess = db_models.PredictionSession(
        event_id=ev.id, source="lab_preview", status="completed",
    )
    db.add(sess)
    db.flush()

    skipped: list[str] = []
    for order, sf in enumerate(req.fights):
        r1 = _resolve_fighter_row(db, ds, sf.fighter_1)
        r2 = _resolve_fighter_row(db, ds, sf.fighter_2)
        if r1 is None or r2 is None:
            miss = sf.fighter_1 if r1 is None else sf.fighter_2
            skipped.append(f"{sf.fighter_1} vs {sf.fighter_2} (no DB fighter: {miss})")
            continue
        fight = _get_or_create_fight(
            db, ev.id, r1.id, r2.id, order,
            sf.odds_f1_american, sf.odds_f2_american,
        )
        # community picks → tapology_picks row (oriented to this fight)
        if sf.community_picks is not None:
            _upsert_community_picks(db, fight, r1.id, r2.id, sf.community_picks)
        for short, mp in sf.models.items():
            p1 = float(mp.probability_f1)
            existing = (
                db.query(db_models.Prediction)
                  .filter_by(session_id=sess.id, fight_id=fight.id, model_short=short)
                  .one_or_none()
            )
            if existing is not None:
                continue
            db.add(db_models.Prediction(
                session_id=sess.id,
                fight_id=fight.id,
                model_short=short,
                version_idx=version_map.get(short, 0),
                prob_f1=p1,
                prob_f2=round(1.0 - p1, 6),
                method_pred=None,
                raw_response={"full_name": mp.full_name, "probability_f1": p1},
            ))

    db.commit()
    return SaveSessionResponse(ok=True, id=sess.id, skipped=skipped)


def _upsert_community_picks(db: Session, fight, f1_id: int, f2_id: int, cp: CommunityPicksOut) -> None:
    tp = db.query(db_models.TapologyPicks).filter_by(fight_id=fight.id).one_or_none()
    payload = dict(
        total_picks=cp.total_picks,
        fighter_a_id=f1_id, fighter_b_id=f2_id,
        fighter_a_win_pct=cp.fighter_1_win_pct,
        fighter_b_win_pct=cp.fighter_2_win_pct,
        fighter_a_methods=cp.fighter_1_methods.model_dump(),
        fighter_b_methods=cp.fighter_2_methods.model_dump(),
    )
    if tp is None:
        db.add(db_models.TapologyPicks(fight_id=fight.id, **payload))
    else:
        for k, v in payload.items():
            setattr(tp, k, v)


_MODEL_FULLNAME_CACHE: dict[str, str] = {}


def _model_full_name(db: Session, short: str) -> str:
    if short in _MODEL_FULLNAME_CACHE:
        return _MODEL_FULLNAME_CACHE[short]
    m = db.query(db_models.Model).filter_by(short=short).one_or_none()
    full = (m.description or m.short) if m else short
    _MODEL_FULLNAME_CACHE[short] = full
    return full


def _reconstruct_session_fights(db: Session, ds, session_id: int) -> list[RichFightPrediction]:
    """Rebuild the rich fight cards from stored Prediction rows."""
    from collections import defaultdict
    from lab_api.services.predict_engine import _method_breakdown

    preds = db.query(db_models.Prediction).filter_by(session_id=session_id).all()
    by_fight: dict[int, list[db_models.Prediction]] = defaultdict(list)
    for p in preds:
        by_fight[p.fight_id].append(p)

    items: list[tuple[int, RichFightPrediction]] = []
    for fight_id, plist in by_fight.items():
        f = db.query(db_models.Fight).filter_by(id=fight_id).one_or_none()
        if f is None:
            continue
        f1 = db.query(db_models.Fighter).filter_by(id=f.fighter_1_id).one()
        f2 = db.query(db_models.Fighter).filter_by(id=f.fighter_2_id).one()
        name1, name2 = f1.name, f2.name

        models: dict[str, ModelPredictionOut] = {}
        votes1 = 0
        probs: list[float] = []
        for p in plist:
            p1 = float(p.prob_f1)
            winner = name1 if p1 >= 0.5 else name2
            if p1 >= 0.5:
                votes1 += 1
            probs.append(p1)
            models[p.model_short] = ModelPredictionOut(
                full_name=_model_full_name(db, p.model_short),
                predicted_winner=winner,
                probability_f1=round(p1, 4),
                confidence=round(max(p1, 1.0 - p1), 4),
            )
        total = len(plist)
        votes2 = total - votes1
        mean_p1 = sum(probs) / total if total else 0.5
        if votes1 > votes2:
            cwinner = name1
        elif votes2 > votes1:
            cwinner = name2
        else:
            cwinner = name1 if mean_p1 >= 0.5 else name2
        consensus = ConsensusOut(
            fighter_1_votes=votes1, fighter_2_votes=votes2, total_models=total,
            consensus_winner=cwinner,
            consensus_pct=round(max(votes1, votes2) / total * 100.0, 1) if total else 0.0,
        ) if total else None

        h1 = ds.fighter_histories.get(ds.resolve_name(name1), []) or []
        h2 = ds.fighter_histories.get(ds.resolve_name(name2), []) or []

        items.append((f.fight_order if f.fight_order is not None else 9999, RichFightPrediction(
            fighter_1=name1,
            fighter_2=name2,
            event="",
            odds_f1_american=f.odds_f1_american,
            odds_f2_american=f.odds_f2_american,
            models=models,
            consensus=consensus,
            prob_f1=round(mean_p1, 4),
            prob_f2=round(1.0 - mean_p1, 4),
            fighter_1_has_history=bool(h1),
            fighter_2_has_history=bool(h2),
            fighter_1_n_fights=len(h1),
            fighter_2_n_fights=len(h2),
            fighter_1_methods=_methods_out(_method_breakdown(h1)),
            fighter_2_methods=_methods_out(_method_breakdown(h2)),
            community_picks=_community_out(_community_picks_for_fight(db, f.id)),
            real_winner=f.real_winner,
            fight_id=f.id,
            outcome=_fight_outcome(f.result, f.method),
        )))

    items.sort(key=lambda t: t[0])
    return [rf for _, rf in items]


def _session_counts(fights: list[RichFightPrediction]) -> tuple[int, int, int, float | None]:
    """Return (n_fights, n_results, n_correct, accuracy)."""
    n_results = 0
    n_correct = 0
    for rf in fights:
        if not rf.real_winner:
            continue
        n_results += 1
        if rf.consensus and rf.consensus.consensus_winner == rf.real_winner:
            n_correct += 1
    acc = (n_correct / n_results) if n_results else None
    return len(fights), n_results, n_correct, acc


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(db: Session = Depends(get_db)) -> list[SessionSummary]:
    ds = get_data_store()
    sessions = (
        db.query(db_models.PredictionSession)
          .filter_by(source="lab_preview")
          .order_by(db_models.PredictionSession.created_at.desc())
          .all()
    )
    out: list[SessionSummary] = []
    for s in sessions:
        ev = db.query(db_models.Event).filter_by(id=s.event_id).one_or_none()
        fights = _reconstruct_session_fights(db, ds, s.id)
        n_fights, n_results, n_correct, acc = _session_counts(fights)
        out.append(SessionSummary(
            id=s.id,
            event=ev.name if ev else "(deleted)",
            created_at=s.created_at.isoformat() if s.created_at else "",
            event_date=ev.date.isoformat() if (ev and ev.date) else None,
            n_fights=n_fights,
            n_results=n_results,
            n_correct=n_correct,
            accuracy=round(acc, 4) if acc is not None else None,
            promoted=bool(ev and ev.source == "promoted"),
        ))
    return out


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: int, db: Session = Depends(get_db)) -> SessionDetailResponse:
    s = db.query(db_models.PredictionSession).filter_by(id=session_id).one_or_none()
    if s is None:
        raise HTTPException(404, "Session not found")
    ds = get_data_store()
    ev = db.query(db_models.Event).filter_by(id=s.event_id).one_or_none()
    fights = _reconstruct_session_fights(db, ds, s.id)
    for rf in fights:
        rf.event = ev.name if ev else ""
    return SessionDetailResponse(
        id=s.id,
        event=ev.name if ev else "(deleted)",
        created_at=s.created_at.isoformat() if s.created_at else "",
        event_date=ev.date.isoformat() if (ev and ev.date) else None,
        n_fights=len(fights),
        promoted=bool(ev and ev.source == "promoted"),
        fights=fights,
    )


@router.patch("/sessions/{session_id}/result", response_model=MarkResultResponse)
def mark_result(
    session_id: int, req: MarkResultRequest, db: Session = Depends(get_db),
) -> MarkResultResponse:
    """Set (or clear) the real winner of a fight, by its order within the session."""
    s = db.query(db_models.PredictionSession).filter_by(id=session_id).one_or_none()
    if s is None:
        raise HTTPException(404, "Session not found")
    ds = get_data_store()
    fights = _reconstruct_session_fights(db, ds, s.id)
    if req.fight_index < 0 or req.fight_index >= len(fights):
        raise HTTPException(400, "Invalid fight index")
    target = fights[req.fight_index]
    fight = db.query(db_models.Fight).filter_by(id=target.fight_id).one()
    winner = req.real_winner
    if winner:
        # snap to one of the two fighters
        rw = ds.resolve_name(winner)
        if rw == ds.resolve_name(target.fighter_1):
            winner = target.fighter_1
        elif rw == ds.resolve_name(target.fighter_2):
            winner = target.fighter_2
    fight.real_winner = winner or None
    db.commit()

    fights = _reconstruct_session_fights(db, ds, s.id)
    _, n_results, n_correct, acc = _session_counts(fights)
    return MarkResultResponse(
        ok=True, n_results=n_results, n_correct=n_correct,
        accuracy=round(acc, 4) if acc is not None else None,
    )


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)) -> dict:
    s = db.query(db_models.PredictionSession).filter_by(id=session_id).one_or_none()
    if s is None:
        raise HTTPException(404, "Session not found")
    ev = db.query(db_models.Event).filter_by(id=s.event_id).one_or_none()
    db.query(db_models.Prediction).filter_by(session_id=s.id).delete()
    db.delete(s)
    # Clean up an orphan preview event with no remaining sessions/fights left
    # untouched on real events.
    if ev is not None and ev.source == "preview":
        other = (
            db.query(db_models.PredictionSession)
              .filter(db_models.PredictionSession.event_id == ev.id,
                      db_models.PredictionSession.id != s.id)
              .count()
        )
        if other == 0:
            db.query(db_models.Fight).filter_by(event_id=ev.id).delete()
            db.delete(ev)
    db.commit()
    return {"ok": True}


@router.delete("/sessions")
def delete_all_sessions(db: Session = Depends(get_db)) -> dict:
    sessions = db.query(db_models.PredictionSession).filter_by(source="lab_preview").all()
    deleted = 0
    for s in sessions:
        ev = db.query(db_models.Event).filter_by(id=s.event_id).one_or_none()
        db.query(db_models.Prediction).filter_by(session_id=s.id).delete()
        db.delete(s)
        if ev is not None and ev.source == "preview":
            db.query(db_models.Fight).filter_by(event_id=ev.id).delete()
            db.delete(ev)
        deleted += 1
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.post("/sessions/{session_id}/promote", response_model=PromoteResponse)
def promote_session(
    session_id: int, req: PromoteRequest, db: Session = Depends(get_db),
) -> PromoteResponse:
    """Promote a preview session's event to a historical (completed) event."""
    s = db.query(db_models.PredictionSession).filter_by(id=session_id).one_or_none()
    if s is None:
        raise HTTPException(404, "Session not found")
    ev = db.query(db_models.Event).filter_by(id=s.event_id).one_or_none()
    if ev is None:
        raise HTTPException(404, "Event not found")
    if req.event_date:
        ev.date = _parse_event_date(req.event_date)
    if req.event_location:
        ev.location = req.event_location
    ev.source = "promoted"
    ev.status = "completed"
    n_fights = db.query(db_models.Fight).filter_by(event_id=ev.id).count()
    db.commit()
    return PromoteResponse(
        ok=True, event=ev.name, n_fights=n_fights,
        message="Session promoted to historical event",
    )


@router.post("/sessions/{session_id}/import-odds", response_model=ImportOddsResponse)
async def import_odds(
    session_id: int, req: ImportOddsRequest, db: Session = Depends(get_db),
) -> ImportOddsResponse:
    """Scrape a Tapology event and import American odds onto the session's fights."""
    if "tapology.com" not in (req.tapology_url or ""):
        return ImportOddsResponse(ok=False, error="URL must be a Tapology event page")
    s = db.query(db_models.PredictionSession).filter_by(id=session_id).one_or_none()
    if s is None:
        raise HTTPException(404, "Session not found")

    from ufc_core.scrapers.tapology import TapologyScraper
    try:
        scraped = await TapologyScraper().scrape_event(req.tapology_url)
    except Exception as e:  # noqa: BLE001
        return ImportOddsResponse(ok=False, error=f"Scraping failed: {e!r}")

    fights = db.query(db_models.Fight).filter_by(event_id=s.event_id).all()
    # index DB fights by normalized last-name set
    def _key(a: str, b: str) -> frozenset[str]:
        return frozenset({_norm_name(a).split()[-1] if _norm_name(a) else _norm_name(a),
                          _norm_name(b).split()[-1] if _norm_name(b) else _norm_name(b)})

    db_index: dict[frozenset[str], db_models.Fight] = {}
    db_names: dict[int, tuple[str, str]] = {}
    for f in fights:
        f1 = db.query(db_models.Fighter).filter_by(id=f.fighter_1_id).one()
        f2 = db.query(db_models.Fighter).filter_by(id=f.fighter_2_id).one()
        db_index[_key(f1.name, f2.name)] = f
        db_names[f.id] = (f1.name, f2.name)

    updated = 0
    updated_fights: list[str] = []
    not_matched: list[str] = []
    for tf in scraped.fights:
        match = db_index.get(_key(tf.fighter_1, tf.fighter_2))
        if match is None:
            not_matched.append(f"{tf.fighter_1} vs {tf.fighter_2}")
            continue
        n1, n2 = db_names[match.id]
        # orient scraped odds to the DB fight's fighter_1/fighter_2
        if _norm_name(tf.fighter_1).split()[-1:] == _norm_name(n1).split()[-1:]:
            o1, o2 = tf.odds_f1_american, tf.odds_f2_american
        else:
            o1, o2 = tf.odds_f2_american, tf.odds_f1_american
        if o1 is not None:
            match.odds_f1_american = o1
        if o2 is not None:
            match.odds_f2_american = o2
        updated += 1
        updated_fights.append(f"{n1} vs {n2}")
    db.commit()
    return ImportOddsResponse(
        ok=True, updated=updated, updated_fights=updated_fights, not_matched=not_matched,
    )


# ─── Tapology scrape (prefill the New-prediction form) ────────────────────────


class TapologyScrapeIn(BaseModel):
    url: str


@router.post("/tapology-scrape")
async def tapology_scrape(req: TapologyScrapeIn) -> dict:
    """Scrape a Tapology event page into ``{event_name, n_fights, fights[]}``."""
    if "tapology.com" not in (req.url or ""):
        raise HTTPException(400, "URL must be a Tapology event page")
    from ufc_core.scrapers.tapology import TapologyScraper
    try:
        scraped = await TapologyScraper().scrape_event(req.url)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Scraping failed: {e!r}")
    return scraped.model_dump()
