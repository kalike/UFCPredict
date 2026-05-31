"""Shared inference engine for the predictions router.

Centralises the TTA + ensemble inference used by every predict-style endpoint
(arbitrary matchups, past events, saved-session previews) so the router stays
thin and the logic lives in one place.

Design notes
------------
* **TTA (Test-Time Augmentation):** each fight is scored twice — normal order
  and with fighter_1 / fighter_2 swapped. The TTA probability for fighter_1 is
  ``(p_normal + (1 - p_swapped)) / 2``.
* **Consensus:** a simple majority vote across the active models (one vote each).
  Ties are broken by the mean fighter_1 probability. This mirrors the legacy
  legacy backend's consensus, NOT a single weighted number.
* **Ensemble probability:** the accuracy-weighted mean of every model's
  ``probability_f1`` (same weighting the lab already uses in compare /
  predict_event), shown in the probability bar.
* **Skips:** ``compute_features_for_fights`` drops a fight only when *both*
  fighters lack history. We pre-compute that condition ourselves so the surviving
  rows map 1:1 (and in order) onto both the normal and swapped frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ufc_core.config import BASE_ELO, TEMPERATURE
from ufc_core.db import models as db_models
from ufc_core.features.engine import compute_features_for_fights
from ufc_core.parsers import aggregate_stats

from lab_api.routers.fighters import _get_elo_ratings
from lab_api.routers.predictions_artifacts import load_artifact


# ─── Result containers ────────────────────────────────────────────────────────


@dataclass
class ModelVote:
    short: str
    full_name: str
    predicted_winner: str
    probability_f1: float
    confidence: float
    weight: float


@dataclass
class Consensus:
    fighter_1_votes: int
    fighter_2_votes: int
    total_models: int
    consensus_winner: str
    consensus_pct: float


@dataclass
class MethodBreakdown:
    """Career win/loss method counts, used by the KO/SUB/DEC bars."""

    wins: int = 0
    losses: int = 0
    ko_wins: int = 0
    sub_wins: int = 0
    dec_wins: int = 0
    ko_losses: int = 0
    sub_losses: int = 0
    dec_losses: int = 0


@dataclass
class FightResult:
    fighter_1: str
    fighter_2: str
    event: str
    odds_f1_american: int | None
    odds_f2_american: int | None
    models: dict[str, ModelVote]
    consensus: Consensus | None
    prob_f1: float
    prob_f2: float
    fighter_1_has_history: bool
    fighter_2_has_history: bool
    fighter_1_n_fights: int
    fighter_2_n_fights: int
    fighter_1_methods: MethodBreakdown
    fighter_2_methods: MethodBreakdown
    community_picks: dict | None = None
    # index back into the caller's original fight list (for re-aligning skips)
    input_index: int = -1


@dataclass
class InferenceOutput:
    fights: list[FightResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)        # "F1 vs F2 (sin historial)"
    skipped_models: list[str] = field(default_factory=list)  # "short: <err>"
    n_models: int = 0


# ─── Active-model loading ─────────────────────────────────────────────────────


@dataclass
class _Version:
    short: str
    full_name: str
    version_idx: int
    art: dict
    weight: float


def build_versions(db: Session) -> tuple[list[_Version], list[str]]:
    """Load every active model + its active version + artifact.

    Returns ``(versions, skipped)`` where skipped is a list of
    ``"short: <repr error>"`` for artifacts that failed to load.
    """
    versions: list[_Version] = []
    skipped: list[str] = []
    for am in db.query(db_models.ActiveModel).all():
        m = db.query(db_models.Model).filter_by(id=am.model_id).one()
        v = db.query(db_models.ModelVersion).filter_by(id=am.version_id).one()
        try:
            art = load_artifact(v.artifact_uri)
        except Exception as e:  # noqa: BLE001 — surfaced to the caller, not swallowed
            skipped.append(f"{m.short}: {e!r}")
            continue
        weight = 1.0
        if v.metrics_json and isinstance(v.metrics_json, dict):
            weight = float(v.metrics_json.get("accuracy", 1.0) or 1.0)
        versions.append(_Version(
            short=m.short,
            full_name=(m.description or m.short),
            version_idx=v.version_idx,
            art=art,
            weight=weight,
        ))
    return versions, skipped


# ─── Feature preparation ──────────────────────────────────────────────────────


def _prepare(frame: pd.DataFrame, art: dict, feat_cols: list[str]) -> np.ndarray:
    """Impute → transform → scale, matching the training pipeline."""
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


def _temperature_scale(proba: np.ndarray) -> np.ndarray:
    """Apply temperature scaling (no-op when TEMPERATURE == 1.0)."""
    t = TEMPERATURE
    if t == 1.0:
        return proba
    p = np.clip(proba, 1e-10, 1 - 1e-10)
    logits = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-logits / t))


# ─── Main entry point ─────────────────────────────────────────────────────────


def run_inference(
    db: Session,
    ds,
    fights: list[dict],
    *,
    event_date=None,
    before_event_date=None,
    versions: list[_Version] | None = None,
    versions_skipped: list[str] | None = None,
) -> InferenceOutput:
    """Run TTA + ensemble inference over a list of fight dicts.

    Each ``fight`` dict must carry ``fighter_1``, ``fighter_2`` and ``event``;
    optional ``odds_f1_american``, ``odds_f2_american``, ``community_picks``.

    Names are resolved canonically. Fights where both fighters lack history are
    reported under ``skipped`` and produce no FightResult.
    """
    if versions is None:
        versions, versions_skipped = build_versions(db)
    versions_skipped = versions_skipped or []

    out = InferenceOutput(skipped_models=versions_skipped, n_models=len(versions))

    elo = _get_elo_ratings()

    # Resolve names + decide which fights survive (≥1 fighter with history).
    normal_inputs: list[dict] = []
    swapped_inputs: list[dict] = []
    survivors: list[dict] = []   # metadata per surviving fight
    for idx, f in enumerate(fights):
        name1 = ds.resolve_name(f["fighter_1"])
        name2 = ds.resolve_name(f["fighter_2"])
        hist1 = ds.fighter_histories.get(name1, []) or []
        hist2 = ds.fighter_histories.get(name2, []) or []
        if not hist1 and not hist2:
            out.skipped.append(f"{f['fighter_1']} vs {f['fighter_2']} (sin historial)")
            continue
        o1 = f.get("odds_f1_american")
        o2 = f.get("odds_f2_american")
        ev = f.get("event", "Prediction")
        normal_inputs.append({
            "event": ev, "fighter_1": name1, "fighter_2": name2,
            "odds_f1_american": o1, "odds_f2_american": o2, "result": np.nan,
        })
        swapped_inputs.append({
            "event": ev, "fighter_1": name2, "fighter_2": name1,
            "odds_f1_american": o2, "odds_f2_american": o1, "result": np.nan,
        })
        survivors.append({
            "input_index": idx,
            "name1": name1, "name2": name2,
            "hist1": hist1, "hist2": hist2,
            "odds_f1_american": o1, "odds_f2_american": o2,
            "event": ev,
            "community_picks": f.get("community_picks"),
        })

    if not survivors:
        return out

    feats_n, _ = compute_features_for_fights(
        fights=normal_inputs,
        fighter_histories=ds.fighter_histories,
        fighter_lookup=ds.fighter_lookup,
        event_dates=ds.event_dates,
        elo_ratings=elo,
        base_elo=BASE_ELO,
        event_date=event_date,
        before_event_date=before_event_date,
    )
    feats_s, _ = compute_features_for_fights(
        fights=swapped_inputs,
        fighter_histories=ds.fighter_histories,
        fighter_lookup=ds.fighter_lookup,
        event_dates=ds.event_dates,
        elo_ratings=elo,
        base_elo=BASE_ELO,
        event_date=event_date,
        before_event_date=before_event_date,
    )
    # Both frames drop the exact same fights (skip iff both lack history, which
    # we already filtered out), so they align 1:1 with `survivors`.
    if len(feats_n) != len(survivors) or len(feats_s) != len(survivors):
        # Defensive: if the engine dropped extra rows, bail out gracefully.
        n = min(len(feats_n), len(feats_s), len(survivors))
        feats_n = feats_n.iloc[:n].reset_index(drop=True)
        feats_s = feats_s.iloc[:n].reset_index(drop=True)
        survivors = survivors[:n]

    # per_fight_probs[i] = list of (short, full_name, p_f1, weight)
    per_fight: list[list[tuple[str, str, float, float]]] = [[] for _ in survivors]
    for ver in versions:
        clf = ver.art["clf"]
        feat_cols = ver.art["feat_cols"]
        for c in feat_cols:
            if c not in feats_n.columns:
                feats_n[c] = 0.0
            if c not in feats_s.columns:
                feats_s[c] = 0.0
        X_n = _prepare(feats_n, ver.art, feat_cols)
        X_s = _prepare(feats_s, ver.art, feat_cols)
        try:
            p_n = clf.predict_proba(X_n)[:, 1].astype(float)
            p_s = clf.predict_proba(X_s)[:, 1].astype(float)
        except Exception:  # noqa: BLE001 — some regressors expose only predict()
            p_n = clf.predict(X_n).astype(float)
            p_s = clf.predict(X_s).astype(float)
        p_tta = np.clip((p_n + (1.0 - p_s)) / 2.0, 0.0, 1.0)
        p_tta = _temperature_scale(p_tta)
        for i in range(len(survivors)):
            per_fight[i].append((ver.short, ver.full_name, float(p_tta[i]), ver.weight))

    # Assemble results
    for i, s in enumerate(survivors):
        rows = per_fight[i]
        name1, name2 = s["name1"], s["name2"]
        models: dict[str, ModelVote] = {}
        votes_f1 = 0
        wsum = 0.0
        wprob = 0.0
        prob_mean_acc = []
        for short, full_name, p1, w in rows:
            winner = name1 if p1 >= 0.5 else name2
            if p1 >= 0.5:
                votes_f1 += 1
            models[short] = ModelVote(
                short=short, full_name=full_name, predicted_winner=winner,
                probability_f1=round(p1, 4), confidence=round(max(p1, 1.0 - p1), 4),
                weight=w,
            )
            wsum += w
            wprob += p1 * w
            prob_mean_acc.append(p1)

        total = len(rows)
        votes_f2 = total - votes_f1
        ens_p1 = (wprob / wsum) if wsum else float(np.mean(prob_mean_acc or [0.5]))

        consensus = None
        if total > 0:
            if votes_f1 > votes_f2:
                cwinner = name1
            elif votes_f2 > votes_f1:
                cwinner = name2
            else:  # tie → break by mean prob
                cwinner = name1 if ens_p1 >= 0.5 else name2
            consensus = Consensus(
                fighter_1_votes=votes_f1,
                fighter_2_votes=votes_f2,
                total_models=total,
                consensus_winner=cwinner,
                consensus_pct=round(max(votes_f1, votes_f2) / total * 100.0, 1),
            )

        out.fights.append(FightResult(
            fighter_1=name1,
            fighter_2=name2,
            event=s["event"],
            odds_f1_american=s["odds_f1_american"],
            odds_f2_american=s["odds_f2_american"],
            models=models,
            consensus=consensus,
            prob_f1=round(ens_p1, 4),
            prob_f2=round(1.0 - ens_p1, 4),
            fighter_1_has_history=bool(s["hist1"]),
            fighter_2_has_history=bool(s["hist2"]),
            fighter_1_n_fights=len(s["hist1"]),
            fighter_2_n_fights=len(s["hist2"]),
            fighter_1_methods=_method_breakdown(s["hist1"]),
            fighter_2_methods=_method_breakdown(s["hist2"]),
            community_picks=s["community_picks"],
            input_index=s["input_index"],
        ))

    return out


def _method_breakdown(history: list[dict]) -> MethodBreakdown:
    if not history:
        return MethodBreakdown()
    agg = aggregate_stats(history)
    return MethodBreakdown(
        wins=int(agg.get("wins", 0)),
        losses=int(agg.get("losses", 0)),
        ko_wins=int(agg.get("ko_wins", 0)),
        sub_wins=int(agg.get("sub_wins", 0)),
        dec_wins=int(agg.get("dec_wins", 0)),
        ko_losses=int(agg.get("ko_losses", 0)),
        sub_losses=int(agg.get("sub_losses", 0)),
        dec_losses=int(agg.get("dec_losses", 0)),
    )
