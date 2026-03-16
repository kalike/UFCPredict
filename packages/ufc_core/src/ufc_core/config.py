"""Configuration for ufc_core, env-var driven.

Kept intentionally minimal — only values that ufc_core needs at module-load time.
"""
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("UFC_DATA_DIR", os.path.expanduser("~/.ufc-core/data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Model constants (from legacy backend config.py) ──
BASE_ELO: float = float(os.environ.get("BASE_ELO", "1500"))
TEMPERATURE: float = float(os.environ.get("TEMPERATURE_SCALING", "1.0"))
TEST_CUTOFF_DATE: str = os.environ.get("TEST_CUTOFF_DATE", "2024-01-01")
REALWORLD_CUTOFF_DATE: str = os.environ.get("REALWORLD_CUTOFF_DATE", "2025-09-01")

# Paths
MODELS_DIR = DATA_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

ELO_RATINGS_PATH = DATA_DIR / "elo_ratings.json"

# Datetime parsed versions for comparisons
REALWORLD_CUTOFF_DT = datetime.strptime(REALWORLD_CUTOFF_DATE, "%Y-%m-%d")
TEST_CUTOFF_DT = datetime.strptime(TEST_CUTOFF_DATE, "%Y-%m-%d")

# Model file paths (mirrors the legacy config MODEL_FILES + PYTORCH_MODELS)
MODEL_FILES = {
    "RF (35f) PRO": MODELS_DIR / "rf_35f_PRO.joblib",
    "RF D+Aug (35f) PRO": MODELS_DIR / "rf_daug_35f_PRO.joblib",
    "LGBM D+Aug (35f) PRO": MODELS_DIR / "lgbm_daug_35f_PRO.joblib",
    "RF D+Aug (52f) PRO": MODELS_DIR / "rf_daug_52f_PRO.joblib",
    "MLP sklearn (35f) PRO": MODELS_DIR / "mlp_sklearn_35f_PRO.joblib",
    "SVM Base (35f) PRO": MODELS_DIR / "svm_base_35f_PRO.joblib",
    "SVM GSearch (35f) PRO": MODELS_DIR / "svm_gs_35f_PRO.joblib",
    "SVM Robust (35f) PRO": MODELS_DIR / "svm_rob_35f_PRO.joblib",
    "XGB D+Aug (35f) PRO": MODELS_DIR / "xgb_daug_35f_PRO.joblib",
    "XGB D+Aug (52f) PRO": MODELS_DIR / "xgb_daug_52f_PRO.joblib",
    "CB D+Aug (35f) PRO": MODELS_DIR / "cb_daug_35f_PRO.joblib",
    "CB D+Aug (52f) PRO": MODELS_DIR / "cb_daug_52f_PRO.joblib",
    "LR ElasticNet (35f) PRO": MODELS_DIR / "lr_enet_35f_PRO.joblib",
    "LR ElasticNet (52f) PRO": MODELS_DIR / "lr_enet_52f_PRO.joblib",
    "MLP Shallow (35f) PRO": MODELS_DIR / "mlp_shallow_35f_PRO.joblib",
    "MLP Shallow (52f) PRO": MODELS_DIR / "mlp_shallow_52f_PRO.joblib",
}

PYTORCH_MODELS = {
    "DeepMLP (35f) PRO": MODELS_DIR / "deep_mlp_35f_PRO.pt",
    "ResNet (35f) PRO": MODELS_DIR / "resnet_35f_PRO.pt",
}

# Alias used by trainer.py (ELO_RATINGS path)
ELO_RATINGS = MODELS_DIR / "elo_ratings_PRO.joblib"
