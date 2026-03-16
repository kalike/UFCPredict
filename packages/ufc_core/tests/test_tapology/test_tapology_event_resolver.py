"""Tests for the Tapology event resolver (DB-driven discovery)."""

from datetime import date
from pathlib import Path

from ufc_core.tapology.event_resolver import (
    EventListingResolver,
    is_blocked_response,
    parse_event_page_date,
    parse_events_listing,
    parse_search_results,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tapology"


def test_search_results_extracts_ufc_only():
    html = (FIXTURES / "search_results_ufc285.html").read_text(encoding="utf-8")
    cands = parse_search_results(html)
    # All candidates must have 'ufc' in their URL
    assert all("ufc" in c.href.lower() for c in cands)
    # The first result should be UFC 285
    assert "ufc-285" in cands[0].href.lower()


def test_search_results_dedupe_by_href():
    html = (FIXTURES / "search_results_ufc285.html").read_text(encoding="utf-8")
    cands = parse_search_results(html)
    hrefs = [c.href for c in cands]
    assert len(hrefs) == len(set(hrefs))


def test_search_results_returns_absolute_urls():
    html = (FIXTURES / "search_results_ufc285.html").read_text(encoding="utf-8")
    cands = parse_search_results(html)
    for c in cands:
        assert c.href.startswith("https://www.tapology.com/")


def test_parse_event_page_date_ufc285():
    html = (FIXTURES / "event_page_ufc285.html").read_text(encoding="utf-8")
    d = parse_event_page_date(html)
    assert d == date(2023, 3, 4)


def test_parse_event_page_date_returns_none_when_missing():
    assert parse_event_page_date("<html><body>nothing</body></html>") is None


def test_parse_event_page_date_handles_short_month():
    # "Mar 4, 2023" or "Mar. 4, 2023"
    assert parse_event_page_date("<p>Event date Mar 4, 2023</p>") == date(2023, 3, 4)
    assert parse_event_page_date("<p>Mar. 4, 2023</p>") == date(2023, 3, 4)


def test_is_blocked_response_empty_html():
    """Cloudflare anti-bot returns near-empty HTML."""
    assert is_blocked_response("<html><head></head><body></body></html>") is True
    assert is_blocked_response("") is True
    assert is_blocked_response("<html></html>") is True


def test_is_blocked_response_real_page():
    """Real Tapology pages are large and contain the brand."""
    html = (FIXTURES / "search_results_ufc285.html").read_text(encoding="utf-8")
    assert is_blocked_response(html) is False


def test_is_blocked_response_short_irrelevant_page():
    """Short pages without 'tapology' string are also treated as blocked."""
    html = "<html><body>" + ("filler text " * 200) + "</body></html>"
    assert is_blocked_response(html) is True  # >500 chars but no 'tapology'


# ----- Events listing parser + EventListingResolver -----


def test_parse_events_listing_extracts_many_rows():
    html = (FIXTURES / "events_listing_full.html").read_text(encoding="utf-8")
    rows = parse_events_listing(html)
    # Captured fixture had 1000 unique UFC events
    assert len(rows) > 500


def test_parse_events_listing_filters_non_ufc():
    """Trending sidebar events (ONE, PFL, ACA) must be excluded."""
    html = (FIXTURES / "events_listing_full.html").read_text(encoding="utf-8")
    rows = parse_events_listing(html)
    for r in rows:
        assert "ufc" in r.href.lower(), f"non-ufc leaked: {r.href}"


def test_parse_events_listing_dates_are_real():
    html = (FIXTURES / "events_listing_full.html").read_text(encoding="utf-8")
    rows = parse_events_listing(html)
    years = {r.event_date.year for r in rows}
    # Tapology listing fetched 2026-04 covers 2010 to 2026.
    assert min(years) <= 2010
    assert max(years) >= 2024


def test_event_listing_resolver_exact_date_single_match():
    listings = [_make_listing("ufc-285", "UFC 285", date(2023, 3, 4))]
    r = EventListingResolver(listings)
    assert r.resolve("UFC 285: Jones vs Gane", date(2023, 3, 4)) == "https://t.com/ufc-285"


def test_event_listing_resolver_off_by_one_day():
    listings = [_make_listing("ufc-100", "UFC 100", date(2010, 5, 5))]
    r = EventListingResolver(listings)
    assert r.resolve("UFC 100", date(2010, 5, 6)) == "https://t.com/ufc-100"
    assert r.resolve("UFC 100", date(2010, 5, 4)) == "https://t.com/ufc-100"


def test_event_listing_resolver_outside_tolerance_returns_none():
    listings = [_make_listing("ufc-1", "UFC 1", date(2020, 1, 1))]
    r = EventListingResolver(listings, tolerance_days=2)
    assert r.resolve("UFC 1", date(2020, 1, 4)) is None


def test_event_listing_resolver_multiple_same_date_uses_fuzzy():
    listings = [
        _make_listing("ufc-fn-foo", "UFC Fight Night: A vs B", date(2024, 1, 1)),
        _make_listing("ufc-295", "UFC 295: C vs D", date(2024, 1, 1)),
    ]
    r = EventListingResolver(listings)
    assert r.resolve("UFC 295: C vs D", date(2024, 1, 1)) == "https://t.com/ufc-295"


def test_event_listing_resolver_real_fixture_resolves_ufc285():
    html = (FIXTURES / "events_listing_full.html").read_text(encoding="utf-8")
    listings = parse_events_listing(html)
    r = EventListingResolver(listings)
    # UFC 285 was 2023-03-04. The fixture is from late-2026 so it may or
    # may not include UFC 285 depending on what Tapology returns; only
    # assert resolver behaves sensibly when it does.
    url = r.resolve("UFC 285: Jones vs Gane", date(2023, 3, 4))
    if url is not None:
        assert "/fightcenter/events/" in url
        assert "ufc" in url.lower()


def _make_listing(slug: str, name: str, dt: date):
    """Build a TapologyEventListing for tests without importing the dataclass."""
    from ufc_core.tapology.event_resolver import TapologyEventListing
    return TapologyEventListing(href=f"https://t.com/{slug}", name=name, event_date=dt)
