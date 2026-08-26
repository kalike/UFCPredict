"""Scraping router — UFCStats incremental + Tapology hook, DB-only.

Replaces the legacy backend's file-based pipeline (fighters_all*.json + backups).
Writes directly to ufc_lab via ufc_core.db.ingest.
"""

import logging
import os
import threading
from datetime import date, datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_data_store, get_db

logger = logging.getLogger("lab-api.scraping")

router = APIRouter(prefix="/api/scraping", tags=["scraping"])

# Keep the in-memory log tail bounded so a long scrape can't grow without limit.
MAX_LOG_LINES = 400
# Photo download targets fighters who fought within the last N years.
PHOTOS_RECENCY_YEARS = 3

# Ordered pipeline phases surfaced to the UI stepper. These mirror the real
# lab-api flow (letter scrape → ingest → tapology → feature store), NOT the
# legacy backend's A–E file pipeline.
PIPELINE_PHASES = ["scraping", "ingest", "tapology", "features"]

# ─── Shared job state (single-tenant lab) ──────────────────
_lock = threading.Lock()
_state: dict = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "step": None,
    "phase": None,
    "progress_current": 0,
    "progress_total": 0,
    "log_lines": [],
    "counts": None,
    "error": None,
}


def _set(**kw) -> None:
    """Update the scrape state under the lock. Never call while holding _lock."""
    with _lock:
        _state.update(kw)


def _log(msg: str) -> None:
    """Append one line to the scrape log tail. Never call while holding _lock."""
    with _lock:
        lines: list[str] = _state["log_lines"]
        lines.append(msg)
        if len(lines) > MAX_LOG_LINES:
            del lines[: -MAX_LOG_LINES]

# ─── Photo job state (runs independently of the UFCStats scrape) ──────
_photo_lock = threading.Lock()
_photo_state: dict = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "step": None,
    "phase": None,
    "progress_current": 0,
    "progress_total": 0,
    "log_lines": [],
    "counts": None,
    "error": None,
}


def _photo_set(**kw) -> None:
    """Update the photo state under its lock. Never call while holding the lock."""
    with _photo_lock:
        _photo_state.update(kw)


def _photo_log(msg: str) -> None:
    """Append one line to the photo log tail. Never call while holding the lock."""
    with _photo_lock:
        lines: list[str] = _photo_state["log_lines"]
        lines.append(msg)
        if len(lines) > MAX_LOG_LINES:
            del lines[: -MAX_LOG_LINES]


def _recent_fighter_names(years: int) -> list[str]:
    """Fighter names with a fight within the last `years` years (per DataStore).

    Mirrors the ranking's activity filter: the long tail of retired fighters
    mostly 404s on ufc.com, so the photo backfill targets active faces only.
    """
    ds = get_data_store()
    cutoff = date.today() - timedelta(days=years * 365)
    names: list[str] = []
    for name, history in ds.fighter_histories.items():
        if not history:
            continue
        last_dt = ds.event_dates.get(history[0].get("event", ""))
        if last_dt is None:
            continue
        last_d = last_dt.date() if isinstance(last_dt, datetime) else last_dt
        if last_d >= cutoff:
            names.append(name)
    return sorted(names)


class StartResponse(BaseModel):
    started: bool
    message: str


class StatusResponse(BaseModel):
    is_running: bool
    started_at: str | None = None
    finished_at: str | None = None
    step: str | None = None
    phase: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    log_lines: list[str] = []
    counts: dict | None = None
    error: str | None = None


def _refresh_and_recalc_after_scrape(event_count: int) -> None:
    """Make freshly scraped events show up everywhere without a manual step.

    A scrape writes new events/results to the DB, but the API serves the
    dashboards from a cached DataStore singleton and cached summaries, and the
    default dashboard reads ``lab_recalc`` PredictionSession rows that only the
    recalculation creates. So after an ingest we:

      1. Drop the cached DataStore singleton, so the dashboards (which read it
         via ``Depends(get_data_store)``) rebuild fighters_raw/event_dates with
         the new data.
      2. Invalidate the aggregated + realworld_df dashboard caches.
      3. Kick off a RealWorld-window recalculation so ``lab_recalc`` sessions
         exist for the new events (skipped if one is already running).

    Best-effort: callers wrap this so a failure never breaks the scrape.
    """
    from lab_api.deps import get_data_store
    from lab_api.services import dashboard as dsvc
    from lab_api.services import dashboard_realworld as rwsvc
    from lab_api.services import recalculation as recalc_svc

    get_data_store.cache_clear()
    dsvc.invalidate()
    rwsvc.invalidate()
    if not recalc_svc.get_status()["is_running"]:
        recalc_svc.start_recalculation(None)


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
            "phase": None, "progress_current": 0, "progress_total": 0,
            "log_lines": [], "counts": None, "error": None,
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

                # Crash-recovery dump: every scraped fighter is appended here
                # the moment its letter finishes, BEFORE ingest. If an ingest
                # fails, the payload survives on disk and /reingest can replay
                # it without touching the network. Deleted on full success.
                import json as _json
                from ufc_core.config import SCRAPE_DUMPS_DIR
                SCRAPE_DUMPS_DIR.mkdir(parents=True, exist_ok=True)
                dump_path = (
                    SCRAPE_DUMPS_DIR
                    / f"ufcstats_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.jsonl"
                )
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

                _set(
                    phase="scraping",
                    progress_current=0,
                    progress_total=len(target),
                    step=(
                        f"scraping {len(target)} letters × {FIGHTER_WORKERS} fighter workers"
                        f" (letter pool={LETTER_WORKERS})"
                    ),
                )
                _log(
                    f"[INFO] scraping {len(target)} letters "
                    f"({FIGHTER_WORKERS} fighter workers, letter pool={LETTER_WORKERS})"
                )

                from concurrent.futures import ThreadPoolExecutor, as_completed
                done_letters = 0
                all_failures: list[dict] = []  # [{name, url, error}]
                # Per-letter ingest: each letter commits on its own, so a
                # failure in one letter never rolls back the others (nor
                # forces a full re-scrape — the incremental index will skip
                # whatever was committed). Totals accumulate across letters.
                counts = {
                    "fighters_new": 0, "fighters_updated": 0,
                    "events_new": 0, "fights_new": 0, "fights_updated": 0,
                }
                ingest_failed_letters: list[str] = []
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
                            _set(
                                progress_current=done_letters,
                                step=(
                                    f"letter '{letter}' done "
                                    f"({done_letters}/{len(target)}) · "
                                    f"+{len(new_f)} new, +{len(updated_f)} updated, "
                                    f"{len(fails)} failed"
                                ),
                            )
                            _log(
                                f"[OK] letter '{letter}' ({done_letters}/{len(target)}): "
                                f"+{len(new_f)} new, +{len(updated_f)} updated, "
                                f"{len(fails)} failed"
                            )

                            letter_payload = new_f + updated_f
                            if not letter_payload:
                                continue

                            # 1. Persist the raw payload BEFORE ingesting it.
                            with open(dump_path, "a", encoding="utf-8") as fh:
                                for fighter_dict in letter_payload:
                                    fh.write(
                                        _json.dumps(fighter_dict, ensure_ascii=False,
                                                    default=str) + "\n"
                                    )

                            # 2. Ingest this letter in its own transaction.
                            try:
                                letter_counts = ingest_fighters_payload(db, letter_payload)
                                for k in counts:
                                    counts[k] += letter_counts.get(k, 0)
                                _log(
                                    f"[OK] ingest '{letter}': "
                                    f"+{letter_counts['fighters_new']} new, "
                                    f"+{letter_counts['fighters_updated']} updated"
                                )
                            except Exception as ing_exc:
                                db.rollback()
                                ingest_failed_letters.append(letter)
                                logger.exception("ingest for letter %s failed", letter)
                                _log(f"[ERROR] ingest '{letter}' failed: {ing_exc!r}")
                        except Exception as e:
                            logger.exception("letter %s failed: %s", letter, e)
                            all_failures.append({"name": f"<letter:{letter}>", "url": "", "error": str(e)})
                            done_letters += 1
                            _set(progress_current=done_letters, step=f"letter '{letter}' failed: {e!r}")
                            _log(f"[ERROR] letter '{letter}' failed: {e!r}")

                _set(
                    phase="ingest",
                    step=(
                        f"ingest done: +{counts['fighters_new']} new, "
                        f"+{counts['fighters_updated']} updated"
                    ),
                )
                _log(
                    f"[OK] ingest done: +{counts['fighters_new']} new, "
                    f"+{counts['fighters_updated']} updated"
                )
                if ingest_failed_letters:
                    _log(
                        f"[WARN] ingest failed for letters "
                        f"{','.join(sorted(ingest_failed_letters))} — raw payload kept at "
                        f"{dump_path}; fix the cause and POST /api/scraping/reingest"
                    )
                elif dump_path.exists():
                    # Everything ingested and committed: the crash-recovery
                    # dump has served its purpose.
                    dump_path.unlink()

                # ── 2. Compute event names touched ─────────────────────
                # Events referenced by the newly ingested fighters' fight
                # histories. Used to scope feature materialization (step 4)
                # and the post-scrape recalc (step 6).
                event_names: set[str] = set()
                for fighter in all_payload:
                    for fight in fighter.get("fights", []):
                        ev = fight.get("event")
                        if ev:
                            event_names.add(ev)

                # ── 3. Tapology hook (best-effort) ─────────────────────
                # Always runs, even when this pass ingested nothing new: the
                # hook selects pending events from the DB itself (the whole
                # RealWorld window without final picks), so gating it on
                # event_names would leave events from earlier runs without
                # picks forever if the hook failed back then (e.g. Playwright
                # browsers missing). This also makes an initial load backfill
                # picks+odds for every RealWorld event automatically.
                tap_summary: dict | None = None
                _set(phase="tapology", step="tapology hook (events pending picks)")
                _log("[INFO] tapology hook: checking DB for events pending picks")
                try:
                    import asyncio
                    from ufc_core.tapology import tapology_hook_for_event_names

                    def _tap_progress(done: int, total: int, msg: str) -> None:
                        _set(progress_current=done, progress_total=total,
                             step=f"tapology {done}/{total}: {msg}")
                        _log(f"[INFO] tapology {done}/{total}: {msg}")

                    tap_summary = asyncio.run(
                        tapology_hook_for_event_names(
                            event_names, progress_cb=_tap_progress
                        )
                    )
                    logger.info("tapology hook summary: %s", tap_summary)
                    _log(
                        f"[OK] tapology: "
                        f"resolved={tap_summary.get('events_resolved', 0)} "
                        f"picks={tap_summary.get('picks_inserted', 0)} "
                        f"unresolved={tap_summary.get('unresolved', 0)} "
                        f"skipped={tap_summary.get('skipped_recent', 0)} "
                        f"failures={tap_summary.get('event_failures', 0)}"
                    )
                except Exception as tap_exc:
                    logger.exception("tapology hook failed (non-fatal)")
                    tap_summary = {"error": repr(tap_exc)}
                    _log(f"[WARN] tapology hook failed (non-fatal): {tap_exc!r}")

                # ── 4. Materialize fight_features (v7) ─────────────────
                # Iterate only over events we just touched. For each, compute
                # features for all its fights and upsert into fight_features.
                feat_count = 0
                if event_names:
                    _set(phase="features", step="materializing fight_features (v7)")
                    _log(f"[INFO] materializing fight_features (v7) for {len(event_names)} events")
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
                        _log(f"[OK] fight_features (v7): {feat_count} rows upserted")
                    except Exception as feat_exc:
                        logger.exception("feature store materialization failed (non-fatal)")
                        _log(f"[WARN] feature store materialization failed (non-fatal): {feat_exc!r}")

                # ── 4.5 Fighter photos (best-effort, incremental) ──────
                # Download missing headshots for the fighters touched this run.
                # download_missing_photos skips files already on disk, so this
                # is cheap on repeat runs and only fetches genuinely new faces.
                photo_summary: dict | None = None
                scraped_names = [f["name"] for f in all_payload if f.get("name")]
                if scraped_names:
                    _set(step=f"downloading photos for {len(scraped_names)} fighters")
                    _log(f"[INFO] downloading photos for {len(scraped_names)} fighters")
                    try:
                        from ufc_core.config import FOTOS_DIR
                        from ufc_core.scrapers.fotos import download_missing_photos
                        photo_summary = download_missing_photos(scraped_names, FOTOS_DIR)
                        logger.info("photo summary: %s", photo_summary)
                        _log(
                            f"[OK] photos: ok={photo_summary.get('ok', 0)} "
                            f"skip={photo_summary.get('skip', 0)} "
                            f"404={photo_summary.get('not_found', 0)}"
                        )
                    except Exception as photo_exc:
                        logger.exception("photo download failed (non-fatal)")
                        photo_summary = {"error": repr(photo_exc)}
                        _log(f"[WARN] photo download failed (non-fatal): {photo_exc!r}")

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

                # ── 6. Refresh caches + kick off RealWorld recalc ──────
                # New events are invisible in the dashboard until the cached
                # DataStore/summaries are dropped and a recalc creates their
                # lab_recalc sessions. Best-effort: never fail the scrape here.
                if event_names:
                    try:
                        _set(step="refreshing caches + recalculating RealWorld")
                        _refresh_and_recalc_after_scrape(len(event_names))
                        _log("[OK] caches refreshed + RealWorld recalc triggered")
                    except Exception as rc_exc:
                        logger.exception("post-scrape refresh/recalc failed (non-fatal)")
                        _log(f"[WARN] post-scrape refresh/recalc failed (non-fatal): {rc_exc!r}")

                _log(
                    f"[OK] done · scraped={len(all_payload)} · events={len(event_names)} "
                    f"· tap={(tap_summary or {}).get('picks_inserted', 0)} · feats={feat_count} "
                    f"· photos={(photo_summary or {}).get('ok', 0)} · failed={len(all_failures)}"
                )
                with _lock:
                    _state.update({
                        "is_running": False,
                        "phase": "done",
                        "finished_at": datetime.now(UTC).isoformat(),
                        "step": (
                            f"done · scraped={len(all_payload)} · events={len(event_names)} "
                            f"· tap={(tap_summary or {}).get('picks_inserted', 0)} "
                            f"· feats={feat_count} · photos={(photo_summary or {}).get('ok', 0)} "
                            f"· failed={len(all_failures)}"
                        ),
                        "counts": {
                            **counts,
                            "events_touched": len(event_names),
                            "fight_features_upserted": feat_count,
                            "photos_downloaded": (photo_summary or {}).get("ok", 0),
                            "failed_count": len(all_failures),
                            "ingest_failed_letters": sorted(ingest_failed_letters),
                        },
                        "error": (
                            f"ingest failed for letters "
                            f"{','.join(sorted(ingest_failed_letters))} — payload kept at "
                            f"{dump_path}; POST /api/scraping/reingest to replay"
                            if ingest_failed_letters else None
                        ),
                    })
            finally:
                db.close()
        except Exception as e:
            logger.exception("scrape job failed")
            _log(f"[ERROR] scrape job failed: {e!r}")
            dp = locals().get("dump_path")
            if dp is not None and dp.exists():
                _log(
                    f"[INFO] raw scraped payload kept at {dp} — "
                    f"POST /api/scraping/reingest to replay it without re-scraping"
                )
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


@router.post("/reingest", response_model=StartResponse)
def start_reingest(path: str | None = None) -> StartResponse:
    """Replay a raw scrape dump into the DB without touching the network.

    Every scrape run appends its scraped fighters to a .jsonl dump under
    SCRAPE_DUMPS_DIR before ingesting them, and deletes it on full success.
    If an ingest failed, this endpoint re-ingests the surviving dump — the
    newest one by default, or the one named by `path` (a filename inside
    SCRAPE_DUMPS_DIR). Ingest is idempotent, so fighters that already made it
    into the DB are simply updated. The dump is deleted once fully replayed.
    """
    from pathlib import Path

    from ufc_core.config import SCRAPE_DUMPS_DIR

    if path:
        # Restrict to files inside the dumps dir: `path` is a filename, not a
        # free-form filesystem path.
        dump = (SCRAPE_DUMPS_DIR / Path(path).name).resolve()
    else:
        dumps = (
            sorted(SCRAPE_DUMPS_DIR.glob("*.jsonl"))
            if SCRAPE_DUMPS_DIR.exists() else []
        )
        dump = dumps[-1] if dumps else None
    if dump is None or not dump.is_file():
        raise HTTPException(404, "No scrape dump found to reingest")

    with _lock:
        if _state["is_running"]:
            raise HTTPException(409, "A scrape is already running")
        _state.update({
            "is_running": True,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None, "step": f"reingesting {dump.name}",
            "phase": "ingest", "progress_current": 0, "progress_total": 0,
            "log_lines": [], "counts": None, "error": None,
        })

    def _job():
        import json as _json
        from ufc_core.db.engine import SessionLocal
        from ufc_core.db.ingest import ingest_fighters_payload

        try:
            payload: list[dict] = []
            with open(dump, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        payload.append(_json.loads(line))

            _set(progress_total=len(payload))
            _log(f"[INFO] reingesting {len(payload)} fighters from {dump}")

            counts = {
                "fighters_new": 0, "fighters_updated": 0,
                "events_new": 0, "fights_new": 0, "fights_updated": 0,
            }
            # Batches bound the transaction size; each ingest call commits, so
            # the incremental progress survives a mid-run failure.
            BATCH = 500
            db: Session = SessionLocal()
            try:
                for i in range(0, len(payload), BATCH):
                    batch_counts = ingest_fighters_payload(db, payload[i:i + BATCH])
                    for k in counts:
                        counts[k] += batch_counts.get(k, 0)
                    done = min(i + BATCH, len(payload))
                    _set(progress_current=done,
                         step=f"reingested {done}/{len(payload)} fighters")
                    _log(f"[OK] reingested {done}/{len(payload)}")

                run = db_models.ScrapingRun(
                    source="reingest",
                    finished_at=datetime.now(UTC),
                    new_count=counts["fighters_new"],
                    updated_count=counts["fighters_updated"],
                    error_msg=None,
                )
                db.add(run); db.commit()
            finally:
                db.close()

            dump.unlink(missing_ok=True)

            try:
                _set(step="refreshing caches + recalculating RealWorld")
                _refresh_and_recalc_after_scrape(0)
                _log("[OK] caches refreshed + RealWorld recalc triggered")
            except Exception as rc_exc:
                logger.exception("post-reingest refresh/recalc failed (non-fatal)")
                _log(f"[WARN] post-reingest refresh failed (non-fatal): {rc_exc!r}")

            _log(
                f"[OK] reingest done: +{counts['fighters_new']} new, "
                f"+{counts['fighters_updated']} updated"
            )
            with _lock:
                _state.update({
                    "is_running": False,
                    "phase": "done",
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": (
                        f"reingest done: +{counts['fighters_new']} new, "
                        f"+{counts['fighters_updated']} updated"
                    ),
                    "counts": counts,
                })
        except Exception as e:
            logger.exception("reingest job failed")
            _log(f"[ERROR] reingest job failed: {e!r} — dump kept at {dump}")
            with _lock:
                _state.update({
                    "is_running": False,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "step": "failed", "error": repr(e),
                })

    threading.Thread(target=_job, daemon=True).start()
    return StartResponse(started=True, message=f"Reingest of {dump.name} kicked off")


@router.post("/photos", response_model=StartResponse)
def start_photo_scrape(
    limit: int | None = None,
    recent_only: bool = True,
    db: Session = Depends(get_db),
) -> StartResponse:
    """Backfill missing fighter headshots into FOTOS_DIR (best-effort, async).

    download_missing_photos is incremental (skips PNGs already on disk), so
    repeat runs are cheap. By default only fighters who fought within the last
    PHOTOS_RECENCY_YEARS years are targeted — the long tail of retired fighters
    mostly 404s on ufc.com and isn't worth hammering. Pass `recent_only=false`
    to attempt every fighter, or `limit` to cap the count for a quick smoke run.
    """
    with _photo_lock:
        if _photo_state["is_running"]:
            raise HTTPException(409, "A photo download is already running")
        _photo_state.update({
            "is_running": True,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None, "step": "starting",
            "phase": "photos", "progress_current": 0, "progress_total": 0,
            "log_lines": [], "counts": None, "error": None,
        })

    if recent_only:
        names = _recent_fighter_names(PHOTOS_RECENCY_YEARS)
    else:
        names = [
            n for (n,) in
            db.query(db_models.Fighter.name).order_by(db_models.Fighter.name).all()
        ]
    if limit:
        names = names[:limit]
    scope = f"last {PHOTOS_RECENCY_YEARS}y" if recent_only else "all fighters"
    _photo_log(f"[INFO] {len(names)} fighters considered ({scope}, incremental)")

    def _job():
        from ufc_core.config import FOTOS_DIR
        from ufc_core.db.engine import SessionLocal
        from ufc_core.scrapers.fotos import download_missing_photos

        try:
            def _progress(done: int, total: int) -> None:
                _photo_set(
                    step=f"downloading {done}/{total}",
                    progress_current=done,
                    progress_total=total,
                )

            summary = download_missing_photos(
                names, FOTOS_DIR, log_cb=_photo_log, progress_cb=_progress,
            )

            db2: Session = SessionLocal()
            try:
                run = db_models.ScrapingRun(
                    source="fotos",
                    finished_at=datetime.now(UTC),
                    new_count=summary.get("ok", 0),
                    updated_count=0,
                    error_msg=None,
                )
                db2.add(run); db2.commit()
            finally:
                db2.close()

            _photo_log(
                f"[OK] done · ok={summary.get('ok', 0)} · skip={summary.get('skip', 0)} "
                f"· 404={summary.get('not_found', 0)} · err={summary.get('error', 0)}"
            )
            _photo_set(
                is_running=False,
                finished_at=datetime.now(UTC).isoformat(),
                step=(
                    f"done · ok={summary.get('ok', 0)} · skip={summary.get('skip', 0)} "
                    f"· 404={summary.get('not_found', 0)} · err={summary.get('error', 0)}"
                ),
                counts=summary,
            )
        except Exception as e:
            logger.exception("photo download job failed")
            _photo_log(f"[ERROR] {e!r}")
            _photo_set(
                is_running=False,
                finished_at=datetime.now(UTC).isoformat(),
                step="failed", error=repr(e),
            )

    threading.Thread(target=_job, daemon=True).start()
    return StartResponse(
        started=True,
        message=f"Photo download kicked off for {len(names)} fighters",
    )


@router.get("/photos/status", response_model=StatusResponse)
def photo_status() -> StatusResponse:
    with _photo_lock:
        snap = dict(_photo_state)
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
