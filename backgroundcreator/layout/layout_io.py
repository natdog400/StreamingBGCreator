from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LAYOUT_VERSION = 1


@dataclass(frozen=True)
class LayoutFile:
    version: int
    payload: dict[str, Any]


def load_layout_file(file_path: str) -> LayoutFile:
    path = Path(file_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    version = int(data.get("version", 0))
    return LayoutFile(version=version, payload=data)


def save_layout_file(file_path: str, payload: dict[str, Any]) -> None:
    path = Path(file_path)
    data = dict(payload)
    data["version"] = int(data.get("version") or LAYOUT_VERSION)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
