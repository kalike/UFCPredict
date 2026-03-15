def test_scraper_modules_importable():
    from ufc_core.scrapers import (
        ufcstats, tapology, tapology_historical, fotos, normaliza,
    )
    for mod in (ufcstats, tapology, tapology_historical, fotos, normaliza):
        assert hasattr(mod, "__name__")


def test_public_api_surface():
    from ufc_core.scrapers import (
        TapologyScraper,
        TapologyHistoricalScraper,
        run_incremental_scrape,
        parse_fighter_page,
    )

    assert callable(parse_fighter_page)
    assert callable(run_incremental_scrape)
    assert TapologyScraper.__name__ == "TapologyScraper"
    assert TapologyHistoricalScraper.__name__ == "TapologyHistoricalScraper"
