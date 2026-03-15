"""Configuration for ufc_core, env-var driven.

Kept intentionally minimal — only values that ufc_core needs at module-load time.
"""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("UFC_DATA_DIR", os.path.expanduser("~/.ufc-core/data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
