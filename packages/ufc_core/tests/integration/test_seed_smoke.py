"""End-to-end smoke: scrape ~10 fighters from UFCStats and ingest to DB.

Network-gated. Default `pytest` runs SKIP this; opt in with:
    UFC_RUN_NETWORK_TESTS=1 pytest packages/ufc_core/tests/integration/ -v
"""

import os

import pytest

from ufc_core.db import Base, models


pytestmark = pytest.mark.skipif(
    os.environ.get("UFC_RUN_NETWORK_TESTS") != "1",
    reason="set UFC_RUN_NETWORK_TESTS=1 to run live network smoke",
)


@pytest.fixture
def fresh_db(test_engine):
    """Truncate-and-recreate all tables to start fresh for an e2e scrape run."""
    from sqlalchemy import text

    Base.metadata.create_all(test_engine)
    with test_engine.connect() as conn:
        # Truncate all tables in dependency order via CASCADE
        for tbl in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{tbl.name}" RESTART IDENTITY CASCADE'))
        conn.commit()
    yield test_engine


def _scrape_index_letter(letter: str, max_fighters: int = 10) -> list[dict]:
    """Walk one letter of the UFCStats fighter index and parse up to N fighters."""
    import requests
    from bs4 import BeautifulSoup

    from ufc_core.scrapers.ufcstats import parse_fighter_page

    url = f"http://www.ufcstats.com/statistics/fighters?char={letter}&page=all"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table.b-statistics__table tbody tr")[:max_fighters]
    fighter_urls: list[str] = []
    for tr in rows:
        a = tr.select_one("td a")
        if a is None:
            continue
        href = a.get("href")
        if href and "fighter-details" in href:
            fighter_urls.append(href)

    payload: list[dict] = []
    for u in fighter_urls[:max_fighters]:
        try:
            data = parse_fighter_page(u)
            if data and data.get("name"):
                payload.append(data)
        except Exception:
            # Tolerate transient network/parse errors on individual fighters
            continue
    return payload


def test_scrape_first_10_fighters_writes_to_db(fresh_db):
    """Scrape ~10 fighters from letter 'a' and ingest them to a fresh DB."""
    from sqlalchemy.orm import sessionmaker

    from ufc_core.db.ingest import ingest_fighters_payload

    payload = _scrape_index_letter("a", max_fighters=10)
    assert payload, "Scraper returned empty payload — check network or UFCStats layout"

    Session = sessionmaker(bind=fresh_db, future=True)
    with Session() as db:
        counts = ingest_fighters_payload(db, payload)

    assert counts["fighters_new"] >= 1
    # Verify rows landed on disk by opening a fresh session
    with Session() as db:
        assert db.query(models.Fighter).count() >= len(payload)
        # Events may or may not be present depending on each fighter's history;
        # confirm at least one Event ingested when any fighter has fights.
        if any(p.get("fights") for p in payload):
            assert db.query(models.Event).count() >= 1
