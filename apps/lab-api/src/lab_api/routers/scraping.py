"""Scraping router — UFCStats incremental + Tapology hook, DB-only.

Replaces the legacy backend's file-based pipeline (fighters_all*.json + backups).
Writes directly to ufc_lab via ufc_core.db.ingest.
"""

import logging
import threading
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

logger = logging.getLogger("lab-api.scraping")

router = APIRouter(prefix="/api/scraping", tags=["scraping"])

# ─── Shared job state (single-tenant lab) ──────────────────
_lock = threading.Lock()
_state: dict = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "step": None,
    "counts": None,
    "error": None,
}


class StartResponse(BaseModel):
    started: bool
    message: str


class StatusResponse(BaseModel):
    is_running: bool
    started_at: str | None = None
    finished_at: str | None = None
    step: str | None = None
    counts: dict | None = None
    error: str | None = None


@router.post("/start", response_model=StartResponse)
def start_scrape(letters: str | None = None) -> StartResponse:
    """Launch an async UFCStats incremental scrape + DB ingest.

    Args:
        letters: optional comma-separated subset (e.g. "a,b,c") for quick tests.
                 Default scrapes all letters.
    """
    with _lock:
        if _state["is_running"]:
            raise HTTPException(409, "A scrape is already running")
        _state.update({
            "is_running": True,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None, "step": "starting",
            "counts": None, "error": None,
        })

    def _job():
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db.ingest import ingest_fighters_payload
        from ufc_core.scrapers.ufcstats import process_letter_incremental

        from string import ascii_lowercase

        target = (
            [c.strip().lower() for c in letters.split(",")]
            if letters else list(ascii_lowercase)
        )

        try:
            db: Session = SessionLocal()
            try:
                # Build existing index from current DB state (by url).
                existing_index = {
                    f.ufcstats_url: f.record or ""
                    for f in db.query(db_models.Fighter).all()
                }
                all_payload: list[dict] = []
                for letter in target:
                    with _lock:
                        _state["step"] = f"scraping letter '{letter}'"
                    new_f, updated_f, _ = process_letter_incremental(
                        letter, existing_index
                    )
                    all_payload.extend(new_f)
                    all_payload.extend(updated_f)

                with _lock:
                    _state["step"] = f"ingesting {len(all_payload)} fighters"
                counts = ingest_fighters_payload(db, all_payload)

                # Audit row
                run = db_models.ScrapingRun(
                    source="ufcstats",
                    finished_at=datetime.now(UTC),
                    new_count=counts["fighters_new"],
                    updated_count=counts["fighters_updated"],
                    error_msg=None,
                )
                db.add(run)
                db.commit()

                with _lock:
                    _state.update({
                        "is_running": False,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": "done", "counts": counts,
                    })
            finally:
                db.close()
        except Exception as e:
            logger.exception("scrape job failed")
            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": "failed", "error": repr(e),
                })

    threading.Thread(target=_job, daemon=True).start()
    return StartResponse(started=True, message="Scrape kicked off in background")


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    with _lock:
        snap = dict(_state)
    return StatusResponse(**snap)


class RunSummary(BaseModel):
    id: int
    source: str
    started_at: str
    finished_at: str | None
    new_count: int
    updated_count: int
    error_msg: str | None


@router.get("/runs", response_model=list[RunSummary])
def list_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[RunSummary]:
    """Last N scraping runs (audit log)."""
    rows = (
        db.query(db_models.ScrapingRun)
          .order_by(db_models.ScrapingRun.started_at.desc())
          .limit(limit)
          .all()
    )
    return [
        RunSummary(
            id=r.id, source=r.source,
            started_at=r.started_at.isoformat() if r.started_at else "",
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
            new_count=r.new_count, updated_count=r.updated_count,
            error_msg=r.error_msg,
        ) for r in rows
    ]
