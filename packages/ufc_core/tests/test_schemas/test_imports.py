def test_schema_modules_importable():
    from ufc_core.schemas import (
        base, betting, combo_search, compare, dashboard,
        fighters, models, predictions, scraping, system, tapology,
    )
    for mod in (base, betting, combo_search, compare, dashboard,
                fighters, models, predictions, scraping, system, tapology):
        assert hasattr(mod, "__name__")


def test_retrain_request_defaults():
    from ufc_core.schemas.models import RetrainRequest
    r = RetrainRequest(models=[])
    assert r.feature_set == "legacy"
    assert r.feat_type == "auto"
