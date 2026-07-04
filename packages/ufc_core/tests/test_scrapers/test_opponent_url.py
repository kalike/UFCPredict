from bs4 import BeautifulSoup
from ufc_core.scrapers.ufcstats import _opponent_url_from_cell

OWNER = "http://ufcstats.com/fighter-details/aaa111"
OPP = "http://ufcstats.com/fighter-details/bbb222"


def _cell(html: str):
    return BeautifulSoup(f"<table><tr><td>{html}</td></tr></table>", "html.parser").find("td")


def test_returns_opponent_url_when_two_links():
    cell = _cell(
        f'<p><a href="{OWNER}">Davey Grant</a></p>'
        f'<p><a href="{OPP}">Luna Martinetti</a></p>'
    )
    assert _opponent_url_from_cell(cell, OWNER) == OPP


def test_owner_can_be_second_link():
    cell = _cell(
        f'<p><a href="{OPP}">Luna Martinetti</a></p>'
        f'<p><a href="{OWNER}">Davey Grant</a></p>'
    )
    assert _opponent_url_from_cell(cell, OWNER) == OPP


def test_returns_none_when_no_opponent_link():
    cell = _cell(f'<p><a href="{OWNER}">Davey Grant</a></p>')
    assert _opponent_url_from_cell(cell, OWNER) is None


def test_ignores_non_fighter_links():
    cell = _cell(
        f'<p><a href="{OWNER}">Davey Grant</a></p>'
        f'<p><a href="http://ufcstats.com/fight-details/zzz">view</a></p>'
    )
    assert _opponent_url_from_cell(cell, OWNER) is None


def test_opponent_from_cell_returns_clean_name_and_url():
    from ufc_core.scrapers.ufcstats import _opponent_from_cell
    # The cell links BOTH fighters; the opponent name must be just the opponent,
    # not the whole cell text (owner + opponent concatenated).
    cell = _cell(
        f'<p><a href="{OWNER}">Davey Grant</a></p>'
        f'<p><a href="{OPP}">Luna Martinetti</a></p>'
    )
    name, url = _opponent_from_cell(cell, OWNER)
    assert name == "Luna Martinetti"
    assert url == OPP


def test_opponent_from_cell_owner_second():
    from ufc_core.scrapers.ufcstats import _opponent_from_cell
    cell = _cell(
        f'<p><a href="{OPP}">Luna Martinetti</a></p>'
        f'<p><a href="{OWNER}">Davey Grant</a></p>'
    )
    name, url = _opponent_from_cell(cell, OWNER)
    assert name == "Luna Martinetti"
    assert url == OPP
