"""Tapology subsystem: scraper state, matchers, picks repo, orchestration."""

from ufc_core.tapology.alias_map import AliasMap
from ufc_core.tapology.event_resolver import (
    TapologyBlockedError,
    is_blocked_response,
    resolve_event_url,
)
from ufc_core.tapology.matcher import (
    EventCandidate,
    EventMatcher,
    FightCandidate,
    FightMatcher,
    FighterCandidate,
    FighterMatcher,
)
from ufc_core.tapology.picks_repo import (
    PickRow,
    TapologyPicksRepo,
    build_picks_lookup_by_event_pair,
    load_db_picks_lookup,
    orient_picks_for_fight,
)
from ufc_core.tapology.unmatched import RetryQueue, UnmatchedLogger
from ufc_core.tapology.orchestrator import (
    build_matchers,
    discover_db_events,
    process_matchup_dto,
    tapology_hook_for_event_names,
)

__all__ = [
    # alias_map
    "AliasMap",
    # event_resolver
    "TapologyBlockedError",
    "is_blocked_response",
    "resolve_event_url",
    # matcher
    "EventCandidate",
    "EventMatcher",
    "FightCandidate",
    "FightMatcher",
    "FighterCandidate",
    "FighterMatcher",
    # picks_repo
    "PickRow",
    "TapologyPicksRepo",
    "build_picks_lookup_by_event_pair",
    "load_db_picks_lookup",
    "orient_picks_for_fight",
    # unmatched
    "RetryQueue",
    "UnmatchedLogger",
    # orchestrator
    "build_matchers",
    "discover_db_events",
    "process_matchup_dto",
    "tapology_hook_for_event_names",
]
