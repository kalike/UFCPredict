"""Scraping router — UFCStats incremental + Tapology hook, DB-only.

Replaces the legacy backend's file-based pipeline (fighters_all*.json + backups).
Writes directly to ufc_lab via ufc_core.db.ingest.
"""

import logging
import os
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
                # ── 1. UFCStats incremental ────────────────────────────
                existing_index = {
                    f.ufcstats_url: f.record or ""
                    for f in db.query(db_models.Fighter).all()
                }
                all_payload: list[dict] = []
                summary_dict: dict = {}
                # Two-level parallelism:
                #   - LETTER_WORKERS letters in parallel
                #   - inside each letter, FIGHTER_WORKERS fighter pages in parallel
                # Total peak concurrency = LETTER_WORKERS * FIGHTER_WORKERS.
                # Default 2 × 3 = 6 concurrent requests — UFCStats rate-limits
                # aggressively above ~8 in our experience. get_soup() has retry
                # with exponential backoff so transient 429s self-heal, but
                # keeping peak concurrency low avoids stalling on backoff.
                LETTER_WORKERS = int(os.environ.get("UFC_SCRAPE_LETTER_WORKERS", "2"))
                FIGHTER_WORKERS = int(os.environ.get("UFC_SCRAPE_FIGHTER_WORKERS", "3"))

                with _lock:
                    _state["step"] = (
                        f"scraping {len(target)} letters × {FIGHTER_WORKERS} fighter workers"
                        f" (letter pool={LETTER_WORKERS})"
                    )

                from concurrent.futures import ThreadPoolExecutor, as_completed
                done_letters = 0
                all_failures: list[dict] = []  # [{name, url, error}]
                with ThreadPoolExecutor(max_workers=LETTER_WORKERS) as letter_pool:
                    futures = {
                        letter_pool.submit(
                            process_letter_incremental,
                            letter, existing_index, summary_dict,
                            None, FIGHTER_WORKERS,
                        ): letter
                        for letter in target
                    }
                    for fut in as_completed(futures):
                        letter = futures[fut]
                        try:
                            new_f, updated_f, _, fails = fut.result()
                            all_payload.extend(new_f)
                            all_payload.extend(updated_f)
                            all_failures.extend(fails)
                            done_letters += 1
                            with _lock:
                                _state["step"] = (
                                    f"letter '{letter}' done "
                                    f"({done_letters}/{len(target)}) · "
                                    f"+{len(new_f)} new, +{len(updated_f)} updated, "
                                    f"{len(fails)} failed"
                                )
                        except Exception as e:
                            logger.exception("letter %s failed: %s", letter, e)
                            all_failures.append({"name": f"<letter:{letter}>", "url": "", "error": str(e)})
                            with _lock:
                                _state["step"] = f"letter '{letter}' failed: {e!r}"

                with _lock:
                    _state["step"] = f"ingesting {len(all_payload)} fighters"
                counts = ingest_fighters_payload(db, all_payload)

                # ── 2. Compute event names touched ─────────────────────
                # Tapology hook receives a list of event names that may need
                # community picks. We collect every event referenced by the
                # newly ingested fighters' fight histories.
                event_names: set[str] = set()
                for fighter in all_payload:
                    for fight in fighter.get("fights", []):
                        ev = fight.get("event")
                        if ev:
                            event_names.add(ev)

                # ── 3. Tapology hook (best-effort) ─────────────────────
                tap_summary: dict | None = None
                if event_names:
                    with _lock:
                        _state["step"] = f"tapology hook for {len(event_names)} events"
                    try:
                        import asyncio
                        from ufc_core.tapology import tapology_hook_for_event_names
                        tap_summary = asyncio.run(
                            tapology_hook_for_event_names(event_names)
                        )
                        logger.info("tapology hook summary: %s", tap_summary)
                    except Exception as tap_exc:
                        logger.exception("tapology hook failed (non-fatal)")
                        tap_summary = {"error": repr(tap_exc)}

                # ── 4. Materialize fight_features (v7) ─────────────────
                # Iterate only over events we just touched. For each, compute
                # features for all its fights and upsert into fight_features.
                feat_count = 0
                if event_names:
                    with _lock:
                        _state["step"] = "materializing fight_features (v7)"
                    try:
                        from ufc_core.data_loader import DataStoreDB
                        from ufc_core.features.engine import compute_features_for_fights
                        from ufc_core.features.store import upsert_fight_features
                        from ufc_core.tapology.picks_repo import build_picks_lookup_by_event_pair

                        ds = DataStoreDB()
                        ds.load()

                        picks_lookup = build_picks_lookup_by_event_pair(db)

                        for ev_name in event_names:
                            ev_row = (
                                db.query(db_models.Event).filter_by(name=ev_name).one_or_none()
                            )
                            if ev_row is None:
                                continue
                            fights = (
                                db.query(db_models.Fight)
                                  .filter_by(event_id=ev_row.id).all()
                            )
                            fight_inputs = []
                            fight_id_for_row: dict[tuple, int] = {}
                            for f in fights:
                                f1 = db.query(db_models.Fighter).filter_by(id=f.fighter_1_id).one()
                                f2 = db.query(db_models.Fighter).filter_by(id=f.fighter_2_id).one()
                                fight_inputs.append({
                                    "event": ev_name,
                                    "fighter_1": f1.name,
                                    "fighter_2": f2.name,
                                    "result": (
                                        1 if f.result == "win" else 0 if f.result == "loss" else None
                                    ),
                                    "odds_f1_american": f.odds_f1_american,
                                    "odds_f2_american": f.odds_f2_american,
                                })
                                fight_id_for_row[(ev_name, frozenset({f1.name, f2.name}))] = f.id

                            if not fight_inputs:
                                continue

                            df, _ = compute_features_for_fights(
                                fights=fight_inputs,
                                fighter_histories=ds.fighter_histories,
                                fighter_lookup=ds.fighter_lookup,
                                event_dates=ds.event_dates,
                                base_elo=1500.0,
                                event_date=ev_row.date,
                                before_event_date=ev_row.date,
                                tapology_picks_by_key=picks_lookup,
                            )

                            META = {"result", "event_date", "fighter_1", "fighter_2", "event"}
                            for _, row in df.iterrows():
                                key = (ev_name, frozenset({row.get("fighter_1"), row.get("fighter_2")}))
                                fid = fight_id_for_row.get(key)
                                if fid is None:
                                    continue
                                vec = {k: float(v) for k, v in row.items()
                                       if k not in META and isinstance(v, (int, float))
                                       and v == v}  # exclude NaN
                                upsert_fight_features(
                                    db, fid, "v7", vec, before_event_date=ev_row.date,
                                )
                                feat_count += 1
                        db.commit()
                    except Exception as feat_exc:
                        logger.exception("feature store materialization failed (non-fatal)")

                # ── 5. Audit row ───────────────────────────────────────
                # Serialize failures into error_msg as JSON so /runs can
                # show what didn't make it. Limit to 200 entries to keep
                # the audit row small.
                import json as _json
                if all_failures:
                    sample = all_failures[:200]
                    error_payload = _json.dumps({
                        "failed_count": len(all_failures),
                        "failed_sample": sample,
                    })
                else:
                    error_payload = None

                run = db_models.ScrapingRun(
                    source="ufcstats",
                    finished_at=datetime.now(UTC),
                    new_count=counts["fighters_new"],
                    updated_count=counts["fighters_updated"],
                    error_msg=error_payload,
                    recent_event_names=sorted(event_names) if event_names else None,
                )
                db.add(run); db.commit()

                with _lock:
                    _state.update({
                        "is_running": False,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": (
                            f"done · scraped={len(all_payload)} · events={len(event_names)} "
                            f"· tap={(tap_summary or {}).get('matched', 0)} "
                            f"· feats={feat_count} · failed={len(all_failures)}"
                        ),
                        "counts": {
                            **counts,
                            "events_touched": len(event_names),
                            "fight_features_upserted": feat_count,
                            "failed_count": len(all_failures),
                        },
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
