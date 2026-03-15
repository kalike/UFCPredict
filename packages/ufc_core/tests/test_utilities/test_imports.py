def test_utilities_importable():
    from ufc_core import parsers, transforms, imputer
    assert hasattr(parsers, "__name__")
    assert hasattr(transforms, "__name__")
    assert hasattr(imputer, "__name__")
