"""
Stubs for betting submodules that depend on legacy backend-only persistence services.

TODO(F1.T15): These will be replaced by proper ports in a later task.
"""
from __future__ import annotations

from typing import TYPE_CHECKING


# ---------------------------------------------------------------------------
# PredictionSessionService stub (used by BacktestEngine)
# ---------------------------------------------------------------------------

class PredictionSessionService:
    """Stub for the PredictionSessionService that lives in the legacy backend.

    TODO(F1.T15): `sessions.PredictionSessionService` not ported yet.
    Replace this stub when the sessions module is ported.
    """

    def list_all(self) -> list[dict]:
        raise NotImplementedError(
            "PredictionSessionService is not yet ported to ufc_core; "
            "stub for import-time compatibility only."
        )

    def get(self, session_id: str) -> dict | None:
        raise NotImplementedError(
            "PredictionSessionService is not yet ported to ufc_core."
        )


# ---------------------------------------------------------------------------
# _resolve_session stub (used by ParlayService)
# ---------------------------------------------------------------------------

def _resolve_session(db, session_id: str):
    """Stub for db.sessions._resolve_session.

    TODO(F1.T15): `db.sessions._resolve_session` not ported yet.
    """
    raise NotImplementedError(
        "_resolve_session is not yet ported to ufc_core; "
        "stub for import-time compatibility only."
    )
