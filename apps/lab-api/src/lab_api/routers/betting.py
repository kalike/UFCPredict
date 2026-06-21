"""Betting router — defaults, backtest, recommend, compare, config presets."""
from __future__ import annotations

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db
from lab_api.schemas.betting import (
    BacktestResponse, BettingConfig, CompareRequest, CompareResponse, RecommendResponse,
)
from lab_api.services.backtest_engine import run_backtest
from lab_api.services.betting_engine import generate_event_plan
from lab_api.services.lab_session_provider import get_session_fights

router = APIRouter(prefix="/api/betting", tags=["betting"])


@router.get("/defaults", response_model=BettingConfig)
def get_defaults() -> BettingConfig:
    return BettingConfig()


@router.post("/backtest", response_model=BacktestResponse)
def backtest(config: BettingConfig, db: Session = Depends(get_db)) -> BacktestResponse:
    return run_backtest(db, config)


@router.post("/recommend/{session_id}", response_model=RecommendResponse)
def recommend(session_id: int, config: BettingConfig,
              db: Session = Depends(get_db)) -> RecommendResponse:
    event_name, fights = get_session_fights(db, session_id)
    if not fights:
        raise HTTPException(404, f"Session {session_id} not found or has no fights")
    return generate_event_plan(fights, config, event_name)


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    return CompareResponse(results=[run_backtest(db, cfg) for cfg in req.configs])


# --- Config presets CRUD ---

class BetConfigIn(BaseModel):
    name: str
    params: dict
    is_default: bool = False


class BetConfigOut(BaseModel):
    id: int
    name: str
    params: dict
    is_default: bool
    created_at: str | None = None
    updated_at: str | None = None


def _config_out(row: db_models.LabBetConfig) -> BetConfigOut:
    return BetConfigOut(
        id=row.id, name=row.name, params=row.params, is_default=row.is_default,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.get("/configs", response_model=list[BetConfigOut])
def list_configs(db: Session = Depends(get_db)) -> list[BetConfigOut]:
    rows = db.query(db_models.LabBetConfig).order_by(db_models.LabBetConfig.name).all()
    return [_config_out(r) for r in rows]


@router.post("/configs", response_model=BetConfigOut)
def upsert_config(req: BetConfigIn, db: Session = Depends(get_db)) -> BetConfigOut:
    row = db.query(db_models.LabBetConfig).filter_by(name=req.name).one_or_none()
    if row is None:
        row = db_models.LabBetConfig(name=req.name, params=req.params, is_default=req.is_default)
        db.add(row)
    else:
        row.params = req.params
        row.is_default = req.is_default
        row.updated_at = datetime.now(UTC)
    if req.is_default:
        for other in db.query(db_models.LabBetConfig).filter(db_models.LabBetConfig.name != req.name):
            other.is_default = False
    db.commit()
    db.refresh(row)
    return _config_out(row)


@router.put("/configs/{config_id}", response_model=BetConfigOut)
def update_config(config_id: int, req: BetConfigIn, db: Session = Depends(get_db)) -> BetConfigOut:
    row = db.query(db_models.LabBetConfig).filter_by(id=config_id).one_or_none()
    if row is None:
        raise HTTPException(404, "Config not found")
    row.name = req.name
    row.params = req.params
    row.is_default = req.is_default
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _config_out(row)


@router.delete("/configs/{config_id}")
def delete_config(config_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.query(db_models.LabBetConfig).filter_by(id=config_id).one_or_none()
    if row is None:
        raise HTTPException(404, "Config not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
