"""User bets router (lab) — personal bet tracking over lab_user_bet."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from lab_api.deps import get_db
from lab_api.schemas.betting import BetCombo
from lab_api.services import user_bets as svc

router = APIRouter(prefix="/api/user-bets", tags=["user-bets"])


class ImportRequest(BaseModel):
    event_name: str
    combos: list[BetCombo]
    session_id: int | None = None


class UpdateRequest(BaseModel):
    stake: float | None = None
    combined_odds: float | None = None
    potential_return: float | None = None
    picks: list[dict] | None = None
    status: str | None = Field(None, description="pending|won|lost|void|cashout")
    actual_return: float | None = None
    notes: str | None = None


@router.get("")
def list_bets(event_id: int | None = None, status: str | None = None,
              bet_type: str | None = None, db: Session = Depends(get_db)):
    return svc.list_bets(db, event_id=event_id, status=status, bet_type=bet_type)


@router.get("/stats")
def stats(event_id: int | None = None, db: Session = Depends(get_db)):
    return svc.compute_stats(db, event_id=event_id)


@router.post("/import")
def import_bets(req: ImportRequest, db: Session = Depends(get_db)):
    combos = [c.model_dump() for c in req.combos]
    try:
        bets = svc.import_from_combos(db, req.event_name, combos, req.session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "n_imported": len(combos), "bets": bets}


@router.patch("/{bet_id}")
def update_bet(bet_id: int, patch: UpdateRequest, db: Session = Depends(get_db)):
    try:
        return svc.update_bet(db, bet_id, patch.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{bet_id}")
def delete_bet(bet_id: int, db: Session = Depends(get_db)):
    try:
        svc.delete_bet(db, bet_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}
