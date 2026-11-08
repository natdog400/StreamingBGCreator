"""Headless smoke test that builds the real MainWindow and drives core features.

Covers: window construction, solid background colour, layer effects (colorize)
serialization + restore, save/load round-trip, frame export, FPS cap and
fit/fill. Skips itself when Qt cannot load a platform plugin.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_RUNTIME_DIR", tempfile.mkdtemp(prefix="qt-runtime-"))

try:
    from PySide6.QtGui import QColor

    from backgroundcreator.gui.layers import ParticleLayerItem, PulsingGlowEffect, TextEffect, TextLayerItem
    from backgroundcreator.gui.main_window import MainWindow
    from backgroundcreator.layout.layout_io import save_layout_file
    from PySide6.QtWidgets import (
        QApplication,
        QColorDialog,
        QFileDialog,
        QGraphicsColorizeEffect,
        QMessageBox,
    )

    QT_OK = True
    QT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on host libraries
    QT_OK = False
    QT_ERROR = exc


def _patch(obj: object, name: str, value: object) -> None:
    try:
        setattr(obj, name, staticmethod(value))
    except Exception:  # pragma: no cover - some bindings refuse assignment
        pass


@unittest.skipUnless(QT_OK, f"Qt unavailable: {QT_ERROR}")
class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        _patch(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
        _patch(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
        _patch(QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok)
        cls.window = MainWindow()

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="bgcreator-smoke-")
        self.window._clear_monitor_layout(0)
        self.scene = self.window._current_scene()

    def tearDown(self) -> None:
        try:
            self.window._clear_monitor_layout(0)
        except Exception:
            pass
        self.app.processEvents()

    def test_window_builds(self) -> None:
        self.assertTrue(self.window._monitor_editors)
        self.assertIs(self.window._current_editor(), self.window._monitor_editors[0])
        rect = self.scene.sceneRect()
        self.assertGreater(rect.width(), 0.0)
        self.assertGreater(rect.height(), 0.0)
        self.assertTrue(self.window.windowTitle())

    def test_background_colour_roundtrip(self) -> None:
        self.scene.set_background_color(QColor("#112233"))
        state = self.scene.background_state()
        self.assertEqual(state.kind, "color")
        self.assertEqual(QColor(str(state.color)).name(), "#112233")
        payload = self.window._serialize_layout()
        bg = payload["monitors"][0]["background"]
        self.assertEqual(bg["kind"], "color")
        self.assertEqual(QColor(str(bg["color"])).name(), "#112233")

    def test_layers_effects_save_and_load(self) -> None:
        text = TextLayerItem("Smoke test", 1)
        text.setPos(40, 40)
        self.window._add_layer_item(text, "Smoke text")
        particles = ParticleLayerItem(300.0, 200.0)
        particles.setPos(10, 10)
        self.window._add_layer_item(particles, "Smoke particles")
        particles.set_effect("blur", {"radius": 4.0})
        particles.set_effect("colorize", {"color": QColor("#ff8800"), "strength": 0.75})

        self.scene.set_background_color(QColor("#223344"))
        payload = self.window._serialize_layout()
        blob = json.dumps(payload)
        self.assertIn("colorize", blob)

        path = str(Path(self.tmp) / "layout.json")
        save_layout_file(path, payload)
        self.assertTrue(Path(path).exists())

        self.window._clear_monitor_layout(0)
        self.assertTrue(self.window._load_layout_from_path(path))

        state = self.window._monitor_states[0]
        texts = [it for it in state.items.values() if isinstance(it, TextLayerItem)]
        self.assertTrue(texts, "text layer was not restored")
        self.assertEqual(texts[0].text(), "Smoke test")

        parts = [it for it in state.items.values() if isinstance(it, ParticleLayerItem)]
        self.assertTrue(parts, "particle layer was not restored")
        effect = parts[0].graphicsEffect()
        self.assertTrue(
            isinstance(effect, QGraphicsColorizeEffect),
            f"colorize effect was not restored (got {type(effect).__name__})",
        )

        restored_bg = self.window._monitor_editors[0].scene.background_state()
        self.assertEqual(restored_bg.kind, "color")
        self.assertEqual(QColor(str(restored_bg.color)).name(), "#223344")

    def test_export_frame_writes_png(self) -> None:
        text = TextLayerItem("Export", 3)
        self.window._add_layer_item(text, "Export text")
        target = Path(self.tmp) / "frame.png"
        _patch(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "PNG Image (*.png)"))
        self.window._export_frame_image()
        self.assertTrue(target.exists(), "exported frame was not written")
        self.assertGreater(target.stat().st_size, 500)

    def test_fps_cap_and_fit_fill(self) -> None:
        self.window._apply_fps_cap(24)
        self.assertEqual(self.window._current_scene().fps_cap(), 24)
        self.window._apply_fps_cap(60)
        self.assertEqual(self.window._current_scene().fps_cap(), 60)

        item = TextLayerItem("Fit me", 4)
        self.window._add_layer_item(item, "Fit layer")
        item.setScale(0.2)
        item.setSelected(True)
        self.window._fit_selected_to_canvas("fill")
        self.assertGreater(item.scale(), 0.0)
        item.setSelected(True)
        self.window._fit_selected_to_canvas("fit")
        self.assertGreater(item.scale(), 0.0)

    def test_view_zoom(self) -> None:
        editor = self.window._current_editor()
        view = getattr(editor, "view", None) or getattr(editor, "_view", None)
        if view is None or not hasattr(view, "zoom_in"):
            self.skipTest("view zoom API not found")
        before = float(view.transform().m11())
        view.zoom_in()
        self.assertGreater(float(view.transform().m11()), before)

    def test_background_colour_dialog_path(self) -> None:
        _patch(QColorDialog, "getColor", lambda *a, **k: QColor("#0a0b0c"))
        self.window._set_background_color()
        state = self.window._current_scene().background_state()
        self.assertEqual(state.kind, "color")
        self.assertEqual(QColor(str(state.color)).name(), "#0a0b0c")

    def test_clearing_layout_does_not_warn(self) -> None:
        """Removing a layer that is not attached to the scene must not warn."""
        from PySide6.QtCore import qInstallMessageHandler

        messages: list[str] = []
        previous = qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
        try:
            scene = self.window._current_scene()
            attached = scene.add_text_layer()
            self.window._add_layer_item(attached, "Attached layer")
            detached = TextLayerItem("Detached", 99)
            self.window._add_layer_item(detached, "Detached layer")
            self.window._clear_monitor_layout(0)
            self.window._clear_monitor_layout(0)
        finally:
            qInstallMessageHandler(previous)
        bad = [m for m in messages if "removeItem" in m]
        self.assertEqual(bad, [], f"Qt emitted removeItem warnings: {bad}")

    def test_theme_application_emits_no_font_warnings(self) -> None:
        """Re-applying the app stylesheet must not emit QFont::setPointSize warnings."""
        from PySide6.QtCore import qInstallMessageHandler

        messages: list[str] = []
        previous = qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
        try:
            base = self.app.styleSheet()
            self.window._apply_gui_theme_styles()
            self.app.setStyleSheet(base + "\nQComboBox { padding: 2px; }")
            self.app.processEvents()
            self.app.setStyleSheet(base)
            self.app.processEvents()
        finally:
            qInstallMessageHandler(previous)
        bad = [m for m in messages if "setPointSize" in m]
        self.assertEqual(bad, [], f"Qt emitted font-size warnings: {bad}")

    def test_pixel_sized_font_shows_real_point_size(self) -> None:
        """A font sized in pixels must not collapse the size spinner to its floor."""
        import dataclasses

        from PySide6.QtGui import QFont

        scene = self.window._current_scene()
        item = scene.add_text_layer()
        item.set_text("pixel sized")
        style = item.style()
        pixel_font = QFont("Sans Serif")
        pixel_font.setPixelSize(40)
        self.assertEqual(pixel_font.pointSize(), -1)
        if dataclasses.is_dataclass(style):
            item.set_style(dataclasses.replace(style, font=pixel_font))
        else:
            item.set_style(style.__class__(**{**style.__dict__, "font": pixel_font}))

        self.window._sync_text_to_ui(item)
        shown = self.window._spin_font_size.value()
        self.assertEqual(shown, 30)  # 40px at 96 DPI

    def test_every_animated_text_effect_renders(self) -> None:
        """Each new text effect must animate, render and keep its geometry."""
        import dataclasses

        from PySide6.QtGui import QImage, QPainter

        scene = self.window._current_scene()
        item = scene.add_text_layer()
        item.set_text("Effects")
        base = item.style()
        for effect in (TextEffect.SHIMMER, TextEffect.NEON, TextEffect.GLITCH, TextEffect.LEVITATE):
            item.set_style(dataclasses.replace(base, effect=effect))
            self.assertTrue(item.needs_animation(), f"{effect.value} does not animate")
            item.advance_time(0.3)
            self.assertGreater(item.boundingRect().width(), 0.0)
            image = QImage(240, 120, QImage.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            try:
                item.paint(painter, None)
            finally:
                painter.end()

    def test_new_text_effect_serializes(self) -> None:
        import dataclasses

        text = TextLayerItem("Neon", 11)
        text.set_style(dataclasses.replace(text.style(), effect=TextEffect.NEON))
        self.window._add_layer_item(text, "Neon text")
        blob = json.dumps(self.window._serialize_layout())
        self.assertIn('"effect": "neon"', blob)

    def test_particle_presets_apply(self) -> None:
        particles = ParticleLayerItem(300.0, 200.0)
        self.window._add_layer_item(particles, "Preset particles")
        particles.setSelected(True)
        names = {
            self.window._combo_particle_preset.itemText(i): i
            for i in range(self.window._combo_particle_preset.count())
        }
        for name in ("Fire", "Bubbles", "Confetti", "Sparkle", "Smoke"):
            self.assertIn(name, names, f"{name} preset missing")
            self.window._combo_particle_preset.setCurrentIndex(names[name])
            self.window._apply_particle_preset()
            self.assertGreater(particles.count, 0, f"{name} preset left no particles")

    def test_glow_pulse_effect_roundtrip(self) -> None:
        particles = ParticleLayerItem(200.0, 150.0)
        self.window._add_layer_item(particles, "Pulsing particles")
        particles.set_effect("glow_pulse", {"radius": 30.0, "speed": 1.5, "color": QColor("#ff00ff")})
        effect = particles.graphicsEffect()
        self.assertIsInstance(effect, PulsingGlowEffect)
        first = effect.blurRadius()
        effect.advance_time(0.25)
        self.assertNotEqual(first, effect.blurRadius(), "pulsing glow did not animate")

        path = str(Path(self.tmp) / "pulse.json")
        save_layout_file(path, self.window._serialize_layout())
        self.window._clear_monitor_layout(0)
        self.assertTrue(self.window._load_layout_from_path(path))
        restored = [
            it for it in self.window._monitor_states[0].items.values()
            if isinstance(it, ParticleLayerItem)
        ]
        self.assertTrue(restored, "pulsing particle layer was not restored")
        self.assertIsInstance(restored[0].graphicsEffect(), PulsingGlowEffect)


if __name__ == "__main__":
    unittest.main()
