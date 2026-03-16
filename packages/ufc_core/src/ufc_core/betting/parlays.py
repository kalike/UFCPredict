"""
UFC Predictor — ParlayService.

Handles saving and loading user-edited parlay strategy instances linked to
a prediction session. Uses the existing ``parlays`` DB table.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

try:
    from ufc_core.db.engine import SessionLocal as SyncSessionLocal
except ImportError:
    SyncSessionLocal = None  # type: ignore[assignment]
from ufc_core.db.models import Parlay
from ufc_core.betting._stubs import _resolve_session  # TODO(F1.T15): sessions._resolve_session stub
from ufc_core.exceptions import NotFoundError


class ParlayService:
    # ── Save ──────────────────────────────────────────────────────────────

    def save_instances(self, session_id: str, instances: list[dict]) -> list[dict]:
        """Replace all saved parlay instances for a session with the new ones.

        Each ``instance`` dict must have:
            instance_id, strategy_type, picks, combined_odds, combined_prob, ev, kelly_pct
        """
        db: Session = SyncSessionLocal()
        try:
            ps = _resolve_session(db, session_id)
            if ps is None:
                raise NotFoundError("Session not found")

            # Delete existing parlays for this session
            db.execute(delete(Parlay).where(Parlay.session_id == ps.id))
            db.flush()

            saved: list[dict] = []
            for inst in instances:
                row = Parlay(
                    session_id=ps.id,
                    strategy=inst["instance_id"],       # e.g. "safe-0", "safe-1"
                    picks=inst.get("picks", []),
                    combined_odds=inst.get("combined_odds"),
                    combined_prob=inst.get("combined_prob", 0.0),
                    ev=inst.get("ev"),
                    kelly_pct=inst.get("kelly_pct"),
                    hit=None,
                    created_at=datetime.now(UTC),
                )
                db.add(row)
                db.flush()
                saved.append(self._row_to_dict(row, inst.get("strategy_type", "")))

            db.commit()
            return saved
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ── Load ──────────────────────────────────────────────────────────────

    def load_instances(self, session_id: str) -> list[dict]:
        """Return all saved parlay instances for a session."""
        db: Session = SyncSessionLocal()
        try:
            ps = _resolve_session(db, session_id)
            if ps is None:
                raise NotFoundError("Session not found")

            rows = (
                db.execute(select(Parlay).where(Parlay.session_id == ps.id))
                .scalars()
                .all()
            )
            return [self._row_to_dict(r) for r in rows]
        finally:
            db.close()

    # ── Helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: Parlay, strategy_type: str = "") -> dict:
        # Infer strategy_type from instance_id if not provided
        if not strategy_type and row.strategy:
            strategy_type = row.strategy.rsplit("-", 1)[0]
        return {
            "id": row.id,
            "instance_id": row.strategy,
            "strategy_type": strategy_type,
            "picks": row.picks or [],
            "combined_odds": row.combined_odds,
            "combined_prob": row.combined_prob or 0.0,
            "ev": row.ev,
            "kelly_pct": row.kelly_pct,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
