"""Trainer module — DB-backed re-export of the legacy backend's trainer.py."""

from ufc_core.trainer.core import *  # noqa: F401, F403

# Re-export the most common entry points if they exist
try:
    from ufc_core.trainer.core import (  # noqa: F401
        train_model,
        evaluate_model,
        recalculate_elo,
    )
except ImportError:
    pass
