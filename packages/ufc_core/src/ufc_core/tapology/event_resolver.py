"""Resolve a DB event (name, date) to its Tapology event URL via search."""

import asyncio
import logging
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger("ufc-predictor.tapology-resolver")


class TapologyBlockedError(Exception):
    """Tapology returned an empty/Cloudflare-challenge response."""


_EVENT_HREF = re.compile(r"^/fightcenter/events/")
_LISTING_DATE = re.compile(r"^\s*(\d{4})\.(\d{2})\.(\d{2})\s*$")
_LISTING_URL = (
    "https://www.tapology.com/search?term=ufc&search=Enviar&mainSearchFilter=events"
)
_DATE_PATTERNS = [
    # "March 4, 2023" or "March  4, 2023" (double space for single-digit days)
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{1,2}),?\s*(\d{4})\b"
    ),
    # "Mar. 4, 2023" / "Mar 4, 2023"
    re.compile(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s*(\d{4})\b"
    ),
]
_MONTHS = {
    "Jan": 1, "January": 1,
    "Feb": 2, "February": 2,
    "Mar": 3, "March": 3,
    "Apr": 4, "April": 4,
    "May": 5,
    "Jun": 6, "June": 6,
    "Jul": 7, "July": 7,
    "Aug": 8, "August": 8,
    "Sep": 9, "September": 9,
    "Oct": 10, "October": 10,
    "Nov": 11, "November": 11,
    "Dec": 12, "December": 12,
}


@dataclass(frozen=True)
class SearchCandidate:
    href: str  # absolute URL
    slug_label: str  # human-readable label from anchor


@dataclass(frozen=True)
class TapologyEventListing:
    """A row in the Tapology events search listing."""

    href: str  # absolute URL
    name: str
    event_date: date


def parse_search_results(html: str) -> list[SearchCandidate]:
    """Return UFC-only event candidates from a Tapology search results page.

    Filters to results whose slug contains 'ufc'. Dedupes by href, preserves
    document order (top results first).
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[SearchCandidate] = []
    for a in soup.find_all("a", href=_EVENT_HREF):
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        text = a.get_text(strip=True)
        if not text:
            continue
        if "ufc" not in href.lower():
            continue
        full = href if href.startswith("http") else f"https://www.tapology.com{href}"
        out.append(SearchCandidate(href=full, slug_label=text))
    return out


def parse_events_listing(html: str) -> list[TapologyEventListing]:
    """Parse the table inside <div class="searchResultsEvent"> into rows.

    Each row has: anchor with href + name, and a cell with date YYYY.MM.DD.
    Skips rows without a parseable date or with non-UFC slug.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", class_="searchResultsEvent")
    if container is None:
        return []
    out: list[TapologyEventListing] = []
    seen: set[str] = set()
    for tr in container.find_all("tr"):
        a = tr.find("a", href=_EVENT_HREF)
        if not a:
            continue
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        name = a.get_text(strip=True)
        date_obj: date | None = None
        for td in tr.find_all("td"):
            m = _LISTING_DATE.match(td.get_text())
            if m:
                try:
                    date_obj = date(
                        int(m.group(1)), int(m.group(2)), int(m.group(3))
                    )
                except ValueError:
                    pass
                break
        if not name or date_obj is None:
            continue
        # Filter to UFC events only (slug contains 'ufc')
        if "ufc" not in href.lower():
            continue
        full = href if href.startswith("http") else f"https://www.tapology.com{href}"
        out.append(
            TapologyEventListing(href=full, name=name, event_date=date_obj)
        )
    return out


async def fetch_all_ufc_events_listing(
    context: Any,
    cache_path: Any = None,
    cache_ttl_hours: int = 24,
) -> list[TapologyEventListing]:
    """Get all UFC events from Tapology, with on-disk HTML cache.

    Strategy:
      1. If cache exists and is fresh (< cache_ttl_hours), parse it.
      2. Otherwise try live fetch.
      3. If live fails (Cloudflare), fall back to the cache (even if stale).

    cache_path is a Path; if None, no cache is used.
    """
    from pathlib import Path
    import time

    cache = Path(cache_path) if cache_path is not None else None

    # 1. Use fresh cache
    if cache and cache.exists():
        age_hours = (time.time() - cache.stat().st_mtime) / 3600
        if age_hours < cache_ttl_hours:
            html = cache.read_text(encoding="utf-8")
            logger.info(
                "Using cached listing (age=%.1fh, ttl=%dh)", age_hours, cache_ttl_hours
            )
            return parse_events_listing(html)

    # 2. Try live fetch
    try:
        html = await _fetch_html(context, _LISTING_URL)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(html, encoding="utf-8")
            logger.info("Listing cache refreshed at %s", cache)
        return parse_events_listing(html)
    except TapologyBlockedError:
        # 3. Fallback to stale cache
        if cache and cache.exists():
            age_hours = (time.time() - cache.stat().st_mtime) / 3600
            logger.warning(
                "Live listing blocked, using stale cache (age=%.1fh)", age_hours
            )
            html = cache.read_text(encoding="utf-8")
            return parse_events_listing(html)
        raise


class EventListingResolver:
    """In-memory resolver: matches DB events to a pre-fetched Tapology listing.

    Uses date as primary key (Tapology listings have exact event dates).
    Falls back to fuzzy name match when multiple events share a date.
    """

    def __init__(
        self,
        listings: list[TapologyEventListing],
        tolerance_days: int = 2,
        name_threshold: int = 60,
    ) -> None:
        self._tolerance = tolerance_days
        self._name_threshold = name_threshold
        self._by_date: dict[date, list[TapologyEventListing]] = {}
        for L in listings:
            self._by_date.setdefault(L.event_date, []).append(L)
        self._size = len(listings)

    def __len__(self) -> int:
        return self._size

    def resolve(self, event_name: str, expected_date: date) -> str | None:
        """Return the Tapology URL for this DB event, or None."""
        from rapidfuzz import fuzz

        # Search exact date first, then ±tolerance days
        deltas = sorted(range(-self._tolerance, self._tolerance + 1), key=abs)
        for delta in deltas:
            d = expected_date + timedelta(days=delta)
            cands = self._by_date.get(d)
            if not cands:
                continue
            if len(cands) == 1:
                return cands[0].href
            # Multiple events on same date: pick best fuzzy name match
            best = max(
                cands,
                key=lambda c: fuzz.WRatio(event_name.lower(), c.name.lower()),
            )
            if fuzz.WRatio(event_name.lower(), best.name.lower()) >= self._name_threshold:
                return best.href
        return None


_CLOUDFLARE_MARKERS = (
    "just a moment",
    "challenge-platform",
    "cf-chl-",
    "cf_chl_",
    "checking your browser",
    "_cf_chl_opt",
)


def is_blocked_response(html: str) -> bool:
    """True if Tapology returned an empty/Cloudflare-challenge response.

    Real Tapology pages are >100KB. An empty body or one matching Cloudflare
    challenge markers means we got blocked.
    """
    if len(html) < 500:
        return True
    if "tapology" not in html.lower():
        return True
    low = html.lower()
    # Cloudflare challenge HTML is ~30KB and contains specific markers
    if any(m in low for m in _CLOUDFLARE_MARKERS):
        return True
    return False


def parse_event_page_date(html: str) -> date | None:
    """Extract the event date from a Tapology event detail page.

    Looks for the first month-day-year pattern in the document; works because
    Tapology event pages put the date prominently in <meta> and headings.
    """
    for pat in _DATE_PATTERNS:
        m = pat.search(html)
        if not m:
            continue
        month_name, day, year = m.group(1), m.group(2), m.group(3)
        try:
            return date(int(year), _MONTHS[month_name], int(day))
        except (KeyError, ValueError):
            continue
    return None


async def _fetch_html(
    context: Any, url: str, timeout_ms: int = 45_000, max_wait_s: int = 25
) -> str:
    """Fetch a page; if Cloudflare challenge, wait for it to resolve.

    Cloudflare's JS challenge typically completes in 5-10s if Playwright is
    not detected as a bot. We poll the page content up to max_wait_s seconds.

    Raises TapologyBlockedError if the page never produces real content.
    """
    p = await context.new_page()
    try:
        await p.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Random short jitter to look human
        await p.wait_for_timeout(800 + random.randint(0, 600))

        # Poll: if we see Cloudflare challenge, wait up to max_wait_s for it
        # to resolve. Real content appears once challenge passes.
        deadline_ms = max_wait_s * 1000
        elapsed = 0
        html = await p.content()
        while is_blocked_response(html) and elapsed < deadline_ms:
            await p.wait_for_timeout(2_000)
            elapsed += 2_000
            html = await p.content()
            if not is_blocked_response(html):
                logger.info(
                    "Cloudflare challenge passed for %s after %dms", url, elapsed
                )
                break
    finally:
        await p.close()
    if is_blocked_response(html):
        raise TapologyBlockedError(f"Empty/challenge response for {url}")
    return html


async def resolve_event_url(
    context: Any,  # playwright BrowserContext
    event_name: str,
    expected_date: date,
    tolerance_days: int = 2,
    max_candidates: int = 3,
) -> str | None:
    """Resolve a DB event (name, date) to its Tapology event_url.

    Raises TapologyBlockedError if Tapology returns an empty/anti-bot
    response — caller should back off and retry (do NOT mark as unmatched).
    """
    search_url = (
        "https://www.tapology.com/search?term="
        f"{event_name.replace(' ', '+')}&type=Event"
    )
    search_html = await _fetch_html(context, search_url)

    candidates = parse_search_results(search_html)[:max_candidates]
    tolerance = timedelta(days=tolerance_days)

    for cand in candidates:
        try:
            ev_html = await _fetch_html(context, cand.href)
        except TapologyBlockedError:
            # If a single event page is blocked but the search worked,
            # treat as transient and try the next candidate.
            logger.warning("Event page blocked: %s", cand.href)
            continue
        ev_date = parse_event_page_date(ev_html)
        if ev_date is None:
            continue
        if abs((ev_date - expected_date).days) <= tolerance.days:
            return cand.href

    return None
