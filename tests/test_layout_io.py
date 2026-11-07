from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backgroundcreator.layout.layout_io import LAYOUT_VERSION, load_layout_file, save_layout_file


class LayoutIoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_round_trip_preserves_payload(self) -> None:
        payload = {"monitors": [{"layers": [{"type": "text", "text": "hi"}]}], "follow_paths": {"path1": [[0, 0]]}}
        path = self.dir / "layout.json"
        save_layout_file(str(path), payload)
        loaded = load_layout_file(str(path))
        self.assertEqual(loaded.version, LAYOUT_VERSION)
        self.assertEqual(loaded.payload["monitors"], payload["monitors"])
        self.assertEqual(loaded.payload["follow_paths"], payload["follow_paths"])

    def test_version_is_stamped(self) -> None:
        path = self.dir / "stamped.json"
        save_layout_file(str(path), {"monitors": []})
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], LAYOUT_VERSION)

    def test_explicit_version_is_kept(self) -> None:
        path = self.dir / "explicit.json"
        save_layout_file(str(path), {"version": 7, "monitors": []})
        self.assertEqual(load_layout_file(str(path)).version, 7)

    def test_unicode_paths_and_text_round_trip(self) -> None:
        path = self.dir / "Éevee layout ✓.json"
        save_layout_file(str(path), {"text": "émoji 🎨"})
        self.assertEqual(load_layout_file(str(path)).payload["text"], "émoji 🎨")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(OSError):
            load_layout_file(str(self.dir / "nope.json"))


if __name__ == "__main__":
    unittest.main()
