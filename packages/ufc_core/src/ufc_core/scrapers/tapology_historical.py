"""Historical Tapology scraper: backfill 2010-today + per-event scraping.

Discovery is DB-driven (see tapology_event_resolver): for each UFC event in
the local DB, search Tapology and verify the date matches. Once we have the
Tapology event URL, reuse the existing TapologyScraper parsers to extract
matchup URLs and per-matchup community picks.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from ufc_core.scrapers.tapology import TapologyScraper
from ufc_core.tapology.event_resolver import (
    TapologyBlockedError,
    _fetch_html,
    is_blocked_response,
    resolve_event_url,
)

logger = logging.getLogger("ufc-predictor.tapology-historical")


@dataclass
class MatchupPicksDto:
    """Raw scraped data for a matchup, before matching to DB rows."""

    fighter_a_name: str
    fighter_b_name: str
    total_picks: int
    fighter_a_win_pct: float | None
    fighter_b_win_pct: float | None
    fighter_a_methods: dict[str, float] | None
    fighter_b_methods: dict[str, float] | None
    matchup_url: str


def parse_matchup_to_picks_dto(html: str, matchup_url: str) -> MatchupPicksDto:
    """Convert raw matchup HTML to MatchupPicksDto.

    Reuses TapologyScraper._parse_matchup_page() and adapts its TapologyFight
    schema into our DTO. Diacritics are preserved verbatim (matching is the
    matcher's job, not the parser's).
    """
    scraper = TapologyScraper()
    fight = scraper._parse_matchup_page(html, matchup_url)

    cp = fight.community_picks
    if cp is None or cp.total_picks == 0:
        return MatchupPicksDto(
            fighter_a_name=fight.fighter_1,
            fighter_b_name=fight.fighter_2,
            total_picks=cp.total_picks if cp else 0,
            fighter_a_win_pct=None,
            fighter_b_win_pct=None,
            fighter_a_methods=None,
            fighter_b_methods=None,
            matchup_url=matchup_url,
        )

    return MatchupPicksDto(
        fighter_a_name=fight.fighter_1,
        fighter_b_name=fight.fighter_2,
        total_picks=cp.total_picks,
        fighter_a_win_pct=cp.fighter_1_win_pct,
        fighter_b_win_pct=cp.fighter_2_win_pct,
        fighter_a_methods={
            "ko_tko_pct": cp.fighter_1_methods.ko_tko_pct,
            "submission_pct": cp.fighter_1_methods.submission_pct,
            "decision_pct": cp.fighter_1_methods.decision_pct,
        },
        fighter_b_methods={
            "ko_tko_pct": cp.fighter_2_methods.ko_tko_pct,
            "submission_pct": cp.fighter_2_methods.submission_pct,
            "decision_pct": cp.fighter_2_methods.decision_pct,
        },
        matchup_url=matchup_url,
    )


class TapologyHistoricalScraper:
    """Resolve event → fetch event page → fetch matchup pages → DTOs.

    Persistence and DB matching are NOT this class's concerns; it returns
    DTOs that the CLI/hook then matches and persists.
    """

    def __init__(
        self,
        concurrency: int = 3,
        delay: float = 0.5,
        user_agent: str | None = None,
    ) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._delay = delay
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )

    async def resolve_event(
        self, context: Any, event_name: str, event_date: date
    ) -> str | None:
        """Resolve a DB event to its Tapology URL via search + date verify."""
        return await resolve_event_url(context, event_name, event_date)

    async def scrape_event_matchups(
        self, context: Any, event_url: str
    ) -> tuple[str, list[MatchupPicksDto]]:
        """Fetch event page → matchup URLs → per-matchup DTOs.

        `context` is a Playwright BrowserContext owned by the caller; this
        method does not create or close the browser.
        """
        # _fetch_html handles Cloudflare challenges and HTTP errors uniformly,
        # raising TapologyBlockedError for any non-recoverable failure.
        try:
            event_html = await _fetch_html(context, event_url)
        except TapologyBlockedError:
            raise
        except Exception as exc:
            # Unwrap arbitrary Playwright errors (HTTP 5xx, network, etc.)
            raise TapologyBlockedError(f"Event page error {event_url}: {exc}") from exc

        base_scraper = TapologyScraper()
        event_name, matchup_urls = base_scraper._parse_event_page(event_html)

        dtos: list[MatchupPicksDto | None] = [None] * len(matchup_urls)

        async def _fetch(idx: int, url: str) -> None:
            async with self._sem:
                await asyncio.sleep(self._delay)
                for attempt in range(3):
                    try:
                        p = await context.new_page()
                        try:
                            await p.goto(
                                url, wait_until="domcontentloaded", timeout=30_000
                            )
                            html = await p.content()
                        finally:
                            await p.close()
                        dtos[idx] = parse_matchup_to_picks_dto(html, url)
                        return
                    except Exception as exc:
                        wait = 2**attempt
                        logger.warning(
                            "Matchup %s attempt %d failed: %s (sleep %ss)",
                            url,
                            attempt + 1,
                            exc,
                            wait,
                        )
                        await asyncio.sleep(wait)
                logger.error("Matchup %s failed after 3 attempts", url)

        await asyncio.gather(*[_fetch(i, u) for i, u in enumerate(matchup_urls)])
        return event_name, [d for d in dtos if d is not None]
