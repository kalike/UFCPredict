"""Predictions router — serve cached predictions per event.

Supports listing events, reading caches, and running real ensemble inference
against all active models for a given event.
"""

import json
from datetime import datetime, UTC
from pathlib import Path
import joblib
import numpy as np

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

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


def _load_artifact(uri: str) -> dict:
    """Load an artifact saved by the training service.

    Accepts ``file://path`` or absolute path. Returns the dict
    ``{clf, feat_cols, feature_set, model_short}`` produced at training time.
    """
    if uri.startswith("file://"):
        path = uri[len("file://"):]
    else:
        path = uri
    return joblib.load(path)


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
