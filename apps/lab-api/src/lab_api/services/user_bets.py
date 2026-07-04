"""User bets service (lab, single-tenant) — tracking over lab_user_bet."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

VALID_STATUSES = {"pending", "won", "lost", "void", "cashout"}
VALID_TYPES = {"single", "double", "triple"}


def _combo_key(bet_type: str, picks: list[dict]) -> str:
    return f"{bet_type}:" + "+".join(p.get("pick", "") for p in picks)


def _bet_to_dict(b: db_models.LabUserBet, event_name: str | None) -> dict:
    return {
        "id": b.id,
        "event_id": b.event_id,
        "event_name": event_name,
        "session_id": b.session_id,
        "bet_type": b.bet_type,
        "picks": b.picks,
        "combo_key": b.combo_key,
        "combined_odds": b.combined_odds,
        "stake": b.stake,
        "potential_return": b.potential_return,
        "status": b.status,
        "actual_return": b.actual_return,
        "notes": b.notes,
        "engine_snapshot": b.engine_snapshot,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _event_name(db: Session, event_id: int) -> str | None:
    ev = db.query(db_models.Event).filter_by(id=event_id).one_or_none()
    return ev.name if ev else None


def _resolve_event_id(db: Session, event_name: str) -> int:
    ev = db.execute(select(db_models.Event).where(db_models.Event.name == event_name)).scalar_one_or_none()
    if ev is None:
        raise ValueError(f"Event '{event_name}' not found")
    return ev.id


def _winners_for_event(db: Session, event_id: int) -> dict[tuple[str, str], str]:
    """{(fighter_1_name, fighter_2_name): real_winner} from resolved fights."""
    winners: dict[tuple[str, str], str] = {}
    fights = (
        db.query(db_models.Fight)
          .filter(db_models.Fight.event_id == event_id,
                  db_models.Fight.real_winner.isnot(None))
          .all()
    )
    if not fights:
        return winners
    ids = {f.fighter_1_id for f in fights} | {f.fighter_2_id for f in fights}
    fighter_map = {r.id: r.name for r in
                   db.query(db_models.Fighter).filter(db_models.Fighter.id.in_(ids)).all()}
    for f in fights:
        n1, n2 = fighter_map.get(f.fighter_1_id), fighter_map.get(f.fighter_2_id)
        if n1 and n2:
            winners[(n1, n2)] = f.real_winner
    return winners


def list_bets(db: Session, event_id=None, status=None, bet_type=None) -> list[dict]:
    q = select(db_models.LabUserBet)
    if event_id is not None:
        q = q.where(db_models.LabUserBet.event_id == event_id)
    if status:
        q = q.where(db_models.LabUserBet.status == status)
    if bet_type:
        q = q.where(db_models.LabUserBet.bet_type == bet_type)
    q = q.order_by(db_models.LabUserBet.created_at.desc())
    rows = db.execute(q).scalars().all()
    name_cache: dict[int, str | None] = {}
    out = []
    for b in rows:
        if b.event_id not in name_cache:
            name_cache[b.event_id] = _event_name(db, b.event_id)
        out.append(_bet_to_dict(b, name_cache[b.event_id]))
    return out


def import_from_combos(db: Session, event_name: str, combos: list[dict],
                       session_id: int | None = None) -> list[dict]:
    if not combos:
        return list_bets(db)
    event_id = _resolve_event_id(db, event_name)
    existing = set(db.execute(
        select(db_models.LabUserBet.combo_key).where(db_models.LabUserBet.event_id == event_id)
    ).scalars().all())
    for combo in combos:
        bet_type = combo.get("type") or "single"
        if bet_type not in VALID_TYPES:
            continue
        picks = combo.get("picks") or []
        if not picks:
            continue
        key = _combo_key(bet_type, picks)
        if key in existing:
            continue
        stake = float(combo.get("stake", 0) or 0)
        odds = float(combo.get("combined_odds", 1) or 1)
        pot = float(combo.get("potential_return", stake * odds) or 0)
        db.add(db_models.LabUserBet(
            event_id=event_id, session_id=session_id, bet_type=bet_type, picks=picks,
            combo_key=key, combined_odds=odds, stake=stake, potential_return=pot,
            status="pending", engine_snapshot=combo,
        ))
        existing.add(key)
    db.commit()
    resolve_pending_on_promotion(db, event_name)
    return list_bets(db, event_id=event_id)


def update_bet(db: Session, bet_id: int, patch: dict) -> dict:
    bet = db.get(db_models.LabUserBet, bet_id)
    if bet is None:
        raise ValueError("User bet not found")
    if patch.get("stake") is not None:
        bet.stake = float(patch["stake"])
    if patch.get("combined_odds") is not None:
        bet.combined_odds = float(patch["combined_odds"])
    if patch.get("potential_return") is not None:
        bet.potential_return = float(patch["potential_return"])
    if patch.get("picks"):
        new_key = _combo_key(bet.bet_type, patch["picks"])
        clash = db.execute(select(db_models.LabUserBet).where(
            db_models.LabUserBet.event_id == bet.event_id,
            db_models.LabUserBet.combo_key == new_key,
            db_models.LabUserBet.id != bet.id,
        )).scalar_one_or_none()
        if clash:
            raise ValueError("Duplicate combo_key for this event")
        bet.picks = patch["picks"]
        bet.combo_key = new_key
    if patch.get("status"):
        if patch["status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{patch['status']}'")
        bet.status = patch["status"]
    if "actual_return" in patch:
        bet.actual_return = float(patch["actual_return"]) if patch["actual_return"] is not None else None
    if "notes" in patch:
        bet.notes = patch["notes"]
    if bet.status == "cashout" and bet.actual_return is None:
        raise ValueError("cashout status requires actual_return")
    db.commit()
    db.refresh(bet)
    return _bet_to_dict(bet, _event_name(db, bet.event_id))


def delete_bet(db: Session, bet_id: int) -> None:
    bet = db.get(db_models.LabUserBet, bet_id)
    if bet is None:
        raise ValueError("User bet not found")
    db.delete(bet)
    db.commit()


def _pick_result(pick: dict, winners: dict[tuple[str, str], str]) -> bool | None:
    f1, f2, chosen = pick.get("fighter_1"), pick.get("fighter_2"), pick.get("pick")
    if not (f1 and f2 and chosen):
        return None
    winner = winners.get((f1, f2)) or winners.get((f2, f1))
    if not winner:
        return None
    return chosen == winner


def resolve_pending_on_promotion(db: Session, event_name: str) -> int:
    ev = db.execute(select(db_models.Event).where(db_models.Event.name == event_name)).scalar_one_or_none()
    if ev is None:
        return 0
    winners = _winners_for_event(db, ev.id)
    if not winners:
        return 0
    bets = db.execute(select(db_models.LabUserBet).where(
        db_models.LabUserBet.event_id == ev.id,
        db_models.LabUserBet.status == "pending",
    )).scalars().all()
    updated = 0
    for bet in bets:
        results = [_pick_result(p, winners) for p in bet.picks]
        if any(r is None for r in results):
            continue
        if all(results):
            bet.status = "won"
            bet.actual_return = bet.stake * bet.combined_odds
        else:
            bet.status = "lost"
            bet.actual_return = 0.0
        updated += 1
    db.commit()
    return updated


# ── stats (ported from legacy backend the legacy user_bets service) ──


def _pnl(bet: db_models.LabUserBet) -> tuple[float, float, float]:
    """Return (stake, returned, net_profit) for a bet.

    pending bets contribute 0 to returned/profit.
    """
    stake = bet.stake or 0.0
    if bet.status in ("won", "cashout"):
        returned = bet.actual_return or (stake * (bet.combined_odds or 1))
    elif bet.status == "void":
        returned = stake
    elif bet.status == "lost":
        returned = 0.0
    else:  # pending
        return stake, 0.0, 0.0
    return stake, returned, returned - stake


def _engine_roi_for_event(bets: list[db_models.LabUserBet]) -> tuple[float, float, float]:
    """ROI that would have been obtained following engine_snapshot recommendations
    for the SAME event the user bet on.

    Uses: stake = engine_snapshot.stake; hit = all picks won (same winners lookup
    already baked into bet.picks). Approximation: we use the same resolution the
    user bets received — if all picks hit → won, else lost.
    """
    stake = 0.0
    returned = 0.0
    for b in bets:
        snap = b.engine_snapshot or {}
        snap_stake = float(snap.get("stake", 0) or 0)
        snap_odds = float(snap.get("combined_odds", 1) or 1)
        if snap_stake <= 0:
            continue
        stake += snap_stake
        # Reuse resolution: if bet.status is won/lost, engine would have same
        # outcome since picks are identical. cashout/void treated as if pending.
        if b.status == "won":
            returned += snap_stake * snap_odds
        # lost → 0, pending/cashout/void → skip contribution beyond stake
    profit = returned - stake
    return stake, returned, profit


def compute_stats(db: Session, event_id: int | None = None) -> dict[str, Any]:
    q = select(db_models.LabUserBet)
    if event_id is not None:
        q = q.where(db_models.LabUserBet.event_id == event_id)
    bets = db.execute(q).scalars().all()

    total_stake = 0.0
    total_returned = 0.0
    n_settled = 0
    n_won = 0
    by_type: dict[str, dict[str, float]] = defaultdict(
        lambda: {"stake": 0.0, "returned": 0.0, "n": 0, "n_won": 0, "n_settled": 0}
    )
    bets_by_event: dict[int, list[db_models.LabUserBet]] = defaultdict(list)

    for b in bets:
        stake, returned, _ = _pnl(b)
        total_stake += stake
        total_returned += returned
        bt = by_type[b.bet_type]
        bt["stake"] += stake
        bt["returned"] += returned
        bt["n"] += 1
        if b.status in ("won", "lost", "cashout", "void"):
            n_settled += 1
            bt["n_settled"] += 1
            if b.status == "won" or (b.status == "cashout" and returned > stake):
                n_won += 1
                bt["n_won"] += 1
        bets_by_event[b.event_id].append(b)

    # Engine comparison: sum across events where user has bets
    engine_stake = 0.0
    engine_returned = 0.0
    for ev_bets in bets_by_event.values():
        s, r, _ = _engine_roi_for_event(ev_bets)
        engine_stake += s
        engine_returned += r

    net_profit = total_returned - total_stake
    roi_pct = (net_profit / total_stake * 100) if total_stake > 0 else 0.0
    winrate = (n_won / n_settled) if n_settled > 0 else 0.0

    breakdown = []
    for t, agg in by_type.items():
        bt_profit = agg["returned"] - agg["stake"]
        breakdown.append(
            {
                "bet_type": t,
                "n_bets": int(agg["n"]),
                "n_settled": int(agg["n_settled"]),
                "stake": agg["stake"],
                "returned": agg["returned"],
                "profit": bt_profit,
                "roi_pct": (bt_profit / agg["stake"] * 100) if agg["stake"] > 0 else 0.0,
                "winrate": (agg["n_won"] / agg["n_settled"]) if agg["n_settled"] > 0 else 0.0,
            }
        )
    breakdown.sort(key=lambda d: d["bet_type"])

    engine_profit = engine_returned - engine_stake
    engine_roi = (engine_profit / engine_stake * 100) if engine_stake > 0 else 0.0

    return {
        "n_bets": len(bets),
        "n_settled": n_settled,
        "n_won": n_won,
        "winrate": winrate,
        "total_stake": total_stake,
        "total_returned": total_returned,
        "net_profit": net_profit,
        "roi_pct": roi_pct,
        "by_type": breakdown,
        "engine_comparison": {
            "engine_stake": engine_stake,
            "engine_returned": engine_returned,
            "engine_profit": engine_profit,
            "engine_roi_pct": engine_roi,
            "delta_roi_pct": roi_pct - engine_roi,
        },
    }
