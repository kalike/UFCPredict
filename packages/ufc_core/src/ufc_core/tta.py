"""Test-Time Augmentation (TTA): the fighter-swap flip of a feature matrix.

Single source of truth for the symmetric flip used by training/realworld
evaluation, calibration, and production inference. Building it per-call from
feat_cols (rather than a contiguous half-swap) is what makes it correct for
feature sets that append symmetric fight-level columns (e.g. V7's tapology
``tap_*`` scalars). The old ``np.hstack([X[:, n:], X[:, :n]])`` assumed
feat_cols was exactly ``[f1_block | f2_block]``; any trailing symmetric column
shifted the split and scrambled every column past it.
"""

from __future__ import annotations

import numpy as np


def build_tta_flip(X: np.ndarray, feat_cols: list[str]) -> np.ndarray:
    """Return the fighter-swapped (TTA) view of ``X``.

    For each column in ``feat_cols``:
      * ``f1_<suffix>`` is swapped with its ``f2_<suffix>`` partner (and vice
        versa) — this covers asymmetric paired features like ``f1_tap_win_pct``.
      * ``delta_<suffix>`` is negated (delta = f1 - f2, so swapping fighters
        negates it).
      * any other column is symmetric at the fight level (e.g.
        ``tap_consensus_strength``) and is left unchanged.

    On a clean 52f layout (sorted f1 block then f2 block, no symmetric columns)
    this is identical to the legacy contiguous half-swap; on a 35f delta layout
    with no symmetric columns it is identical to ``-X``.
    """
    X_flip = X.copy()
    f2_index = {c[3:]: i for i, c in enumerate(feat_cols) if c.startswith("f2_")}
    for i, c in enumerate(feat_cols):
        if c.startswith("f1_"):
            j = f2_index.get(c[3:])
            if j is not None:
                X_flip[:, i] = X[:, j]
                X_flip[:, j] = X[:, i]
        elif c.startswith("delta_"):
            X_flip[:, i] = -X[:, i]
        # else: symmetric fight-level column -> leave unchanged
    return X_flip
