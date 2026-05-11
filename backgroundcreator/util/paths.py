from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Roaming"

    directory = root / "BackgroundCreator"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_dir() -> Path:
    if bool(getattr(sys, "frozen", False)):
        try:
            return Path(sys.executable).resolve().parent
        except Exception:
            return Path.cwd()
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()
