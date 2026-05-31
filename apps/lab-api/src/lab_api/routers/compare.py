"""Compare router — head-to-head between two fighters.

Two endpoints:
  GET /api/compare?a=&b=           — basic DB stats by fighter id (legacy)
  GET /api/compare/by-name?f1=&f2= — full comparison (career, ELO, stat
      comparison, feature deltas, recent fights, optional prediction with
      the lab's active models). Port of the old backend's ComparisonService.
"""

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.config import BASE_ELO
from ufc_core.db import models as db_models
from ufc_core.features.engine import STAT_COLS, compute_features_for_fights
from ufc_core.parsers import aggregate_stats

from lab_api.deps import get_data_store, get_db
from lab_api.routers.fighters import _get_elo_ratings, _photo_url_map, _resolve_photo_url
from lab_api.routers.predictions import _load_artifact

router = APIRouter(prefix="/api/compare", tags=["compare"])


class FighterStats(BaseModel):
    id: int
    name: str
    record: str | None
    stance: str | None
    height_cm: float | None
    reach_cm: float | None
    fight_count: int


class CompareResponse(BaseModel):
    fighter_a: FighterStats
    fighter_b: FighterStats


def _stats(db: Session, f: db_models.Fighter) -> FighterStats:
    from sqlalchemy import or_
    fight_count = (
        db.query(db_models.Fight)
          .filter(or_(db_models.Fight.fighter_1_id == f.id,
                      db_models.Fight.fighter_2_id == f.id))
          .count()
    )
    return FighterStats(
        id=f.id, name=f.name, record=f.record, stance=f.stance,
        height_cm=f.height_cm, reach_cm=f.reach_cm, fight_count=fight_count,
    )


@router.get("", response_model=CompareResponse)
def compare(a: int, b: int, db: Session = Depends(get_db)) -> CompareResponse:
    """Compare two fighters by id."""
    fa = db.query(db_models.Fighter).filter_by(id=a).one_or_none()
    fb = db.query(db_models.Fighter).filter_by(id=b).one_or_none()
    if fa is None:
        raise HTTPException(404, f"Fighter {a} not found")
    if fb is None:
        raise HTTPException(404, f"Fighter {b} not found")
    return CompareResponse(fighter_a=_stats(db, fa), fighter_b=_stats(db, fb))


# ─── Full by-name comparison (port of the old ComparisonService) ─────────────

_DELTA_LABELS: dict[str, str] = {
    "delta_win_rate": "Win Rate",
    "delta_total_fights": "Total peleas",
    "delta_kd_differential": "KD Diferencial",
    "delta_sig_str_accuracy": "Precisión Golpes Sig.",
    "delta_sig_str_defense": "Defensa Golpes Sig.",
    "delta_td_accuracy": "Precisión Takedowns",
    "delta_td_defense": "Defensa Takedowns",
    "delta_ctrl_time_differential": "Control (dif seg)",
    "delta_avg_sub_attempts": "Intentos Sumisión",
    "delta_avg_reversals": "Reversals",
    "delta_ko_rate": "KO Rate",
    "delta_sub_rate": "Sub Rate",
    "delta_dec_rate": "Dec Rate",
    "delta_avg_sig_str_landed": "Golpes Sig. / Pelea",
    "delta_avg_sig_str_received": "Golpes Sig. Recibidos",
    "delta_avg_td_landed": "TD Logrados / Pelea",
    "delta_avg_td_received": "TD Recibidos / Pelea",
    "delta_recent_win_rate": "Win Rate Reciente",
    "delta_win_streak": "Racha Victorias",
    "delta_lose_streak": "Racha Derrotas",
    "delta_avg_head_landed": "Golpes Cabeza",
    "delta_avg_body_landed": "Golpes Cuerpo",
    "delta_avg_leg_landed": "Golpes Pierna",
    "delta_avg_distance_landed": "Golpes Distancia",
    "delta_avg_clinch_landed": "Golpes Clinch",
    "delta_avg_ground_landed": "Golpes Suelo",
    "delta_momentum": "Momentum",
    "delta_finish_rate": "Finish Rate",
    "delta_exp_ratio": "Ratio Experiencia",
    "delta_striking_volume": "Volumen Striking",
    "delta_height_in": "Altura (in)",
    "delta_reach_in": "Reach (in)",
    "delta_age": "Edad (años)",
    "delta_days_inactive": "Inactividad (días)",
    "delta_elo": "ELO",
}

# Stats where lower is better
_REVERSE_COLS = {
    "lose_streak",
    "avg_sig_str_received",
    "avg_td_received",
    "avg_kd_received",
    "avg_opp_ctrl_time",
}


class CompareFighter(BaseModel):
    name: str
    stats: dict
    career: dict
    elo: float
    photo_url: str


class StatComparison(BaseModel):
    f1_value: float
    f2_value: float
    better: str  # fighter_1 | fighter_2 | tie


class FeatureDelta(BaseModel):
    feature: str
    label: str
    f1_value: float | None
    f2_value: float | None
    delta: float
    better: str


class RecentFight(BaseModel):
    fight_index: int
    result: str
    opponent: str
    method: str
    round: str
    event: str
    event_date: str


class HeadToHeadPrediction(BaseModel):
    prob_f1: float
    prob_f2: float
    models: dict[str, float]  # model_short -> P(fighter_1 wins), TTA
    contributing_models: list[str]
    fighter_1_has_history: bool
    fighter_2_has_history: bool


class CompareByNameResponse(BaseModel):
    fighter_1: CompareFighter
    fighter_2: CompareFighter
    stat_comparison: dict[str, StatComparison]
    prediction: HeadToHeadPrediction | None
    feature_deltas: list[FeatureDelta]
    recent_fights_f1: list[RecentFight]
    recent_fights_f2: list[RecentFight]


def _recent_fights(ds, name: str, max_n: int = 8) -> list[RecentFight]:
    ftr = ds.get_fighter(name)
    if not ftr:
        return []
    out = []
    for i, f in enumerate(ftr.get("fights", [])[:max_n]):
        method = " ".join((f.get("method") or "").strip().split())
        ev_name = f.get("event", "")
        ev_dt = ds.event_dates.get(ev_name)
        out.append(RecentFight(
            fight_index=i,
            result=f.get("result", ""),
            opponent=f.get("opponent", ""),
            method=method,
            round=str(f.get("round", "")),
            event=ev_name,
            event_date=ev_dt.strftime("%b %d, %Y") if ev_dt else "",
        ))
    return out


def _predict_head_to_head(
    db: Session, ds, name1: str, name2: str, has1: bool, has2: bool,
) -> HeadToHeadPrediction | None:
    """TTA + weighted-ensemble inference with the lab's active models.

    Same scheme as predictions.predict_event but for one hypothetical fight
    and without persisting anything. Returns None when there are no loadable
    active models or features can't be computed.
    """
    active_rows = db.query(db_models.ActiveModel).all()
    if not active_rows:
        return None

    versions: list[tuple[str, dict, float]] = []
    for am in active_rows:
        m = db.query(db_models.Model).filter_by(id=am.model_id).one()
        v = db.query(db_models.ModelVersion).filter_by(id=am.version_id).one()
        try:
            art = _load_artifact(v.artifact_uri)
        except Exception:
            continue
        weight = 1.0
        if v.metrics_json and isinstance(v.metrics_json, dict):
            weight = float(v.metrics_json.get("accuracy", 1.0) or 1.0)
        versions.append((m.short, art, weight))
    if not versions:
        return None

    def _features(a: str, b: str):
        df, _ = compute_features_for_fights(
            fights=[{"event": "Comparison", "fighter_1": a, "fighter_2": b,
                     "odds_f1_american": None, "odds_f2_american": None}],
            fighter_histories=ds.fighter_histories,
            fighter_lookup=ds.fighter_lookup,
            event_dates=ds.event_dates,
            elo_ratings=_get_elo_ratings(),
            base_elo=BASE_ELO,
        )
        return df

    feats_n = _features(name1, name2)
    feats_s = _features(name2, name1)
    if len(feats_n) == 0 or len(feats_s) == 0:
        return None

    total_w = sum(w for _, _, w in versions) or 1.0
    models: dict[str, float] = {}
    prob_f1 = 0.0
    for short, art, w in versions:
        clf = art["clf"]
        feat_cols = art["feat_cols"]
        for c in feat_cols:
            if c not in feats_n.columns:
                feats_n[c] = 0.0
            if c not in feats_s.columns:
                feats_s[c] = 0.0
        X_n = feats_n[feat_cols].values
        X_s = feats_s[feat_cols].values
        try:
            p_n = float(clf.predict_proba(X_n)[0, 1])
            p_s = float(clf.predict_proba(X_s)[0, 1])
        except Exception:
            p_n = float(clf.predict(X_n)[0])
            p_s = float(clf.predict(X_s)[0])
        # TTA: average of (normal P(f1), 1 - swapped P(f1))
        p1 = float(np.clip((p_n + (1.0 - p_s)) / 2.0, 0.0, 1.0))
        models[short] = round(p1, 4)
        prob_f1 += p1 * (w / total_w)

    return HeadToHeadPrediction(
        prob_f1=round(prob_f1, 4),
        prob_f2=round(1.0 - prob_f1, 4),
        models=models,
        contributing_models=list(models),
        fighter_1_has_history=has1,
        fighter_2_has_history=has2,
    )


@router.get("/by-name", response_model=CompareByNameResponse)
def compare_by_name(f1: str, f2: str, db: Session = Depends(get_db)) -> CompareByNameResponse:
    """Full head-to-head comparison by fighter name."""
    ds = get_data_store()
    ftr1 = ds.get_fighter(f1)
    ftr2 = ds.get_fighter(f2)
    if ftr1 is None:
        raise HTTPException(404, f"Fighter '{f1}' not found")
    if ftr2 is None:
        raise HTTPException(404, f"Fighter '{f2}' not found")

    name1 = ftr1.get("name", f1)
    name2 = ftr2.get("name", f2)

    hist1 = ds.fighter_histories.get(name1, [])
    hist2 = ds.fighter_histories.get(name2, [])
    career1 = aggregate_stats(hist1) if hist1 else {}
    career2 = aggregate_stats(hist2) if hist2 else {}

    elo = _get_elo_ratings()
    elo1 = float(elo.get(name1, BASE_ELO))
    elo2 = float(elo.get(name2, BASE_ELO))
    photos = _photo_url_map(db, [name1, name2])

    fighter_1 = CompareFighter(
        name=name1, stats=ftr1.get("stats", {}), career=career1, elo=elo1,
        photo_url=_resolve_photo_url(name1, photos.get(name1)) or "",
    )
    fighter_2 = CompareFighter(
        name=name2, stats=ftr2.get("stats", {}), career=career2, elo=elo2,
        photo_url=_resolve_photo_url(name2, photos.get(name2)) or "",
    )

    # Stat-by-stat comparison over career aggregates + ELO + fight counts
    stat_comparison: dict[str, StatComparison] = {}

    def _cmp(key: str, v1: float, v2: float, reverse: bool = False) -> None:
        if reverse:
            better = "fighter_1" if v1 < v2 else ("fighter_2" if v2 < v1 else "tie")
        else:
            better = "fighter_1" if v1 > v2 else ("fighter_2" if v2 > v1 else "tie")
        stat_comparison[key] = StatComparison(
            f1_value=round(float(v1), 4), f2_value=round(float(v2), 4), better=better,
        )

    for col in STAT_COLS:
        _cmp(col, career1.get(col, 0) or 0, career2.get(col, 0) or 0,
             reverse=col in _REVERSE_COLS)
    _cmp("elo", elo1, elo2)
    _cmp("n_fights", len(ftr1.get("fights", [])), len(ftr2.get("fights", [])))

    # Feature deltas + prediction (need at least one history)
    feature_deltas: list[FeatureDelta] = []
    prediction: HeadToHeadPrediction | None = None
    if hist1 or hist2:
        df, _ = compute_features_for_fights(
            fights=[{"event": "Comparison", "fighter_1": name1, "fighter_2": name2,
                     "odds_f1_american": None, "odds_f2_american": None,
                     "result": np.nan}],
            fighter_histories=ds.fighter_histories,
            fighter_lookup=ds.fighter_lookup,
            event_dates=ds.event_dates,
            elo_ratings=elo,
            base_elo=BASE_ELO,
        )
        if len(df) > 0:
            row = df.iloc[0]

            def _clean(v) -> float | None:
                if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
                    return None
                return round(float(v), 4)

            for col in df.columns:
                if not col.startswith("delta_"):
                    continue
                val = row[col]
                if isinstance(val, (float, np.floating)) and np.isnan(val):
                    val = 0.0
                feature_deltas.append(FeatureDelta(
                    feature=col,
                    label=_DELTA_LABELS.get(col, col),
                    f1_value=_clean(row.get(col.replace("delta_", "f1_"))),
                    f2_value=_clean(row.get(col.replace("delta_", "f2_"))),
                    delta=round(float(val), 4),
                    better="fighter_1" if float(val) > 0
                           else ("fighter_2" if float(val) < 0 else "tie"),
                ))

            prediction = _predict_head_to_head(
                db, ds, name1, name2, bool(hist1), bool(hist2),
            )

    return CompareByNameResponse(
        fighter_1=fighter_1,
        fighter_2=fighter_2,
        stat_comparison=stat_comparison,
        prediction=prediction,
        feature_deltas=feature_deltas,
        recent_fights_f1=_recent_fights(ds, name1),
        recent_fights_f2=_recent_fights(ds, name2),
    )
