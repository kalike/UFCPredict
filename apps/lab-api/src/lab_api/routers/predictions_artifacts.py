"""Artifact loading shared by the predictions router, compare router and the
inference engine. Kept in its own module to avoid an import cycle between the
router and ``services.predict_engine``.
"""

import joblib


def load_artifact(uri: str) -> dict:
    """Load an artifact saved by the training service.

    Accepts ``file://path`` or an absolute path. Returns the dict
    ``{clf, feat_cols, feature_set, model_short, ...}`` produced at training time.
    """
    if uri.startswith("file://"):
        path = uri[len("file://"):]
    else:
        path = uri
    return joblib.load(path)
