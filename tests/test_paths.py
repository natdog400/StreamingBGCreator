from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backgroundcreator.util import paths


class AppDataDirTests(unittest.TestCase):
    def test_xdg_data_home_is_used_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(paths.sys, "platform", "linux"), mock.patch.dict(
                os.environ, {"XDG_DATA_HOME": tmp}, clear=False
            ):
                directory = paths.app_data_dir()
                self.assertEqual(directory, Path(tmp) / "BackgroundCreator")
                self.assertTrue(directory.is_dir())

    def test_appdata_is_used_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(paths.sys, "platform", "win32"), mock.patch.dict(
                os.environ, {"APPDATA": tmp}, clear=False
            ):
                self.assertEqual(paths.app_data_dir(), Path(tmp) / "BackgroundCreator")

    def test_project_dir_points_at_checkout(self) -> None:
        root = paths.project_dir()
        self.assertTrue((root / "main.py").exists(), root)


if __name__ == "__main__":
    unittest.main()
