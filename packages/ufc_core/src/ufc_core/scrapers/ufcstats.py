"""
UFC Stats Scraper — Incremental mode (ufc_core edition).

Compares an in-memory fighter list (provided by the caller from DB) against
UFCStats.com. Only re-scrapes fighters whose record changed or who are new.
Returns an in-memory payload dict instead of writing JSON files; persistence
is the caller's responsibility (T11 ingest).
"""

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# -------------------------------
# CONFIGURACIÓN
# -------------------------------
BASE_URL = "http://ufcstats.com/statistics/fighters"
LETTERS = [chr(i) for i in range(ord("a"), ord("z") + 1)]
MAX_WORKERS = 8

log_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────
# LOGGING  (callback-aware: si se inyecta cb se usa, si no → print)
# ──────────────────────────────────────────────────────────────────────
_log_cb: Callable[[str], None] | None = None
_log_file: str | None = None


def set_log_callback(cb: Callable[[str], None] | None):
    global _log_cb
    _log_cb = cb


def set_log_file(path: str | None):
    global _log_file
    _log_file = path


def log(message: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full = f"[{timestamp}] {message}"
    if _log_cb:
        _log_cb(full)
    else:
        print(full)
    if _log_file:
        with log_lock:
            with open(_log_file, "a", encoding="utf-8") as f:
                f.write(full + "\n")


# ──────────────────────────────────────────────────────────────────────
# UTILIDADES DE SCRAPING  (unchanged from original)
# ──────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────
# ANTI-BOT CHALLENGE (proof-of-work interstitial)
# ──────────────────────────────────────────────────────────────────────
# UFCStats fronts pages with a JS interstitial ("Checking your browser…")
# that computes sha256(nonce + ':' + n) until the hex digest starts with N
# leading zeros, then POSTs {nonce, n} to /__c to obtain a session cookie
# (`_fmc`). requests cannot run JS, so we solve the PoW ourselves and reuse a
# shared Session so the cookie is sent on every subsequent request.
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
})
_challenge_lock = threading.Lock()

_RE_CH_NONCE = re.compile(r'nonce\s*=\s*"([0-9a-fA-F]+)"')
_RE_CH_ZEROS = re.compile(r"new Array\((\d+)\+1\)\.join\('0'\)")
_RE_CH_POST = re.compile(r"\.open\(\s*'POST'\s*,\s*\"([^\"]+)\"")


def _extract_challenge(html: str) -> tuple[str, int, str] | None:
    """Return (nonce, leading_zeros, post_path) if html is the PoW interstitial.

    Returns None for a normal page. Detection requires the interstitial marker
    plus all three parseable fields, so a real fighters page never matches.
    """
    if "Checking your browser" not in html:
        return None
    n = _RE_CH_NONCE.search(html)
    z = _RE_CH_ZEROS.search(html)
    p = _RE_CH_POST.search(html)
    if n and z and p:
        return n.group(1), int(z.group(1)), p.group(1)
    return None


def _solve_pow(nonce: str, zeros: int) -> int:
    """Smallest n such that sha256(f'{nonce}:{n}') has `zeros` leading hex zeros."""
    target = "0" * zeros
    n = 0
    while not hashlib.sha256(f"{nonce}:{n}".encode()).hexdigest().startswith(target):
        n += 1
    return n


def _pass_challenge(challenge: tuple[str, int, str], page_url: str) -> None:
    """Solve the PoW and POST it so the shared session gets the access cookie."""
    from urllib.parse import urljoin
    nonce, zeros, post_path = challenge
    with _challenge_lock:
        n = _solve_pow(nonce, zeros)
        log(f"  🧩 solved UFCStats PoW challenge (zeros={zeros}, n={n})")
        _session.post(
            urljoin(page_url, post_path),
            data={"nonce": nonce, "n": n},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )


def get_soup(url, max_retries: int = 5, base_backoff: float = 2.0):
    """GET + parse with retry/backoff for 429/5xx, and the PoW anti-bot challenge.

    Backs off exponentially: base * 2**attempt + small jitter. When the response
    is the anti-bot interstitial, solve the proof-of-work, submit it, and retry
    the same URL (now with the session cookie) — this counts as an attempt.
    """
    import random
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = _session.get(url, timeout=20)
            if response.status_code == 429:
                # Honour Retry-After header when present, else exponential backoff
                ra = response.headers.get("Retry-After")
                try:
                    wait = float(ra) if ra else base_backoff * (2 ** attempt)
                except ValueError:
                    wait = base_backoff * (2 ** attempt)
                wait += random.uniform(0.0, 1.5)
                log(f"  ⏳ 429 received, sleeping {wait:.1f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            if 500 <= response.status_code < 600:
                wait = base_backoff * (2 ** attempt) + random.uniform(0.0, 1.0)
                log(f"  ⏳ {response.status_code} received, sleeping {wait:.1f}s")
                time.sleep(wait)
                continue
            response.raise_for_status()
            challenge = _extract_challenge(response.text)
            if challenge is not None:
                _pass_challenge(challenge, response.url)
                continue  # retry the GET with the access cookie now set
            return BeautifulSoup(response.text, "html.parser")
        except requests.exceptions.RequestException as e:
            last_exc = e
            wait = base_backoff * (2 ** attempt) + random.uniform(0.0, 1.0)
            time.sleep(wait)
    # All retries exhausted
    raise last_exc if last_exc is not None else RuntimeError(f"Failed to fetch {url}")


def parse_table(table):
    headers = [th.text.strip() for th in table.find_all("th")]
    rows = []
    for row in table.find_all("tr")[1:]:
        cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if cols:
            rows.append(dict(zip(headers, cols, strict=False)))
    return rows


def parse_fight_details(fight_url):
    soup = get_soup(fight_url)
    details = {}
    header = soup.find(string=lambda x: x and "Method:" in x)  # type: ignore
    if header:
        parts = header.strip().split("Referee:")
        details["method_info"] = parts[0].strip()
        details["referee"] = parts[1].strip() if len(parts) > 1 else ""

    tables = {"totals": [], "per_round": [], "significant_strikes": [], "sig_strikes_per_round": []}
    all_tables = soup.find_all("table")
    if len(all_tables) >= 4:
        tables["totals"] = parse_table(all_tables[0])
        tables["per_round"] = parse_table(all_tables[1])
        tables["significant_strikes"] = parse_table(all_tables[2])
        tables["sig_strikes_per_round"] = parse_table(all_tables[3])
    elif len(all_tables) > 0:
        keys = list(tables.keys())
        for i, table in enumerate(all_tables):
            tables[keys[i]] = parse_table(table)
    details["tables"] = tables
    return details


def _parse_event_cell(cell) -> tuple[str, str | None]:
    """
    Extract event name and date from UFCStats fighter-history "EVENT" cell.

    The cell contains two <p> tags: first = event name (inside an <a>), second = date
    (e.g. "Aug. 01, 2017"). Returns (event_name, iso_date_or_none). Falls back to the
    raw cell text if structure is unexpected.
    """
    paragraphs = cell.find_all("p")
    if len(paragraphs) >= 2:
        event_name = paragraphs[0].get_text(" ", strip=True)
        date_raw = paragraphs[1].get_text(" ", strip=True)
    else:
        event_name = cell.get_text(" ", strip=True)
        date_raw = ""

    iso_date: str | None = None
    if date_raw:
        for fmt in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                iso_date = datetime.strptime(date_raw, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        if iso_date is None:
            log(f"  ⚠️ Unparseable event date '{date_raw}' for event '{event_name}'")
            iso_date = date_raw  # keep raw as fallback
    return event_name, iso_date


def _opponent_from_cell(cell, owner_url: str) -> tuple[str, str | None]:
    """Return (opponent_name, opponent_url) from the 'Fighter' cell.

    The cell links BOTH fighters of the bout; the opponent is the fighter-details
    anchor whose href is not the page owner's. We take the name from that anchor
    rather than cell.text — the latter concatenates owner + opponent (with
    whitespace), which corrupts the display name. Falls back to the raw cell text
    when no opponent anchor exists (opponent has no UFCStats page).
    """
    for a in cell.find_all("a"):
        href = (a.get("href") or "").strip()
        if "fighter-details/" in href and href != owner_url:
            return a.get_text(strip=True), href
    return cell.get_text(" ", strip=True), None


def _opponent_url_from_cell(cell, owner_url: str) -> str | None:
    """Opponent's UFCStats fighter-details URL, or None. See _opponent_from_cell."""
    return _opponent_from_cell(cell, owner_url)[1]


def parse_fighter_page(fighter_url: str) -> dict:
    soup = get_soup(fighter_url)
    name_el = soup.find("span", class_="b-content__title-highlight")
    record_el = soup.find("span", class_="b-content__title-record")

    name = name_el.text.strip() if name_el else "N/A"
    record = record_el.text.strip() if record_el else "N/A"

    stats = {}
    info_section = soup.find_all(
        "li", class_="b-list__box-list-item b-list__box-list-item_type_block"
    )
    for li in info_section:
        if ":" in li.text:
            k, v = li.text.split(":", 1)
            stats[k.strip()] = v.strip()

    fights = []
    fight_rows = soup.find_all("tr")[1:]
    for row in fight_rows:
        cols = row.find_all("td")
        if not cols or len(cols) < 7:
            continue
        fight_url_cell = cols[0].find("a")
        if not fight_url_cell:
            continue
        fight_href = fight_url_cell["href"]
        if not fight_href:
            continue
        label = cols[0].text.strip().lower()
        if "next" in label or "preview" in label or "matchup" in label:
            continue

        event_name, event_date = _parse_event_cell(cols[6])
        opp_name, opp_url = _opponent_from_cell(cols[1], fighter_url)
        fight_data = {
            "result": cols[0].text.strip(),
            "opponent": opp_name,
            "opponent_url": opp_url,
            "event": event_name,
            "event_date": event_date,
            "method": cols[7].text.strip(),
            "round": cols[8].text.strip(),
            "time": cols[9].text.strip(),
            "fight_url": fight_href,
        }
        try:
            fight_data["details"] = parse_fight_details(fight_href)
        except Exception as e:
            fight_data["error"] = str(e)
        fights.append(fight_data)

    return {
        "name": name,
        "record": record,
        "stats": stats,
        "url": fighter_url,
        "fights": fights,
        "num_fights": len(fights),
    }


# ──────────────────────────────────────────────────────────────────────
# INDEX de peleadores existentes (para modo incremental)
# ──────────────────────────────────────────────────────────────────────
def build_existing_index(existing_json_path: str | Path) -> dict[str, str]:
    """Return {url: record} for every fighter in the existing JSON.

    Keyed by ``url`` (UFCStats fighter-details URL — globally unique) instead
    of ``name``, because UFCStats has homonymous fighters (e.g. multiple
    "Mike Davis", "Bruno Silva") that collide on name. With name-keyed
    lookup, the index would silently overwrite one with the other and the
    incremental scraper would flip-flop the JSON between two records on
    every run, plus accumulate duplicate entries.
    """
    path = Path(existing_json_path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    index: dict[str, str] = {}
    for fighter in data:
        url = fighter.get("url")
        if not url:
            # Legacy entries without URL: fall back to name. They will be
            # rewritten with URL on the next successful scrape.
            url = f"name:{fighter.get('name','')}"
        index[url] = fighter.get("record", "")
    return index


def load_existing_fighters(existing_json_path: str | Path) -> list[dict]:
    """Load full fighter list from existing JSON, deduplicated by URL.

    Past versions of the incremental scraper had keying bugs that caused
    duplicate entries (same URL, same record) to accumulate. We dedupe at
    load time so a single run also self-heals the file.
    """
    path = Path(existing_json_path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    seen: set[str] = set()
    deduped: list[dict] = []
    for fighter in data:
        key = fighter.get("url") or f"name:{fighter.get('name','')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fighter)
    return deduped


# ──────────────────────────────────────────────────────────────────────
# PROCESAMIENTO INCREMENTAL POR LETRA
# ──────────────────────────────────────────────────────────────────────
def process_letter_incremental(
    letter: str,
    existing_index: dict[str, str],
    summary_dict: dict,
    progress_cb: Callable[[str, int, int], None] | None = None,
    fighter_workers: int = 1,
):
    """
    Scrape a single letter page.  For each fighter:
    - If name+record match existing → skip
    - Otherwise → full scrape of that fighter

    Args:
        fighter_workers: if > 1, parses fighter pages in parallel using a
            ThreadPoolExecutor. Default 1 = sequential (back-compat).
            Be conservative — UFCStats may rate-limit on bursts.

    Returns (new_fighters, updated_fighters, skipped_count)
    """
    start = time.time()
    url = f"{BASE_URL}?char={letter}&page=all"
    soup = get_soup(url)

    all_rows = soup.find_all("tr")[2:]
    new_fighters: list[dict] = []
    updated_fighters: list[dict] = []
    skipped = 0

    # Phase 1: scan index, decide per-row action (skip or fetch URL)
    to_fetch: list[tuple[int, str, str, str | None]] = []  # (idx, fighter_url, fighter_name, existing_record)
    for idx, row in enumerate(all_rows, 1):
        cols = row.find_all("td")
        if not cols or not cols[0].find("a"):
            continue
        fighter_url = cols[0].find("a")["href"]  # type: ignore
        # Single-name fighters (e.g. Kaiwen, Mizuki) have an empty first-name
        # column. Concatenating with a literal space would produce " Kaiwen",
        # which then never matches the JSON entry stored as "Kaiwen", causing
        # the same fighter to be flagged NUEVO on every incremental run.
        fighter_name = " ".join(
            (cols[0].text.strip() + " " + cols[1].text.strip()).split()
        )

        # Record built from W/L/D columns (7, 8, 9) of the UFCStats fighter index.
        if len(cols) >= 10:
            w = cols[7].text.strip()
            l = cols[8].text.strip()
            d = cols[9].text.strip()
            web_record = f"{w}-{l}-{d}"
        else:
            web_record = ""

        existing_record = existing_index.get(fighter_url)
        if existing_record is None:
            existing_record = existing_index.get(f"name:{fighter_name}")

        if existing_record is not None and _normalise_record(existing_record) == _normalise_record(
            web_record
        ):
            skipped += 1
            if progress_cb:
                progress_cb(letter, idx, len(all_rows))
            continue

        to_fetch.append((idx, fighter_url, fighter_name, existing_record))

    failures: list[dict] = []  # [{"name", "url", "error"}]

    # Phase 2: fetch fighter pages (parallel if fighter_workers > 1)
    def _do_one(item: tuple[int, str, str, str | None]):
        idx, fighter_url, fighter_name, existing_record = item
        action = "NUEVO" if existing_record is None else "ACTUALIZADO"
        log(f"  [{letter.upper()} {idx}/{len(all_rows)}] {action}: {fighter_name}")
        try:
            fighter_data = parse_fighter_page(fighter_url)
            return ("new" if existing_record is None else "updated", fighter_data, None)
        except Exception as e:
            log(f"  ❌ Error {fighter_name}: {e}")
            return (None, None, {"name": fighter_name, "url": fighter_url, "error": str(e)})

    if fighter_workers > 1 and len(to_fetch) > 1:
        with ThreadPoolExecutor(max_workers=fighter_workers) as pool:
            futures = {pool.submit(_do_one, item): item for item in to_fetch}
            done = 0
            for fut in as_completed(futures):
                kind, data, fail = fut.result()
                done += 1
                if data is not None:
                    if kind == "new":
                        new_fighters.append(data)
                    else:
                        updated_fighters.append(data)
                elif fail is not None:
                    failures.append(fail)
                if progress_cb:
                    progress_cb(letter, done, len(to_fetch))
    else:
        for item in to_fetch:
            kind, data, fail = _do_one(item)
            if data is not None:
                if kind == "new":
                    new_fighters.append(data)
                else:
                    updated_fighters.append(data)
            elif fail is not None:
                failures.append(fail)
            if progress_cb:
                progress_cb(letter, item[0], len(all_rows))

    elapsed = round(time.time() - start, 2)
    summary_dict[letter] = {
        "total": len(all_rows),
        "new": len(new_fighters),
        "updated": len(updated_fighters),
        "skipped": skipped,
        "time_s": elapsed,
    }
    summary_dict[letter]["failed"] = len(failures)
    log(
        f"  🔠 {letter.upper()}: {len(all_rows)} total, {len(new_fighters)} nuevos, "
        f"{len(updated_fighters)} actualizados, {skipped} sin cambios, "
        f"{len(failures)} fallidos ({elapsed}s)"
    )
    return new_fighters, updated_fighters, skipped, failures


_RECORD_PATTERN = re.compile(r"(\d+)-(\d+)-(\d+)")


def _normalise_record(record: str) -> str:
    """Extract the W-L-D triplet from a record string.

    Handles formats like:
      - "7-1-0"                    (web index columns)
      - "Record: 7-1-0"            (older fighter pages)
      - "Record: 7-1-0 (1 NC)"     (with No Contest count)
      - "7-1-0 (2 NC)"             (without prefix but with NC)

    Returns the canonical "W-L-D" string or "" if no triplet found.
    The NC suffix is intentionally ignored: a No Contest re-classification
    is not a meaningful change to the win/loss/draw counts and triggering
    a full re-scrape for it is wasteful.
    """
    if not record:
        return ""
    m = _RECORD_PATTERN.search(record)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


# ──────────────────────────────────────────────────────────────────────
# MAIN INCREMENTAL
# ──────────────────────────────────────────────────────────────────────
def run_incremental_scrape(
    existing_json_path: str | Path,
    output_json_path: str | Path,
    log_file_path: str | Path | None = None,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
    max_workers: int = MAX_WORKERS,
) -> dict:
    """
    Run an incremental scrape.

    Args:
        existing_json_path: Path to current fighters_all.json (raw, not normalised)
        output_json_path:   Where to write the updated fighters_all.json
        log_file_path:      Optional file for logging
        log_callback:       Optional function(msg) for live log lines
        progress_callback:  Optional function(letter, current, total) for progress
        max_workers:        Thread pool size

    Returns:
        Summary dict with stats about the scrape.
    """
    set_log_callback(log_callback)
    set_log_file(str(log_file_path) if log_file_path else None)

    start_total = time.time()

    # 1. Build index of existing fighters
    log("📖 Cargando índice de peleadores existentes...")
    existing_index = build_existing_index(existing_json_path)
    existing_fighters = load_existing_fighters(existing_json_path)
    log(f"   {len(existing_index)} peleadores en el JSON actual")

    # 2. Scrape all letters (incremental)
    log(f"🚀 Iniciando scraping incremental ({max_workers} hilos)...")
    summary: dict = {}
    all_new: list[dict] = []
    all_updated: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_letter_incremental, letter, existing_index, summary, progress_callback
            ): letter
            for letter in LETTERS
        }
        for future in as_completed(futures):
            letter = futures[future]
            try:
                new_f, upd_f, _, _ = future.result()
                all_new.extend(new_f)
                all_updated.extend(upd_f)
            except Exception as e:
                log(f"⚠️ Error en letra {letter.upper()}: {e}")

    # 3. Merge: keyed by URL so we replace the right entry and never duplicate.
    # Updated fighters win over existing; new fighters are appended.
    updated_urls = {f.get("url") for f in all_updated if f.get("url")}
    merged = [f for f in existing_fighters if f.get("url") not in updated_urls]
    merged.extend(all_updated)

    # Final dedupe pass by URL just in case (defence-in-depth — historical
    # JSON files accumulated duplicates from earlier name-based logic).
    seen_urls: set[str] = set()
    deduped_merged: list[dict] = []
    for f in merged + all_new:
        key = f.get("url") or f"name:{f.get('name','')}"
        if key in seen_urls:
            continue
        seen_urls.add(key)
        deduped_merged.append(f)
    merged = deduped_merged

    # 4. Write consolidated output
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4, ensure_ascii=False)

    total_time = round(time.time() - start_total, 2)

    result = {
        "total_existing": len(existing_fighters),
        "total_new": len(all_new),
        "total_updated": len(all_updated),
        "total_after_merge": len(merged),
        "total_time_s": total_time,
        "output_path": str(output_path),
        "per_letter": summary,
    }

    log("=" * 60)
    log(f"📊 Resumen: {len(all_new)} nuevos, {len(all_updated)} actualizados, {len(merged)} total")
    log(f"🏁 Tiempo total: {total_time}s")
    log(f"📦 Guardado en: {output_path}")
    log("=" * 60)

    # Expose recent event names so callers (the API pipeline) can drive the
    # Tapology hook AFTER ingesting fights into the DB. The hook used to fire
    # here, but it can't match new events whose fights aren't in the DB yet.
    result["recent_event_names"] = sorted(
        _extract_recent_event_names(all_new + all_updated)
    )

    set_log_callback(None)
    set_log_file(None)
    return result


def _extract_recent_event_names(
    fighters: list[dict], days_window: int = 60
) -> set[str]:
    """Extract distinct event names from a fighter list, filtered to recent dates.

    Limits to events occurring in the last `days_window` days to avoid
    scraping the entire history of a fighter that just got updated.
    """
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(days=days_window)
    names: set[str] = set()
    for ftr in fighters:
        for fight in ftr.get("fights", []):
            ev_name = fight.get("event")
            ev_date_str = fight.get("date")
            if not ev_name:
                continue
            if ev_date_str:
                try:
                    ev_date = datetime.strptime(ev_date_str, "%b. %d, %Y")
                except ValueError:
                    try:
                        ev_date = datetime.strptime(ev_date_str, "%B %d, %Y")
                    except ValueError:
                        continue
                if ev_date < cutoff:
                    continue
            names.add(ev_name)
    return names


if __name__ == "__main__":
    # Default: incremental mode using existing raw data
    run_incremental_scrape(
        existing_json_path="fighters_dataXXXX/fighters_all.json",
        output_json_path="fighters_dataXXXX/fighters_all.json",
    )
