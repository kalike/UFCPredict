"""Smoke-import tests for T15 modules.

These tests only verify that modules can be imported without errors.
Behavioral tests (train/predict/betting logic) come in T17+.
"""


def test_trainer_importable():
    from ufc_core.trainer import core as trainer_core
    assert hasattr(trainer_core, "__name__")


def test_predictor_importable():
    from ufc_core.predictor import core as predictor_core
    assert hasattr(predictor_core, "__name__")


def test_betting_modules_importable():
    from ufc_core.betting import engine, backtest, parlays
    assert hasattr(engine, "__name__")
    assert hasattr(backtest, "__name__")
    assert hasattr(parlays, "__name__")


def test_bias_validation_importable():
    from ufc_core import bias_validation
    assert hasattr(bias_validation, "__name__")
