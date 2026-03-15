from enum import Enum

from ufc_core.features.engine import (
    compute_fight_features,
    compute_features_for_fights,
    build_fighter_histories,
)
from ufc_core.features.store import (
    upsert_fight_features,
    get_features_for_fight,
    bulk_load_feature_vectors,
)


class FeatureSet(str, Enum):
    LEGACY = "legacy"
    V2 = "v2"
    V3 = "v3"
    V4 = "v4"
    V5 = "v5"
    V6 = "v6"
    V7 = "v7"


__all__ = [
    "FeatureSet",
    "compute_fight_features",
    "compute_features_for_fights",
    "build_fighter_histories",
    "upsert_fight_features",
    "get_features_for_fight",
    "bulk_load_feature_vectors",
]
