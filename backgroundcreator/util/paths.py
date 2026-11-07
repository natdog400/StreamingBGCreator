from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else (Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base) if base else (Path.home() / ".local" / "share")

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
