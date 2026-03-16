"""Betting module — engine, backtest, parlays."""

from ufc_core.betting import engine, backtest, parlays  # noqa: F401

# Common API re-exports (guarded)
try:
    from ufc_core.betting.engine import american_to_decimal, generate_event_plan  # noqa: F401
except ImportError:
    pass
