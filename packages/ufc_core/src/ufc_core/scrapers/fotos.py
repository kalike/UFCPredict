"""
UFC Predictor — Photos scraper.

Downloads headshot photos from ufc.com/athlete/{slug} for a list of
fighter names. Writes PNG files to `fotos_dir` named `{Sanitized_Name}.png`.

- Incremental: files already on disk (> 1KB) are skipped.
- Concurrent: ThreadPoolExecutor with configurable workers.
- Retries: 2 retries on network errors / timeouts with backoff.
- Resumable: progress written to `_progreso.json` every 50 downloads.

Adapted from the original stand-alone script in the `UFC - EDA` project.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.ufc.com/athlete/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 15
RETRY_LIMIT = 2
MIN_FILE_BYTES = 1000  # files smaller than this are considered invalid
MIN_IMG_BYTES = 500


def _name_to_slug(name: str) -> str:
    """Brandon Moreno -> brandon-moreno."""
    slug = name.strip().lower()
    slug = re.sub(r"[''`]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def sanitize_filename(name: str) -> str:
    """Brandon Moreno -> Brandon_Moreno.png."""
    safe = re.sub(r"[^A-Za-z0-9 _-]", "", name)
    return safe.replace(" ", "_") + ".png"


def _find_headshot_url(html: str) -> str | None:
    """Locate the headshot URL on an ufc.com/athlete/... page."""
    soup = BeautifulSoup(html, "html.parser")

    # Priority 1: athlete_bio_full_body (large image)
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "athlete_bio_full_body" in src:
            return src

    # Priority 2: athlete_headshot / event_results_athlete
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "athlete_headshot" in src or "event_results_athlete" in src:
            return src

    # Priority 3: any PNG under /images/styles/
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "/images/styles/" in src and src.endswith(".png"):
            return src

    return None


def _download_one(name: str, fotos_dir: Path) -> dict:
    """Download the headshot for a single fighter. Returns a result dict."""
    filename = sanitize_filename(name)
    filepath = fotos_dir / filename

    if filepath.exists() and filepath.stat().st_size > MIN_FILE_BYTES:
        return {"name": name, "status": "skip", "msg": "ya existe"}

    slug = _name_to_slug(name)
    url = BASE_URL + slug

    for attempt in range(RETRY_LIMIT + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 404:
                return {"name": name, "status": "not_found", "msg": f"404 {url}"}
            if resp.status_code == 403:
                time.sleep(2)
                continue
            resp.raise_for_status()

            img_url = _find_headshot_url(resp.text)
            if not img_url:
                return {"name": name, "status": "no_image", "msg": f"sin <img> en {url}"}

            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif not img_url.startswith("http"):
                img_url = urljoin("https://ufc.com", img_url)

            img_resp = requests.get(img_url, headers=HEADERS, timeout=TIMEOUT)
            img_resp.raise_for_status()

            if len(img_resp.content) < MIN_IMG_BYTES:
                return {"name": name, "status": "tiny", "msg": f"imagen muy pequena ({len(img_resp.content)}b)"}

            filepath.write_bytes(img_resp.content)
            return {"name": name, "status": "ok", "msg": f"{len(img_resp.content):,}b -> {filename}"}

        except requests.exceptions.Timeout:
            if attempt < RETRY_LIMIT:
                time.sleep(1)
                continue
            return {"name": name, "status": "timeout", "msg": f"timeout tras {RETRY_LIMIT+1} intentos"}
        except requests.exceptions.RequestException as e:
            if attempt < RETRY_LIMIT:
                time.sleep(1)
                continue
            return {"name": name, "status": "error", "msg": str(e)[:100]}

    return {"name": name, "status": "error", "msg": "agotados reintentos"}


def download_missing_photos(
    names: list[str],
    fotos_dir: Path,
    log_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    max_workers: int = 5,
) -> dict:
    """Download missing photos for the given fighter names.

    Incremental: already-downloaded photos (> 1KB on disk) are skipped up-front.
    Writes `_progreso.json` in `fotos_dir` every 50 downloads for resumability.

    Parameters
    ----------
    names : list[str]
        Fighter names to try to fetch.
    fotos_dir : Path
        Target directory for PNG files.
    log_cb : callable[[str], None], optional
        Called with human-readable log lines (one per fighter result).
    progress_cb : callable[[int, int], None], optional
        Called with (done, total_pending) after each completion.
    max_workers : int
        Number of concurrent HTTP workers.

    Returns
    -------
    dict
        {total, pending, ok, skip, not_found, no_image, error, timeout, tiny}.
    """
    fotos_dir.mkdir(parents=True, exist_ok=True)
    progress_file = fotos_dir / "_progreso.json"

    unique = sorted(set(names))
    total = len(unique)

    # Skip already-downloaded files up-front (incremental).
    pending: list[str] = []
    skipped = 0
    for name in unique:
        fp = fotos_dir / sanitize_filename(name)
        if fp.exists() and fp.stat().st_size > MIN_FILE_BYTES:
            skipped += 1
        else:
            pending.append(name)

    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    _log(f"[INFO] {total} luchadores; {skipped} ya descargados, {len(pending)} pendientes")

    if not pending:
        return {"total": total, "pending": 0, "ok": 0, "skip": skipped,
                "not_found": 0, "no_image": 0, "error": 0, "timeout": 0, "tiny": 0}

    counters = {"ok": 0, "skip": skipped, "not_found": 0,
                "no_image": 0, "error": 0, "timeout": 0, "tiny": 0}
    results: list[dict] = []
    done = 0

    icon = {"ok": "OK", "skip": "SKIP", "not_found": "404",
            "no_image": "NO-IMG", "error": "ERR", "timeout": "TIMEOUT", "tiny": "TINY"}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_one, name, fotos_dir): name for name in pending}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = result["status"]
            counters[status] = counters.get(status, 0) + 1
            done += 1

            _log(f"  [{done}/{len(pending)}] {icon.get(status, '?'):7s} {result['name']:30s} {result['msg']}")
            if progress_cb:
                progress_cb(done, len(pending))

            if done % 50 == 0:
                try:
                    progress_file.write_text(json.dumps(results, indent=1), encoding="utf-8")
                except OSError:
                    pass

    try:
        progress_file.write_text(json.dumps(results, indent=1), encoding="utf-8")
    except OSError:
        pass

    return {"total": total, "pending": len(pending), **counters}
