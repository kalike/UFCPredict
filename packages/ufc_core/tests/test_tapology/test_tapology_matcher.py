"""Tests for the three-level Tapology matcher."""

from datetime import date

from ufc_core.tapology.alias_map import AliasMap
from ufc_core.tapology.matcher import (
    EventCandidate,
    EventMatcher,
    FightCandidate,
    FightMatcher,
    FighterCandidate,
    FighterMatcher,
)


# ---------- EventMatcher ----------


def test_event_match_exact_date():
    candidates = [
        EventCandidate(id=1, name="UFC 285: Jones vs Gane", date=date(2023, 3, 4)),
        EventCandidate(id=2, name="UFC Fight Night", date=date(2023, 3, 11)),
    ]
    m = EventMatcher(candidates)
    assert m.match("UFC 285: Jones vs Gane", date(2023, 3, 4)) == 1


def test_event_match_off_by_one_day():
    candidates = [EventCandidate(id=7, name="UFC 100", date=date(2010, 5, 5))]
    m = EventMatcher(candidates)
    assert m.match("UFC 100", date(2010, 5, 6)) == 7
    assert m.match("UFC 100", date(2010, 5, 4)) == 7


def test_event_match_ambiguous_uses_fuzzy():
    candidates = [
        EventCandidate(id=1, name="UFC Fight Night: A vs B", date=date(2024, 1, 1)),
        EventCandidate(id=2, name="UFC 295: C vs D", date=date(2024, 1, 1)),
    ]
    m = EventMatcher(candidates)
    assert m.match("UFC 295 - C vs D", date(2024, 1, 1)) == 2


def test_event_match_returns_none_when_no_candidate():
    m = EventMatcher([])
    assert m.match("UFC X", date(2026, 1, 1)) is None


def test_event_match_skips_candidates_without_date():
    candidates = [EventCandidate(id=99, name="UFC X", date=None)]
    m = EventMatcher(candidates)
    assert m.match("UFC X", date(2024, 1, 1)) is None


# ---------- FighterMatcher ----------


def test_fighter_alias_takes_priority(tmp_path):
    aliases = AliasMap(tmp_path / "a.json")
    aliases.add("Jiří Procházka", "Jiri Prochazka")
    candidates = [
        FighterCandidate(id=10, canonical_name="Jiri Prochazka"),
        FighterCandidate(id=11, canonical_name="Aleksandar Rakic"),
    ]
    m = FighterMatcher(candidates, aliases)
    assert m.match("Jiří Procházka") == 10


def test_fighter_nfkd_match(tmp_path):
    aliases = AliasMap(tmp_path / "a.json")
    candidates = [FighterCandidate(id=20, canonical_name="Edgar Chairez")]
    m = FighterMatcher(candidates, aliases)
    assert m.match("Edgar Cháirez") == 20


def test_fighter_fuzzy_match_above_threshold(tmp_path):
    aliases = AliasMap(tmp_path / "a.json")
    candidates = [FighterCandidate(id=30, canonical_name="Khalil Rountree")]
    m = FighterMatcher(candidates, aliases)
    assert m.match("Khalil Rountree Jr") == 30


def test_fighter_returns_none_when_no_match(tmp_path):
    aliases = AliasMap(tmp_path / "a.json")
    m = FighterMatcher(
        [FighterCandidate(id=1, canonical_name="John Doe")], aliases
    )
    assert m.match("Completely Different Person") is None


# ---------- FightMatcher ----------


def test_fight_match_either_order():
    candidates = [
        FightCandidate(id=100, event_id=5, fighter_id=10, opponent_id=20)
    ]
    m = FightMatcher(candidates)
    assert m.match(event_id=5, fighter_a_id=10, fighter_b_id=20) == 100
    assert m.match(event_id=5, fighter_a_id=20, fighter_b_id=10) == 100


def test_fight_no_match_different_event():
    candidates = [
        FightCandidate(id=100, event_id=5, fighter_id=10, opponent_id=20)
    ]
    m = FightMatcher(candidates)
    assert m.match(event_id=99, fighter_a_id=10, fighter_b_id=20) is None
