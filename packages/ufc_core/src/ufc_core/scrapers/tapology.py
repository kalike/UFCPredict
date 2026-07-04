"""
UFC Predictor — Tapology scraper for community fight predictions.

Uses Playwright (async) to fetch pages because Tapology blocks raw requests.
"""

import asyncio
import logging
import re

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from ufc_core.schemas.tapology import (
    TapologyCommunityPicks,
    TapologyFight,
    TapologyMethodBreakdown,
    TapologyScrapeResponse,
)
from ufc_core.tapology.event_resolver import (
    TapologyBlockedError,
    _fetch_html,
)

logger = logging.getLogger("ufc-predictor.tapology")

_SEM_MAX = 4  # max concurrent matchup-page fetches
# Chromium is reliably flagged by Cloudflare; webkit passes the challenge and
# firefox is a fallback. Tried in order until the event page loads unblocked.
_ENGINES = ("webkit", "firefox")


class TapologyScraper:
    """Scrapes a Tapology event page and its matchup sub-pages."""

    async def scrape_event(self, event_url: str) -> TapologyScrapeResponse:
        """Main entry point: scrape event → matchup pages → return structured data."""
        errors: list[str] = []

        async with async_playwright() as pw:
            # 1. Fetch event page, falling back across engines if blocked.
            #    Tapology sits behind Cloudflare: _fetch_html waits for the
            #    challenge to resolve and raises if the page never unblocks.
            browser = None
            context = None
            event_html = ""
            for engine in _ENGINES:
                browser = await getattr(pw, engine).launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                )
                try:
                    event_html = await _fetch_html(context, event_url)
                    break
                except TapologyBlockedError:
                    logger.warning(
                        "Tapology event page blocked by Cloudflare (%s): %s",
                        engine, event_url,
                    )
                    errors.append(f"Cloudflare blocked the event page with {engine}")
                    await browser.close()
                    browser = None

            if browser is None:
                return TapologyScrapeResponse(
                    event_name="",
                    n_fights=0,
                    fights=[],
                    errors=errors,
                )

            event_name, matchup_urls = self._parse_event_page(event_html)

            if not matchup_urls:
                logger.warning(
                    "No matchup URLs found on event page (size=%d, name=%r): %s",
                    len(event_html), event_name, event_url,
                )
                await browser.close()
                return TapologyScrapeResponse(
                    event_name=event_name,
                    n_fights=0,
                    fights=[],
                    errors=["No matchup URLs found on event page"],
                )

            # 2. Fetch each matchup page concurrently
            sem = asyncio.Semaphore(_SEM_MAX)
            fights: list[TapologyFight | None] = [None] * len(matchup_urls)

            async def _fetch_matchup(idx: int, url: str) -> None:
                async with sem:
                    try:
                        html = await _fetch_html(context, url)
                        fights[idx] = self._parse_matchup_page(html, url)
                    except TapologyBlockedError:
                        logger.warning(
                            "Tapology matchup blocked by Cloudflare: %s", url
                        )
                        errors.append(f"Matchup {url}: cloudflare_blocked")
                    except Exception as exc:
                        logger.warning("Failed to scrape matchup %s: %s", url, exc)
                        errors.append(f"Matchup {url}: {exc}")

            await asyncio.gather(
                *[_fetch_matchup(i, u) for i, u in enumerate(matchup_urls)]
            )
            await browser.close()

        valid_fights = [f for f in fights if f is not None]

        return TapologyScrapeResponse(
            event_name=event_name,
            n_fights=len(valid_fights),
            fights=valid_fights,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_event_page(self, html: str) -> tuple[str, list[str]]:
        """Extract event name and unique matchup URLs from the event page."""
        soup = BeautifulSoup(html, "html.parser")

        # Event name from <h2>
        h2 = soup.select_one("h2.text-xl")
        event_name = h2.get_text(strip=True) if h2 else ""

        # Matchup links: <a> with text "Matchup Page"
        links: list[str] = []
        for a_tag in soup.find_all("a", string=re.compile(r"Matchup\s+Page", re.I)):
            href = a_tag.get("href", "")
            if "/fightcenter/bouts/" in href:
                full = href if href.startswith("http") else f"https://www.tapology.com{href}"
                if full not in links:
                    links.append(full)

        return event_name, links

    def _parse_matchup_page(self, html: str, matchup_url: str) -> TapologyFight:
        """Extract fighter names, odds, and community picks from a matchup page."""
        soup = BeautifulSoup(html, "html.parser")

        # Fighter full names from <h2> "Fighter1 vs. Fighter2 III"
        h2 = soup.select_one("h2")
        h2_text = h2.get_text(strip=True) if h2 else ""
        # Strip trailing rematch numeral (II, III, IV, V, etc.)
        h2_text = re.sub(r"\s+[IVX]+\s*$", "", h2_text)
        parts = re.split(r"\s+vs\.?\s+", h2_text, maxsplit=1)
        fighter_1 = parts[0].strip() if len(parts) >= 1 else ""
        fighter_2 = parts[1].strip() if len(parts) >= 2 else ""

        # Odds: look for patterns like "-140 (Slight Favorite)" / "+110 (Near Even)"
        odds_f1, odds_f2 = self._extract_odds(soup, fighter_1, fighter_2)

        # Community picks — pass fighter names so rows can be matched correctly
        community = self._extract_community_picks(soup, fighter_1, fighter_2)

        return TapologyFight(
            fighter_1=fighter_1,
            fighter_2=fighter_2,
            matchup_url=matchup_url,
            odds_f1_american=odds_f1,
            odds_f2_american=odds_f2,
            community_picks=community,
        )

    def _extract_odds(
        self, soup: BeautifulSoup, fighter_1: str, fighter_2: str
    ) -> tuple[int | None, int | None]:
        """Extract American odds, matching each value to the correct fighter.

        The odds table has a mobile header row (``tr.md:hidden``) with fighter
        last names that reveals which column belongs to which fighter.  The
        column order does NOT always match the h2 title order, so we match by
        name — the same approach used by ``_extract_community_picks``.
        """
        f1_last = fighter_1.split()[-1].lower() if fighter_1 else ""
        f2_last = fighter_2.split()[-1].lower() if fighter_2 else ""

        for tbody in soup.find_all("tbody"):
            # Look for the mobile-only header row with fighter last names
            mobile_row = None
            for tr in tbody.find_all("tr"):
                if "md:hidden" in " ".join(tr.get("class", [])):
                    mobile_row = tr
                    break
            if mobile_row is None:
                continue

            tds = mobile_row.find_all("td")
            names = [td.get_text(strip=True) for td in tds if td.get_text(strip=True)]
            if len(names) < 2:
                continue

            left_name = names[0].lower()
            right_name = names[-1].lower()

            # Verify these names match our fighters (avoid grabbing wrong table)
            left_match = left_name.endswith(f1_last) or left_name.endswith(f2_last)
            right_match = right_name.endswith(f1_last) or right_name.endswith(f2_last)
            if not (left_match or right_match):
                continue

            # Extract odds from this tbody (DOM order = left, right)
            odds_divs = tbody.select("div.hidden.md\\:inline")
            found: list[int] = []
            for div in odds_divs:
                text = div.get_text(strip=True)
                m = re.match(r"([+-]\d+)", text)
                if m:
                    found.append(int(m.group(1)))
                if len(found) == 2:
                    break

            if len(found) != 2:
                continue

            left_odds, right_odds = found

            # Match column position → fighter
            if left_name.endswith(f1_last):
                return left_odds, right_odds
            if left_name.endswith(f2_last):
                return right_odds, left_odds
            # Fallback: DOM order
            return left_odds, right_odds

        # Fallback: global search (original behaviour)
        odds_divs = soup.select("div.hidden.md\\:inline")
        found = []
        for div in odds_divs:
            text = div.get_text(strip=True)
            m = re.match(r"([+-]\d+)", text)
            if m:
                found.append(int(m.group(1)))
            if len(found) == 2:
                break
        if len(found) == 2:
            return found[0], found[1]
        return None, None

    def _extract_community_picks(
        self, soup: BeautifulSoup, fighter_1: str, fighter_2: str
    ) -> TapologyCommunityPicks | None:
        """Extract community prediction data from chartRows and total_bars.

        Chart rows on Tapology are sorted by community favourite, NOT by the
        h2 title order.  We match each row's ``.chartLabel`` (last name) to
        *fighter_1* / *fighter_2* so the data is returned in the correct order.
        """
        text = soup.get_text(" ", strip=True)

        # Total picks
        picks_match = re.search(r"Community\s+Picks[:\s]*([\d,]+)", text, re.I)
        if not picks_match:
            return None
        total_picks = int(picks_match.group(1).replace(",", ""))

        # Chart rows: each has a .chartLabel (last name) and .number (win %)
        chart_rows = soup.select(".chartRow")
        if len(chart_rows) < 2:
            return None

        def _parse_row(row_el) -> tuple[str, float, TapologyMethodBreakdown]:
            label_el = row_el.select_one(".chartLabel")
            label = label_el.get_text(strip=True).lower() if label_el else ""

            num_el = row_el.select_one(".number")
            pct_text = num_el.get_text(strip=True) if num_el else "0%"
            win_pct = float(pct_text.replace("%", "").strip() or 0)

            desktop_bar = row_el.select_one(".total_bar.hidden")
            tko_pct = sub_pct = dec_pct = 0.0
            if desktop_bar:
                tko_el = desktop_bar.select_one("[class*='tko']")
                sub_el = desktop_bar.select_one("[class*='sub']")
                dec_el = desktop_bar.select_one("[class*='dec']")
                tko_pct = self._parse_width(tko_el)
                sub_pct = self._parse_width(sub_el)
                dec_pct = self._parse_width(dec_el)

            methods = TapologyMethodBreakdown(
                ko_tko_pct=tko_pct,
                submission_pct=sub_pct,
                decision_pct=dec_pct,
            )
            return label, win_pct, methods

        parsed = [_parse_row(row) for row in chart_rows[:2]]

        # Match rows to fighters. Tapology uses .chartLabel that may be:
        #   - a simple last name ("Page", "Jones")
        #   - a compound last name ("Machado Garry", "Bueno Silva")
        #   - the same last token as the full fighter name
        # We match if the label is a substring of the fighter's full name
        # (case-insensitive), or vice-versa, or last tokens coincide.
        def _matches(label: str, fighter: str) -> bool:
            if not label or not fighter:
                return False
            la, fi = label.lower().strip(), fighter.lower().strip()
            if la in fi or fi in la:
                return True
            la_tokens, fi_tokens = la.split(), fi.split()
            return bool(la_tokens) and bool(fi_tokens) and la_tokens[-1] == fi_tokens[-1]

        f1_pct, f1_methods = 0.0, TapologyMethodBreakdown()
        f2_pct, f2_methods = 0.0, TapologyMethodBreakdown()
        f1_idx, f2_idx = -1, -1

        for idx, (label, pct, methods) in enumerate(parsed):
            if f1_idx == -1 and _matches(label, fighter_1):
                f1_pct, f1_methods, f1_idx = pct, methods, idx
            elif f2_idx == -1 and _matches(label, fighter_2):
                f2_pct, f2_methods, f2_idx = pct, methods, idx

        # If only one fighter matched, infer the other from the remaining row
        if f1_idx == -1 and f2_idx != -1 and len(parsed) >= 2:
            other = next(i for i in range(len(parsed)) if i != f2_idx)
            _, f1_pct, f1_methods = parsed[other]
        elif f2_idx == -1 and f1_idx != -1 and len(parsed) >= 2:
            other = next(i for i in range(len(parsed)) if i != f1_idx)
            _, f2_pct, f2_methods = parsed[other]
        # Fallback: if neither matched, use positional
        elif f1_idx == -1 and f2_idx == -1 and len(parsed) >= 2:
            _, f1_pct, f1_methods = parsed[0]
            _, f2_pct, f2_methods = parsed[1]

        return TapologyCommunityPicks(
            total_picks=total_picks,
            fighter_1_win_pct=f1_pct,
            fighter_2_win_pct=f2_pct,
            fighter_1_methods=f1_methods,
            fighter_2_methods=f2_methods,
        )

    @staticmethod
    def _parse_width(el) -> float:
        """Extract percentage from an element's inline style width."""
        if el is None:
            return 0.0
        style = el.get("style", "")
        m = re.search(r"width:\s*([\d.]+)%", style)
        return float(m.group(1)) if m else 0.0
