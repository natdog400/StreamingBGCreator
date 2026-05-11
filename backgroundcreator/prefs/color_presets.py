from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor

from backgroundcreator.util.paths import app_data_dir


@dataclass(frozen=True)
class ColorPreset:
    name: str
    color: QColor


class ColorPresets:
    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or (app_data_dir() / "color_presets.json")
        self._presets: list[ColorPreset] = []
        self.load()

    @property
    def presets(self) -> list[ColorPreset]:
        return list(self._presets)

    def add(self, name: str, color: QColor) -> None:
        self._presets.append(ColorPreset(name=name, color=QColor(color)))
        self.save()

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._presets):
            self._presets.pop(index)
            self.save()

    def load(self) -> None:
        if not self._file_path.exists():
            self._presets = [
                ColorPreset("White", QColor("#ffffff")),
                ColorPreset("Black", QColor("#000000")),
                ColorPreset("Red", QColor("#ff3b30")),
                ColorPreset("Blue", QColor("#007aff")),
            ]
            self.save()
            return

        data = json.loads(self._file_path.read_text(encoding="utf-8"))
        presets: list[ColorPreset] = []
        for item in data.get("presets", []):
            name = str(item.get("name", "Preset"))
            value = str(item.get("color", "#ffffff"))
            presets.append(ColorPreset(name=name, color=QColor(value)))
        self._presets = presets

    def save(self) -> None:
        payload = {
            "presets": [{"name": p.name, "color": p.color.name(QColor.HexArgb)} for p in self._presets]
        }
        self._file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

