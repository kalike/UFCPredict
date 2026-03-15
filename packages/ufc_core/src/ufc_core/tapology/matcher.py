"""Three-level matchers for linking Tapology data to UFCStats DB rows."""

from dataclasses import dataclass
from datetime import date, timedelta

from rapidfuzz import fuzz

from ufc_core.data_loader_base import _normalize_name
from ufc_core.tapology.alias_map import AliasMap


_EVENT_FUZZY_THRESHOLD = 80
_FIGHTER_FUZZY_THRESHOLD = 92


@dataclass(frozen=True)
class EventCandidate:
    id: int
    name: str
    date: date | None


@dataclass(frozen=True)
class FighterCandidate:
    id: int
    canonical_name: str


@dataclass(frozen=True)
class FightCandidate:
    id: int
    event_id: int
    fighter_id: int
    opponent_id: int


class EventMatcher:
    """Match a Tapology (event_name, event_date) to events.id."""

    def __init__(self, candidates: list[EventCandidate]) -> None:
        self._by_date: dict[date, list[EventCandidate]] = {}
        for c in candidates:
            if c.date is None:
                continue
            self._by_date.setdefault(c.date, []).append(c)

    def match(self, tapology_name: str, tapology_date: date) -> int | None:
        for delta in (0, -1, 1):
            d = tapology_date + timedelta(days=delta)
            cands = self._by_date.get(d)
            if not cands:
                continue
            if len(cands) == 1:
                return cands[0].id
            best, best_score = None, 0
            for c in cands:
                s = fuzz.ratio(tapology_name.lower(), c.name.lower())
                if s > best_score:
                    best, best_score = c, s
            if best and best_score >= _EVENT_FUZZY_THRESHOLD:
                return best.id
        return None


class FighterMatcher:
    """Match a Tapology fighter name to fighters.id (alias -> NFKD -> fuzzy)."""

    def __init__(
        self, candidates: list[FighterCandidate], alias_map: AliasMap
    ) -> None:
        self._aliases = alias_map
        self._by_canonical: dict[str, int] = {
            c.canonical_name: c.id for c in candidates
        }
        self._by_normalized: dict[str, int] = {
            _normalize_name(c.canonical_name): c.id for c in candidates
        }
        self._all_canonical: list[tuple[str, int]] = [
            (c.canonical_name, c.id) for c in candidates
        ]

    def match(self, tapology_name: str) -> int | None:
        # Step 1: alias map
        canonical = self._aliases.resolve(tapology_name)
        if canonical and canonical in self._by_canonical:
            return self._by_canonical[canonical]

        # Step 2: NFKD normalisation
        norm = _normalize_name(tapology_name)
        if norm in self._by_normalized:
            return self._by_normalized[norm]

        # Step 3: fuzzy (WRatio handles "Jr"/"Sr" suffixes better than ratio)
        best_id, best_score = None, 0
        for cand_name, cand_id in self._all_canonical:
            s = fuzz.WRatio(norm, _normalize_name(cand_name))
            if s > best_score:
                best_id, best_score = cand_id, s
        if best_id is not None and best_score >= _FIGHTER_FUZZY_THRESHOLD:
            return best_id
        return None


class FightMatcher:
    """Match (event_id, fighter_a_id, fighter_b_id) to fights.id (either order)."""

    def __init__(self, candidates: list[FightCandidate]) -> None:
        self._index: dict[tuple[int, frozenset[int]], int] = {}
        for c in candidates:
            key = (c.event_id, frozenset({c.fighter_id, c.opponent_id}))
            self._index[key] = c.id

    def match(
        self, event_id: int, fighter_a_id: int, fighter_b_id: int
    ) -> int | None:
        key = (event_id, frozenset({fighter_a_id, fighter_b_id}))
        return self._index.get(key)
