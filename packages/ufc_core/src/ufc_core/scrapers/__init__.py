from ufc_core.scrapers.ufcstats import (
    build_existing_index,
    load_existing_fighters,
    parse_fighter_page,
    run_incremental_scrape,
)
from ufc_core.scrapers.tapology import TapologyScraper
from ufc_core.scrapers.tapology_historical import (
    TapologyHistoricalScraper,
    MatchupPicksDto,
    parse_matchup_to_picks_dto,
)
from ufc_core.scrapers.fotos import download_missing_photos
from ufc_core.scrapers.normaliza import normalizar_fighters_data

__all__ = [
    "build_existing_index",
    "load_existing_fighters",
    "parse_fighter_page",
    "run_incremental_scrape",
    "TapologyScraper",
    "TapologyHistoricalScraper",
    "MatchupPicksDto",
    "parse_matchup_to_picks_dto",
    "download_missing_photos",
    "normalizar_fighters_data",
]
