from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QPointF, QRect, QRectF, QSizeF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QCloseEvent, QFont, QFontDatabase, QGuiApplication, QIcon, QImage, QKeySequence, QMovie, QPainter, QPainterPath, QPalette, QPen, QPixmap, QScreen, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QColorDialog,
    QDockWidget,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFontDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QLabel,
    QCheckBox,
    QMenu,
    QSystemTrayIcon,
    QStyle,
    QTextBrowser,
    QToolButton,
    QLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QProxyStyle,
    QStyleOptionComboBox,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsColorizeEffect,
)

from backgroundcreator.gui.editor_widget import EditorWidget
from backgroundcreator.gui.layers import BlendMode, FillMode, TextEffect, TextLayerItem, TextStyle, ImageLayerItem, VideoLayerItem, ParticleLayerItem
from backgroundcreator.gui.scene import ITEM_DATA_ANIM_MODE, ITEM_DATA_ANIM_PAYLOAD, ITEM_DATA_SOURCE_KIND, ITEM_DATA_SOURCE_PATH
from backgroundcreator.gui.wallpaper_window import WallpaperWindow
from backgroundcreator.win32.wallpaper_host import wallpaper_supported
from backgroundcreator.layout.layout_io import LAYOUT_VERSION, load_layout_file, save_layout_file
from backgroundcreator.prefs.color_presets import ColorPresets
from backgroundcreator.util.paths import app_data_dir, project_dir

ITEM_DATA_LOCKED = 0xBC10
ITEM_DATA_HIDDEN = 0xBC11


class ComboArrowProxyStyle(QProxyStyle):
    def __init__(self, base_style: QStyle | None = None) -> None:
        super().__init__(base_style)

    def drawComplexControl(
        self,
        control: QStyle.ComplexControl,
        option: QStyleOptionComboBox,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        super().drawComplexControl(control, option, painter, widget)
        if control != QStyle.ComplexControl.CC_ComboBox:
            return
        if not isinstance(option, QStyleOptionComboBox):
            return

        try:
            rect = self.subControlRect(control, option, QStyle.SubControl.SC_ComboBoxArrow, widget)
        except Exception:
            return
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            color = QColor(option.palette.color(QPalette.ColorRole.Text))
            if not (option.state & QStyle.StateFlag.State_Enabled):
                color.setAlpha(max(30, int(color.alpha() * 0.55)))

            cx = float(rect.center().x())
            cy = float(rect.center().y())
            s = float(min(rect.width(), rect.height())) * 0.34
            path = QPainterPath()
            path.moveTo(QPointF(cx - s, cy - (s * 0.15)))
            path.lineTo(QPointF(cx + s, cy - (s * 0.15)))
            path.lineTo(QPointF(cx, cy + (s * 0.80)))
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)
        finally:
            painter.restore()


class ArrowComboBox(QComboBox):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        opt = QStyleOptionComboBox()
        try:
            self.initStyleOption(opt)
        except Exception:
            return
        try:
            rect = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxArrow, self)
        except Exception:
            rect = QRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            rect = QRect(max(0, int(self.width()) - 22), 0, 22, int(self.height()))

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            color = QColor(self.palette().color(QPalette.ColorRole.Text))
            if not self.isEnabled():
                color.setAlpha(max(30, int(color.alpha() * 0.55)))

            cx = float(rect.center().x())
            cy = float(rect.center().y())
            s = float(min(rect.width(), rect.height())) * 0.34
            path = QPainterPath()
            path.moveTo(QPointF(cx - s, cy - (s * 0.15)))
            path.lineTo(QPointF(cx + s, cy - (s * 0.15)))
            path.lineTo(QPointF(cx, cy + (s * 0.80)))
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)
        finally:
            painter.end()


class CollapsibleBox(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet("QToolButton { border: none; text-align: left; font-weight: bold; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle_button.clicked.connect(self.on_pressed)
        self.toggle_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.content_area = QWidget()
        self.content_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(0)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.addWidget(self.toggle_button)
        self._main_layout.addWidget(self.content_area)

    def on_pressed(self) -> None:
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.content_area.setVisible(checked)

    def set_content_layout(self, layout: QLayout) -> None:
        self.content_area.setLayout(layout)


class ResettableDockWidget(QDockWidget):
    def __init__(
        self,
        title: str,
        parent: QMainWindow,
        default_area: Qt.DockWidgetArea,
        on_close: Callable[[QDockWidget], None],
    ) -> None:
        super().__init__(title, parent)
        self._default_area = default_area
        self._on_close = on_close

    @property
    def default_area(self) -> Qt.DockWidgetArea:
        return self._default_area

    def closeEvent(self, event: QCloseEvent) -> None:
        parent = self.parentWidget()
        if parent is not None and getattr(parent, "_closing", False):
            event.accept()
            return
        event.ignore()
        QTimer.singleShot(0, lambda: self._on_close(self))


@dataclass
class MonitorState:
    items: dict[int, object] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    order: list[int] = field(default_factory=list)


class _SetTransformCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: object, before: tuple[float, float, float, float], after: tuple[float, float, float, float]) -> None:
        super().__init__("Transform")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._before = before
        self._after = after

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_item_transform_snapshot(self._item, self._before))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_item_transform_snapshot(self._item, self._after))


class _MultiTransformCommand(QUndoCommand):
    def __init__(
        self,
        window,
        monitor_index: int,
        label: str,
        changes: list[tuple[object, tuple[float, float, float, float], tuple[float, float, float, float]]],
    ) -> None:
        super().__init__(str(label))
        self._window = window
        self._monitor_index = int(monitor_index)
        self._changes = list(changes)

    def undo(self) -> None:
        def do() -> None:
            for item, before, _after in self._changes:
                self._window._apply_item_transform_snapshot(item, before)

        self._window._run_on_monitor(self._monitor_index, do)

    def redo(self) -> None:
        def do() -> None:
            for item, _before, after in self._changes:
                self._window._apply_item_transform_snapshot(item, after)

        self._window._run_on_monitor(self._monitor_index, do)


class _SetTextCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: TextLayerItem, before_text: str, before_style: TextStyle, after_text: str, after_style: TextStyle) -> None:
        super().__init__("Text")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._before_text = before_text
        self._before_style = before_style
        self._after_text = after_text
        self._after_style = after_style

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_text_snapshot(self._item, self._before_text, self._before_style))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_text_snapshot(self._item, self._after_text, self._after_style))


class _AddLayerCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, create_fn) -> None:
        super().__init__("Add Layer")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._create_fn = create_fn
        self._item: object | None = None
        self._label: str | None = None

    def undo(self) -> None:
        if self._item is None or self._label is None:
            return
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._remove_layer_item(self._item))

    def redo(self) -> None:
        def do():
            if self._item is None or self._label is None:
                item, label = self._create_fn()
                self._item = item
                self._label = label
            self._window._ensure_layer_item_present(self._item, self._label)
        self._window._run_on_monitor(self._monitor_index, do)


class _RemoveLayerCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: object, label: str, index: int) -> None:
        super().__init__("Delete Layer")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._label = label
        self._index = int(index)

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._restore_removed_layer_item(self._item, self._label, self._index))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._remove_layer_item(self._item))


class _ReorderLayersCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, before: list[int], after: list[int], select_gid: int | None = None) -> None:
        super().__init__("Reorder Layers")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._before = list(before)
        self._after = list(after)
        self._select_gid = select_gid

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._set_layer_order(self._before, select_gid=self._select_gid))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._set_layer_order(self._after, select_gid=self._select_gid))


class _RenameLayerLabelCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, gid: int, before: str, after: str) -> None:
        super().__init__("Rename Layer")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._gid = int(gid)
        self._before = before
        self._after = after

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._set_layer_label(self._gid, self._before))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._set_layer_label(self._gid, self._after))


class _SetLayerLockedCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: object, locked_before: bool, locked_after: bool) -> None:
        super().__init__("Lock Layer" if locked_after else "Unlock Layer")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._before = bool(locked_before)
        self._after = bool(locked_after)

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_locked(self._item, self._before))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_locked(self._item, self._after))


class _SetLayerHiddenCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: object, hidden_before: bool, hidden_after: bool) -> None:
        super().__init__("Hide Layer" if hidden_after else "Show Layer")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._before = bool(hidden_before)
        self._after = bool(hidden_after)

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_hidden(self._item, self._before))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_hidden(self._item, self._after))


class _SetLayerOpacityCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: object, before: float, after: float) -> None:
        super().__init__("Opacity")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._before = float(before)
        self._after = float(after)

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_opacity(self._item, self._before))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_opacity(self._item, self._after))


class _SetLayerBlendModeCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, item: object, before: str, after: str) -> None:
        super().__init__("Blend Mode")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._item = item
        self._before = str(before)
        self._after = str(after)

    def undo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_blend_mode(self._item, self._before))

    def redo(self) -> None:
        self._window._run_on_monitor(self._monitor_index, lambda: self._window._apply_layer_blend_mode(self._item, self._after))


class _SetMultiLayerBlendModeCommand(QUndoCommand):
    def __init__(self, window, monitor_index: int, changes: list[tuple[object, str, str]]) -> None:
        super().__init__("Blend Mode")
        self._window = window
        self._monitor_index = int(monitor_index)
        self._changes = list(changes)

    def undo(self) -> None:
        def do() -> None:
            for item, before, _after in self._changes:
                self._window._apply_layer_blend_mode(item, before)

        self._window._run_on_monitor(self._monitor_index, do)

    def redo(self) -> None:
        def do() -> None:
            for item, _before, after in self._changes:
                self._window._apply_layer_blend_mode(item, after)

        self._window._run_on_monitor(self._monitor_index, do)


class _AllMonitorsPathView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, path_item: object) -> None:
        super().__init__(scene)
        self._path_item = path_item
        self._drawing = False
        self._points: list[QPointF] = []
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.NoFrame)

    def points(self) -> list[QPointF]:
        return [QPointF(float(p.x()), float(p.y())) for p in self._points]

    def set_points(self, points: list[QPointF]) -> None:
        self._points = [QPointF(float(p.x()), float(p.y())) for p in (points or [])]
        self._update_path()

    def clear_points(self) -> None:
        self._points = []
        self._drawing = False
        self._update_path()

    def _update_path(self) -> None:
        if self._path_item is None:
            return
        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for p in self._points[1:]:
                path.lineTo(p)
        try:
            self._path_item.setPath(path)
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        try:
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drawing = True
            try:
                p = self.mapToScene(event.position().toPoint())
                self._points.append(QPointF(float(p.x()), float(p.y())))
                self._update_path()
            except Exception:
                pass
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drawing:
            try:
                p = self.mapToScene(event.position().toPoint())
                if not self._points:
                    self._points.append(QPointF(float(p.x()), float(p.y())))
                    self._update_path()
                    event.accept()
                    return
                last = self._points[-1]
                dx = float(p.x() - last.x())
                dy = float(p.y() - last.y())
                if (dx * dx) + (dy * dy) >= (3.0 * 3.0):
                    self._points.append(QPointF(float(p.x()), float(p.y())))
                    self._update_path()
                event.accept()
                return
            except Exception:
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drawing and event.button() == Qt.LeftButton:
            self._drawing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _AllMonitorsPathDialog(QDialog):
    def __init__(self, parent: QWidget, desktop_rect: QRectF, monitor_rects: list[QRectF], existing: list[QPointF]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Draw Path (All Monitors)")
        self.resize(1000, 600)

        scene = QGraphicsScene(self)
        scene.setSceneRect(QRectF(desktop_rect))

        for r in monitor_rects:
            try:
                rect_item = scene.addRect(QRectF(r))
                pen = rect_item.pen()
                pen.setColor(QColor(255, 255, 255, 160))
                pen.setWidth(2)
                rect_item.setPen(pen)
                rect_item.setBrush(QColor(0, 0, 0, 35))
            except Exception:
                pass

        path_item = scene.addPath(QPainterPath())
        try:
            pen = QPen(QColor(255, 255, 255, 230))
            pen.setWidth(3)
            pen.setCosmetic(True)
            path_item.setPen(pen)
            path_item.setZValue(10_000_000)
        except Exception:
            pass

        self._view = _AllMonitorsPathView(scene, path_item)
        self._view.set_points(existing)

        btn_clear = QPushButton("Clear")
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_clear.clicked.connect(self._view.clear_points)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_clear)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)

        layout = QVBoxLayout()
        layout.addWidget(self._view)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        try:
            self._view.fitInView(self._view.sceneRect(), Qt.KeepAspectRatio)
        except Exception:
            pass

    def points(self) -> list[QPointF]:
        return self._view.points()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._closing = False
        self.setWindowTitle("<3Eevee's_BG_Creator<3")
        self.resize(1200, 750)

        app = QApplication.instance()
        self._ensure_combo_arrow_style()
        self._default_app_font = QFont(app.font()) if app is not None else QFont()
        self._base_app_stylesheet = str(app.styleSheet()) if app is not None else ""
        self._gui_theme: dict[str, object] = {
            "buttons": None,
            "outer": None,
            "inner": None,
            "panel_bg": None,
            "text_area_bg": None,
            "text": None,
            "accent": None,
            "border": None,
            "hover": None,
            "pressed": None,
            "tab_active": None,
            "tab_inactive": None,
            "scroll_track": None,
            "scroll_thumb": None,
            "corner_radius": None,
            "control_padding": None,
            "ui_font": None,
            "ui_font_family": None,
            "ui_font_size": None,
        }

        self._screens: list[QScreen] = list(QGuiApplication.screens())
        min_x = 0
        min_y = 0
        max_x = 0
        max_y = 0
        if self._screens:
            try:
                min_x = min(int(s.geometry().x()) for s in self._screens)
                min_y = min(int(s.geometry().y()) for s in self._screens)
                max_x = max(int(s.geometry().x() + s.geometry().width()) for s in self._screens)
                max_y = max(int(s.geometry().y() + s.geometry().height()) for s in self._screens)
            except Exception:
                min_x = 0
                min_y = 0
                max_x = 0
                max_y = 0
        self._virtual_origin = (float(min_x), float(min_y))
        self._virtual_desktop_rect = QRectF(0.0, 0.0, float(max_x - min_x), float(max_y - min_y))
        self._monitor_global_rects: dict[int, QRectF] = {}
        for i, screen in enumerate(self._screens):
            geo = screen.geometry()
            self._monitor_global_rects[i] = QRectF(
                float(int(geo.x()) - min_x),
                float(int(geo.y()) - min_y),
                float(int(geo.width())),
                float(int(geo.height())),
            )
        self._global_path_points: list[QPointF] = []
        self._follow_paths: dict[str, list[QPointF]] = {"path1": [], "path2": [], "path3": [], "path4": []}
        self._monitor_tabs = QTabWidget()
        self._monitor_tabs.setDocumentMode(True)
        self._monitor_tabs.setMovable(False)
        self._monitor_editors: list[EditorWidget] = []
        self._monitor_states: dict[int, MonitorState] = {}
        self._wallpaper_windows: dict[int, WallpaperWindow] = {}
        for i, screen in enumerate(self._screens):
            geo = screen.geometry()
            scene_rect = QRectF(0, 0, geo.width(), geo.height())
            editor = EditorWidget(scene_rect)
            self._monitor_editors.append(editor)
            self._monitor_states[i] = MonitorState()
            self._monitor_tabs.addTab(editor, self._monitor_label(screen, i))
            try:
                editor.scene.item_transform_committed.connect(self._on_item_transform_committed)
            except Exception:
                pass
            try:
                editor.view.transform_committed.connect(self._on_item_transform_committed)
            except Exception:
                pass
        scenes_registry: dict[int, object] = {}
        for i, editor in enumerate(self._monitor_editors):
            scenes_registry[i] = editor.scene
        for i, editor in enumerate(self._monitor_editors):
            try:
                editor.scene.configure_virtual_desktop(
                    monitor_index=i,
                    monitor_global_rect=self._monitor_global_rects.get(i, QRectF()),
                    virtual_desktop_rect=self._virtual_desktop_rect,
                    scenes_registry=scenes_registry,
                )
                editor.scene.set_global_paths(self._follow_paths)
            except Exception:
                pass

        self.setCentralWidget(self._monitor_tabs)
        self._connected_scene = None

        self._undo_stack = QUndoStack(self)
        self._undo_blocked = False
        self._transform_baseline: tuple[int, int, tuple[float, float, float, float]] | None = None
        self._opacity_baseline: tuple[int, int, float] | None = None
        self._text_undo_timer = QTimer(self)
        self._text_undo_timer.setSingleShot(True)
        self._text_undo_timer.timeout.connect(self._commit_text_undo)
        self._pending_text_undo: tuple[int, int, str, TextStyle] | None = None
        self._transform_undo_timer = QTimer(self)
        self._transform_undo_timer.setSingleShot(True)
        self._transform_undo_timer.timeout.connect(self._commit_transform_undo)
        self._opacity_undo_timer = QTimer(self)
        self._opacity_undo_timer.setSingleShot(True)
        self._opacity_undo_timer.timeout.connect(self._commit_opacity_undo)
        self._label_baseline: tuple[int, int, str] | None = None
        self._label_undo_timer = QTimer(self)
        self._label_undo_timer.setSingleShot(True)
        self._label_undo_timer.timeout.connect(self._commit_label_undo)
        self._layers_order_before: list[int] | None = None
        self._selection_primary_gid: dict[int, int] = {}
        self._selection_prev_gids: dict[int, set[int]] = {}

        self._layers_list = QListWidget()
        self._layers_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._layers_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._layers_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list_item_by_gid: dict[int, QListWidgetItem] = {}
        self._updating_layers_list = False

        self._color_presets = ColorPresets()

        self._layout_cycles_path = app_data_dir() / "layout_cycles.json"
        self._layout_cycles: dict[int, dict] = {}
        self._cycle_timers: dict[int, QTimer] = {}
        for i in range(len(self._screens)):
            timer = QTimer(self)
            timer.setSingleShot(False)
            timer.timeout.connect(lambda i=i: self._cycle_next_layout(monitor_index=i, from_timer=True))
            self._cycle_timers[i] = timer
        self._load_layout_cycles()

        self._keep_running_on_close = False
        self._tray: QSystemTrayIcon | None = None
        self._ui_state_path = app_data_dir() / "ui_state.json"
        self._autosave_path = app_data_dir() / "autosave.json"
        self._recent_layouts: list[str] = []
        self._fps_cap = 30
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60_000)
        self._autosave_timer.timeout.connect(self._autosave_now)
        self._autosave_last_json: str | None = None

        self._build_actions()
        self._build_ui()
        self._restore_ui_state()
        self._wire()
        try:
            self._toggle_anim_avoid_taskbar(bool(self._chk_anim_avoid_taskbar.isChecked()))
        except Exception:
            pass
        self._refresh_animation_controls()
        self._install_shortcuts()
        self._on_monitor_changed(self._monitor_tabs.currentIndex())
        self._apply_fps_cap(self._fps_cap)
        self._update_recent_menu()
        self._autosave_timer.start()

    def _build_actions(self) -> None:
        self._act_undo = self._undo_stack.createUndoAction(self, "Undo")
        self._act_redo = self._undo_stack.createRedoAction(self, "Redo")
        try:
            self._act_undo.setShortcut(QKeySequence.Undo)
            self._act_redo.setShortcut(QKeySequence.Redo)
        except Exception:
            pass

        self._act_save_layout = QAction("Save Layout…", self)
        self._act_load_layout = QAction("Load Layout…", self)
        self._act_export_packaged_layout = QAction("Export Packaged Layout…", self)
        self._act_export_frame = QAction("Export Frame as Image…", self)
        self._act_recover_autosave = QAction("Recover Autosave", self)
        self._act_open_background = QAction("Open Background…", self)
        self._act_background_color = QAction("Background Color…", self)
        self._act_quit = QAction("Quit", self)
        try:
            self._act_quit.setShortcut(QKeySequence.Quit)
        except Exception:
            pass
        self._act_desktop_preview = QAction("Desktop Preview", self)
        self._act_desktop_preview.setCheckable(True)
        self._act_keep_running = QAction("Keep Wallpaper Running On Close", self)
        self._act_keep_running.setCheckable(True)
        self._act_set_wallpaper_current = QAction("Set Wallpaper (This Monitor)", self)
        self._act_unset_wallpaper_current = QAction("Stop Wallpaper (This Monitor)", self)
        self._act_set_wallpaper = QAction("Set as Wallpaper", self)
        self._act_unset_wallpaper = QAction("Stop Wallpaper", self)
        self._act_unset_wallpaper_current.setEnabled(False)
        self._act_unset_wallpaper.setEnabled(False)

        self._act_show_hotkeys = QAction("Hotkeys", self)
        self._act_zoom_in = QAction("Zoom In", self)
        self._act_zoom_out = QAction("Zoom Out", self)
        self._act_zoom_reset = QAction("Reset Zoom", self)

        self._act_snap_grid = QAction("Snap Grid", self)
        self._act_snap_grid.setCheckable(True)
        self._act_snap_center = QAction("Snap Center", self)
        self._act_snap_center.setCheckable(True)
        self._act_show_grid = QAction("Show Grid", self)
        self._act_show_grid.setCheckable(True)

        self._act_duplicate_layer = QAction("Duplicate Layer", self)
        self._act_bring_forward = QAction("Bring Forward", self)
        self._act_send_backward = QAction("Send Backward", self)
        self._act_bring_to_front = QAction("Bring To Front", self)
        self._act_send_to_back = QAction("Send To Back", self)
        self._act_toggle_lock = QAction("Toggle Lock", self)
        self._act_toggle_hide = QAction("Toggle Hide", self)

        self._act_theme_buttons = QAction("Buttons", self)
        self._act_theme_outer = QAction("GUI Outer", self)
        self._act_theme_inner = QAction("GUI Inner", self)
        self._act_theme_panel_bg = QAction("Panel Background", self)
        self._act_theme_text_area_bg = QAction("Text Area Background", self)
        self._act_theme_text = QAction("Word Color", self)
        self._act_theme_accent = QAction("Accent / Selection", self)
        self._act_theme_border = QAction("Borders / Dividers", self)
        self._act_theme_hover = QAction("Hover Color", self)
        self._act_theme_pressed = QAction("Pressed Color", self)
        self._act_theme_tab_active = QAction("Tab Active", self)
        self._act_theme_tab_inactive = QAction("Tab Inactive", self)
        self._act_theme_scroll_track = QAction("Scrollbar Track", self)
        self._act_theme_scroll_thumb = QAction("Scrollbar Thumb", self)
        self._act_theme_ui_font = QAction("UI Font…", self)
        self._act_theme_control_padding = QAction("Control Padding…", self)
        self._act_theme_corner_radius = QAction("Corner Radius…", self)
        self._act_theme_preset_lavender = QAction("Lavender", self)
        self._act_theme_preset_dark = QAction("Dark", self)
        self._act_theme_preset_light = QAction("Light", self)
        self._act_theme_preset_midnight = QAction("Midnight", self)
        self._act_theme_reset = QAction("Reset GUI Colors", self)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        try:
            if event.type() in (
                QEvent.Type.WindowStateChange,
                QEvent.Type.ActivationChange,
                QEvent.Type.Show,
                QEvent.Type.Hide,
            ):
                self._refresh_scene_activity()
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_scene_activity()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._refresh_scene_activity()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_ui_state()
        if not self._closing and self._keep_running_on_close:
            tray_ok = self._ensure_tray()
            if tray_ok:
                event.ignore()
                self.hide()
                try:
                    self._tray.showMessage(
                        "<3Eevee's_BG_Creator<3",
                        "Still running in the background. Use the tray icon to reopen or quit.",
                        QSystemTrayIcon.Information,
                        1500,
                    )
                except Exception:
                    pass
                return

            event.ignore()
            self.showMinimized()
            self.setWindowState(self.windowState() | Qt.WindowMinimized)
            return

        self._closing = True
        try:
            for timer in self._cycle_timers.values():
                timer.stop()
        except Exception:
            pass
        try:
            self._unset_wallpaper()
        except Exception:
            pass
        super().closeEvent(event)

    def _ensure_tray(self) -> bool:
        if self._tray is not None:
            return True
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        tray = QSystemTrayIcon(self)
        try:
            tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon))
        except Exception:
            tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        act_show = QAction("Show", self)
        act_quit = QAction("Quit", self)
        act_show.triggered.connect(self._show_from_tray)
        act_quit.triggered.connect(self._quit_from_tray)
        menu.addAction(act_show)
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.setToolTip("<3Eevee's_BG_Creator<3")
        tray.show()
        self._tray = tray
        return tray.isVisible()

    def _show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_scene_activity()

    def _quit_from_tray(self) -> None:
        self._closing = True
        # Quitting skips closeEvent, so persist window/theme state and tear the
        # wallpaper windows down here as well.
        try:
            self._save_ui_state()
        except Exception:
            pass
        try:
            self._unset_wallpaper()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_from_tray()

    def _toggle_keep_running(self, enabled: bool) -> None:
        self._keep_running_on_close = bool(enabled)
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(not self._keep_running_on_close)
        if self._keep_running_on_close:
            self._ensure_tray()
        else:
            if self._tray is not None:
                try:
                    self._tray.hide()
                except Exception:
                    pass
                self._tray = None

    def _restore_ui_state(self) -> None:
        if not self._ui_state_path.exists():
            return
        try:
            data = json.loads(self._ui_state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        geom = data.get("geometry")
        if isinstance(geom, str) and geom:
            try:
                self.restoreGeometry(bytes.fromhex(geom))
            except Exception:
                pass
        state = data.get("state")
        if isinstance(state, str) and state:
            try:
                self.restoreState(bytes.fromhex(state))
            except Exception:
                pass
        self._load_gui_theme(data.get("gui_theme"))
        paths = data.get("last_background_paths")
        if isinstance(paths, list):
            for i, p in enumerate(paths):
                if isinstance(p, str) and p.strip() and Path(p).exists() and i < len(self._monitor_editors):
                    try:
                        self._monitor_editors[i].scene.set_background(p)
                    except Exception:
                        continue
        colors = data.get("last_background_colors")
        if isinstance(colors, list):
            for i, c in enumerate(colors):
                if not isinstance(c, str) or not c.strip() or i >= len(self._monitor_editors):
                    continue
                has_path = (
                    isinstance(paths, list)
                    and i < len(paths)
                    and isinstance(paths[i], str)
                    and bool(paths[i].strip())
                )
                if has_path:
                    continue
                try:
                    self._monitor_editors[i].scene.set_background_color(QColor(c))
                except Exception:
                    continue
        try:
            saved_fps = int(data.get("fps_cap", 0) or 0)
        except Exception:
            saved_fps = 0
        if saved_fps > 0:
            self._apply_fps_cap(saved_fps)
        recents = data.get("recent_layouts")
        if isinstance(recents, list):
            self._recent_layouts = [str(p) for p in recents if isinstance(p, str) and p.strip()][:8]
            self._update_recent_menu()

    def _save_ui_state(self) -> None:
        try:
            self._ui_state_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        bg_paths: list[str | None] = []
        bg_colors: list[str | None] = []
        try:
            for editor in self._monitor_editors:
                try:
                    scene = editor.scene
                    st = getattr(scene, "_background_state", None)
                    p = getattr(st, "path", None)
                    bg_paths.append(str(p) if p is not None else None)
                    c = getattr(st, "color", None)
                    bg_colors.append(str(c) if c else None)
                except Exception:
                    bg_paths.append(None)
                    bg_colors.append(None)
        except Exception:
            bg_paths = []
            bg_colors = []
        data = {
            "geometry": bytes(self.saveGeometry()).hex(),
            "state": bytes(self.saveState()).hex(),
            "gui_theme": self._serialize_gui_theme(),
            "last_background_paths": bg_paths,
            "last_background_colors": bg_colors,
            "fps_cap": int(self._fps_cap),
            "recent_layouts": list(self._recent_layouts),
        }
        try:
            self._ui_state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _serialize_gui_theme(self) -> dict[str, object]:
        out: dict[str, object] = {}
        for k, v in (self._gui_theme or {}).items():
            if not isinstance(k, str) or not k:
                continue
            if isinstance(v, QColor) and v.isValid():
                try:
                    out[str(k)] = str(v.name(QColor.NameFormat.HexArgb))
                except Exception:
                    continue
            elif isinstance(v, (int, float, str)) and v != "":
                out[str(k)] = v
        return out

    def _load_gui_theme(self, data: object) -> None:
        if not isinstance(data, dict):
            self._apply_gui_theme_styles()
            self._refresh_theme_toolbar_icons()
            return
        color_keys = (
            "buttons",
            "outer",
            "inner",
            "panel_bg",
            "text_area_bg",
            "text",
            "accent",
            "border",
            "hover",
            "pressed",
            "tab_active",
            "tab_inactive",
            "scroll_track",
            "scroll_thumb",
        )
        for k in color_keys:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                c = QColor(v.strip())
                self._gui_theme[k] = c if c.isValid() else None
            else:
                self._gui_theme[k] = None

        try:
            cr = data.get("corner_radius")
            self._gui_theme["corner_radius"] = float(cr) if cr is not None else None
        except Exception:
            self._gui_theme["corner_radius"] = None
        try:
            cp = data.get("control_padding")
            self._gui_theme["control_padding"] = int(cp) if cp is not None else None
        except Exception:
            self._gui_theme["control_padding"] = None

        uf = data.get("ui_font")
        self._gui_theme["ui_font"] = str(uf) if isinstance(uf, str) and uf.strip() else None
        ff = data.get("ui_font_family")
        self._gui_theme["ui_font_family"] = str(ff) if isinstance(ff, str) and ff.strip() else None
        try:
            fs = data.get("ui_font_size")
            self._gui_theme["ui_font_size"] = int(fs) if fs is not None else None
        except Exception:
            self._gui_theme["ui_font_size"] = None
        self._apply_gui_theme_styles()
        self._refresh_theme_toolbar_icons()

    def _ensure_combo_arrow_style(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        try:
            current = app.style()
        except Exception:
            return
        try:
            if isinstance(current, ComboArrowProxyStyle):
                return
        except Exception:
            pass
        try:
            app.setStyle(ComboArrowProxyStyle(current))
        except Exception:
            pass

    def _css_rgba(self, c: QColor) -> str:
        cc = QColor(c)
        return f"rgba({int(cc.red())}, {int(cc.green())}, {int(cc.blue())}, {int(cc.alpha())})"

    def _auto_text_color(self, c: QColor) -> QColor:
        cc = QColor(c)
        r = float(cc.red())
        g = float(cc.green())
        b = float(cc.blue())
        lum = (0.299 * r) + (0.587 * g) + (0.114 * b)
        return QColor(255, 255, 255) if lum < 150.0 else QColor(0, 0, 0)

    def _apply_gui_theme_styles(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._ensure_combo_arrow_style()

        buttons = self._gui_theme.get("buttons")
        outer = self._gui_theme.get("outer")
        inner = self._gui_theme.get("inner")
        panel_bg = self._gui_theme.get("panel_bg")
        text_area_bg = self._gui_theme.get("text_area_bg")
        text = self._gui_theme.get("text")
        accent = self._gui_theme.get("accent")
        border = self._gui_theme.get("border")
        hover = self._gui_theme.get("hover")
        pressed = self._gui_theme.get("pressed")
        tab_active = self._gui_theme.get("tab_active")
        tab_inactive = self._gui_theme.get("tab_inactive")
        scroll_track = self._gui_theme.get("scroll_track")
        scroll_thumb = self._gui_theme.get("scroll_thumb")
        corner_radius = self._gui_theme.get("corner_radius")
        control_padding = self._gui_theme.get("control_padding")
        ui_font = self._gui_theme.get("ui_font")
        ui_font_family = self._gui_theme.get("ui_font_family")
        ui_font_size = self._gui_theme.get("ui_font_size")

        def valid_color(v: object) -> bool:
            return isinstance(v, QColor) and v.isValid()

        def down_arrow_png_data_url(c: QColor) -> str:
            pm = QPixmap(10, 10)
            pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pm)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                cc = QColor(c)
                cc.setAlpha(255)
                pen = QPen(cc)
                pen.setWidthF(1.6)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                path = QPainterPath()
                path.moveTo(2.0, 3.5)
                path.lineTo(5.0, 6.5)
                path.lineTo(8.0, 3.5)
                painter.drawPath(path)
            finally:
                try:
                    painter.end()
                except Exception:
                    pass

            payload = QByteArray()
            buf = QBuffer(payload)
            try:
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                pm.save(buf, "PNG")
            finally:
                try:
                    buf.close()
                except Exception:
                    pass
            b64 = str(bytes(payload.toBase64()), encoding="ascii")
            return f"data:image/png;base64,{b64}"

        any_custom = any(
            valid_color(v)
            for v in (
                buttons,
                outer,
                inner,
                panel_bg,
                text_area_bg,
                text,
                accent,
                border,
                hover,
                pressed,
                tab_active,
                tab_inactive,
                scroll_track,
                scroll_thumb,
            )
        ) or any(v is not None for v in (corner_radius, control_padding, ui_font, ui_font_family, ui_font_size))
        if not any_custom:
            base = str(self._base_app_stylesheet or "")
            extra = """
            QComboBox::drop-down, QFontComboBox::drop-down {
                width: 22px;
            }
            QComboBox::down-arrow, QFontComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }
            """
            try:
                app.setStyleSheet("\n".join((base, extra)))
            except Exception:
                pass
            try:
                app.setFont(QFont(self._default_app_font))
            except Exception:
                pass
            return

        rules: list[str] = []
        text_override = QColor(text) if valid_color(text) else None
        panel_bg_color = QColor(panel_bg) if valid_color(panel_bg) else None
        text_area_bg_color = QColor(text_area_bg) if valid_color(text_area_bg) else None
        accent_color = QColor(accent) if valid_color(accent) else None
        border_color = QColor(border) if valid_color(border) else None
        hover_color = QColor(hover) if valid_color(hover) else None
        pressed_color = QColor(pressed) if valid_color(pressed) else None

        radius_px: float | None = None
        if isinstance(corner_radius, (int, float)):
            try:
                radius_px = float(corner_radius)
            except Exception:
                radius_px = None
        if radius_px is not None:
            radius_px = max(0.0, radius_px)

        padding_px: int | None = None
        if isinstance(control_padding, int):
            padding_px = max(0, int(control_padding))

        font = QFont(self._default_app_font)
        if isinstance(ui_font, str) and ui_font.strip():
            try:
                f = QFont()
                if f.fromString(ui_font.strip()):
                    font = QFont(f)
            except Exception:
                pass
        if not (isinstance(ui_font, str) and ui_font.strip()):
            if isinstance(ui_font_family, str) and ui_font_family.strip():
                try:
                    font.setFamily(ui_font_family.strip())
                except Exception:
                    pass
            if isinstance(ui_font_size, int) and int(ui_font_size) > 0:
                try:
                    font.setPointSize(int(ui_font_size))
                except Exception:
                    pass
        try:
            app.setFont(font)
        except Exception:
            pass

        font_rule_bits: list[str] = []
        try:
            ff = str(font.family() or "").strip()
            if ff:
                ff_css = ff.replace('"', '\\"')
                font_rule_bits.append(f' font-family: "{ff_css}";')
        except Exception:
            pass
        try:
            ps = int(font.pointSize())
            if ps > 0:
                font_rule_bits.append(f" font-size: {ps}pt;")
        except Exception:
            pass
        try:
            w = int(font.weight())
            if w > 0:
                font_rule_bits.append(f" font-weight: {w};")
        except Exception:
            pass
        try:
            if bool(font.italic()):
                font_rule_bits.append(" font-style: italic;")
        except Exception:
            pass
        if font_rule_bits:
            rules.append("QWidget {" + "".join(font_rule_bits) + " }")

        if accent_color is not None:
            sel_text = self._auto_text_color(accent_color)
            rules.append(
                "QWidget {"
                f" selection-background-color: {self._css_rgba(accent_color)};"
                f" selection-color: {self._css_rgba(sel_text)};"
                " }"
            )

        if isinstance(outer, QColor) and outer.isValid():
            outer_text = QColor(text_override) if text_override is not None else self._auto_text_color(outer)
            rules.append(
                "QMainWindow, QMenuBar, QToolBar {"
                f" background-color: {self._css_rgba(outer)};"
                f" color: {self._css_rgba(outer_text)};"
                " }"
            )
            rules.append(
                "QDockWidget {"
                f" background-color: {self._css_rgba(outer)};"
                f" color: {self._css_rgba(outer_text)};"
                " }"
            )
            rules.append(
                "QDockWidget::title {"
                f" background-color: {self._css_rgba(outer.darker(115))};"
                f" color: {self._css_rgba(outer_text)};"
                " }"
            )
            rules.append(
                "QMenu {"
                f" background-color: {self._css_rgba(outer)};"
                f" color: {self._css_rgba(outer_text)};"
                " }"
            )
            if radius_px is not None or padding_px is not None:
                rules.append(
                    "QMenuBar::item {"
                    " background: transparent;"
                    + (f" padding: {padding_px}px {max(6, padding_px * 2)}px;" if padding_px is not None else "")
                    + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                    + " }"
                )
                rules.append(
                    "QMenu::item {"
                    + (f" padding: {max(2, padding_px)}px {max(8, padding_px * 3)}px;" if padding_px is not None else "")
                    + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                    + " }"
                )
            if hover_color is not None or accent_color is not None:
                over = hover_color if hover_color is not None else accent_color
                if over is not None:
                    rules.append(
                        "QMenuBar::item:selected {"
                        f" background-color: {self._css_rgba(over)};"
                        " }"
                    )
                    rules.append(
                        "QMenu::item:selected {"
                        f" background-color: {self._css_rgba(over)};"
                        " }"
                    )

        effective_panel_bg = panel_bg_color
        if effective_panel_bg is None:
            if isinstance(inner, QColor) and inner.isValid():
                effective_panel_bg = QColor(inner)
            elif isinstance(outer, QColor) and outer.isValid():
                effective_panel_bg = QColor(outer)
        if effective_panel_bg is not None:
            panel_text = QColor(text_override) if text_override is not None else self._auto_text_color(effective_panel_bg)
            rules.append(
                "QDockWidget QWidget, QScrollArea::viewport {"
                f" background: {self._css_rgba(effective_panel_bg)};"
                f" color: {self._css_rgba(panel_text)};"
                " }"
            )

        if text_area_bg_color is not None and not (isinstance(inner, QColor) and inner.isValid()):
            text_area_text = QColor(text_override) if text_override is not None else self._auto_text_color(text_area_bg_color)
            computed_border = border_color if border_color is not None else text_area_bg_color.darker(135)
            rules.append(
                "QListWidget, QTextBrowser, QTextEdit, QPlainTextEdit {"
                f" background: {self._css_rgba(text_area_bg_color)};"
                f" color: {self._css_rgba(text_area_text)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                " }"
            )
            rules.append(
                "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
                f" background: {self._css_rgba(text_area_bg_color)};"
                f" color: {self._css_rgba(text_area_text)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                + (f" padding: {padding_px}px;" if padding_px is not None else "")
                + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                + " }"
            )
            rules.append("QComboBox { padding-right: 26px; }")
            rules.append(
                "QComboBox::drop-down {"
                " subcontrol-origin: padding;"
                " subcontrol-position: top right;"
                " width: 22px;"
                f" border-left: 1px solid {self._css_rgba(computed_border)};"
                " }"
            )
            rules.append(f'QComboBox::down-arrow {{ image: url("{down_arrow_png_data_url(text_area_text)}"); width: 10px; height: 10px; }}')

        if isinstance(inner, QColor) and inner.isValid():
            inner_text = QColor(text_override) if text_override is not None else self._auto_text_color(inner)
            computed_border = border_color if border_color is not None else inner.darker(135)
            rules.append(
                "QTabWidget::pane, QScrollArea {"
                f" background: {self._css_rgba(inner)};"
                f" color: {self._css_rgba(inner_text)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                " }"
            )
            list_and_browser_bg = text_area_bg_color if text_area_bg_color is not None else inner
            rules.append(
                "QListWidget, QTextBrowser {"
                f" background: {self._css_rgba(list_and_browser_bg)};"
                f" color: {self._css_rgba(inner_text)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                " }"
            )
            text_controls_bg = text_area_bg_color if text_area_bg_color is not None else inner.lighter(105)
            rules.append(
                "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {"
                f" background: {self._css_rgba(text_controls_bg)};"
                f" color: {self._css_rgba(inner_text)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                + (f" padding: {padding_px}px;" if padding_px is not None else "")
                + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                + " }"
            )
            rules.append("QComboBox { padding-right: 26px; }")
            rules.append(
                "QComboBox::drop-down {"
                " subcontrol-origin: padding;"
                " subcontrol-position: top right;"
                " width: 22px;"
                f" border-left: 1px solid {self._css_rgba(computed_border)};"
                " }"
            )
            rules.append(f'QComboBox::down-arrow {{ image: url("{down_arrow_png_data_url(inner_text)}"); width: 10px; height: 10px; }}')
            rules.append(
                "QLabel, QCheckBox {"
                f" color: {self._css_rgba(inner_text)};"
                " }"
            )
            if radius_px is not None:
                rules.append(
                    "QListWidget::item {"
                    f" border-radius: {radius_px}px;"
                    " }"
                )
            if valid_color(tab_inactive):
                tab_bg = QColor(tab_inactive)
            else:
                tab_bg = inner.darker(110)
            rules.append(
                "QTabBar::tab {"
                f" background-color: {self._css_rgba(tab_bg)};"
                f" color: {self._css_rgba(inner_text)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                + (f" padding: {max(2, padding_px)}px {max(8, padding_px * 3)}px;" if padding_px is not None else " padding: 4px 10px;")
                + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                + " }"
            )
            if valid_color(tab_active):
                active_bg = QColor(tab_active)
            else:
                active_bg = inner
            rules.append(
                "QTabBar::tab:selected {"
                f" background-color: {self._css_rgba(active_bg)};"
                " }"
            )
            rules.append(
                "QListWidget::item:selected {"
                f" background-color: {self._css_rgba((accent_color if accent_color is not None else inner.lighter(125)))};"
                f" color: {self._css_rgba(inner_text)};"
                " }"
            )
            if accent_color is not None:
                rules.append(
                    "QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {"
                    f" border: 1px solid {self._css_rgba(accent_color)};"
                    " }"
                )

        if isinstance(buttons, QColor) and buttons.isValid():
            btn_text = QColor(text_override) if text_override is not None else self._auto_text_color(buttons)
            btn_border = border_color if border_color is not None else buttons.darker(145)
            btn_hover = hover_color if hover_color is not None else buttons.lighter(110)
            btn_pressed = pressed_color if pressed_color is not None else buttons.darker(120)
            rules.append(
                "QPushButton, QToolButton {"
                f" background-color: {self._css_rgba(buttons)};"
                f" color: {self._css_rgba(btn_text)};"
                f" border: 1px solid {self._css_rgba(btn_border)};"
                + (f" padding: {padding_px}px {max(6, padding_px * 2)}px;" if padding_px is not None else " padding: 4px 10px;")
                + (f" border-radius: {radius_px}px;" if radius_px is not None else " border-radius: 6px;")
                + " }"
            )
            rules.append(
                "QPushButton::menu-indicator, QToolButton::menu-indicator {"
                " subcontrol-origin: padding;"
                " subcontrol-position: center right;"
                f' image: url("{down_arrow_png_data_url(btn_text)}");'
                " width: 10px;"
                " height: 10px;"
                " right: 6px;"
                " }"
            )
            rules.append(
                "QPushButton:hover, QToolButton:hover {"
                f" background-color: {self._css_rgba(btn_hover)};"
                " }"
            )
            rules.append(
                "QPushButton:pressed, QToolButton:pressed {"
                f" background-color: {self._css_rgba(btn_pressed)};"
                " }"
            )
        else:
            if hover_color is not None:
                rules.append(
                    "QPushButton:hover, QToolButton:hover {"
                    f" background-color: {self._css_rgba(hover_color)};"
                    " }"
                )
            if pressed_color is not None:
                rules.append(
                    "QPushButton:pressed, QToolButton:pressed {"
                    f" background-color: {self._css_rgba(pressed_color)};"
                    " }"
                )

        if isinstance(inner, QColor) and inner.isValid():
            computed_border = border_color if border_color is not None else inner.darker(135)
            preview_bg = QColor(panel_bg_color) if panel_bg_color is not None else QColor(inner)
            rules.append(
                "QGraphicsView {"
                f" background: {self._css_rgba(preview_bg)};"
                f" border: 1px solid {self._css_rgba(computed_border)};"
                + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                + " }"
            )

        checked_bg = (
            accent_color
            if accent_color is not None
            else (pressed_color if pressed_color is not None else (QColor(buttons).darker(115) if valid_color(buttons) else None))
        )
        if checked_bg is None and valid_color(inner):
            checked_bg = QColor(inner).lighter(120)
        if checked_bg is not None:
            checked_text = QColor(text_override) if text_override is not None else self._auto_text_color(checked_bg)
            checked_border = border_color if border_color is not None else checked_bg.darker(145)
            rules.append(
                "QToolButton:checked, QPushButton:checked {"
                f" background-color: {self._css_rgba(checked_bg)};"
                f" color: {self._css_rgba(checked_text)};"
                f" border: 2px solid {self._css_rgba(checked_border)};"
                " }"
            )
            if hover_color is not None:
                rules.append(
                    "QToolButton:checked:hover, QPushButton:checked:hover {"
                    f" background-color: {self._css_rgba(hover_color)};"
                    " }"
                )

        if border_color is not None:
            rules.append(
                "QMainWindow::separator, QToolBar::separator {"
                f" background: {self._css_rgba(border_color)};"
                " }"
            )
            rules.append(
                "QToolBar {"
                f" border: 1px solid {self._css_rgba(border_color)};"
                " }"
            )
            rules.append(
                "QMenuBar {"
                f" border-bottom: 1px solid {self._css_rgba(border_color)};"
                " }"
            )
            rules.append(
                "QMenu {"
                f" border: 1px solid {self._css_rgba(border_color)};"
                " }"
            )
            rules.append(
                "QDockWidget::title {"
                f" border: 1px solid {self._css_rgba(border_color)};"
                " }"
            )
            rules.append(
                "QDockWidget::widget {"
                f" border: 1px solid {self._css_rgba(border_color)};"
                " }"
            )

        if valid_color(scroll_track) or valid_color(scroll_thumb):
            track = QColor(scroll_track) if valid_color(scroll_track) else (QColor(inner).lighter(105) if valid_color(inner) else QColor(0, 0, 0, 0))
            thumb = QColor(scroll_thumb) if valid_color(scroll_thumb) else (QColor(buttons) if valid_color(buttons) else QColor(track).darker(120))
            rules.append(
                "QScrollBar:vertical, QScrollBar:horizontal {"
                f" background: {self._css_rgba(track)};"
                " margin: 0px;"
                " }"
            )
            rules.append(
                "QScrollBar::handle:vertical, QScrollBar::handle:horizontal {"
                f" background: {self._css_rgba(thumb)};"
                + (f" border-radius: {radius_px}px;" if radius_px is not None else "")
                + " min-height: 16px;"
                + " min-width: 16px;"
                + " }"
            )
            rules.append("QScrollBar::add-line, QScrollBar::sub-line { background: transparent; }")
            rules.append("QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }")

        if text_override is not None and not rules:
            rules.append(
                "QMainWindow, QMenuBar, QToolBar, QDockWidget, QMenu, QLabel, QCheckBox, QListWidget, QTextBrowser, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
                f" color: {self._css_rgba(text_override)};"
                " }"
            )

        try:
            app.setStyleSheet("\n".join((self._base_app_stylesheet, "\n".join(rules))).strip())
        except Exception:
            pass

    def _color_icon(self, c: QColor | None) -> QIcon:
        pm = QPixmap(14, 14)
        if isinstance(c, QColor) and c.isValid():
            pm.fill(QColor(c))
        else:
            pm.fill(QColor(0, 0, 0, 0))
        return QIcon(pm)

    def _refresh_theme_toolbar_icons(self) -> None:
        try:
            self._act_theme_buttons.setIcon(self._color_icon(self._gui_theme.get("buttons")))
            self._act_theme_outer.setIcon(self._color_icon(self._gui_theme.get("outer")))
            self._act_theme_inner.setIcon(self._color_icon(self._gui_theme.get("inner")))
            self._act_theme_panel_bg.setIcon(self._color_icon(self._gui_theme.get("panel_bg")))
            self._act_theme_text_area_bg.setIcon(self._color_icon(self._gui_theme.get("text_area_bg")))
            self._act_theme_text.setIcon(self._color_icon(self._gui_theme.get("text")))
            self._act_theme_accent.setIcon(self._color_icon(self._gui_theme.get("accent")))
            self._act_theme_border.setIcon(self._color_icon(self._gui_theme.get("border")))
            self._act_theme_hover.setIcon(self._color_icon(self._gui_theme.get("hover")))
            self._act_theme_pressed.setIcon(self._color_icon(self._gui_theme.get("pressed")))
            self._act_theme_tab_active.setIcon(self._color_icon(self._gui_theme.get("tab_active")))
            self._act_theme_tab_inactive.setIcon(self._color_icon(self._gui_theme.get("tab_inactive")))
            self._act_theme_scroll_track.setIcon(self._color_icon(self._gui_theme.get("scroll_track")))
            self._act_theme_scroll_thumb.setIcon(self._color_icon(self._gui_theme.get("scroll_thumb")))
        except Exception:
            pass

    def _pick_gui_theme_color(self, key: str) -> None:
        k = str(key or "").strip().lower()
        if k not in (
            "buttons",
            "outer",
            "inner",
            "panel_bg",
            "text_area_bg",
            "text",
            "accent",
            "border",
            "hover",
            "pressed",
            "tab_active",
            "tab_inactive",
            "scroll_track",
            "scroll_thumb",
        ):
            return
        current = self._gui_theme.get(k)
        start = current if isinstance(current, QColor) and current.isValid() else QColor(60, 60, 60)
        title = {
            "buttons": "Pick Buttons Color",
            "outer": "Pick GUI Outer Color",
            "inner": "Pick GUI Inner Color",
            "panel_bg": "Pick Panel Background",
            "text_area_bg": "Pick Text Area Background",
            "text": "Pick Word Color",
            "accent": "Pick Accent / Selection Color",
            "border": "Pick Border / Divider Color",
            "hover": "Pick Hover Color",
            "pressed": "Pick Pressed Color",
            "tab_active": "Pick Active Tab Color",
            "tab_inactive": "Pick Inactive Tab Color",
            "scroll_track": "Pick Scrollbar Track Color",
            "scroll_thumb": "Pick Scrollbar Thumb Color",
        }.get(k, "Pick Color")
        color = QColorDialog.getColor(start, self, title, QColorDialog.ShowAlphaChannel)
        if not color.isValid():
            return
        self._gui_theme[k] = QColor(color)
        self._apply_gui_theme_styles()
        self._refresh_theme_toolbar_icons()
        self._save_ui_state()

    def _pick_gui_theme_ui_font(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        start = QFont(app.font())
        result = QFontDialog.getFont(start, self, "Pick UI Font")
        ok = False
        font = None
        if isinstance(result, tuple) and len(result) == 2:
            a, b = result
            if isinstance(a, bool):
                ok = bool(a)
                font = b
            else:
                font = a
                ok = bool(b)
        if not ok:
            return
        if not isinstance(font, QFont):
            return
        try:
            self._gui_theme["ui_font"] = str(font.toString())
        except Exception:
            self._gui_theme["ui_font"] = None
        self._gui_theme["ui_font_family"] = str(font.family())
        self._gui_theme["ui_font_size"] = int(font.pointSize()) if int(font.pointSize()) > 0 else None
        self._apply_gui_theme_styles()
        self._save_ui_state()

    def _pick_gui_theme_control_padding(self) -> None:
        current = self._gui_theme.get("control_padding")
        start = int(current) if isinstance(current, int) else 4
        value, ok = QInputDialog.getInt(self, "Control Padding", "Padding (px):", start, 0, 24, 1)
        if not ok:
            return
        self._gui_theme["control_padding"] = int(value)
        self._apply_gui_theme_styles()
        self._save_ui_state()

    def _pick_gui_theme_corner_radius(self) -> None:
        current = self._gui_theme.get("corner_radius")
        start = float(current) if isinstance(current, (int, float)) else 6.0
        value, ok = QInputDialog.getDouble(self, "Corner Radius", "Radius (px):", start, 0.0, 30.0, 1)
        if not ok:
            return
        self._gui_theme["corner_radius"] = float(value)
        self._apply_gui_theme_styles()
        self._save_ui_state()

    def _apply_gui_theme_preset(self, name: str) -> None:
        n = str(name or "").strip().lower()
        presets: dict[str, dict[str, object]] = {
            "lavender": {
                "outer": QColor("#E9E2FF"),
                "inner": QColor("#F6F2FF"),
                "panel_bg": QColor("#F6F2FF"),
                "text_area_bg": QColor("#FFFFFF"),
                "buttons": QColor("#B99BFF"),
                "text": QColor("#3A275A"),
                "accent": QColor("#9D7BFF"),
                "border": QColor("#D1C2FF"),
                "hover": QColor("#C7B3FF"),
                "pressed": QColor("#A88BFF"),
                "tab_active": QColor("#D1C2FF"),
                "tab_inactive": QColor("#E9E2FF"),
                "scroll_track": QColor("#F6F2FF"),
                "scroll_thumb": QColor("#B99BFF"),
                "corner_radius": 6.0,
                "control_padding": 4,
                "ui_font_family": "Segoe UI",
                "ui_font_size": 12,
            },
            "dark": {
                "outer": QColor("#1F1F24"),
                "inner": QColor("#2A2A32"),
                "panel_bg": QColor("#2A2A32"),
                "text_area_bg": QColor("#31313A"),
                "buttons": QColor("#3C3C46"),
                "text": QColor("#EDEDED"),
                "accent": QColor("#6B85FF"),
                "border": QColor("#3B3B44"),
                "hover": QColor("#4B4B56"),
                "pressed": QColor("#32323C"),
                "tab_active": QColor("#2A2A32"),
                "tab_inactive": QColor("#24242B"),
                "scroll_track": QColor("#24242B"),
                "scroll_thumb": QColor("#3C3C46"),
                "corner_radius": 6.0,
                "control_padding": 4,
                "ui_font_family": "Segoe UI",
                "ui_font_size": 11,
            },
            "light": {
                "outer": QColor("#F2F2F2"),
                "inner": QColor("#FFFFFF"),
                "panel_bg": QColor("#FFFFFF"),
                "text_area_bg": QColor("#FFFFFF"),
                "buttons": QColor("#E2E2E2"),
                "text": QColor("#1A1A1A"),
                "accent": QColor("#6B85FF"),
                "border": QColor("#D2D2D2"),
                "hover": QColor("#EAEAEA"),
                "pressed": QColor("#D7D7D7"),
                "tab_active": QColor("#FFFFFF"),
                "tab_inactive": QColor("#EDEDED"),
                "scroll_track": QColor("#F4F4F4"),
                "scroll_thumb": QColor("#D0D0D0"),
                "corner_radius": 6.0,
                "control_padding": 4,
                "ui_font_family": "Segoe UI",
                "ui_font_size": 11,
            },
            "midnight": {
                "outer": QColor("#0E1020"),
                "inner": QColor("#161A2E"),
                "panel_bg": QColor("#161A2E"),
                "text_area_bg": QColor("#1C2140"),
                "buttons": QColor("#2A2F57"),
                "text": QColor("#E7E7FF"),
                "accent": QColor("#7C90FF"),
                "border": QColor("#2A2F57"),
                "hover": QColor("#3A4073"),
                "pressed": QColor("#23284A"),
                "tab_active": QColor("#161A2E"),
                "tab_inactive": QColor("#12162A"),
                "scroll_track": QColor("#12162A"),
                "scroll_thumb": QColor("#2A2F57"),
                "corner_radius": 6.0,
                "control_padding": 4,
                "ui_font_family": "Segoe UI",
                "ui_font_size": 11,
            },
        }
        theme = presets.get(n)
        if theme is None:
            return
        keys = (
            "buttons",
            "outer",
            "inner",
            "panel_bg",
            "text_area_bg",
            "text",
            "accent",
            "border",
            "hover",
            "pressed",
            "tab_active",
            "tab_inactive",
            "scroll_track",
            "scroll_thumb",
            "corner_radius",
            "control_padding",
            "ui_font",
            "ui_font_family",
            "ui_font_size",
        )
        self._gui_theme = {k: None for k in keys}
        for k, v in theme.items():
            if k in ("corner_radius", "control_padding", "ui_font", "ui_font_family", "ui_font_size"):
                self._gui_theme[k] = v
            elif isinstance(v, QColor) and v.isValid():
                self._gui_theme[k] = QColor(v)
        self._apply_gui_theme_styles()
        self._refresh_theme_toolbar_icons()
        self._save_ui_state()

    def _reset_gui_theme(self) -> None:
        keys = (
            "buttons",
            "outer",
            "inner",
            "panel_bg",
            "text_area_bg",
            "text",
            "accent",
            "border",
            "hover",
            "pressed",
            "tab_active",
            "tab_inactive",
            "scroll_track",
            "scroll_thumb",
            "corner_radius",
            "control_padding",
            "ui_font",
            "ui_font_family",
            "ui_font_size",
        )
        self._gui_theme = {k: None for k in keys}
        self._apply_gui_theme_styles()
        self._refresh_theme_toolbar_icons()
        self._save_ui_state()

    def _restore_dock(self, dock: QDockWidget) -> None:
        area = getattr(dock, "default_area", Qt.LeftDockWidgetArea)
        try:
            dock.setFloating(False)
        except Exception:
            pass
        self.addDockWidget(area, dock)
        dock.show()
        dock.raise_()

    def _build_ui(self) -> None:
        menubar = self.menuBar()
        menu_file = menubar.addMenu("File")
        menu_file.addAction(self._act_save_layout)
        menu_file.addAction(self._act_load_layout)
        self._menu_recent = menu_file.addMenu("Open Recent")
        menu_file.addAction(self._act_export_packaged_layout)
        menu_file.addAction(self._act_export_frame)
        menu_file.addAction(self._act_recover_autosave)
        menu_file.addSeparator()
        menu_file.addAction(self._act_open_background)
        menu_file.addAction(self._act_background_color)
        menu_file.addSeparator()
        menu_file.addAction(self._act_quit)

        menu_edit = menubar.addMenu("Edit")
        menu_edit.addAction(self._act_undo)
        menu_edit.addAction(self._act_redo)
        menu_edit.addSeparator()
        menu_edit.addAction(self._act_duplicate_layer)
        menu_edit.addSeparator()
        menu_edit.addAction(self._act_bring_forward)
        menu_edit.addAction(self._act_send_backward)
        menu_edit.addAction(self._act_bring_to_front)
        menu_edit.addAction(self._act_send_to_back)
        menu_edit.addSeparator()
        menu_edit.addAction(self._act_toggle_lock)
        menu_edit.addAction(self._act_toggle_hide)

        menu_view = menubar.addMenu("View")
        menu_view.addAction(self._act_desktop_preview)
        menu_view.addAction(self._act_keep_running)
        menu_view.addSeparator()
        menu_view.addAction(self._act_snap_grid)
        menu_view.addAction(self._act_snap_center)
        menu_view.addAction(self._act_show_grid)
        menu_view.addSeparator()
        menu_view.addAction(self._act_zoom_in)
        menu_view.addAction(self._act_zoom_out)
        menu_view.addAction(self._act_zoom_reset)
        menu_view.addSeparator()
        menu_theme = menu_view.addMenu("Theme")
        menu_theme_presets = menu_theme.addMenu("Presets")
        menu_theme_presets.addAction(self._act_theme_preset_lavender)
        menu_theme_presets.addAction(self._act_theme_preset_dark)
        menu_theme_presets.addAction(self._act_theme_preset_light)
        menu_theme_presets.addAction(self._act_theme_preset_midnight)
        menu_theme.addSeparator()
        menu_theme.addAction(self._act_theme_buttons)
        menu_theme.addAction(self._act_theme_outer)
        menu_theme.addAction(self._act_theme_inner)
        menu_theme.addAction(self._act_theme_panel_bg)
        menu_theme.addAction(self._act_theme_text_area_bg)
        menu_theme.addAction(self._act_theme_text)
        menu_theme.addSeparator()
        menu_theme.addAction(self._act_theme_accent)
        menu_theme.addAction(self._act_theme_border)
        menu_theme.addAction(self._act_theme_hover)
        menu_theme.addAction(self._act_theme_pressed)
        menu_theme.addAction(self._act_theme_tab_active)
        menu_theme.addAction(self._act_theme_tab_inactive)
        menu_theme.addAction(self._act_theme_scroll_track)
        menu_theme.addAction(self._act_theme_scroll_thumb)
        menu_theme.addSeparator()
        menu_theme.addAction(self._act_theme_ui_font)
        menu_theme.addAction(self._act_theme_control_padding)
        menu_theme.addAction(self._act_theme_corner_radius)
        menu_theme.addSeparator()
        menu_theme.addAction(self._act_theme_reset)

        menu_view.addSeparator()
        menu_fps = menu_view.addMenu("Frame Rate")
        self._fps_actions: dict[int, QAction] = {}
        for fps_value, fps_label in ((60, "60 FPS"), (30, "30 FPS"), (24, "24 FPS"), (15, "15 FPS")):
            act_fps = QAction(fps_label, self)
            act_fps.setCheckable(True)
            act_fps.triggered.connect(lambda _checked=False, v=fps_value: self._apply_fps_cap(v))
            menu_fps.addAction(act_fps)
            self._fps_actions[fps_value] = act_fps
        menu_view.addSeparator()
        menu_wallpaper = menu_view.addMenu("Wallpaper")
        menu_wallpaper.addAction(self._act_set_wallpaper_current)
        menu_wallpaper.addAction(self._act_unset_wallpaper_current)
        menu_wallpaper.addSeparator()
        menu_wallpaper.addAction(self._act_set_wallpaper)
        menu_wallpaper.addAction(self._act_unset_wallpaper)

        menu_help = menubar.addMenu("Help")
        menu_help.addAction(self._act_show_hotkeys)

        self._refresh_theme_toolbar_icons()

        layers_dock = ResettableDockWidget("Layers", self, default_area=Qt.LeftDockWidgetArea, on_close=self._restore_dock)
        layers_dock.setObjectName("LayersDock")
        layers_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        layers_panel = QWidget()
        layers_layout = QVBoxLayout()

        row = QHBoxLayout()
        btn_add_text = QPushButton("Add Text")
        btn_add_media = QPushButton("Add Image/GIF/Video")
        btn_add_particles = QPushButton("Add Particles")
        row.addWidget(btn_add_text)
        row.addWidget(btn_add_media)
        row.addWidget(btn_add_particles)
        layers_layout.addLayout(row)

        row2 = QHBoxLayout()
        btn_layer_up = QPushButton("Up")
        btn_layer_down = QPushButton("Down")
        btn_layer_delete = QPushButton("Delete")
        row2.addWidget(btn_layer_up)
        row2.addWidget(btn_layer_down)
        row2.addWidget(btn_layer_delete)
        layers_layout.addLayout(row2)
        layers_layout.addWidget(self._layers_list)

        self._btn_add_text = btn_add_text
        self._btn_add_media = btn_add_media
        self._btn_add_particles = btn_add_particles
        self._btn_layer_up = btn_layer_up
        self._btn_layer_down = btn_layer_down
        self._btn_layer_delete = btn_layer_delete

        layers_panel.setLayout(layers_layout)
        layers_scroll = QScrollArea()
        layers_scroll.setWidgetResizable(True)
        layers_scroll.setMinimumSize(1, 1)
        layers_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layers_scroll.setWidget(layers_panel)
        layers_dock.setWidget(layers_scroll)
        self.addDockWidget(Qt.LeftDockWidgetArea, layers_dock)
        self._dock_layers = layers_dock

        layouts_dock = ResettableDockWidget("Layouts", self, default_area=Qt.LeftDockWidgetArea, on_close=self._restore_dock)
        layouts_dock.setObjectName("LayoutsDock")
        layouts_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        layouts_panel = QWidget()
        layouts_layout = QVBoxLayout()

        self._layouts_list = QListWidget()
        layouts_layout.addWidget(self._layouts_list)

        row_a = QHBoxLayout()
        self._btn_layout_new = QPushButton("Start New")
        self._btn_layout_add = QPushButton("Add")
        self._btn_layout_update = QPushButton("Update")
        self._btn_layout_delete = QPushButton("Delete")
        row_a.addWidget(self._btn_layout_new)
        row_a.addWidget(self._btn_layout_add)
        row_a.addWidget(self._btn_layout_update)
        row_a.addWidget(self._btn_layout_delete)
        layouts_layout.addLayout(row_a)

        row_b = QHBoxLayout()
        self._btn_layout_prev = QPushButton("Prev")
        self._btn_layout_next = QPushButton("Next")
        self._btn_layout_rename = QPushButton("Rename")
        row_b.addWidget(self._btn_layout_prev)
        row_b.addWidget(self._btn_layout_next)
        row_b.addWidget(self._btn_layout_rename)
        layouts_layout.addLayout(row_b)

        row_c = QHBoxLayout()
        self._chk_layout_autocycle = QCheckBox("Auto cycle")
        self._spin_layout_interval = QSpinBox()
        self._spin_layout_interval.setRange(1, 86_400)
        self._spin_layout_interval.setValue(60)
        row_c.addWidget(self._chk_layout_autocycle)
        row_c.addWidget(QLabel("Seconds"))
        row_c.addWidget(self._spin_layout_interval)
        layouts_layout.addLayout(row_c)

        layouts_panel.setLayout(layouts_layout)
        layouts_scroll = QScrollArea()
        layouts_scroll.setWidgetResizable(True)
        layouts_scroll.setMinimumSize(1, 1)
        layouts_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layouts_scroll.setWidget(layouts_panel)
        layouts_dock.setWidget(layouts_scroll)
        self.addDockWidget(Qt.LeftDockWidgetArea, layouts_dock)
        self._dock_layouts = layouts_dock

        props_dock = ResettableDockWidget("Properties", self, default_area=Qt.RightDockWidgetArea, on_close=self._restore_dock)
        props_dock.setObjectName("PropertiesDock")
        props_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        props_panel = QWidget()
        props_layout = QVBoxLayout()

        layer_box = CollapsibleBox("Layer")
        layer_form = QFormLayout()
        self._txt_layer_name = QLineEdit()
        self._chk_layer_locked = QCheckBox("Locked")
        self._chk_layer_hidden = QCheckBox("Hidden")
        self._spin_opacity = QSpinBox()
        self._spin_opacity.setRange(0, 100)
        self._spin_opacity.setValue(100)
        self._combo_blend_mode = ArrowComboBox()
        self._combo_blend_mode.addItem("Normal", BlendMode.NORMAL.value)
        self._combo_blend_mode.addItem("Multiply", BlendMode.MULTIPLY.value)
        self._combo_blend_mode.addItem("Screen", BlendMode.SCREEN.value)
        self._combo_blend_mode.addItem("Overlay", BlendMode.OVERLAY.value)
        self._combo_blend_mode.addItem("Soft Light", BlendMode.SOFT_LIGHT.value)
        self._combo_blend_mode.addItem("Darken", BlendMode.DARKEN.value)
        self._combo_blend_mode.addItem("Lighten", BlendMode.LIGHTEN.value)
        self._combo_blend_mode.addItem("Add", BlendMode.ADD.value)
        layer_form.addRow("Name", self._txt_layer_name)
        layer_form.addRow("Opacity", self._spin_opacity)
        layer_form.addRow("Blend", self._combo_blend_mode)
        layer_form.addRow("", self._chk_layer_locked)
        layer_form.addRow("", self._chk_layer_hidden)
        layer_box.set_content_layout(layer_form)
        props_layout.addWidget(layer_box)
        props_layout.addSpacing(12)

        transform_box = CollapsibleBox("Transform")
        form = QFormLayout()
        self._spin_x = QDoubleSpinBox()
        self._spin_y = QDoubleSpinBox()
        self._spin_scale = QDoubleSpinBox()
        self._spin_rotation = QDoubleSpinBox()
        for s in (self._spin_x, self._spin_y):
            s.setRange(-100000, 100000)
            s.setDecimals(1)
        self._spin_scale.setRange(0.01, 1000)
        self._spin_scale.setDecimals(3)
        self._spin_scale.setSingleStep(0.05)
        self._spin_rotation.setRange(-3600, 3600)
        self._spin_rotation.setDecimals(1)
        self._spin_rotation.setSingleStep(5)

        form.addRow("X", self._spin_x)
        form.addRow("Y", self._spin_y)
        form.addRow("Scale", self._spin_scale)
        form.addRow("Rotation", self._spin_rotation)
        transform_box.set_content_layout(form)
        props_layout.addWidget(transform_box)
        props_layout.addSpacing(12)


        media_box = CollapsibleBox("Media")
        media_form = QFormLayout()
        media_controls_row = QHBoxLayout()
        self._btn_media_play = QPushButton("Play")
        self._btn_media_pause = QPushButton("Pause")
        self._btn_media_stop = QPushButton("Stop")
        media_controls_row.addWidget(self._btn_media_play)
        media_controls_row.addWidget(self._btn_media_pause)
        media_controls_row.addWidget(self._btn_media_stop)
        self._chk_media_mute = QCheckBox("Mute")
        self._slider_media_volume = QSpinBox()
        self._slider_media_volume.setRange(0, 100)
        self._slider_media_volume.setValue(100)
        self._combo_media_aspect = ArrowComboBox()
        self._combo_media_aspect.addItem("Fit", "fit")
        self._combo_media_aspect.addItem("Stretch", "stretch")
        self._combo_media_aspect.addItem("Original", "original")
        self._spin_media_speed = QDoubleSpinBox()
        self._spin_media_speed.setRange(0.1, 4.0)
        self._spin_media_speed.setSingleStep(0.1)
        self._spin_media_speed.setValue(1.0)
        media_form.addRow("Controls", QWidget())
        media_form.itemAt(media_form.rowCount()-1, QFormLayout.ItemRole.FieldRole).widget().setLayout(media_controls_row)
        media_form.addRow("Mute", self._chk_media_mute)
        media_form.addRow("Volume", self._slider_media_volume)
        media_form.addRow("Aspect", self._combo_media_aspect)
        media_form.addRow("Speed", self._spin_media_speed)
        media_box.set_content_layout(media_form)
        props_layout.addWidget(media_box)
        props_layout.addSpacing(12)

        align_box = CollapsibleBox("Alignment")
        align_content_layout = QVBoxLayout()
        
        align_row = QHBoxLayout()
        self._btn_align_left = QPushButton("Left")
        self._btn_align_center = QPushButton("Center")
        self._btn_align_right = QPushButton("Right")
        align_row.addWidget(self._btn_align_left)
        align_row.addWidget(self._btn_align_center)
        align_row.addWidget(self._btn_align_right)
        align_content_layout.addLayout(align_row)

        valign_row = QHBoxLayout()
        self._btn_align_top = QPushButton("Top")
        self._btn_align_middle = QPushButton("Middle")
        self._btn_align_bottom = QPushButton("Bottom")
        valign_row.addWidget(self._btn_align_top)
        valign_row.addWidget(self._btn_align_middle)
        valign_row.addWidget(self._btn_align_bottom)
        align_content_layout.addLayout(valign_row)

        self._combo_align_target = ArrowComboBox()
        self._combo_align_target.addItem("Align To: Scene", "scene")
        self._combo_align_target.addItem("Align To: Selection", "selection")
        align_content_layout.addWidget(self._combo_align_target)

        distribute_row = QHBoxLayout()
        self._btn_distribute_h = QPushButton("Space H")
        self._btn_distribute_v = QPushButton("Space V")
        distribute_row.addWidget(self._btn_distribute_h)
        distribute_row.addWidget(self._btn_distribute_v)
        align_content_layout.addLayout(distribute_row)

        match_row = QHBoxLayout()
        self._btn_match_w = QPushButton("Match W")
        self._btn_match_h = QPushButton("Match H")
        match_row.addWidget(self._btn_match_w)
        match_row.addWidget(self._btn_match_h)
        align_content_layout.addLayout(match_row)

        fit_row = QHBoxLayout()
        self._btn_fit_canvas = QPushButton("Fit to Canvas")
        self._btn_fill_canvas = QPushButton("Fill Canvas")
        fit_row.addWidget(self._btn_fit_canvas)
        fit_row.addWidget(self._btn_fill_canvas)
        align_content_layout.addLayout(fit_row)
        
        align_box.set_content_layout(align_content_layout)
        props_layout.addWidget(align_box)

        props_layout.addSpacing(12)
        anim_container = CollapsibleBox("Animation")
        anim_wrapper = QVBoxLayout()

        self._combo_anim_mode = ArrowComboBox()
        self._combo_anim_mode.addItem("None", "none")
        self._combo_anim_mode.addItem("Slide", "slide")
        self._combo_anim_mode.addItem("Bounce", "bounce")
        self._combo_anim_mode.addItem("Orbit Edge", "orbit_edge")
        self._combo_anim_mode.addItem("Orbit Center", "orbit_center")
        self._combo_anim_mode.addItem("Follow Path", "follow_path")
        self._combo_anim_mode.addItem("Drift", "drift")
        self._combo_anim_mode.addItem("Zigzag", "zigzag")
        self._combo_anim_mode.addItem("Figure-8", "figure8")
        self._combo_anim_mode.addItem("Lissajous", "lissajous")
        self._combo_anim_mode.addItem("Pendulum", "pendulum")
        self._combo_anim_mode.addItem("Wander", "wander")
        self._combo_anim_mode.addItem("Shake", "shake")
        self._combo_anim_mode.addItem("Spin", "spin")
        self._combo_anim_mode.addItem("Wobble", "wobble")
        self._combo_anim_mode.addItem("Tumble", "tumble")
        self._combo_anim_mode.addItem("Pulse", "pulse")
        self._combo_anim_mode.addItem("Pop", "pop")
        self._combo_anim_mode.addItem("Fade In", "fade_in")
        self._combo_anim_mode.addItem("Fade Out", "fade_out")
        self._combo_anim_mode.addItem("Blink", "blink")
        self._combo_anim_mode.addItem("Float + Bob", "float_bob")
        self._combo_anim_mode.addItem("Hover + Wobble", "hover_wobble")
        self._combo_anim_mode.addItem("Orbit + Pulse", "orbit_pulse")
        self._combo_anim_mode.addItem("Heartbeat", "heartbeat")
        self._combo_anim_mode.addItem("Glitch", "glitch")
        self._combo_anim_mode.addItem("Rain", "rain")
        self._combo_anim_mode.addItem("Spiral", "spiral")

        self._combo_anim_slide_dir = ArrowComboBox()
        self._combo_anim_slide_dir.addItem("Left → Right", "lr")
        self._combo_anim_slide_dir.addItem("Right → Left", "rl")
        self._combo_anim_slide_dir.addItem("Top → Bottom", "tb")
        self._combo_anim_slide_dir.addItem("Bottom → Top", "bt")

        self._spin_anim_speed = QDoubleSpinBox()
        self._spin_anim_speed.setRange(0.0, 5000.0)
        self._spin_anim_speed.setDecimals(1)
        self._spin_anim_speed.setSingleStep(25.0)
        self._spin_anim_speed.setValue(200.0)

        self._spin_anim_padding = QDoubleSpinBox()
        self._spin_anim_padding.setRange(0.0, 1000.0)
        self._spin_anim_padding.setDecimals(1)
        self._spin_anim_padding.setSingleStep(5.0)
        self._spin_anim_padding.setValue(0.0)

        self._chk_anim_avoid_taskbar = QCheckBox("Avoid taskbar")
        self._chk_anim_avoid_taskbar.setChecked(True)

        self._combo_anim_follow_path = ArrowComboBox()
        self._combo_anim_follow_path.addItem("Path 1", "path1")
        self._combo_anim_follow_path.addItem("Path 2", "path2")
        self._combo_anim_follow_path.addItem("Path 3", "path3")
        self._combo_anim_follow_path.addItem("Path 4", "path4")

        self._combo_anim_orbit_center = ArrowComboBox()
        self._combo_anim_orbit_center.addItem("Center 1", "center1")
        self._combo_anim_orbit_center.addItem("Center 2", "center2")
        self._combo_anim_orbit_center.addItem("Center 3", "center3")
        self._combo_anim_orbit_center.addItem("Center 4", "center4")

        self._combo_anim_orbit_dir = ArrowComboBox()
        self._combo_anim_orbit_dir.addItem("Clockwise", 1.0)
        self._combo_anim_orbit_dir.addItem("Counterclockwise", -1.0)

        self._spin_anim_angle = QDoubleSpinBox()
        self._spin_anim_angle.setRange(-360.0, 360.0)
        self._spin_anim_angle.setDecimals(1)
        self._spin_anim_angle.setSingleStep(5.0)
        self._spin_anim_angle.setValue(0.0)

        self._spin_anim_amp_x = QDoubleSpinBox()
        self._spin_anim_amp_x.setRange(0.0, 5000.0)
        self._spin_anim_amp_x.setDecimals(1)
        self._spin_anim_amp_x.setSingleStep(5.0)
        self._spin_anim_amp_x.setValue(40.0)

        self._spin_anim_amp_y = QDoubleSpinBox()
        self._spin_anim_amp_y.setRange(0.0, 5000.0)
        self._spin_anim_amp_y.setDecimals(1)
        self._spin_anim_amp_y.setSingleStep(5.0)
        self._spin_anim_amp_y.setValue(40.0)

        self._spin_anim_rate = QDoubleSpinBox()
        self._spin_anim_rate.setRange(0.0, 20.0)
        self._spin_anim_rate.setDecimals(2)
        self._spin_anim_rate.setSingleStep(0.1)
        self._spin_anim_rate.setValue(1.0)

        self._spin_anim_rate2 = QDoubleSpinBox()
        self._spin_anim_rate2.setRange(0.0, 20.0)
        self._spin_anim_rate2.setDecimals(2)
        self._spin_anim_rate2.setSingleStep(0.1)
        self._spin_anim_rate2.setValue(2.0)

        self._spin_anim_phase = QDoubleSpinBox()
        self._spin_anim_phase.setRange(-360.0, 360.0)
        self._spin_anim_phase.setDecimals(1)
        self._spin_anim_phase.setSingleStep(5.0)
        self._spin_anim_phase.setValue(0.0)

        self._spin_anim_rot_speed = QDoubleSpinBox()
        self._spin_anim_rot_speed.setRange(-1440.0, 1440.0)
        self._spin_anim_rot_speed.setDecimals(1)
        self._spin_anim_rot_speed.setSingleStep(10.0)
        self._spin_anim_rot_speed.setValue(90.0)

        self._spin_anim_rot_amp = QDoubleSpinBox()
        self._spin_anim_rot_amp.setRange(0.0, 360.0)
        self._spin_anim_rot_amp.setDecimals(1)
        self._spin_anim_rot_amp.setSingleStep(5.0)
        self._spin_anim_rot_amp.setValue(10.0)

        self._spin_anim_scale_min = QDoubleSpinBox()
        self._spin_anim_scale_min.setRange(0.0, 10.0)
        self._spin_anim_scale_min.setDecimals(2)
        self._spin_anim_scale_min.setSingleStep(0.05)
        self._spin_anim_scale_min.setValue(0.9)

        self._spin_anim_scale_max = QDoubleSpinBox()
        self._spin_anim_scale_max.setRange(0.0, 10.0)
        self._spin_anim_scale_max.setDecimals(2)
        self._spin_anim_scale_max.setSingleStep(0.05)
        self._spin_anim_scale_max.setValue(1.1)

        self._spin_anim_opacity_min = QDoubleSpinBox()
        self._spin_anim_opacity_min.setRange(0.0, 1.0)
        self._spin_anim_opacity_min.setDecimals(2)
        self._spin_anim_opacity_min.setSingleStep(0.05)
        self._spin_anim_opacity_min.setValue(0.0)

        self._spin_anim_opacity_max = QDoubleSpinBox()
        self._spin_anim_opacity_max.setRange(0.0, 1.0)
        self._spin_anim_opacity_max.setDecimals(2)
        self._spin_anim_opacity_max.setSingleStep(0.05)
        self._spin_anim_opacity_max.setValue(1.0)

        self._spin_anim_jitter = QDoubleSpinBox()
        self._spin_anim_jitter.setRange(0.0, 5000.0)
        self._spin_anim_jitter.setDecimals(1)
        self._spin_anim_jitter.setSingleStep(10.0)
        self._spin_anim_jitter.setValue(200.0)

        anim_form = QFormLayout()
        anim_form.addRow("Mode", self._combo_anim_mode)
        anim_form.addRow("Slide dir", self._combo_anim_slide_dir)
        anim_form.addRow("Path", self._combo_anim_follow_path)
        anim_form.addRow("Center", self._combo_anim_orbit_center)
        anim_form.addRow("Orbit dir", self._combo_anim_orbit_dir)
        anim_form.addRow("Speed (px/s)", self._spin_anim_speed)
        anim_form.addRow("Padding", self._spin_anim_padding)
        anim_form.addRow("Angle (deg)", self._spin_anim_angle)
        anim_form.addRow("Amp X", self._spin_anim_amp_x)
        anim_form.addRow("Amp Y", self._spin_anim_amp_y)
        anim_form.addRow("Rate (Hz)", self._spin_anim_rate)
        anim_form.addRow("Rate 2 (Hz)", self._spin_anim_rate2)
        anim_form.addRow("Phase (deg)", self._spin_anim_phase)
        anim_form.addRow("Rot speed (deg/s)", self._spin_anim_rot_speed)
        anim_form.addRow("Rot amp (deg)", self._spin_anim_rot_amp)
        anim_form.addRow("Scale min", self._spin_anim_scale_min)
        anim_form.addRow("Scale max", self._spin_anim_scale_max)
        anim_form.addRow("Opacity min", self._spin_anim_opacity_min)
        anim_form.addRow("Opacity max", self._spin_anim_opacity_max)
        anim_form.addRow("Jitter", self._spin_anim_jitter)
        anim_form.addRow("Taskbar", self._chk_anim_avoid_taskbar)
        anim_box = QWidget()
        anim_box.setLayout(anim_form)
        anim_wrapper.addWidget(anim_box)

        anim_btn_row = QHBoxLayout()
        self._btn_anim_start = QPushButton("Start")
        self._btn_anim_stop = QPushButton("Stop")
        self._btn_anim_draw_path = QPushButton("Draw Path")
        self._btn_anim_pick_center = QPushButton("Pick Center")
        self._btn_anim_draw_path.setEnabled(False)
        self._btn_anim_pick_center.setEnabled(False)
        anim_btn_row.addWidget(self._btn_anim_start)
        anim_btn_row.addWidget(self._btn_anim_stop)
        anim_btn_row.addWidget(self._btn_anim_draw_path)
        anim_btn_row.addWidget(self._btn_anim_pick_center)
        anim_wrapper.addLayout(anim_btn_row)
        
        anim_container.set_content_layout(anim_wrapper)
        props_layout.addWidget(anim_container)

        props_layout.addSpacing(12)
        text_container = CollapsibleBox("Text")
        text_wrapper = QVBoxLayout()

        self._txt_text = QLineEdit()
        self._font_combo = ArrowComboBox()
        try:
            families = [str(f) for f in QFontDatabase.families() if str(f).strip()]
            self._font_combo.addItems(families)
        except Exception:
            pass
        self._spin_font_size = QSpinBox()
        self._spin_font_size.setRange(6, 240)
        self._chk_shadow = QCheckBox("Shadow")
        self._chk_glow = QCheckBox("Glow")
        self._btn_shadow_color = QPushButton("Shadow Color")
        self._spin_shadow_blur = QDoubleSpinBox()
        self._spin_shadow_blur.setRange(0.0, 200.0)
        self._spin_shadow_blur.setDecimals(1)
        self._spin_shadow_blur.setSingleStep(1.0)
        self._spin_shadow_dx = QDoubleSpinBox()
        self._spin_shadow_dy = QDoubleSpinBox()
        for s in (self._spin_shadow_dx, self._spin_shadow_dy):
            s.setRange(-500.0, 500.0)
            s.setDecimals(1)
            s.setSingleStep(1.0)

        self._btn_glow_color = QPushButton("Glow Color")
        self._spin_glow_blur = QDoubleSpinBox()
        self._spin_glow_blur.setRange(0.0, 300.0)
        self._spin_glow_blur.setDecimals(1)
        self._spin_glow_blur.setSingleStep(1.0)

        self._chk_blur = QCheckBox("Blur")
        self._spin_blur_radius = QDoubleSpinBox()
        self._spin_blur_radius.setRange(0.0, 100.0)
        self._spin_blur_radius.setDecimals(1)
        self._spin_blur_radius.setSingleStep(1.0)

        self._combo_text_effect = ArrowComboBox()
        self._combo_text_effect.addItems(["None", "Rainbow", "Wave", "Typewriter", "Scramble", "Pulse"])
        self._spin_effect_speed = QDoubleSpinBox()
        self._spin_effect_speed.setRange(0.0, 25.0)
        self._spin_effect_speed.setDecimals(2)
        self._spin_effect_speed.setSingleStep(0.1)
        self._spin_effect_speed.setValue(1.0)
        self._spin_effect_amount = QDoubleSpinBox()
        self._spin_effect_amount.setRange(0.0, 250.0)
        self._spin_effect_amount.setDecimals(1)
        self._spin_effect_amount.setSingleStep(1.0)
        self._spin_effect_amount.setValue(20.0)

        self._combo_fill_mode = ArrowComboBox()
        self._combo_fill_mode.addItems(["Solid", "Gradient"])
        self._btn_text_color = QPushButton("Pick Color")
        self._btn_grad_start = QPushButton("Gradient Start")
        self._btn_grad_end = QPushButton("Gradient End")

        self._combo_presets = ArrowComboBox()
        self._btn_save_preset = QPushButton("Save Preset")
        self._btn_delete_preset = QPushButton("Delete Preset")

        text_form = QFormLayout()
        text_form.addRow("Text", self._txt_text)
        text_form.addRow("Font", self._font_combo)
        text_form.addRow("Size", self._spin_font_size)
        text_form.addRow("Fill", self._combo_fill_mode)
        text_form.addRow("", self._btn_text_color)
        text_form.addRow("", self._btn_grad_start)
        text_form.addRow("", self._btn_grad_end)
        text_form.addRow("", self._chk_shadow)
        text_form.addRow("Shadow blur", self._spin_shadow_blur)
        shadow_offset_row = QHBoxLayout()
        shadow_offset_row.addWidget(QLabel("dx"))
        shadow_offset_row.addWidget(self._spin_shadow_dx)
        shadow_offset_row.addWidget(QLabel("dy"))
        shadow_offset_row.addWidget(self._spin_shadow_dy)
        shadow_offset_widget = QWidget()
        shadow_offset_widget.setLayout(shadow_offset_row)
        text_form.addRow("Shadow offset", shadow_offset_widget)
        text_form.addRow("", self._btn_shadow_color)
        text_form.addRow("", self._chk_glow)
        text_form.addRow("Glow blur", self._spin_glow_blur)
        text_form.addRow("", self._btn_glow_color)
        text_form.addRow("", self._chk_blur)
        text_form.addRow("Blur radius", self._spin_blur_radius)
        text_form.addRow("Effect", self._combo_text_effect)
        text_form.addRow("Effect speed", self._spin_effect_speed)
        text_form.addRow("Effect amount", self._spin_effect_amount)

        presets_row = QHBoxLayout()
        presets_row.addWidget(self._combo_presets)
        presets_row.addWidget(self._btn_save_preset)
        presets_row.addWidget(self._btn_delete_preset)
        text_wrapper.addLayout(text_form)
        text_wrapper.addWidget(QLabel("Custom Colors"))
        text_wrapper.addLayout(presets_row)
        
        text_container.set_content_layout(text_wrapper)
        props_layout.addWidget(text_container)

        props_layout.addSpacing(12)

        effects_box = CollapsibleBox("Visual Effects")
        effects_form = QFormLayout()
        
        self._combo_effect_type = ArrowComboBox()
        self._combo_effect_type.addItems(["None", "Blur", "Shadow", "Glow", "Colorize"])
        
        self._spin_effect_radius = QDoubleSpinBox()
        self._spin_effect_radius.setRange(0.0, 200.0)
        self._spin_effect_radius.setDecimals(1)

        self._spin_effect_strength = QDoubleSpinBox()
        self._spin_effect_strength.setRange(0.0, 100.0)
        self._spin_effect_strength.setDecimals(0)
        self._spin_effect_strength.setSingleStep(5.0)
        self._spin_effect_strength.setValue(60.0)
        
        self._spin_effect_dx = QDoubleSpinBox()
        self._spin_effect_dy = QDoubleSpinBox()
        for s in (self._spin_effect_dx, self._spin_effect_dy):
            s.setRange(-500.0, 500.0)
            s.setDecimals(1)
            
        self._btn_effect_color = QPushButton("Color")
        
        effects_form.addRow("Type", self._combo_effect_type)
        effects_form.addRow("Radius", self._spin_effect_radius)
        effects_form.addRow("Strength %", self._spin_effect_strength)
        
        eff_offset_row = QHBoxLayout()
        eff_offset_row.addWidget(QLabel("dx"))
        eff_offset_row.addWidget(self._spin_effect_dx)
        eff_offset_row.addWidget(QLabel("dy"))
        eff_offset_row.addWidget(self._spin_effect_dy)
        eff_offset_widget = QWidget()
        eff_offset_widget.setLayout(eff_offset_row)
        
        effects_form.addRow("Offset", eff_offset_widget)
        effects_form.addRow("Color", self._btn_effect_color)
        
        effects_box.set_content_layout(effects_form)
        props_layout.addWidget(effects_box)
        props_layout.addSpacing(12)

        particles_container = CollapsibleBox("Particles")
        particles_wrapper = QVBoxLayout()
        
        self._combo_particle_preset = ArrowComboBox()
        self._combo_particle_preset.addItems(["Custom", "Snow", "Rain", "Explosion"])
        
        self._combo_particle_emission = ArrowComboBox()
        self._combo_particle_emission.addItems(["Point", "Rectangle"])
        
        self._spin_particle_direction = QDoubleSpinBox()
        self._spin_particle_direction.setRange(0.0, 360.0)
        
        self._spin_particle_count = QSpinBox()
        self._spin_particle_count.setRange(0, 10000)
        self._spin_particle_count.setSingleStep(10)
        self._spin_particle_speed = QDoubleSpinBox()
        self._spin_particle_speed.setRange(0.0, 1000.0)
        self._spin_particle_size = QDoubleSpinBox()
        self._spin_particle_size.setRange(0.1, 100.0)
        self._btn_particle_color = QPushButton("Color")
        self._spin_particle_gravity_x = QDoubleSpinBox()
        self._spin_particle_gravity_x.setRange(-1000.0, 1000.0)
        self._spin_particle_gravity_y = QDoubleSpinBox()
        self._spin_particle_gravity_y.setRange(-1000.0, 1000.0)
        self._spin_particle_lifetime = QDoubleSpinBox()
        self._spin_particle_lifetime.setRange(0.1, 60.0)
        self._spin_particle_spread = QDoubleSpinBox()
        self._spin_particle_spread.setRange(0.0, 360.0)

        particles_form = QFormLayout()
        particles_form.addRow("Preset", self._combo_particle_preset)
        particles_form.addRow("Emission", self._combo_particle_emission)
        particles_form.addRow("Direction", self._spin_particle_direction)
        particles_form.addRow("Count", self._spin_particle_count)
        particles_form.addRow("Speed", self._spin_particle_speed)
        particles_form.addRow("Size", self._spin_particle_size)
        particles_form.addRow("", self._btn_particle_color)
        particles_form.addRow("Gravity X", self._spin_particle_gravity_x)
        particles_form.addRow("Gravity Y", self._spin_particle_gravity_y)
        particles_form.addRow("Lifetime", self._spin_particle_lifetime)
        particles_form.addRow("Spread", self._spin_particle_spread)
        particles_wrapper.addLayout(particles_form)
        particles_container.set_content_layout(particles_wrapper)
        props_layout.addWidget(particles_container)

        self._particles_container = particles_container

        props_layout.addStretch(1)
        props_panel.setLayout(props_layout)
        props_scroll = QScrollArea()
        props_scroll.setWidgetResizable(True)
        props_scroll.setMinimumSize(1, 1)
        props_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        props_scroll.setWidget(props_panel)
        props_dock.setWidget(props_scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, props_dock)
        self._dock_props = props_dock

        self._refresh_presets()
        self._update_recent_menu()

    def _wire(self) -> None:
        self._act_save_layout.triggered.connect(self._save_layout)
        self._act_load_layout.triggered.connect(self._load_layout)
        self._act_export_packaged_layout.triggered.connect(self._export_packaged_layout)
        self._act_export_frame.triggered.connect(self._export_frame_image)
        self._act_recover_autosave.triggered.connect(self._recover_autosave)
        self._act_open_background.triggered.connect(self._open_background)
        self._act_background_color.triggered.connect(self._set_background_color)
        self._act_quit.triggered.connect(self._quit_from_tray)
        self._act_show_hotkeys.triggered.connect(self._show_hotkeys)
        self._act_zoom_in.triggered.connect(lambda: self._current_editor().view.zoom_in())
        self._act_zoom_out.triggered.connect(lambda: self._current_editor().view.zoom_out())
        self._act_zoom_reset.triggered.connect(lambda: self._current_editor().view.zoom_reset())
        self._act_theme_buttons.triggered.connect(lambda: self._pick_gui_theme_color("buttons"))
        self._act_theme_outer.triggered.connect(lambda: self._pick_gui_theme_color("outer"))
        self._act_theme_inner.triggered.connect(lambda: self._pick_gui_theme_color("inner"))
        self._act_theme_panel_bg.triggered.connect(lambda: self._pick_gui_theme_color("panel_bg"))
        self._act_theme_text_area_bg.triggered.connect(lambda: self._pick_gui_theme_color("text_area_bg"))
        self._act_theme_text.triggered.connect(lambda: self._pick_gui_theme_color("text"))
        self._act_theme_accent.triggered.connect(lambda: self._pick_gui_theme_color("accent"))
        self._act_theme_border.triggered.connect(lambda: self._pick_gui_theme_color("border"))
        self._act_theme_hover.triggered.connect(lambda: self._pick_gui_theme_color("hover"))
        self._act_theme_pressed.triggered.connect(lambda: self._pick_gui_theme_color("pressed"))
        self._act_theme_tab_active.triggered.connect(lambda: self._pick_gui_theme_color("tab_active"))
        self._act_theme_tab_inactive.triggered.connect(lambda: self._pick_gui_theme_color("tab_inactive"))
        self._act_theme_scroll_track.triggered.connect(lambda: self._pick_gui_theme_color("scroll_track"))
        self._act_theme_scroll_thumb.triggered.connect(lambda: self._pick_gui_theme_color("scroll_thumb"))
        self._act_theme_ui_font.triggered.connect(self._pick_gui_theme_ui_font)
        self._act_theme_control_padding.triggered.connect(self._pick_gui_theme_control_padding)
        self._act_theme_corner_radius.triggered.connect(self._pick_gui_theme_corner_radius)
        self._act_theme_preset_lavender.triggered.connect(lambda: self._apply_gui_theme_preset("lavender"))
        self._act_theme_preset_dark.triggered.connect(lambda: self._apply_gui_theme_preset("dark"))
        self._act_theme_preset_light.triggered.connect(lambda: self._apply_gui_theme_preset("light"))
        self._act_theme_preset_midnight.triggered.connect(lambda: self._apply_gui_theme_preset("midnight"))
        self._act_theme_reset.triggered.connect(self._reset_gui_theme)
        self._act_desktop_preview.toggled.connect(self._toggle_desktop_preview)
        self._act_keep_running.toggled.connect(self._toggle_keep_running)
        self._act_snap_grid.toggled.connect(self._toggle_snap_grid)
        self._act_snap_center.toggled.connect(self._toggle_snap_center)
        self._act_show_grid.toggled.connect(self._toggle_show_grid)
        self._act_duplicate_layer.triggered.connect(self._duplicate_selected_layer)
        self._act_bring_forward.triggered.connect(lambda: self._shift_selected_layer(-1))
        self._act_send_backward.triggered.connect(lambda: self._shift_selected_layer(1))
        self._act_bring_to_front.triggered.connect(lambda: self._move_selected_layer_to(edge="front"))
        self._act_send_to_back.triggered.connect(lambda: self._move_selected_layer_to(edge="back"))
        self._act_toggle_lock.triggered.connect(self._toggle_lock_selected_layer)
        self._act_toggle_hide.triggered.connect(self._toggle_hide_selected_layer)
        self._act_set_wallpaper_current.triggered.connect(self._set_wallpaper_current)
        self._act_unset_wallpaper_current.triggered.connect(self._unset_wallpaper_current)
        self._act_set_wallpaper.triggered.connect(self._set_wallpaper)
        self._act_unset_wallpaper.triggered.connect(self._unset_wallpaper)

        self._btn_add_text.clicked.connect(self._add_text)
        self._btn_add_media.clicked.connect(self._add_media)
        self._btn_add_particles.clicked.connect(self._add_particles)
        self._btn_layer_up.clicked.connect(self._move_layer_up)
        self._btn_layer_down.clicked.connect(self._move_layer_down)
        self._btn_layer_delete.clicked.connect(self._delete_layer)

        self._layers_list.currentItemChanged.connect(self._on_layers_current_changed)
        self._layers_list.itemDoubleClicked.connect(self._on_layer_double_clicked)
        self._layers_list.customContextMenuRequested.connect(self._on_layers_context_menu)
        self._layers_list.model().rowsAboutToBeMoved.connect(self._on_layers_reorder_started)
        self._layers_list.model().rowsMoved.connect(self._on_layers_reordered)
        self._monitor_tabs.currentChanged.connect(self._on_monitor_changed)

        self._btn_layout_add.clicked.connect(self._add_monitor_layout)
        self._btn_layout_update.clicked.connect(self._update_selected_monitor_layout)
        self._btn_layout_delete.clicked.connect(self._delete_selected_monitor_layout)
        self._btn_layout_new.clicked.connect(self._start_new_layout)
        self._btn_layout_prev.clicked.connect(lambda: self._cycle_prev_layout(monitor_index=self._current_monitor_index()))
        self._btn_layout_next.clicked.connect(lambda: self._cycle_next_layout(monitor_index=self._current_monitor_index()))
        self._btn_layout_rename.clicked.connect(self._rename_selected_monitor_layout)
        self._layouts_list.itemDoubleClicked.connect(self._apply_selected_monitor_layout)
        self._layouts_list.currentRowChanged.connect(self._on_layout_selection_changed)
        self._chk_layout_autocycle.toggled.connect(self._toggle_autocycle_for_current)
        self._spin_layout_interval.valueChanged.connect(self._update_autocycle_interval_for_current)

        self._shortcut_prev_layout = QShortcut(QKeySequence("Alt+Left"), self)
        self._shortcut_prev_layout.setContext(Qt.ApplicationShortcut)
        self._shortcut_prev_layout.activated.connect(self._on_prev_layout_shortcut)
        self._shortcut_next_layout = QShortcut(QKeySequence("Alt+Right"), self)
        self._shortcut_next_layout.setContext(Qt.ApplicationShortcut)
        self._shortcut_next_layout.activated.connect(self._on_next_layout_shortcut)

        for spin in (self._spin_x, self._spin_y, self._spin_scale, self._spin_rotation):
            spin.valueChanged.connect(self._apply_transform_from_ui)

        self._txt_layer_name.textEdited.connect(self._on_layer_name_text_edited)
        self._txt_layer_name.editingFinished.connect(self._commit_label_undo)
        self._spin_opacity.valueChanged.connect(self._on_opacity_changed_from_ui)
        self._combo_blend_mode.currentIndexChanged.connect(self._on_blend_mode_changed_from_ui)
        self._chk_layer_locked.toggled.connect(self._on_layer_locked_toggled_from_ui)
        self._chk_layer_hidden.toggled.connect(self._on_layer_hidden_toggled_from_ui)

        self._btn_align_left.clicked.connect(lambda: self._align_selected(horizontal="left"))
        self._btn_align_center.clicked.connect(lambda: self._align_selected(horizontal="center"))
        self._btn_align_right.clicked.connect(lambda: self._align_selected(horizontal="right"))
        self._btn_align_top.clicked.connect(lambda: self._align_selected(vertical="top"))
        self._btn_align_middle.clicked.connect(lambda: self._align_selected(vertical="middle"))
        self._btn_align_bottom.clicked.connect(lambda: self._align_selected(vertical="bottom"))
        self._btn_distribute_h.clicked.connect(lambda: self._distribute_selected(axis="x"))
        self._btn_distribute_v.clicked.connect(lambda: self._distribute_selected(axis="y"))
        self._btn_match_w.clicked.connect(lambda: self._match_size_selected(axis="w"))
        self._btn_match_h.clicked.connect(lambda: self._match_size_selected(axis="h"))
        self._btn_fit_canvas.clicked.connect(lambda: self._fit_selected_to_canvas("fit"))
        self._btn_fill_canvas.clicked.connect(lambda: self._fit_selected_to_canvas("fill"))
        self._btn_anim_start.clicked.connect(self._start_animation_selected)
        self._btn_anim_stop.clicked.connect(self._stop_animation_selected)
        self._btn_anim_draw_path.clicked.connect(self._draw_follow_path)
        self._btn_anim_pick_center.clicked.connect(self._pick_orbit_center)
        self._combo_anim_mode.currentIndexChanged.connect(self._refresh_animation_controls)
        self._chk_anim_avoid_taskbar.toggled.connect(self._toggle_anim_avoid_taskbar)

        self._txt_text.textEdited.connect(self._apply_text_from_ui)
        self._font_combo.currentTextChanged.connect(self._apply_text_from_ui)
        self._spin_font_size.valueChanged.connect(self._apply_text_from_ui)
        self._combo_fill_mode.currentIndexChanged.connect(self._apply_text_from_ui)
        self._chk_shadow.stateChanged.connect(self._apply_text_from_ui)
        self._chk_glow.stateChanged.connect(self._apply_text_from_ui)
        self._spin_shadow_blur.valueChanged.connect(self._apply_text_from_ui)
        self._spin_shadow_dx.valueChanged.connect(self._apply_text_from_ui)
        self._spin_shadow_dy.valueChanged.connect(self._apply_text_from_ui)
        self._spin_glow_blur.valueChanged.connect(self._apply_text_from_ui)
        self._chk_blur.stateChanged.connect(self._apply_text_from_ui)
        self._spin_blur_radius.valueChanged.connect(self._apply_text_from_ui)
        self._combo_text_effect.currentIndexChanged.connect(self._apply_text_from_ui)
        self._spin_effect_speed.valueChanged.connect(self._apply_text_from_ui)
        self._spin_effect_amount.valueChanged.connect(self._apply_text_from_ui)

        self._btn_text_color.clicked.connect(lambda: self._pick_text_color(mode="solid"))
        self._btn_grad_start.clicked.connect(lambda: self._pick_text_color(mode="grad_start"))
        self._btn_grad_end.clicked.connect(lambda: self._pick_text_color(mode="grad_end"))
        self._btn_shadow_color.clicked.connect(lambda: self._pick_text_color(mode="shadow"))
        self._btn_glow_color.clicked.connect(lambda: self._pick_text_color(mode="glow"))

        self._combo_presets.currentIndexChanged.connect(self._apply_preset_to_text)
        self._btn_save_preset.clicked.connect(self._save_preset)
        self._btn_delete_preset.clicked.connect(self._delete_preset)

        self._combo_effect_type.currentIndexChanged.connect(self._apply_visual_effects_from_ui)
        self._spin_effect_radius.valueChanged.connect(self._apply_visual_effects_from_ui)
        self._spin_effect_strength.valueChanged.connect(self._apply_visual_effects_from_ui)
        self._spin_effect_dx.valueChanged.connect(self._apply_visual_effects_from_ui)
        self._spin_effect_dy.valueChanged.connect(self._apply_visual_effects_from_ui)
        self._btn_effect_color.clicked.connect(self._pick_effect_color)

        self._spin_particle_count.valueChanged.connect(self._apply_particles_from_ui)
        self._spin_particle_speed.valueChanged.connect(self._apply_particles_from_ui)
        self._spin_particle_size.valueChanged.connect(self._apply_particles_from_ui)
        self._btn_particle_color.clicked.connect(self._pick_particle_color)
        self._spin_particle_gravity_x.valueChanged.connect(self._apply_particles_from_ui)
        self._spin_particle_gravity_y.valueChanged.connect(self._apply_particles_from_ui)
        self._spin_particle_lifetime.valueChanged.connect(self._apply_particles_from_ui)
        self._spin_particle_spread.valueChanged.connect(self._apply_particles_from_ui)
        
        self._combo_particle_preset.currentIndexChanged.connect(self._apply_particle_preset)
        self._combo_particle_emission.currentIndexChanged.connect(self._apply_particles_from_ui)
        self._spin_particle_direction.valueChanged.connect(self._apply_particles_from_ui)

        # Media controls wiring
        self._btn_media_play.clicked.connect(self._on_media_play)
        self._btn_media_pause.clicked.connect(self._on_media_pause)
        self._btn_media_stop.clicked.connect(self._on_media_stop)
        self._chk_media_mute.toggled.connect(self._on_media_mute_toggled)
        self._slider_media_volume.valueChanged.connect(self._on_media_volume_changed)
        self._combo_media_aspect.currentIndexChanged.connect(self._on_media_aspect_changed)
        self._spin_media_speed.valueChanged.connect(self._on_media_speed_changed)

    def _install_shortcuts(self) -> None:
        self._hotkey_entries: list[tuple[str, str]] = []

        def record(keys: str, desc: str) -> None:
            self._hotkey_entries.append((str(keys), str(desc)))

        self._editor_shortcuts: list[QShortcut] = []

        def add_editor_shortcut(seq: str, desc: str, fn) -> None:
            sc = QShortcut(QKeySequence(seq), self._monitor_tabs)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
            self._editor_shortcuts.append(sc)
            record(seq, desc)

        add_editor_shortcut("Left", "Nudge left (1px)", lambda: self._nudge_selected(dx=-1.0, dy=0.0))
        add_editor_shortcut("Right", "Nudge right (1px)", lambda: self._nudge_selected(dx=1.0, dy=0.0))
        add_editor_shortcut("Up", "Nudge up (1px)", lambda: self._nudge_selected(dx=0.0, dy=-1.0))
        add_editor_shortcut("Down", "Nudge down (1px)", lambda: self._nudge_selected(dx=0.0, dy=1.0))
        add_editor_shortcut("Shift+Left", "Nudge left (10px)", lambda: self._nudge_selected(dx=-10.0, dy=0.0))
        add_editor_shortcut("Shift+Right", "Nudge right (10px)", lambda: self._nudge_selected(dx=10.0, dy=0.0))
        add_editor_shortcut("Shift+Up", "Nudge up (10px)", lambda: self._nudge_selected(dx=0.0, dy=-10.0))
        add_editor_shortcut("Shift+Down", "Nudge down (10px)", lambda: self._nudge_selected(dx=0.0, dy=10.0))
        add_editor_shortcut("Delete", "Delete selected layer", self._delete_layer)

        self._global_shortcuts: list[QShortcut] = []

        def add_global_shortcut(seq: str, desc: str, fn) -> None:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(fn)
            self._global_shortcuts.append(sc)
            record(seq, desc)

        add_global_shortcut("Ctrl+D", "Duplicate selected layer", self._duplicate_selected_layer)
        add_global_shortcut("Ctrl+]", "Bring forward (one step)", lambda: self._shift_selected_layer(-1))
        add_global_shortcut("Ctrl+[", "Send backward (one step)", lambda: self._shift_selected_layer(1))
        add_global_shortcut("Ctrl+Shift+]", "Bring to front", lambda: self._move_selected_layer_to(edge="front"))
        add_global_shortcut("Ctrl+Shift+[", "Send to back", lambda: self._move_selected_layer_to(edge="back"))
        add_global_shortcut("Ctrl+L", "Toggle lock", self._toggle_lock_selected_layer)
        add_global_shortcut("Ctrl+H", "Toggle hide", self._toggle_hide_selected_layer)
        add_global_shortcut("Ctrl+G", "Toggle snap grid", lambda: self._act_snap_grid.toggle())
        add_global_shortcut("Ctrl+Shift+G", "Toggle snap center", lambda: self._act_snap_center.toggle())
        add_global_shortcut("Ctrl+=", "Zoom in", lambda: self._current_editor().view.zoom_in())
        add_global_shortcut("Ctrl+-", "Zoom out", lambda: self._current_editor().view.zoom_out())
        add_global_shortcut("Ctrl+0", "Reset zoom / fit canvas", lambda: self._current_editor().view.zoom_reset())
        record("Middle-drag", "Pan canvas")

        record("Alt+Left", "Previous layout")
        record("Alt+Right", "Next layout")
        record("Ctrl+Mouse Wheel", "Rotate selected (5° steps)")
        record("Mouse Wheel", "Scale selected (5% steps)")

        try:
            record(str(self._act_undo.shortcut().toString()), "Undo")
        except Exception:
            pass
        try:
            record(str(self._act_redo.shortcut().toString()), "Redo")
        except Exception:
            pass
        try:
            record(str(self._act_quit.shortcut().toString()), "Quit")
        except Exception:
            pass

    def _show_hotkeys(self) -> None:
        entries: list[tuple[str, str]] = []
        try:
            entries = list(getattr(self, "_hotkey_entries", []))
        except Exception:
            entries = []
        norm: dict[str, str] = {}
        for keys, desc in entries:
            k = str(keys).strip()
            d = str(desc).strip()
            if not k or not d:
                continue
            norm[k] = d
        items = sorted(norm.items(), key=lambda t: t[0].lower())

        rows = "\n".join(
            f"<tr><td style='padding:4px 10px 4px 0; white-space:nowrap;'><b>{k}</b></td><td style='padding:4px 0;'>{v}</td></tr>"
            for k, v in items
        )
        html = f"""
        <html>
        <body>
          <h3>Hotkeys</h3>
          <table>{rows}</table>
        </body>
        </html>
        """

        dlg = QDialog(self)
        dlg.setWindowTitle("Hotkeys")
        dlg.resize(560, 520)
        layout = QVBoxLayout()
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        layout.addWidget(browser)
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.setLayout(layout)
        dlg.exec()

    def _nudge_selected(self, dx: float, dy: float) -> None:
        item = self._selected_graphics_item()
        if item is None:
            return
        try:
            movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
        except Exception:
            movable = True
        if not movable:
            return
        monitor_index = self._current_monitor_index()
        gid = id(item)
        if not self._undo_blocked:
            if (
                self._transform_baseline is None
                or self._transform_baseline[0] != monitor_index
                or self._transform_baseline[1] != gid
            ):
                try:
                    self._transform_baseline = (
                        monitor_index,
                        gid,
                        (
                            float(item.pos().x()),
                            float(item.pos().y()),
                            float(item.scale()),
                            float(item.rotation()),
                        ),
                    )
                except Exception:
                    self._transform_baseline = None
        try:
            pos = item.pos()
            proposed = QPointF(float(pos.x()) + float(dx), float(pos.y()) + float(dy))
            try:
                proposed = self._current_scene().snap_position(item, proposed)
            except Exception:
                pass
            item.setPos(proposed)
        except Exception:
            return
        self._sync_transform_to_ui(item)
        if not self._undo_blocked:
            self._transform_undo_timer.start(250)

    def _shift_selected_layer(self, delta: int) -> None:
        item = self._selected_graphics_item()
        if item is None:
            return
        gid = id(item)
        monitor_index = self._current_monitor_index()
        state = self._current_state()
        if gid not in state.order:
            return
        before = list(state.order)
        i = state.order.index(gid)
        j = i + int(delta)
        if j < 0 or j >= len(state.order):
            return
        after = list(state.order)
        after[i], after[j] = after[j], after[i]
        self._undo_stack.push(_ReorderLayersCommand(self, monitor_index, before, after, select_gid=gid))

    def _move_selected_layer_to(self, edge: str) -> None:
        item = self._selected_graphics_item()
        if item is None:
            return
        gid = id(item)
        monitor_index = self._current_monitor_index()
        state = self._current_state()
        if gid not in state.order:
            return
        before = list(state.order)
        after = [x for x in state.order if x != gid]
        if edge == "front":
            after.insert(0, gid)
        else:
            after.append(gid)
        if after == before:
            return
        self._undo_stack.push(_ReorderLayersCommand(self, monitor_index, before, after, select_gid=gid))

    def _duplicate_selected_layer(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox)):
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        state = self._current_state()
        label = str(state.labels.get(id(item), "Layer"))
        payload = dict(self._serialize_layer(item, label))
        payload.pop("locked", None)
        payload.pop("hidden", None)
        payload.pop("opacity", None)
        if payload.get("type") == "text":
            payload.pop("id", None)
        else:
            src = payload.get("source")
            if not isinstance(src, str) or not src or not Path(src).exists():
                QMessageBox.warning(self, "Duplicate", "This layer's source file is missing.")
                return
        monitor_index = self._current_monitor_index()

        def create():
            missing_files: list[str] = []
            created = self._create_layer_from_payload(self._current_scene(), payload, missing_files, base_dir=None)
            if created is None:
                item = self._current_scene().add_text_layer()
                return item, "Text"
            new_item, new_label = created
            self._apply_transform_from_payload(new_item, payload.get("transform"))
            try:
                pos = new_item.pos()
                new_item.setPos(QPointF(float(pos.x()) + 20.0, float(pos.y()) + 20.0))
            except Exception:
                pass
            return new_item, str(new_label)

        self._undo_stack.push(_AddLayerCommand(self, monitor_index, create))

    def _pick_particle_color(self) -> None:
        item = self._selected_graphics_item()
        if not isinstance(item, ParticleLayerItem):
            return
        c = QColorDialog.getColor(item.color, self, "Pick Particle Color", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            item.color = c
            self._sync_layer_props_to_ui()

    def _apply_particles_from_ui(self) -> None:
        if self._undo_blocked:
            return
        item = self._selected_graphics_item()
        if not isinstance(item, ParticleLayerItem):
            return

        item.count = self._spin_particle_count.value()
        item.speed = self._spin_particle_speed.value()
        item.size = self._spin_particle_size.value()
        item.gravity_x = self._spin_particle_gravity_x.value()
        item.gravity_y = self._spin_particle_gravity_y.value()
        item.lifetime = self._spin_particle_lifetime.value()
        item.spread = self._spin_particle_spread.value()
        item.emission_mode = "rect" if self._combo_particle_emission.currentText() == "Rectangle" else "point"
        item.direction = self._spin_particle_direction.value()

    def _apply_particle_preset(self) -> None:
        preset = self._combo_particle_preset.currentText()
        if preset == "Custom":
            return
            
        item = self._selected_graphics_item()
        if not isinstance(item, ParticleLayerItem):
            return
            
        if preset == "Snow":
            item.count = 200
            item.speed = 20.0
            item.size = 2.0
            item.gravity_x = 0.0
            item.gravity_y = 10.0
            item.lifetime = 10.0
            item.spread = 360.0
            item.emission_mode = "rect"
            item.direction = 90.0
            item.color = QColor("white")
        elif preset == "Rain":
            item.count = 500
            item.speed = 150.0
            item.size = 1.5
            item.gravity_x = 0.0
            item.gravity_y = 0.0
            item.lifetime = 2.0
            item.spread = 0.0
            item.emission_mode = "rect"
            item.direction = 90.0
            item.color = QColor(150, 150, 255)
        elif preset == "Explosion":
            item.count = 300
            item.speed = 200.0
            item.size = 3.0
            item.gravity_x = 0.0
            item.gravity_y = 0.0
            item.lifetime = 1.0
            item.spread = 360.0
            item.emission_mode = "point"
            item.direction = 0.0
            item.color = QColor("orange")
            
        self._sync_particles_to_ui(item)

    def _toggle_lock_selected_layer(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox)):
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        try:
            locked_now = bool(item.data(ITEM_DATA_LOCKED))
        except Exception:
            locked_now = False
        self._undo_stack.push(_SetLayerLockedCommand(self, monitor_index, item, locked_now, not locked_now))

    def _toggle_hide_selected_layer(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox)):
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        try:
            hidden_now = bool(item.data(ITEM_DATA_HIDDEN))
        except Exception:
            hidden_now = False
        self._undo_stack.push(_SetLayerHiddenCommand(self, monitor_index, item, hidden_now, not hidden_now))

    def _toggle_snap_grid(self, enabled: bool) -> None:
        for editor in self._monitor_editors:
            try:
                editor.scene.set_snap_grid(bool(enabled))
            except Exception:
                pass

    def _toggle_snap_center(self, enabled: bool) -> None:
        for editor in self._monitor_editors:
            try:
                editor.scene.set_snap_center(bool(enabled))
            except Exception:
                pass

    def _toggle_show_grid(self, enabled: bool) -> None:
        for editor in self._monitor_editors:
            try:
                editor.view.set_grid_size(float(editor.scene._snap_grid_size))
            except Exception:
                pass
            try:
                editor.view.set_grid_visible(bool(enabled))
            except Exception:
                pass

    def _toggle_anim_avoid_taskbar(self, enabled: bool) -> None:
        for editor in self._monitor_editors:
            try:
                editor.scene.set_anim_avoid_taskbar(bool(enabled))
            except Exception:
                pass

    def _toggle_desktop_preview(self, enabled: bool) -> None:
        if enabled and not self._screens:
            self._act_desktop_preview.setChecked(False)
            return

        for i, screen in enumerate(self._screens):
            geo = screen.geometry()
            work = screen.availableGeometry()
            screen_rect = QRectF(0, 0, geo.width(), geo.height())
            work_rect = QRectF(work.x() - geo.x(), work.y() - geo.y(), work.width(), work.height())
            scene = self._monitor_editors[i].scene
            if enabled:
                scene.set_desktop_preview(True, screen_rect=screen_rect, work_rect=work_rect)
            else:
                scene.set_desktop_preview(False)
                scene.setSceneRect(screen_rect)
            self._monitor_editors[i].fit_to_scene()

    def _refresh_presets(self) -> None:
        self._combo_presets.blockSignals(True)
        self._combo_presets.clear()
        for p in self._color_presets.presets:
            self._combo_presets.addItem(p.name, p.color)
        self._combo_presets.blockSignals(False)

    def _load_layout_cycles(self) -> None:
        if not self._layout_cycles_path.exists():
            self._layout_cycles = {}
            return
        try:
            data = json.loads(self._layout_cycles_path.read_text(encoding="utf-8"))
        except Exception:
            self._layout_cycles = {}
            return
        monitors = data.get("monitors", {})
        if not isinstance(monitors, dict):
            self._layout_cycles = {}
            return
        loaded: dict[int, dict] = {}
        for k, v in monitors.items():
            try:
                idx = int(k)
            except Exception:
                continue
            if not isinstance(v, dict):
                continue
            try:
                default_interval = int(v.get("default_interval", v.get("interval", 60)))
            except Exception:
                default_interval = 60
            default_interval = max(1, min(86_400, default_interval))
            layouts = v.get("layouts", [])
            if not isinstance(layouts, list):
                layouts = []
            norm_layouts: list[dict] = []
            for it in layouts:
                if not isinstance(it, dict):
                    continue
                name = it.get("name")
                payload = it.get("payload")
                if not isinstance(name, str):
                    name = "Layout"
                if not isinstance(payload, dict):
                    payload = {}
                try:
                    interval = int(it.get("interval", default_interval))
                except Exception:
                    interval = default_interval
                interval = max(1, min(86_400, interval))
                norm_layouts.append({"name": name, "payload": payload, "interval": interval})
            auto = bool(v.get("auto", False))
            try:
                current = int(v.get("current", 0))
            except Exception:
                current = 0
            current = max(0, min(len(norm_layouts) - 1, current)) if norm_layouts else 0
            loaded[idx] = {
                "layouts": norm_layouts,
                "auto": auto,
                "default_interval": default_interval,
                "current": current,
            }
        self._layout_cycles = loaded

        for i in self._cycle_timers.keys():
            self._maybe_restart_cycle_timer(i)

    def _save_layout_cycles(self) -> None:
        monitors: dict[str, dict] = {}
        for idx, state in self._layout_cycles.items():
            if not isinstance(idx, int):
                continue
            layouts = state.get("layouts", [])
            if not isinstance(layouts, list):
                layouts = []
            try:
                default_interval = int(state.get("default_interval", 60))
            except Exception:
                default_interval = 60
            default_interval = max(1, min(86_400, default_interval))
            norm_layouts: list[dict] = []
            for it in layouts:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name", "Layout"))
                payload = it.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                try:
                    interval = int(it.get("interval", default_interval))
                except Exception:
                    interval = default_interval
                interval = max(1, min(86_400, interval))
                norm_layouts.append({"name": name, "payload": payload, "interval": interval})
            monitors[str(idx)] = {
                "layouts": norm_layouts,
                "auto": bool(state.get("auto", False)),
                "default_interval": default_interval,
                "current": int(state.get("current", 0)),
            }
        payload = {"version": 1, "monitors": monitors}
        try:
            self._layout_cycles_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _layout_cycle_state(self, monitor_index: int) -> dict:
        state = self._layout_cycles.get(monitor_index)
        if not isinstance(state, dict):
            state = {"layouts": [], "auto": False, "default_interval": 60, "current": 0}
            self._layout_cycles[monitor_index] = state
        if "layouts" not in state or not isinstance(state.get("layouts"), list):
            state["layouts"] = []
        if "auto" not in state:
            state["auto"] = False
        if "default_interval" not in state:
            state["default_interval"] = 60
        if "current" not in state:
            state["current"] = 0
        try:
            default_interval = int(state.get("default_interval", 60))
        except Exception:
            default_interval = 60
        default_interval = max(1, min(86_400, default_interval))
        state["default_interval"] = default_interval
        for it in state["layouts"]:
            if not isinstance(it, dict):
                continue
            if "interval" not in it:
                it["interval"] = default_interval
            else:
                try:
                    it["interval"] = max(1, min(86_400, int(it.get("interval", default_interval))))
                except Exception:
                    it["interval"] = default_interval
        return state

    def _refresh_layouts_ui(self) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)

        self._layouts_list.blockSignals(True)
        try:
            self._layouts_list.clear()
            for it in state["layouts"]:
                name = it.get("name") if isinstance(it, dict) else None
                if not isinstance(name, str) or not name.strip():
                    name = "Layout"
                self._layouts_list.addItem(QListWidgetItem(name))
            current = int(state.get("current", 0))
            if 0 <= current < self._layouts_list.count():
                self._layouts_list.setCurrentRow(current)
        finally:
            self._layouts_list.blockSignals(False)

        self._chk_layout_autocycle.blockSignals(True)
        self._spin_layout_interval.blockSignals(True)
        try:
            self._chk_layout_autocycle.setChecked(bool(state.get("auto", False)))
            layouts = state.get("layouts", [])
            current = int(state.get("current", 0))
            try:
                interval = int(state.get("default_interval", 60))
            except Exception:
                interval = 60
            if isinstance(layouts, list) and 0 <= current < len(layouts) and isinstance(layouts[current], dict):
                try:
                    interval = int(layouts[current].get("interval", interval))
                except Exception:
                    interval = int(state.get("default_interval", 60))
            interval = max(1, min(86_400, int(interval)))
            self._spin_layout_interval.setValue(interval)
            self._spin_layout_interval.setEnabled(bool(layouts))
        finally:
            self._chk_layout_autocycle.blockSignals(False)
        self._spin_layout_interval.blockSignals(False)

    def _apply_fps_cap(self, fps: int) -> None:
        try:
            value = int(fps)
        except Exception:
            value = 30
        value = max(1, min(240, value))
        self._fps_cap = value
        for editor in self._monitor_editors:
            try:
                editor.scene.set_fps_cap(value)
            except Exception:
                pass
        for fps_value, action in getattr(self, "_fps_actions", {}).items():
            try:
                action.setChecked(int(fps_value) == value)
            except Exception:
                pass

    def _refresh_scene_activity(self) -> None:
        """Only animate what the user can actually see: the visible editor tab or a
        monitor that is hosting the live wallpaper."""
        try:
            window_active = bool(self.isVisible()) and not bool(self.isMinimized())
        except Exception:
            window_active = True
        current = self._current_monitor_index()
        for i, editor in enumerate(self._monitor_editors):
            active = i in self._wallpaper_windows
            if not active and window_active and i == current:
                active = True
            try:
                editor.scene.set_render_active(bool(active))
            except Exception:
                pass

    def _remember_recent_layout(self, path: str) -> None:
        try:
            resolved = str(Path(path).resolve())
        except Exception:
            resolved = str(path)
        if not resolved:
            return
        try:
            if Path(resolved) == Path(self._autosave_path).resolve():
                return
        except Exception:
            pass
        recents = [p for p in self._recent_layouts if p != resolved]
        recents.insert(0, resolved)
        self._recent_layouts = recents[:8]
        # Defer the menu rebuild: it is often triggered from an action that
        # lives in the menu being cleared.
        QTimer.singleShot(0, self._update_recent_menu)

    def _clear_recent_layouts(self) -> None:
        self._recent_layouts = []
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        menu = getattr(self, "_menu_recent", None)
        if menu is None:
            return
        menu.clear()
        existing = [p for p in self._recent_layouts if Path(p).exists()]
        if not existing:
            empty = QAction("(no recent layouts)", self)
            empty.setEnabled(False)
            menu.addAction(empty)
            return
        for path in existing:
            action = QAction(path, self)
            action.triggered.connect(lambda _checked=False, p=path: self._load_layout_from_path(p, show_errors=True))
            menu.addAction(action)
        menu.addSeparator()
        clear_action = QAction("Clear Recent", self)
        clear_action.triggered.connect(self._clear_recent_layouts)
        menu.addAction(clear_action)

    def _autosave_now(self) -> None:
        try:
            payload = self._serialize_layout()
        except Exception:
            return
        has_content = False
        for monitor in payload.get("monitors", []) or []:
            if not isinstance(monitor, dict):
                continue
            background = monitor.get("background")
            if isinstance(background, dict) and (background.get("path") or background.get("color")):
                has_content = True
                break
            if monitor.get("layers"):
                has_content = True
                break
        if not has_content:
            return
        try:
            serialized = json.dumps(payload, sort_keys=True)
        except Exception:
            serialized = ""
        if serialized and serialized == self._autosave_last_json:
            return
        try:
            save_layout_file(str(self._autosave_path), payload)
            self._autosave_last_json = serialized
        except Exception:
            pass

    def _recover_autosave(self) -> None:
        if not self._autosave_path.exists():
            QMessageBox.information(self, "Recover Autosave", "There is no autosave file yet.")
            return
        answer = QMessageBox.question(
            self,
            "Recover Autosave",
            "Replace the current layouts with the last autosaved version?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._load_layout_from_path(str(self._autosave_path), show_errors=True)

    def _handle_ipc_command(self, command: str) -> None:
        for raw in (command or "").splitlines():
            line = (raw or "").strip()
            if not line:
                continue
            parts = line.split(None, 1)
            cmd = parts[0].strip().lower()
            arg = parts[1].strip() if len(parts) == 2 else ""

            if cmd == "activate_reset":
                try:
                    self._unset_wallpaper()
                except Exception:
                    pass
                self._show_from_tray()
                return
            if cmd == "activate":
                self._show_from_tray()
                return
            if cmd == "load_layout":
                if arg and Path(arg).exists():
                    self._load_layout_from_path(arg, show_errors=False)

    def _serialize_monitor_layout(self, monitor_index: int) -> dict:
        scene = self._monitor_editors[monitor_index].scene
        state = self._monitor_states[monitor_index]
        bg = scene.background_state()
        layers: list[dict] = []
        for gid in state.order:
            item = state.items.get(gid)
            if item is None:
                continue
            layers.append(self._serialize_layer(item, state.labels.get(gid, "Layer")))
        return {
            "follow_paths": self._serialize_follow_paths(),
            "orbit_centers": self._serialize_orbit_centers(scene),
            "background": {
                "path": str(bg.path) if bg.path is not None else None,
                "kind": bg.kind,
                "color": getattr(bg, "color", None),
            },
            "layers": layers,
        }

    def _serialize_orbit_centers(self, scene) -> dict[str, list[float]]:
        try:
            norms = scene.orbit_center_norms()
        except Exception:
            norms = {}
        out: dict[str, list[float]] = {}
        for cid, v in (norms or {}).items():
            if not isinstance(cid, str) or not cid:
                continue
            try:
                out[str(cid)] = [float(v[0]), float(v[1])]
            except Exception:
                continue
        return out

    def _apply_orbit_centers_to_scene(self, scene, data: object) -> None:
        if not isinstance(data, dict):
            try:
                scene.set_orbit_center_norms({})
            except Exception:
                pass
            return
        try:
            scene.set_orbit_center_norms(data)
        except Exception:
            pass

    def _serialize_follow_paths(self) -> dict[str, list[list[float]]]:
        out: dict[str, list[list[float]]] = {}
        for pid, pts in (self._follow_paths or {}).items():
            if not isinstance(pid, str) or not pid:
                continue
            norm: list[list[float]] = []
            for p in pts or []:
                try:
                    norm.append([float(p.x()), float(p.y())])
                except Exception:
                    continue
            out[str(pid)] = norm
        return out

    def _apply_follow_paths_from_payload(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        base: dict[str, list[QPointF]] = {}
        for k in (self._follow_paths or {}).keys():
            if isinstance(k, str) and k:
                base[str(k)] = []

        for pid, pts in data.items():
            if not isinstance(pid, str) or not pid:
                continue
            if not isinstance(pts, list):
                continue
            norm: list[QPointF] = []
            for p in pts:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    try:
                        norm.append(QPointF(float(p[0]), float(p[1])))
                    except Exception:
                        continue
            base[str(pid)] = norm

        if "path1" not in base:
            base["path1"] = []
        self._follow_paths = base
        self._global_path_points = list(base.get("path1") or [])
        for editor in self._monitor_editors:
            try:
                editor.scene.set_global_paths(self._follow_paths)
            except Exception:
                pass

    def _jsonify_layout_value(self, value: object) -> object:
        if isinstance(value, QPointF):
            return [float(value.x()), float(value.y())]
        if isinstance(value, dict):
            out: dict[str, object] = {}
            for k, v in value.items():
                if not isinstance(k, str) or not k:
                    continue
                out[str(k)] = self._jsonify_layout_value(v)
            return out
        if isinstance(value, (list, tuple)):
            return [self._jsonify_layout_value(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        try:
            return float(value)
        except Exception:
            return str(value)

    def _apply_monitor_layout(self, monitor_index: int, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._apply_follow_paths_from_payload(payload.get("follow_paths"))
        self._clear_monitor_layout(monitor_index)
        scene = self._monitor_editors[monitor_index].scene
        self._apply_orbit_centers_to_scene(scene, payload.get("orbit_centers"))
        state = self._monitor_states[monitor_index]
        missing_files: list[str] = []

        bg = payload.get("background")
        bg_path = None
        if isinstance(bg, dict):
            p = bg.get("path")
            if isinstance(p, str) and p:
                bg_path = self._resolve_layout_path(p, base_dir=None)
        bg_color = bg.get("color") if isinstance(bg, dict) else None
        bg_kind = str(bg.get("kind") or "") if isinstance(bg, dict) else ""
        if bg_path is None and bg_kind == "color" and isinstance(bg_color, str) and bg_color.strip():
            try:
                scene.set_background_color(QColor(bg_color))
            except Exception:
                pass
        elif bg_path is not None and Path(bg_path).exists():
            scene.set_background(str(bg_path))
        elif bg_path is not None:
            missing_files.append(str(bg_path))

        layers_payload = payload.get("layers")
        if not isinstance(layers_payload, list):
            layers_payload = []

        gids: list[int] = []
        for layer in layers_payload:
            if not isinstance(layer, dict):
                continue
            created = self._create_layer_from_payload(scene, layer, missing_files, base_dir=None)
            if created is None:
                continue
            item, label = created
            self._apply_transform_from_payload(item, layer.get("transform"))
            gid = id(item)
            state.items[gid] = item
            state.labels[gid] = label
            gids.append(gid)
        state.order = gids
        self._apply_z_from_state(state)
        try:
            scene.refresh_animation()
        except Exception:
            pass

        if monitor_index == self._current_monitor_index():
            self._rebuild_layers_list()

        if missing_files:
            short = "\n".join(missing_files[:20])
            more = "" if len(missing_files) <= 20 else f"\n… and {len(missing_files) - 20} more"
            QMessageBox.warning(self, "Layouts", f"Some files were missing and were skipped:\n{short}{more}")

    def _selected_layout_row(self) -> int:
        return int(self._layouts_list.currentRow())

    def _start_new_layout(self) -> None:
        i = self._current_monitor_index()
        self._clear_monitor_layout(i)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Background",
            str(project_dir()),
            "Media Files (*.mp4 *.mkv *.avi *.mov *.webm *.gif *.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if path:
            try:
                self._monitor_editors[i].scene.set_background(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load background:\n{e}")
        self._on_monitor_changed(self._monitor_tabs.currentIndex())

    def _add_monitor_layout(self) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        suggested = f"Layout {len(state['layouts']) + 1}"
        name, ok = QInputDialog.getText(self, "Add Layout", "Name:", text=suggested)
        if not ok:
            return
        name = (name or "").strip() or suggested
        payload = self._serialize_monitor_layout(i)
        try:
            interval = int(self._spin_layout_interval.value())
        except Exception:
            interval = int(state.get("default_interval", 60))
        interval = max(1, min(86_400, interval))
        state["default_interval"] = interval
        state["layouts"].append({"name": name, "payload": payload, "interval": interval})
        state["current"] = len(state["layouts"]) - 1
        self._save_layout_cycles()
        self._refresh_layouts_ui()
        self._maybe_restart_cycle_timer(i)

    def _update_selected_monitor_layout(self) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        row = self._selected_layout_row()
        if row < 0 or row >= len(state["layouts"]):
            return
        payload = self._serialize_monitor_layout(i)
        state["layouts"][row]["payload"] = payload
        state["current"] = row
        self._save_layout_cycles()
        self._refresh_layouts_ui()

    def _delete_selected_monitor_layout(self) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        row = self._selected_layout_row()
        if row < 0 or row >= len(state["layouts"]):
            return
        state["layouts"].pop(row)
        if not state["layouts"]:
            state["current"] = 0
        else:
            state["current"] = max(0, min(len(state["layouts"]) - 1, row))
        self._save_layout_cycles()
        self._refresh_layouts_ui()
        self._maybe_restart_cycle_timer(i)

    def _rename_selected_monitor_layout(self) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        row = self._selected_layout_row()
        if row < 0 or row >= len(state["layouts"]):
            return
        current_name = str(state["layouts"][row].get("name", "Layout"))
        name, ok = QInputDialog.getText(self, "Rename Layout", "Name:", text=current_name)
        if not ok:
            return
        name = (name or "").strip() or current_name
        state["layouts"][row]["name"] = name
        self._save_layout_cycles()
        self._refresh_layouts_ui()

    def _apply_selected_monitor_layout(self, _item: QListWidgetItem | None = None) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        row = self._selected_layout_row()
        if row < 0 or row >= len(state["layouts"]):
            return
        payload = state["layouts"][row].get("payload")
        if not isinstance(payload, dict):
            return
        state["current"] = row
        self._save_layout_cycles()
        self._apply_monitor_layout(i, payload)
        self._refresh_layouts_ui()
        if bool(state.get("auto", False)):
            self._maybe_restart_cycle_timer(i)

    def _on_layout_selection_changed(self, row: int) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        if row < 0 or row >= len(state["layouts"]):
            return
        state["current"] = int(row)
        self._save_layout_cycles()
        self._refresh_layouts_ui()
        if bool(state.get("auto", False)):
            self._maybe_restart_cycle_timer(i)

    def _toggle_autocycle_for_current(self, enabled: bool) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        state["auto"] = bool(enabled)
        self._save_layout_cycles()
        self._maybe_restart_cycle_timer(i)

    def _update_autocycle_interval_for_current(self, seconds: int) -> None:
        i = self._current_monitor_index()
        state = self._layout_cycle_state(i)
        try:
            interval = int(seconds)
        except Exception:
            interval = 60
        interval = max(1, min(86_400, interval))
        state["default_interval"] = interval
        row = self._selected_layout_row()
        if row < 0:
            row = int(state.get("current", 0))
        if 0 <= row < len(state["layouts"]) and isinstance(state["layouts"][row], dict):
            state["layouts"][row]["interval"] = interval
        self._save_layout_cycles()
        self._refresh_layouts_ui()
        self._maybe_restart_cycle_timer(i)

    def _maybe_restart_cycle_timer(self, monitor_index: int) -> None:
        timer = self._cycle_timers.get(monitor_index)
        if timer is None:
            return
        state = self._layout_cycle_state(monitor_index)
        if state["auto"] and state["layouts"]:
            layouts = state.get("layouts", [])
            current = int(state.get("current", 0))
            try:
                interval = int(state.get("default_interval", 60))
            except Exception:
                interval = 60
            if isinstance(layouts, list) and 0 <= current < len(layouts) and isinstance(layouts[current], dict):
                try:
                    interval = int(layouts[current].get("interval", interval))
                except Exception:
                    interval = int(state.get("default_interval", 60))
            interval = max(1, min(86_400, int(interval)))
            timer.start(int(interval) * 1000)
        else:
            timer.stop()

    def _cycle_prev_layout(self, monitor_index: int) -> None:
        state = self._layout_cycle_state(monitor_index)
        layouts = state["layouts"]
        if not layouts:
            return
        current = int(state.get("current", 0))
        current = (current - 1) % len(layouts)
        state["current"] = current
        self._save_layout_cycles()
        payload = layouts[current].get("payload")
        if isinstance(payload, dict):
            self._apply_monitor_layout(monitor_index, payload)
        if monitor_index == self._current_monitor_index():
            self._refresh_layouts_ui()
        if bool(state.get("auto", False)):
            self._maybe_restart_cycle_timer(monitor_index)

    def _cycle_next_layout(self, monitor_index: int, from_timer: bool = False) -> None:
        state = self._layout_cycle_state(monitor_index)
        layouts = state["layouts"]
        if not layouts:
            return
        current = int(state.get("current", 0))
        current = (current + 1) % len(layouts)
        state["current"] = current
        self._save_layout_cycles()
        payload = layouts[current].get("payload")
        if isinstance(payload, dict):
            self._apply_monitor_layout(monitor_index, payload)
        if monitor_index == self._current_monitor_index():
            self._refresh_layouts_ui()
        if from_timer or bool(state.get("auto", False)):
            self._maybe_restart_cycle_timer(monitor_index)

    def _should_ignore_arrow_shortcuts(self) -> bool:
        w = self.focusWidget()
        return isinstance(w, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox))

    def _on_prev_layout_shortcut(self) -> None:
        if self._should_ignore_arrow_shortcuts():
            return
        self._cycle_prev_layout(monitor_index=self._current_monitor_index())

    def _on_next_layout_shortcut(self) -> None:
        if self._should_ignore_arrow_shortcuts():
            return
        self._cycle_next_layout(monitor_index=self._current_monitor_index())

    def _monitor_label(self, screen: QScreen, index: int) -> str:
        geo = screen.geometry()
        name = screen.name().strip()
        prefix = name if name else f"Monitor {index + 1}"
        return f"{prefix} ({geo.width()}x{geo.height()})"

    def _current_monitor_index(self) -> int:
        return max(0, self._monitor_tabs.currentIndex())

    def _current_editor(self) -> EditorWidget:
        widget = self._monitor_tabs.currentWidget()
        if isinstance(widget, EditorWidget):
            return widget
        return self._monitor_editors[0]

    def _current_scene(self):
        return self._current_editor().scene

    def _current_state(self) -> MonitorState:
        return self._monitor_states[self._current_monitor_index()]

    def _on_monitor_changed(self, _index: int) -> None:
        self._attach_scene(self._current_scene())
        self._rebuild_layers_list()
        item = self._selected_graphics_item()
        self._sync_layer_props_to_ui(item)
        self._sync_animation_to_ui(item)
        self._sync_text_to_ui(item or object())
        self._refresh_layouts_ui()
        self._update_wallpaper_action_states()

    def _attach_scene(self, scene) -> None:
        if self._connected_scene is scene:
            return
        if self._connected_scene is not None:
            try:
                self._connected_scene.selection_changed.disconnect(self._on_scene_selection_changed)
            except Exception:
                pass
        self._connected_scene = scene
        try:
            scene.selection_changed.connect(self._on_scene_selection_changed)
        except Exception:
            pass

    def _set_background_color(self) -> None:
        scene = self._current_scene()
        try:
            current = QColor(str(scene.background_state().color or "#000000"))
        except Exception:
            current = QColor("#000000")
        color = QColorDialog.getColor(current, self, "Background Color")
        if not color.isValid():
            return
        try:
            scene.set_background_color(color)
            self._save_ui_state()
        except Exception as e:
            QMessageBox.critical(self, "Background", f"Could not set the background color:\n{e}")

    def _open_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Background",
            str(project_dir()),
            "Media Files (*.mp4 *.mkv *.avi *.mov *.webm *.gif *.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if not path:
            return
        try:
            self._current_scene().set_background(path)
            try:
                self._save_ui_state()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load background:\n{e}")

    def _save_layout(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Layout",
            str(project_dir() / "layout.json"),
            "Layout Files (*.json);;All Files (*.*)",
        )
        if not path:
            return
        if not Path(path).suffix:
            path = f"{path}.json"
        try:
            payload = self._serialize_layout()
            save_layout_file(path, payload)
            self._remember_recent_layout(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save layout:\n{e}")

    def _export_packaged_layout(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Packaged Layout",
            str(project_dir() / "layout.json"),
            "Layout Files (*.json);;All Files (*.*)",
        )
        if not path:
            return
        layout_path = Path(path)
        if not layout_path.suffix:
            layout_path = layout_path.with_suffix(".json")
        assets_dir = layout_path.parent / f"{layout_path.stem}_assets"
        try:
            assets_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create assets folder:\n{e}")
            return

        payload = self._serialize_layout()
        missing_files: list[str] = []
        copied: dict[str, str] = {}

        def copy_asset(src_str: str) -> str | None:
            if src_str in copied:
                return copied[src_str]
            src = Path(src_str)
            if not src.exists() or not src.is_file():
                missing_files.append(src_str)
                return None
            name = src.name
            candidate = assets_dir / name
            n = 1
            while candidate.exists():
                name = f"{src.stem}_{n}{src.suffix}"
                candidate = assets_dir / name
                n += 1
            try:
                shutil.copy2(src, candidate)
            except Exception:
                missing_files.append(src_str)
                return None
            rel = f"{assets_dir.name}/{candidate.name}"
            copied[src_str] = rel
            return rel

        monitors = payload.get("monitors")
        if isinstance(monitors, list):
            for m in monitors:
                if not isinstance(m, dict):
                    continue
                bg = m.get("background")
                if isinstance(bg, dict):
                    p = bg.get("path")
                    if isinstance(p, str) and p:
                        rel = copy_asset(p)
                        if rel is not None:
                            bg["path"] = rel
                layers = m.get("layers")
                if isinstance(layers, list):
                    for layer in layers:
                        if not isinstance(layer, dict):
                            continue
                        src = layer.get("source")
                        if isinstance(src, str) and src:
                            rel = copy_asset(src)
                            if rel is not None:
                                layer["source"] = rel

        try:
            save_layout_file(str(layout_path), payload)
            self._remember_recent_layout(str(layout_path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export packaged layout:\n{e}")
            return

        if missing_files:
            short = "\n".join(missing_files[:20])
            more = "" if len(missing_files) <= 20 else f"\n… and {len(missing_files) - 20} more"
            QMessageBox.warning(self, "Export", f"Some files were missing and were skipped:\n{short}{more}")

    def _export_frame_image(self) -> None:
        if not self._screens:
            return
        monitor_index = self._current_monitor_index()
        scene = self._monitor_editors[monitor_index].scene
        rect = scene.sceneRect()
        width = max(1, int(round(float(rect.width()))))
        height = max(1, int(round(float(rect.height()))))

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Frame",
            str(project_dir() / f"frame_monitor{monitor_index + 1}.png"),
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)",
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".png")

        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            scene.render(painter, QRectF(0.0, 0.0, float(width), float(height)), rect)
        finally:
            painter.end()

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if not image.save(str(target)):
            QMessageBox.critical(self, "Export", f"Could not write the image to:\n{target}")

    def _load_layout(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Layout",
            str(project_dir()),
            "Layout Files (*.json);;All Files (*.*)",
        )
        if not path:
            return
        self._load_layout_from_path(path, show_errors=True)

    def _load_layout_from_path(self, path: str, show_errors: bool = False) -> bool:
        if not path:
            return False
        try:
            layout_file = load_layout_file(path)
        except Exception as e:
            if show_errors:
                QMessageBox.critical(self, "Error", f"Failed to load layout file:\n{e}")
            return False
        if layout_file.version <= 0 or layout_file.version > LAYOUT_VERSION:
            if show_errors:
                QMessageBox.critical(
                    self,
                    "Layout",
                    f"Unsupported layout version {layout_file.version} (supported: 1..{LAYOUT_VERSION}).",
                )
            return False
        try:
            self._apply_layout(layout_file.payload, base_dir=Path(path).parent)
        except Exception as e:
            if show_errors:
                QMessageBox.critical(self, "Error", f"Failed to apply layout:\n{e}")
            return False
        self._remember_recent_layout(path)
        return True

    def _set_wallpaper(self) -> None:
        if not self._screens:
            return
        ok_any = True
        for i, screen in enumerate(self._screens):
            window = self._wallpaper_windows.get(i)
            if window is None:
                window = WallpaperWindow(self._monitor_editors[i].scene)
                self._wallpaper_windows[i] = window
            ok = window.show_on_desktop(screen)
            ok_any = ok_any and ok
        if not ok_any:
            hint = "" if wallpaper_supported() else "\n\nLive wallpaper attachment is currently Windows-only."
            QMessageBox.warning(self, "Wallpaper", "Could not attach one or more windows to the desktop." + hint)
        self._update_wallpaper_action_states()

    def _unset_wallpaper(self) -> None:
        for window in list(self._wallpaper_windows.values()):
            try:
                window.close()
            except Exception:
                pass
        self._wallpaper_windows = {}
        self._update_wallpaper_action_states()

    def _set_wallpaper_current(self) -> None:
        if not self._screens:
            return
        i = self._current_monitor_index()
        if i < 0 or i >= len(self._screens):
            return
        screen = self._screens[i]
        window = self._wallpaper_windows.get(i)
        if window is None:
            window = WallpaperWindow(self._monitor_editors[i].scene)
            self._wallpaper_windows[i] = window
        ok = window.show_on_desktop(screen)
        if not ok:
            hint = "" if wallpaper_supported() else "\n\nLive wallpaper attachment is currently Windows-only."
            QMessageBox.warning(self, "Wallpaper", "Could not attach this monitor to the desktop." + hint)
        self._update_wallpaper_action_states()

    def _unset_wallpaper_current(self) -> None:
        i = self._current_monitor_index()
        window = self._wallpaper_windows.pop(i, None)
        if window is not None:
            try:
                window.close()
            except Exception:
                pass
        self._update_wallpaper_action_states()

    def _update_wallpaper_action_states(self) -> None:
        self._refresh_scene_activity()
        if not self._screens:
            self._act_set_wallpaper_current.setEnabled(False)
            self._act_unset_wallpaper_current.setEnabled(False)
            self._act_set_wallpaper.setEnabled(False)
            self._act_unset_wallpaper.setEnabled(False)
            return

        current = self._current_monitor_index()
        has_current = current in self._wallpaper_windows
        self._act_set_wallpaper_current.setEnabled(not has_current)
        self._act_unset_wallpaper_current.setEnabled(has_current)

        has_any = bool(self._wallpaper_windows)
        self._act_unset_wallpaper.setEnabled(has_any)
        self._act_set_wallpaper.setEnabled(len(self._wallpaper_windows) < len(self._screens))

    def _add_text(self) -> None:
        monitor_index = self._current_monitor_index()

        def create():
            item = self._current_scene().add_text_layer()
            return item, "Text"

        self._undo_stack.push(_AddLayerCommand(self, monitor_index, create))

    def _add_particles(self) -> None:
        monitor_index = self._current_monitor_index()

        def create():
            item = self._current_scene().add_particle_layer()
            return item, "Particles"

        self._undo_stack.push(_AddLayerCommand(self, monitor_index, create))

    def _add_media(self) -> None:
        monitor_index = self._current_monitor_index()
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose Image/GIF/Video",
            str(project_dir()),
            "Media Files (*.mp4 *.mkv *.avi *.mov *.webm *.gif *.png *.jpg *.jpeg *.bmp *.webp);;All Files (*.*)",
        )
        if not paths:
            return

        for path in paths:
            if not path:
                continue
            ext = Path(path).suffix.lower()
            if ext == ".gif":
                label = "GIF"

                def create(path=path, label=label):
                    item = self._current_scene().add_gif_layer(path)
                    return item, label
            elif ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                label = "Image"

                def create(path=path, label=label):
                    item = self._current_scene().add_image_layer(path)
                    return item, label
            else:
                label = "Video"

                def create(path=path, label=label):
                    item = self._current_scene().add_video_layer(path)
                    return item, label

            self._undo_stack.push(_AddLayerCommand(self, monitor_index, create))

    def _add_layer_item(self, graphics_item: object, label: str) -> None:
        gid = id(graphics_item)
        state = self._current_state()
        state.items[gid] = graphics_item
        state.labels[gid] = label
        if gid in state.order:
            state.order.remove(gid)
        state.order.insert(0, gid)
        self._rebuild_layers_list(select_gid=gid)

    def _layer_display_name(self, graphics_item: object, fallback: str) -> str:
        prefix = ""
        try:
            if bool(graphics_item.data(ITEM_DATA_LOCKED)):
                prefix += "[Locked] "
        except Exception:
            pass
        try:
            if bool(graphics_item.data(ITEM_DATA_HIDDEN)):
                prefix += "[Hidden] "
        except Exception:
            pass

        if isinstance(graphics_item, TextLayerItem):
            label = (fallback or "").strip() or "Text"
            suffix = f" #{graphics_item.text_id()}"
            text = graphics_item.text().strip()
            if not text:
                return f"{prefix}{label}{suffix}"
            short = text if len(text) <= 20 else (text[:17] + "…")
            return f"{prefix}{label}{suffix}: {short}"
        label = (fallback or "").strip() or "Layer"
        return f"{prefix}{label}"

    def _on_layers_reorder_started(self, *args) -> None:
        if self._updating_layers_list or self._undo_blocked:
            self._layers_order_before = None
            return
        self._layers_order_before = list(self._current_state().order)

    def _on_layers_reordered(self, *args) -> None:
        if self._updating_layers_list or self._undo_blocked:
            return
        monitor_index = self._current_monitor_index()
        state = self._current_state()
        before = self._layers_order_before
        self._layers_order_before = None
        order: list[int] = []
        for i in range(self._layers_list.count()):
            it = self._layers_list.item(i)
            gid = it.data(Qt.UserRole)
            if isinstance(gid, int) and gid in state.items:
                order.append(gid)
        if before is None or order == before:
            state.order = order
            self._apply_z_from_state(state)
            return
        state.order = order
        self._apply_z_from_state(state)
        self._undo_stack.push(_ReorderLayersCommand(self, monitor_index, before, order))

    def _apply_z_from_state(self, state: MonitorState) -> None:
        count = len(state.order)
        for i, gid in enumerate(state.order):
            graphics_item = state.items.get(gid)
            if graphics_item is None:
                continue
            try:
                graphics_item.setZValue(float(count - i))
            except Exception:
                continue

    def _rebuild_layers_list(self, select_gid: int | None = None) -> None:
        state = self._current_state()
        self._updating_layers_list = True
        self._layers_list.blockSignals(True)
        try:
            self._layers_list.clear()
            self._list_item_by_gid = {}
            for gid in state.order:
                graphics_item = state.items.get(gid)
                if graphics_item is None:
                    continue
                fallback = state.labels.get(gid, "Layer")
                text = self._layer_display_name(graphics_item, fallback)
                it = QListWidgetItem(text)
                it.setData(Qt.UserRole, gid)
                self._layers_list.addItem(it)
                self._list_item_by_gid[gid] = it
            self._apply_z_from_state(state)
        finally:
            self._layers_list.blockSignals(False)
            self._updating_layers_list = False

        if select_gid is not None:
            it = self._list_item_by_gid.get(select_gid)
            if it is not None:
                self._layers_list.setCurrentItem(it)

    def _move_layer_up(self) -> None:
        row = self._layers_list.currentRow()
        if row <= 0:
            return
        monitor_index = self._current_monitor_index()
        state = self._current_state()
        if row >= len(state.order):
            return
        before = list(state.order)
        after = list(state.order)
        after[row - 1], after[row] = after[row], after[row - 1]
        self._undo_stack.push(_ReorderLayersCommand(self, monitor_index, before, after, select_gid=after[row - 1]))

    def _move_layer_down(self) -> None:
        row = self._layers_list.currentRow()
        monitor_index = self._current_monitor_index()
        state = self._current_state()
        if row < 0 or row >= len(state.order) - 1:
            return
        before = list(state.order)
        after = list(state.order)
        after[row + 1], after[row] = after[row], after[row + 1]
        self._undo_stack.push(_ReorderLayersCommand(self, monitor_index, before, after, select_gid=after[row + 1]))

    def _delete_layer(self) -> None:
        row = self._layers_list.currentRow()
        if row < 0:
            return
        monitor_index = self._current_monitor_index()
        state = self._current_state()
        gid = self._layers_list.item(row).data(Qt.UserRole)
        if not isinstance(gid, int):
            return
        graphics_item = state.items.get(gid)
        if graphics_item is None:
            return
        label = state.labels.get(gid, "Layer")
        try:
            index = int(state.order.index(gid))
        except Exception:
            index = row
        self._undo_stack.push(_RemoveLayerCommand(self, monitor_index, graphics_item, str(label), index))

    def _stop_media_for_item(self, graphics_item: object) -> None:
        try:
            movie = graphics_item.data(0xBEEF)
            if movie is not None:
                movie.stop()
        except Exception:
            pass
        try:
            player = graphics_item.data(0xFEED)
            if player is not None:
                player.stop()
        except Exception:
            pass

    def _resume_media_for_item(self, graphics_item: object) -> None:
        try:
            movie = graphics_item.data(0xBEEF)
            if movie is not None:
                movie.start()
        except Exception:
            pass
        try:
            player = graphics_item.data(0xFEED)
            if player is not None:
                player.play()
        except Exception:
            pass

    def _apply_item_transform_snapshot(self, item: object, snapshot: tuple[float, float, float, float]) -> None:
        self._undo_blocked = True
        try:
            item.setPos(float(snapshot[0]), float(snapshot[1]))
            item.setScale(float(snapshot[2]))
            item.setRotation(float(snapshot[3]))
        except Exception:
            pass
        finally:
            self._undo_blocked = False
        if item is self._selected_graphics_item():
            self._sync_transform_to_ui(item)

    def _apply_text_snapshot(self, item: TextLayerItem, text: str, style: TextStyle) -> None:
        self._undo_blocked = True
        try:
            item.set_text(str(text))
            item.set_style(style)
        except Exception:
            pass
        finally:
            self._undo_blocked = False
        if item is self._selected_graphics_item():
            self._sync_text_to_ui(item)
        list_item = self._list_item_by_gid.get(id(item))
        if list_item:
            fallback = self._current_state().labels.get(id(item), "Text")
            list_item.setText(self._layer_display_name(item, fallback))

    def _set_layer_label(self, gid: int, label: str) -> None:
        state = self._current_state()
        if gid not in state.items:
            return
        state.labels[gid] = str(label)
        list_item = self._list_item_by_gid.get(gid)
        if list_item:
            graphics_item = state.items.get(gid)
            if graphics_item is not None:
                list_item.setText(self._layer_display_name(graphics_item, str(label)))
        selected = self._selected_graphics_item()
        if selected is not None and id(selected) == gid:
            self._sync_layer_props_to_ui(selected)

    def _ensure_layer_item_present(self, item: object, label: str) -> None:
        state = self._current_state()
        gid = id(item)
        if gid not in state.items:
            state.items[gid] = item
            state.labels[gid] = str(label)
            if gid in state.order:
                state.order.remove(gid)
            state.order.insert(0, gid)
        try:
            if getattr(item, "scene", None) is not None and item.scene() is None:
                self._current_scene().addItem(item)
        except Exception:
            try:
                self._current_scene().addItem(item)
            except Exception:
                pass
        self._resume_media_for_item(item)
        self._apply_z_from_state(state)
        self._rebuild_layers_list(select_gid=gid)
        self._select_graphics_item(item)

    def _remove_layer_item(self, item: object) -> None:
        state = self._current_state()
        gid = id(item)
        state.items.pop(gid, None)
        state.labels.pop(gid, None)
        if gid in state.order:
            state.order.remove(gid)
        self._stop_media_for_item(item)
        try:
            scene = self._current_scene()
            if item.scene() is scene:
                scene.removeItem(item)
        except Exception:
            pass
        self._rebuild_layers_list()
        self._sync_layer_props_to_ui(self._selected_graphics_item())

    def _restore_removed_layer_item(self, item: object, label: str, index: int) -> None:
        state = self._current_state()
        gid = id(item)
        state.items[gid] = item
        state.labels[gid] = str(label)
        if gid in state.order:
            state.order.remove(gid)
        index = max(0, min(int(index), len(state.order)))
        state.order.insert(index, gid)
        try:
            if item.scene() is None:
                self._current_scene().addItem(item)
        except Exception:
            pass
        self._resume_media_for_item(item)
        self._apply_z_from_state(state)
        self._rebuild_layers_list(select_gid=gid)
        self._select_graphics_item(item)

    def _set_layer_order(self, order: list[int], select_gid: int | None = None) -> None:
        state = self._current_state()
        state.order = [gid for gid in order if gid in state.items]
        self._apply_z_from_state(state)
        self._rebuild_layers_list(select_gid=select_gid)

    def _apply_layer_locked(self, item: object, locked: bool) -> None:
        self._undo_blocked = True
        try:
            item.setData(ITEM_DATA_LOCKED, bool(locked))
        except Exception:
            pass
        try:
            item.setFlag(QGraphicsItem.ItemIsMovable, not bool(locked))
        except Exception:
            pass
        finally:
            self._undo_blocked = False
        list_item = self._list_item_by_gid.get(id(item))
        if list_item:
            fallback = self._current_state().labels.get(id(item), "Layer")
            list_item.setText(self._layer_display_name(item, fallback))
        if item is self._selected_graphics_item():
            self._sync_layer_props_to_ui(item)

    def _apply_layer_hidden(self, item: object, hidden: bool) -> None:
        self._undo_blocked = True
        try:
            item.setData(ITEM_DATA_HIDDEN, bool(hidden))
        except Exception:
            pass
        try:
            item.setVisible(not bool(hidden))
        except Exception:
            pass
        finally:
            self._undo_blocked = False
        if hidden and item is self._selected_graphics_item():
            try:
                item.setSelected(False)
            except Exception:
                pass
        list_item = self._list_item_by_gid.get(id(item))
        if list_item:
            fallback = self._current_state().labels.get(id(item), "Layer")
            list_item.setText(self._layer_display_name(item, fallback))
        if item is self._selected_graphics_item():
            self._sync_layer_props_to_ui(item)

    def _apply_layer_opacity(self, item: object, opacity: float) -> None:
        self._undo_blocked = True
        try:
            item.setOpacity(max(0.0, min(1.0, float(opacity))))
        except Exception:
            pass
        finally:
            self._undo_blocked = False
        if item is self._selected_graphics_item():
            self._sync_layer_props_to_ui(item)

    def _commit_transform_undo(self) -> None:
        baseline = self._transform_baseline
        self._transform_baseline = None
        if baseline is None:
            return
        monitor_index, gid, before = baseline
        state = self._monitor_states.get(int(monitor_index))
        if state is None:
            return
        item = state.items.get(gid)
        if item is None:
            return
        try:
            after = (
                float(item.pos().x()),
                float(item.pos().y()),
                float(item.scale()),
                float(item.rotation()),
            )
        except Exception:
            return
        if after != before:
            self._undo_stack.push(_SetTransformCommand(self, monitor_index, item, before, after))

    def _commit_opacity_undo(self) -> None:
        baseline = self._opacity_baseline
        self._opacity_baseline = None
        if baseline is None:
            return
        monitor_index, gid, before = baseline
        state = self._monitor_states.get(int(monitor_index))
        if state is None:
            return
        item = state.items.get(gid)
        if item is None:
            return
        try:
            after = float(item.opacity())
        except Exception:
            return
        if after != float(before):
            self._undo_stack.push(_SetLayerOpacityCommand(self, monitor_index, item, float(before), float(after)))

    def _commit_label_undo(self) -> None:
        baseline = self._label_baseline
        self._label_baseline = None
        if baseline is None:
            return
        monitor_index, gid, before = baseline
        state = self._monitor_states.get(int(monitor_index))
        if state is None:
            return
        if gid not in state.items:
            return
        after = str(state.labels.get(gid, before))
        if after != before:
            self._undo_stack.push(_RenameLayerLabelCommand(self, monitor_index, gid, before, after))

    def _commit_text_undo(self) -> None:
        pending = self._pending_text_undo
        self._pending_text_undo = None
        if pending is None:
            return
        monitor_index, gid, before_text, before_style = pending
        state = self._monitor_states.get(int(monitor_index))
        if state is None:
            return
        item = state.items.get(gid)
        if not isinstance(item, TextLayerItem):
            return
        after_text = str(item.text())
        after_style = item.style()
        if after_text != before_text or after_style != before_style:
            self._undo_stack.push(_SetTextCommand(self, monitor_index, item, before_text, before_style, after_text, after_style))

    def _serialize_layout(self) -> dict:
        monitors: list[dict] = []
        for i, screen in enumerate(self._screens):
            geo = screen.geometry()
            scene = self._monitor_editors[i].scene
            state = self._monitor_states[i]
            bg = scene.background_state()
            layers: list[dict] = []
            for gid in state.order:
                item = state.items.get(gid)
                if item is None:
                    continue
                layers.append(self._serialize_layer(item, state.labels.get(gid, "Layer")))
            monitors.append(
                {
                    "index": i,
                    "screen": {
                        "name": screen.name(),
                        "width": int(geo.width()),
                        "height": int(geo.height()),
                    },
                    "background": {
                        "path": str(bg.path) if bg.path is not None else None,
                        "kind": bg.kind,
                        "color": getattr(bg, "color", None),
                    },
                    "orbit_centers": self._serialize_orbit_centers(scene),
                    "layers": layers,
                }
            )
        return {
            "version": LAYOUT_VERSION,
            "desktop_preview": bool(self._act_desktop_preview.isChecked()),
            "follow_paths": self._serialize_follow_paths(),
            "monitors": monitors,
        }

    def _serialize_layer(self, item: object, label: str) -> dict:
        pos = item.pos()
        origin = None
        try:
            o = item.transformOriginPoint()
            origin = [float(o.x()), float(o.y())]
        except Exception:
            origin = None

        size = None
        if isinstance(item, QGraphicsVideoItem):
            try:
                s = item.size()
                size = [float(s.width()), float(s.height())]
            except Exception:
                size = None

        kind = None
        src = None
        try:
            k = item.data(ITEM_DATA_SOURCE_KIND)
            if isinstance(k, str):
                kind = k
        except Exception:
            pass
        try:
            p = item.data(ITEM_DATA_SOURCE_PATH)
            if isinstance(p, str):
                src = p
        except Exception:
            pass
        if src is None:
            try:
                movie = item.data(0xBEEF)
                if movie is not None:
                    name = movie.fileName()
                    if isinstance(name, str) and name:
                        src = name
                        kind = kind or "gif"
            except Exception:
                pass
        if src is None:
            try:
                player = item.data(0xFEED)
                if player is not None:
                    url = player.source()
                    local = url.toLocalFile()
                    if isinstance(local, str) and local:
                        src = local
                        kind = kind or "video"
                    else:
                        s = url.toString()
                        if isinstance(s, str) and s:
                            src = s
                            kind = kind or "video"
            except Exception:
                pass
        if kind is None:
            if isinstance(item, QGraphicsVideoItem):
                kind = "video"
            else:
                kind = label.lower()

        if isinstance(item, TextLayerItem):
            layer_type = "text"
            payload = {"id": int(item.text_id()), "text": item.text(), "style": self._serialize_text_style(item.style())}
        elif isinstance(item, ParticleLayerItem):
            layer_type = "particles"
            payload = {
                "count": item.count,
                "speed": item.speed,
                "size": item.size,
                "color": item.color.name(QColor.NameFormat.HexArgb),
                "gravity_x": item.gravity_x,
                "gravity_y": item.gravity_y,
                "lifetime": item.lifetime,
                "spread": item.spread,
                "emission_mode": str(item.emission_mode),
                "direction": float(item.direction),
            }
        else:
            layer_type = kind or label.lower()
            payload = {"source": src}

        locked = False
        hidden = False
        opacity = 1.0
        blend_mode = BlendMode.NORMAL.value
        try:
            locked = bool(item.data(ITEM_DATA_LOCKED))
        except Exception:
            pass
        try:
            hidden = bool(item.data(ITEM_DATA_HIDDEN))
        except Exception:
            pass
        try:
            opacity = float(item.opacity())
        except Exception:
            opacity = 1.0
        try:
            bm = item.blend_mode()
            if isinstance(bm, BlendMode):
                blend_mode = bm.value
            else:
                blend_mode = str(bm)
        except Exception:
            blend_mode = BlendMode.NORMAL.value

        anim_mode = None
        anim_payload = None
        try:
            anim_mode = item.data(ITEM_DATA_ANIM_MODE)
        except Exception:
            anim_mode = None
        try:
            anim_payload = item.data(ITEM_DATA_ANIM_PAYLOAD)
        except Exception:
            anim_payload = None

        anim_blob = None
        if isinstance(anim_mode, str) and anim_mode and anim_mode != "none":
            if isinstance(anim_payload, dict):
                anim_blob = {"mode": str(anim_mode), "payload": self._jsonify_layout_value(anim_payload)}
            else:
                anim_blob = {"mode": str(anim_mode), "payload": {}}

        out = {
            "type": layer_type,
            "label": label,
            "locked": locked,
            "hidden": hidden,
            "opacity": max(0.0, min(1.0, float(opacity))),
            "blend_mode": str(blend_mode),
            "transform": {
                "x": float(pos.x()),
                "y": float(pos.y()),
                "scale": float(item.scale()),
                "rotation": float(item.rotation()),
                "origin": origin,
                "size": size,
            },
            **payload,
        }
        if isinstance(item, QGraphicsVideoItem):
            try:
                mode = item.aspectRatioMode()
                out["aspect"] = "fit" if mode == Qt.KeepAspectRatio else "stretch"
            except Exception:
                pass
        if not isinstance(item, TextLayerItem):
            effect_blob = self._serialize_graphics_effect(item)
            if isinstance(effect_blob, dict):
                out["effect"] = effect_blob
        if isinstance(anim_blob, dict):
            out["anim"] = anim_blob
        return out

    def _serialize_graphics_effect(self, item: object) -> dict | None:
        try:
            effect = item.graphicsEffect()
        except Exception:
            return None
        if effect is None:
            return None
        try:
            if isinstance(effect, QGraphicsBlurEffect):
                radius = float(effect.blurRadius())
                if radius <= 0.0:
                    return None
                return {"type": "blur", "radius": radius}
            if isinstance(effect, QGraphicsColorizeEffect):
                return {
                    "type": "colorize",
                    "strength": float(effect.strength()),
                    "color": effect.color().name(QColor.NameFormat.HexArgb),
                }
            if isinstance(effect, QGraphicsDropShadowEffect):
                offset = effect.offset()
                dx = float(offset.x())
                dy = float(offset.y())
                kind = "glow" if abs(dx) < 0.1 and abs(dy) < 0.1 else "shadow"
                return {
                    "type": kind,
                    "radius": float(effect.blurRadius()),
                    "offset": [dx, dy],
                    "color": effect.color().name(QColor.NameFormat.HexArgb),
                }
        except Exception:
            return None
        return None

    def _apply_effect_from_payload(self, item: object, data: dict) -> None:
        if not hasattr(item, "set_effect"):
            return
        kind = data.get("type")
        if not isinstance(kind, str):
            return
        try:
            radius = float(data.get("radius", 0.0))
        except Exception:
            radius = 0.0
        params: dict = {"radius": radius}
        color = data.get("color")
        if isinstance(color, str):
            parsed = QColor(color)
            if parsed.isValid():
                params["color"] = parsed
        offset = data.get("offset")
        if isinstance(offset, list) and len(offset) >= 2:
            try:
                params["offset"] = (float(offset[0]), float(offset[1]))
            except Exception:
                params["offset"] = (0.0, 0.0)
        if kind == "colorize":
            try:
                strength = float(data.get("strength", 0.6))
            except Exception:
                strength = 0.6
            item.set_effect(
                "colorize",
                {
                    "color": params.get("color", QColor("#ffffff")),
                    "strength": max(0.0, min(1.0, strength)),
                },
            )
            return
        if kind == "blur":
            item.set_effect("blur", params)
        elif kind in ("shadow", "glow"):
            if kind == "glow" or "offset" not in params:
                params["offset"] = (0.0, 0.0)
            item.set_effect(str(kind), params)
        else:
            item.set_effect("none", {})

    def _serialize_text_style(self, style: TextStyle) -> dict:
        return {
            "font": style.font.toString(),
            "fill_mode": str(style.fill_mode.value),
            "color": style.color.name(QColor.NameFormat.HexArgb),
            "gradient_start": style.gradient_start.name(QColor.NameFormat.HexArgb),
            "gradient_end": style.gradient_end.name(QColor.NameFormat.HexArgb),
            "effect": str(style.effect.value),
            "effect_speed": float(style.effect_speed),
            "effect_amount": float(style.effect_amount),
            "shadow_enabled": bool(style.shadow_enabled),
            "shadow_color": style.shadow_color.name(QColor.NameFormat.HexArgb),
            "shadow_offset": [float(style.shadow_offset.x()), float(style.shadow_offset.y())],
            "shadow_blur": float(style.shadow_blur),
            "glow_enabled": bool(style.glow_enabled),
            "glow_color": style.glow_color.name(QColor.NameFormat.HexArgb),
            "glow_blur": float(style.glow_blur),
            "blur_enabled": bool(style.blur_enabled),
            "blur_radius": float(style.blur_radius),
        }

    def _resolve_layout_path(self, raw: str, base_dir: Path | None) -> str:
        s = str(raw)
        if "://" in s:
            return s
        try:
            p = Path(s)
        except Exception:
            return s
        if base_dir is not None and not p.is_absolute():
            try:
                return str((base_dir / p).resolve())
            except Exception:
                return str(base_dir / p)
        return s

    def _apply_layout(self, payload: dict, base_dir: Path | None = None) -> None:
        desktop_preview = bool(payload.get("desktop_preview", False))
        self._apply_follow_paths_from_payload(payload.get("follow_paths"))
        monitors_payload = payload.get("monitors", [])
        if not isinstance(monitors_payload, list):
            monitors_payload = []

        mapping = self._map_saved_monitors_to_current(monitors_payload)
        missing_files: list[str] = []

        for saved, idx in mapping:
            if idx is None:
                continue
            self._clear_monitor_layout(idx)
            scene = self._monitor_editors[idx].scene
            state = self._monitor_states[idx]
            if isinstance(saved, dict):
                self._apply_orbit_centers_to_scene(scene, saved.get("orbit_centers"))
            else:
                self._apply_orbit_centers_to_scene(scene, None)

            bg = saved.get("background") if isinstance(saved, dict) else None
            bg_path = None
            if isinstance(bg, dict):
                p = bg.get("path")
                if isinstance(p, str) and p:
                    bg_path = self._resolve_layout_path(p, base_dir=base_dir)
            bg_color = bg.get("color") if isinstance(bg, dict) else None
            bg_kind = str(bg.get("kind") or "") if isinstance(bg, dict) else ""
            if bg_path is None and bg_kind == "color" and isinstance(bg_color, str) and bg_color.strip():
                try:
                    scene.set_background_color(QColor(bg_color))
                except Exception:
                    pass
            elif bg_path is not None and Path(bg_path).exists():
                scene.set_background(str(bg_path))
            elif bg_path is not None:
                missing_files.append(str(bg_path))

            layers_payload = saved.get("layers") if isinstance(saved, dict) else None
            if not isinstance(layers_payload, list):
                layers_payload = []

            gids: list[int] = []
            for layer in layers_payload:
                if not isinstance(layer, dict):
                    continue
                created = self._create_layer_from_payload(scene, layer, missing_files, base_dir=base_dir)
                if created is None:
                    continue
                item, label = created
                self._apply_transform_from_payload(item, layer.get("transform"))
                gid = id(item)
                state.items[gid] = item
                state.labels[gid] = label
                gids.append(gid)

            state.order = gids
            self._apply_z_from_state(state)
            try:
                scene.refresh_animation()
            except Exception:
                pass

        self._act_desktop_preview.blockSignals(True)
        try:
            self._act_desktop_preview.setChecked(desktop_preview)
        finally:
            self._act_desktop_preview.blockSignals(False)
        self._toggle_desktop_preview(desktop_preview)
        self._on_monitor_changed(self._monitor_tabs.currentIndex())

        if missing_files:
            short = "\n".join(missing_files[:20])
            more = "" if len(missing_files) <= 20 else f"\n… and {len(missing_files) - 20} more"
            QMessageBox.warning(self, "Layout", f"Some files were missing and were skipped:\n{short}{more}")

    def _map_saved_monitors_to_current(self, monitors_payload: list[dict]) -> list[tuple[dict, int | None]]:
        current: list[tuple[int, str, int, int]] = []
        for i, screen in enumerate(self._screens):
            geo = screen.geometry()
            current.append((i, screen.name(), int(geo.width()), int(geo.height())))

        used: set[int] = set()
        mapped: list[tuple[dict, int | None]] = []

        for saved in monitors_payload:
            if not isinstance(saved, dict):
                continue
            scr = saved.get("screen")
            saved_name = ""
            saved_w = None
            saved_h = None
            if isinstance(scr, dict):
                saved_name = str(scr.get("name") or "")
                try:
                    saved_w = int(scr.get("width"))
                    saved_h = int(scr.get("height"))
                except Exception:
                    saved_w = None
                    saved_h = None

            best = None
            for i, name, w, h in current:
                if i in used:
                    continue
                if saved_w is not None and saved_h is not None and saved_name and name == saved_name and w == saved_w and h == saved_h:
                    best = i
                    break

            if best is None and saved_w is not None and saved_h is not None:
                for i, _name, w, h in current:
                    if i in used:
                        continue
                    if w == saved_w and h == saved_h:
                        best = i
                        break

            if best is None:
                try:
                    idx = int(saved.get("index"))
                except Exception:
                    idx = None
                if idx is not None and 0 <= idx < len(self._screens) and idx not in used:
                    best = idx

            if best is not None:
                used.add(best)
            mapped.append((saved, best))

        return mapped

    def _clear_monitor_layout(self, idx: int) -> None:
        scene = self._monitor_editors[idx].scene
        state = self._monitor_states[idx]
        for item in list(state.items.values()):
            self._stop_media_for_item(item)
            try:
                if item.scene() is scene:
                    scene.removeItem(item)
            except Exception:
                pass
        state.items = {}
        state.labels = {}
        state.order = []
        try:
            scene.clearSelection()
        except Exception:
            pass
        scene.clear_background()
        scene.reset_text_id_counter()

    def _create_layer_from_payload(self, scene, layer: dict, missing_files: list[str], base_dir: Path | None = None) -> tuple[object, str] | None:
        t = layer.get("type")
        label = layer.get("label")
        if not isinstance(label, str) or not label:
            label = "Layer"

        if t == "text":
            text_id = layer.get("id")
            parsed_id = None
            if isinstance(text_id, int):
                parsed_id = text_id
            elif isinstance(text_id, str):
                s = text_id.strip()
                if s.isdigit():
                    parsed_id = int(s)
            if isinstance(parsed_id, int) and parsed_id > 0:
                item = scene.add_text_layer(parsed_id)
            else:
                item = scene.add_text_layer()
            text = layer.get("text")
            if isinstance(text, str):
                item.set_text(text)
            style_data = layer.get("style")
            if isinstance(style_data, dict):
                item.set_style(self._deserialize_text_style(style_data))
                scene.refresh_text_animation()
            self._apply_layer_state_from_payload(item, layer)
            return item, label

        if t == "particles":
            item = scene.add_particle_layer()
            try:
                item.count = int(layer.get("count", 100))
            except Exception:
                pass
            try:
                item.speed = float(layer.get("speed", 50.0))
            except Exception:
                pass
            try:
                item.size = float(layer.get("size", 3.0))
            except Exception:
                pass
            c = layer.get("color")
            if isinstance(c, str):
                item.color = QColor(c)
            try:
                item.gravity_x = float(layer.get("gravity_x", 0.0))
            except Exception:
                pass
            try:
                item.gravity_y = float(layer.get("gravity_y", 0.0))
            except Exception:
                pass
            try:
                item.lifetime = float(layer.get("lifetime", 2.0))
            except Exception:
                pass
            try:
                item.spread = float(layer.get("spread", 360.0))
            except Exception:
                pass
            emission = layer.get("emission_mode")
            if isinstance(emission, str) and emission in ("point", "rect"):
                item.emission_mode = emission
            try:
                item.direction = float(layer.get("direction", 0.0))
            except Exception:
                pass
            self._apply_layer_state_from_payload(item, layer)
            return item, label

        source = layer.get("source")
        if not isinstance(source, str) or not source:
            return None
        source_resolved = self._resolve_layout_path(source, base_dir=base_dir)
        if "://" in source_resolved or not Path(source_resolved).exists():
            missing_files.append(str(source))
            return None

        if t == "gif":
            item = scene.add_gif_layer(source_resolved)
            self._apply_layer_state_from_payload(item, layer)
            return item, label
        if t == "video":
            item = scene.add_video_layer(source_resolved)
            self._apply_layer_state_from_payload(item, layer)
            return item, label
        item = scene.add_image_layer(source_resolved)
        self._apply_layer_state_from_payload(item, layer)
        return item, label

    def _apply_layer_state_from_payload(self, item: object, layer: dict) -> None:
        locked = bool(layer.get("locked", False))
        hidden = bool(layer.get("hidden", False))
        opacity_raw = layer.get("opacity", 1.0)
        try:
            opacity_val = float(opacity_raw)
        except Exception:
            opacity_val = 1.0
        if opacity_val > 1.0 and opacity_val <= 100.0:
            opacity_val = opacity_val / 100.0
        opacity_val = max(0.0, min(1.0, float(opacity_val)))
        try:
            item.setOpacity(opacity_val)
        except Exception:
            pass
        try:
            item.setData(ITEM_DATA_LOCKED, bool(locked))
        except Exception:
            pass
        try:
            item.setFlag(QGraphicsItem.ItemIsMovable, not bool(locked))
        except Exception:
            pass
        try:
            item.setData(ITEM_DATA_HIDDEN, bool(hidden))
        except Exception:
            pass
        try:
            item.setVisible(not bool(hidden))
        except Exception:
            pass
        blend_raw = layer.get("blend_mode", layer.get("blend"))
        if blend_raw is not None:
            self._apply_layer_blend_mode(item, blend_raw)
        aspect_raw = layer.get("aspect")
        if isinstance(item, QGraphicsVideoItem) and isinstance(aspect_raw, str) and aspect_raw:
            try:
                if aspect_raw == "stretch":
                    item.setAspectRatioMode(Qt.IgnoreAspectRatio)
                else:
                    item.setAspectRatioMode(Qt.KeepAspectRatio)
            except Exception:
                pass

        effect_raw = layer.get("effect")
        if isinstance(effect_raw, dict) and not isinstance(item, TextLayerItem):
            try:
                self._apply_effect_from_payload(item, effect_raw)
            except Exception:
                pass

        anim = layer.get("anim")
        if isinstance(anim, dict):
            mode = anim.get("mode")
            payload = anim.get("payload", {})
            if isinstance(mode, str) and mode and mode != "none" and isinstance(payload, dict):
                try:
                    item.setData(ITEM_DATA_ANIM_MODE, str(mode))
                    item.setData(ITEM_DATA_ANIM_PAYLOAD, dict(payload))
                except Exception:
                    pass

    def _apply_layer_blend_mode(self, item: object, blend: object) -> None:
        self._undo_blocked = True
        try:
            if hasattr(item, "set_blend_mode"):
                item.set_blend_mode(blend)
        except Exception:
            pass
        finally:
            self._undo_blocked = False
        if item is self._selected_graphics_item():
            self._sync_layer_props_to_ui(item)

    def _apply_transform_from_payload(self, item: object, transform: object) -> None:
        if not isinstance(transform, dict):
            return
        try:
            x = float(transform.get("x", 0.0))
            y = float(transform.get("y", 0.0))
            item.setPos(QPointF(x, y))
        except Exception:
            pass
        try:
            item.setScale(float(transform.get("scale", 1.0)))
        except Exception:
            pass
        try:
            item.setRotation(float(transform.get("rotation", 0.0)))
        except Exception:
            pass
        origin = transform.get("origin")
        if isinstance(origin, list) and len(origin) == 2:
            try:
                item.setTransformOriginPoint(float(origin[0]), float(origin[1]))
            except Exception:
                pass
        size = transform.get("size")
        if isinstance(item, QGraphicsVideoItem) and isinstance(size, list) and len(size) == 2:
            try:
                item.setSize(QSizeF(float(size[0]), float(size[1])))
                item.setTransformOriginPoint(item.boundingRect().center())
            except Exception:
                pass

    def _deserialize_text_style(self, data: dict) -> TextStyle:
        font = QFont()
        font_str = data.get("font")
        if isinstance(font_str, str) and font_str:
            try:
                font.fromString(font_str)
            except Exception:
                pass

        fill_mode_value = data.get("fill_mode")
        try:
            fill_mode = FillMode(str(fill_mode_value))
        except Exception:
            fill_mode = FillMode.SOLID

        shadow_offset = data.get("shadow_offset")
        if not isinstance(shadow_offset, list) or len(shadow_offset) != 2:
            shadow_offset = [3.0, 3.0]
        glow_blur = data.get("glow_blur", 18.0)
        shadow_blur = data.get("shadow_blur", 12.0)
        effect_value = data.get("effect", TextEffect.NONE.value)
        try:
            effect = TextEffect(str(effect_value))
        except Exception:
            effect = TextEffect.NONE
        try:
            effect_speed = float(data.get("effect_speed", 1.0))
        except Exception:
            effect_speed = 1.0
        try:
            effect_amount = float(data.get("effect_amount", 20.0))
        except Exception:
            effect_amount = 20.0

        return TextStyle(
            font=font,
            fill_mode=fill_mode,
            color=QColor(str(data.get("color", "#ffffffff"))),
            gradient_start=QColor(str(data.get("gradient_start", "#ffffffff"))),
            gradient_end=QColor(str(data.get("gradient_end", "#ff00e5ff"))),
            effect=effect,
            effect_speed=float(effect_speed),
            effect_amount=float(effect_amount),
            shadow_enabled=bool(data.get("shadow_enabled", True)),
            shadow_color=QColor(str(data.get("shadow_color", "#c8000000"))),
            shadow_offset=QPointF(
                float(shadow_offset[0]),
                float(shadow_offset[1]),
            ),
            shadow_blur=float(shadow_blur),
            glow_enabled=bool(data.get("glow_enabled", False)),
            glow_color=QColor(str(data.get("glow_color", "#ff00e5ff"))),
            glow_blur=float(glow_blur),
            blur_enabled=bool(data.get("blur_enabled", False)),
            blur_radius=float(data.get("blur_radius", 0.0)),
        )

    def _rename_layer(self, list_item: QListWidgetItem) -> None:
        gid = list_item.data(Qt.UserRole)
        if not isinstance(gid, int):
            return
        graphics_item = self._current_state().items.get(gid)
        if not isinstance(graphics_item, TextLayerItem):
            return
        text, ok = QInputDialog.getText(self, "Edit Text", "Text:", text=graphics_item.text())
        if not ok:
            return
        before_text = str(graphics_item.text())
        before_style = graphics_item.style()
        after_text = str(text)
        if after_text != before_text:
            self._undo_stack.push(
                _SetTextCommand(
                    self,
                    self._current_monitor_index(),
                    graphics_item,
                    before_text,
                    before_style,
                    after_text,
                    before_style,
                )
            )

    def _selected_graphics_item(self) -> object | None:
        scene = self._current_scene()
        try:
            selected = list(scene.selectedItems())
        except Exception:
            selected = []
        if not selected:
            return None
        try:
            focus = scene.focusItem()
            if focus is not None and focus in selected:
                return focus
        except Exception:
            pass
        return selected[0]

    def _select_graphics_item(self, item: object) -> None:
        try:
            scene_item = item
            scene_item.setSelected(True)
            scene_item.setFocus()
        except Exception:
            return

        list_item = self._list_item_by_gid.get(id(item))
        if list_item:
            self._layers_list.blockSignals(True)
            self._layers_list.setCurrentItem(list_item)
            self._layers_list.blockSignals(False)

    def _on_scene_selection_changed(self) -> None:
        scene = self._current_scene()
        monitor_index = self._current_monitor_index()
        try:
            selected = list(scene.selectedItems())
        except Exception:
            selected = []

        selected_gids = {id(it) for it in selected}
        prev_gids = self._selection_prev_gids.get(monitor_index, set())
        primary_gid = self._selection_primary_gid.get(monitor_index)

        if not selected_gids:
            self._selection_primary_gid.pop(monitor_index, None)
            self._selection_prev_gids[monitor_index] = set()
            return

        if primary_gid not in selected_gids:
            new_gids = selected_gids - prev_gids
            picked: int | None = None
            try:
                focus = scene.focusItem()
                if focus is not None:
                    fid = id(focus)
                    if fid in selected_gids:
                        if not new_gids or fid in new_gids:
                            picked = fid
            except Exception:
                picked = None

            if picked is None and new_gids:
                for it in selected:
                    gid = id(it)
                    if gid in new_gids:
                        picked = gid
                        break

            if picked is None:
                picked = id(selected[0])

            self._selection_primary_gid[monitor_index] = int(picked)

        self._selection_prev_gids[monitor_index] = set(selected_gids)

        item = self._selected_graphics_item()
        if item is None:
            return

        list_item = self._list_item_by_gid.get(id(item))
        if list_item:
            self._layers_list.blockSignals(True)
            self._layers_list.setCurrentItem(list_item)
            self._layers_list.blockSignals(False)

        self._sync_transform_to_ui(item)
        self._sync_layer_props_to_ui(item)
        self._sync_animation_to_ui(item)
        self._sync_text_to_ui(item)

    def _on_layers_current_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        gid = current.data(Qt.UserRole)
        if not isinstance(gid, int):
            return
        graphics_item = self._current_state().items.get(gid)
        if graphics_item is None:
            return
        try:
            for it in self._current_scene().selectedItems():
                it.setSelected(False)
            graphics_item.setSelected(True)
            graphics_item.setFocus()
        except Exception:
            return
        self._sync_transform_to_ui(graphics_item)
        self._sync_layer_props_to_ui(graphics_item)
        self._sync_animation_to_ui(graphics_item)
        self._sync_text_to_ui(graphics_item)

    def _run_on_monitor(self, monitor_index: int, fn: Callable[[], None]) -> None:
        try:
            idx = int(monitor_index)
        except Exception:
            idx = self._current_monitor_index()
        idx = max(0, min(idx, max(0, len(self._monitor_editors) - 1)))
        if idx != self._current_monitor_index():
            self._monitor_tabs.setCurrentIndex(idx)
        fn()

    def _sync_layer_props_to_ui(self, item: object | None) -> None:
        enabled = item is not None
        for w in (self._txt_layer_name, self._spin_opacity, self._combo_blend_mode, self._chk_layer_locked, self._chk_layer_hidden):
            w.setEnabled(enabled)
        try:
            self._txt_layer_name.blockSignals(True)
            self._spin_opacity.blockSignals(True)
            self._combo_blend_mode.blockSignals(True)
            self._chk_layer_locked.blockSignals(True)
            self._chk_layer_hidden.blockSignals(True)
            if item is None:
                self._txt_layer_name.setText("")
                self._spin_opacity.setValue(100)
                self._combo_blend_mode.setCurrentIndex(0)
                self._chk_layer_locked.setChecked(False)
                self._chk_layer_hidden.setChecked(False)
                return
            gid = id(item)
            label = str(self._current_state().labels.get(gid, "Layer"))
            locked = False
            hidden = False
            opacity = 1.0
            blend_mode = BlendMode.NORMAL.value
            try:
                locked = bool(item.data(ITEM_DATA_LOCKED))
            except Exception:
                pass
            try:
                hidden = bool(item.data(ITEM_DATA_HIDDEN))
            except Exception:
                pass
            try:
                opacity = float(item.opacity())
            except Exception:
                opacity = 1.0
            try:
                bm = item.blend_mode()
                if isinstance(bm, BlendMode):
                    blend_mode = bm.value
                else:
                    blend_mode = str(bm)
            except Exception:
                blend_mode = BlendMode.NORMAL.value
            self._txt_layer_name.setText(label)
            self._spin_opacity.setValue(int(round(max(0.0, min(1.0, opacity)) * 100.0)))
            idx = self._combo_blend_mode.findData(str(blend_mode))
            self._combo_blend_mode.setCurrentIndex(idx if idx >= 0 else 0)
            self._chk_layer_locked.setChecked(bool(locked))
            self._chk_layer_hidden.setChecked(bool(hidden))
        finally:
            self._txt_layer_name.blockSignals(False)
            self._spin_opacity.blockSignals(False)
            self._combo_blend_mode.blockSignals(False)
            self._chk_layer_locked.blockSignals(False)
            self._chk_layer_hidden.blockSignals(False)
        self._sync_media_to_ui(item)
        self._sync_visual_effects_to_ui(item)
        self._sync_particles_to_ui(item)

    def _sync_media_to_ui(self, item: object | None) -> None:
        is_video = isinstance(item, QGraphicsVideoItem)
        widgets = (
            self._btn_media_play,
            self._btn_media_pause,
            self._btn_media_stop,
            self._chk_media_mute,
            self._slider_media_volume,
            self._combo_media_aspect,
            self._spin_media_speed,
        )
        for w in widgets:
            try:
                w.blockSignals(True)
            except Exception:
                pass
        
        try:
            for w in widgets:
                try:
                    w.setEnabled(is_video)
                except Exception:
                    pass
            if not is_video:
                try:
                    self._chk_media_mute.setChecked(False)
                    self._slider_media_volume.setValue(100)
                    self._combo_media_aspect.setCurrentIndex(self._combo_media_aspect.findData("fit"))
                    self._spin_media_speed.setValue(1.0)
                except Exception:
                    pass
                return
            try:
                player = item.data(0xFEED)
                audio = item.data(0xFEED + 1)
            except Exception:
                player = None
                audio = None
            try:
                if isinstance(audio, object) and hasattr(audio, "isMuted"):
                    self._chk_media_mute.setChecked(bool(audio.isMuted()))
            except Exception:
                pass
            try:
                if isinstance(audio, object) and hasattr(audio, "volume"):
                    vol = float(audio.volume())
                    self._slider_media_volume.setValue(int(round(max(0.0, min(1.0, vol)) * 100.0)))
            except Exception:
                pass
            try:
                if isinstance(player, object) and hasattr(player, "playbackRate"):
                    rate = float(player.playbackRate())
                    self._spin_media_speed.setValue(rate)
            except Exception:
                pass
            try:
                mode = item.aspectRatioMode()
                val = "fit" if mode == Qt.KeepAspectRatio else "stretch"
                idx = self._combo_media_aspect.findData(val)
                self._combo_media_aspect.setCurrentIndex(idx if idx >= 0 else 0)
            except Exception:
                pass
        finally:
            for w in widgets:
                try:
                    w.blockSignals(False)
                except Exception:
                    pass

    def _selected_video_item(self) -> QGraphicsVideoItem | None:
        item = self._selected_graphics_item()
        return item if isinstance(item, QGraphicsVideoItem) else None

    def _on_media_play(self) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        try:
            player = item.data(0xFEED)
            if player is not None:
                player.play()
        except Exception:
            pass

    def _on_media_pause(self) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        try:
            player = item.data(0xFEED)
            if player is not None and hasattr(player, "pause"):
                player.pause()
        except Exception:
            pass

    def _on_media_stop(self) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        self._stop_media_for_item(item)

    def _on_media_mute_toggled(self, enabled: bool) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        try:
            audio = item.data(0xFEED + 1)
            if audio is not None and hasattr(audio, "setMuted"):
                audio.setMuted(bool(enabled))
        except Exception:
            pass

    def _on_media_volume_changed(self, value: int) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        try:
            audio = item.data(0xFEED + 1)
            if audio is not None and hasattr(audio, "setVolume"):
                audio.setVolume(max(0.0, min(1.0, float(value) / 100.0)))
        except Exception:
            pass

    def _on_media_aspect_changed(self) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        try:
            val = self._combo_media_aspect.currentData()
        except Exception:
            val = "fit"
        try:
            if val == "stretch":
                item.setAspectRatioMode(Qt.IgnoreAspectRatio)
            elif val == "original":
                try:
                    ns = item.nativeSize()
                except Exception:
                    ns = QSizeF(640.0, 360.0)
                if isinstance(ns, QSizeF) and ns.width() > 0 and ns.height() > 0:
                    item.setAspectRatioMode(Qt.KeepAspectRatio)
                    item.setSize(QSizeF(float(ns.width()), float(ns.height())))
                else:
                    item.setAspectRatioMode(Qt.KeepAspectRatio)
            else:
                item.setAspectRatioMode(Qt.KeepAspectRatio)
            try:
                item.setTransformOriginPoint(item.boundingRect().center())
            except Exception:
                pass
        except Exception:
            pass

    def _on_media_speed_changed(self, value: float) -> None:
        item = self._selected_video_item()
        if item is None:
            return
        try:
            player = item.data(0xFEED)
            if player is not None and hasattr(player, "setPlaybackRate"):
                player.setPlaybackRate(max(0.1, float(value)))
        except Exception:
            pass

    def _sync_visual_effects_to_ui(self, item: object | None) -> None:
        is_visual = isinstance(item, (ImageLayerItem, VideoLayerItem, ParticleLayerItem))
        widgets = (
            self._combo_effect_type,
            self._spin_effect_radius,
            self._spin_effect_strength,
            self._spin_effect_dx,
            self._spin_effect_dy,
            self._btn_effect_color,
        )
        for w in widgets:
            w.setEnabled(is_visual)
            w.blockSignals(True)
        
        if not is_visual:
            for w in widgets:
                w.blockSignals(False)
            return

        try:
            eff = item.graphicsEffect()
            eff_type = "None"
            radius = 0.0
            dx = 0.0
            dy = 0.0
            color = Qt.black

            if isinstance(eff, QGraphicsBlurEffect):
                eff_type = "Blur"
                radius = eff.blurRadius()
            elif isinstance(eff, QGraphicsDropShadowEffect):
                offset = eff.offset()
                if abs(offset.x()) < 0.1 and abs(offset.y()) < 0.1:
                    eff_type = "Glow"
                else:
                    eff_type = "Shadow"
                radius = eff.blurRadius()
                dx = offset.x()
                dy = offset.y()
                color = eff.color()
            elif isinstance(eff, QGraphicsColorizeEffect):
                eff_type = "Colorize"
                color = eff.color()
                try:
                    self._spin_effect_strength.setValue(float(eff.strength()) * 100.0)
                except Exception:
                    pass

            idx = self._combo_effect_type.findText(eff_type)
            if idx >= 0:
                self._combo_effect_type.setCurrentIndex(idx)
            self._spin_effect_radius.setValue(radius)
            self._spin_effect_dx.setValue(dx)
            self._spin_effect_dy.setValue(dy)
            self._current_effect_color = QColor(color)
        except Exception:
            pass
        finally:
            for w in widgets:
                w.blockSignals(False)

    def _sync_particles_to_ui(self, item: object | None) -> None:
        is_particles = isinstance(item, ParticleLayerItem)
        if hasattr(self, "_particles_container"):
            self._particles_container.setVisible(is_particles)
        
        if not is_particles:
            return

        widgets = (
            self._combo_particle_preset,
            self._combo_particle_emission,
            self._spin_particle_direction,
            self._spin_particle_count,
            self._spin_particle_speed,
            self._spin_particle_size,
            self._spin_particle_gravity_x,
            self._spin_particle_gravity_y,
            self._spin_particle_lifetime,
            self._spin_particle_spread,
        )
        for w in widgets:
            w.blockSignals(True)
            
        try:
            self._combo_particle_preset.setCurrentIndex(0) # Custom
            emission_idx = self._combo_particle_emission.findText("Rectangle" if item.emission_mode == "rect" else "Point")
            if emission_idx >= 0:
                 self._combo_particle_emission.setCurrentIndex(emission_idx)
            self._spin_particle_direction.setValue(float(item.direction))
            
            self._spin_particle_count.setValue(int(item.count))
            self._spin_particle_speed.setValue(float(item.speed))
            self._spin_particle_size.setValue(float(item.size))
            self._spin_particle_gravity_x.setValue(float(item.gravity_x))
            self._spin_particle_gravity_y.setValue(float(item.gravity_y))
            self._spin_particle_lifetime.setValue(float(item.lifetime))
            self._spin_particle_spread.setValue(float(item.spread))
            self._current_particle_color = item.color
        except Exception:
            pass
        finally:
            for w in widgets:
                w.blockSignals(False)

    def _apply_visual_effects_from_ui(self) -> None:
        item = self._selected_graphics_item()
        if not isinstance(item, (ImageLayerItem, VideoLayerItem, ParticleLayerItem)):
            return
            
        eff_type = self._combo_effect_type.currentText()
        params = {}
        
        if eff_type == "Blur":
            params["radius"] = self._spin_effect_radius.value()
            item.set_effect("blur", params)
        elif eff_type == "Shadow":
            params["radius"] = self._spin_effect_radius.value()
            params["offset"] = (self._spin_effect_dx.value(), self._spin_effect_dy.value())
            params["color"] = getattr(self, "_current_effect_color", Qt.black)
            item.set_effect("shadow", params)
        elif eff_type == "Glow":
            params["radius"] = self._spin_effect_radius.value()
            params["offset"] = (0.0, 0.0)
            params["color"] = getattr(self, "_current_effect_color", Qt.black)
            item.set_effect("glow", params)
        elif eff_type == "Colorize":
            params["color"] = getattr(self, "_current_effect_color", QColor("#ffffff"))
            params["strength"] = max(0.0, min(1.0, float(self._spin_effect_strength.value()) / 100.0))
            item.set_effect("colorize", params)
        else:
            item.set_effect("none", {})

    def _pick_effect_color(self) -> None:
        current = getattr(self, "_current_effect_color", QColor(Qt.black))
        color = QColorDialog.getColor(current, self, "Pick Effect Color", QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self._current_effect_color = color
            self._apply_visual_effects_from_ui()

    def _sync_animation_to_ui(self, item: object | None) -> None:
        widgets = (
            self._combo_anim_mode,
            self._combo_anim_slide_dir,
            self._combo_anim_follow_path,
            self._combo_anim_orbit_center,
            self._combo_anim_orbit_dir,
            self._spin_anim_speed,
            self._spin_anim_padding,
            self._spin_anim_angle,
            self._spin_anim_amp_x,
            self._spin_anim_amp_y,
            self._spin_anim_rate,
            self._spin_anim_rate2,
            self._spin_anim_phase,
            self._spin_anim_rot_speed,
            self._spin_anim_rot_amp,
            self._spin_anim_scale_min,
            self._spin_anim_scale_max,
            self._spin_anim_opacity_min,
            self._spin_anim_opacity_max,
            self._spin_anim_jitter,
        )
        for w in widgets:
            try:
                w.blockSignals(True)
            except Exception:
                pass
        try:
            if item is None:
                idx = self._combo_anim_mode.findData("none")
                self._combo_anim_mode.setCurrentIndex(idx if idx >= 0 else 0)
                self._refresh_animation_controls()
                return

            try:
                mode = item.data(ITEM_DATA_ANIM_MODE)
            except Exception:
                mode = None
            try:
                payload = item.data(ITEM_DATA_ANIM_PAYLOAD)
            except Exception:
                payload = None
            mode = str(mode or "none").strip() if isinstance(mode, str) else "none"
            if not isinstance(payload, dict):
                payload = {}

            idx = self._combo_anim_mode.findData(mode)
            self._combo_anim_mode.setCurrentIndex(idx if idx >= 0 else 0)

            try:
                self._spin_anim_speed.setValue(float(payload.get("speed", self._spin_anim_speed.value())))
            except Exception:
                pass
            try:
                self._spin_anim_padding.setValue(float(payload.get("padding", self._spin_anim_padding.value())))
            except Exception:
                pass
            try:
                self._spin_anim_angle.setValue(float(payload.get("angle", self._spin_anim_angle.value())))
            except Exception:
                pass
            try:
                self._spin_anim_amp_x.setValue(float(payload.get("amp_x", payload.get("ax", self._spin_anim_amp_x.value()))))
            except Exception:
                pass
            try:
                self._spin_anim_amp_y.setValue(float(payload.get("amp_y", payload.get("ay", self._spin_anim_amp_y.value()))))
            except Exception:
                pass
            if mode == "pendulum":
                try:
                    self._spin_anim_amp_x.setValue(float(payload.get("range", self._spin_anim_amp_x.value())))
                except Exception:
                    pass
                try:
                    self._spin_anim_amp_y.setValue(float(payload.get("len", self._spin_anim_amp_y.value())))
                except Exception:
                    pass
            try:
                self._spin_anim_rate.setValue(float(payload.get("rate", payload.get("freq", self._spin_anim_rate.value()))))
            except Exception:
                pass
            try:
                self._spin_anim_rate2.setValue(float(payload.get("rate2", payload.get("freq2", self._spin_anim_rate2.value()))))
            except Exception:
                pass
            try:
                self._spin_anim_phase.setValue(float(payload.get("phase", self._spin_anim_phase.value())))
            except Exception:
                pass
            try:
                self._spin_anim_rot_speed.setValue(float(payload.get("rot_speed", self._spin_anim_rot_speed.value())))
            except Exception:
                pass
            try:
                self._spin_anim_rot_amp.setValue(float(payload.get("rot_amp", self._spin_anim_rot_amp.value())))
            except Exception:
                pass
            try:
                self._spin_anim_scale_min.setValue(float(payload.get("scale_min", self._spin_anim_scale_min.value())))
            except Exception:
                pass
            try:
                self._spin_anim_scale_max.setValue(float(payload.get("scale_max", self._spin_anim_scale_max.value())))
            except Exception:
                pass
            try:
                self._spin_anim_opacity_min.setValue(float(payload.get("opacity_min", self._spin_anim_opacity_min.value())))
            except Exception:
                pass
            try:
                self._spin_anim_opacity_max.setValue(float(payload.get("opacity_max", self._spin_anim_opacity_max.value())))
            except Exception:
                pass
            try:
                self._spin_anim_jitter.setValue(float(payload.get("jitter", payload.get("noise", self._spin_anim_jitter.value()))))
            except Exception:
                pass

            if mode in ("slide", "bounce"):
                axis = str(payload.get("axis") or "")
                dir_sign = None
                try:
                    dir_sign = float(payload.get("dir", 1.0))
                except Exception:
                    dir_sign = None
                guess = None
                if axis == "y":
                    guess = "bt" if (dir_sign is not None and dir_sign < 0.0) else "tb"
                elif axis == "x":
                    guess = "rl" if (dir_sign is not None and dir_sign < 0.0) else "lr"
                if guess is not None:
                    i2 = self._combo_anim_slide_dir.findData(guess)
                    self._combo_anim_slide_dir.setCurrentIndex(i2 if i2 >= 0 else 0)

            if mode == "follow_path":
                pid = str(payload.get("path") or "path1")
                i2 = self._combo_anim_follow_path.findData(pid)
                self._combo_anim_follow_path.setCurrentIndex(i2 if i2 >= 0 else 0)

            if mode in ("orbit_center", "orbit_pulse"):
                cid = str(payload.get("center") or "center1")
                i2 = self._combo_anim_orbit_center.findData(cid)
                self._combo_anim_orbit_center.setCurrentIndex(i2 if i2 >= 0 else 0)

            if mode in ("orbit_edge", "orbit_center", "orbit_pulse"):
                try:
                    orbit_dir = float(payload.get("dir", 1.0))
                except Exception:
                    orbit_dir = 1.0
                i2 = self._combo_anim_orbit_dir.findData(orbit_dir)
                if i2 < 0:
                    i2 = self._combo_anim_orbit_dir.findData(1.0 if orbit_dir >= 0.0 else -1.0)
                self._combo_anim_orbit_dir.setCurrentIndex(i2 if i2 >= 0 else 0)

            self._refresh_animation_controls()
        finally:
            for w in widgets:
                try:
                    w.blockSignals(False)
                except Exception:
                    pass

    def _on_blend_mode_changed_from_ui(self, _index: int) -> None:
        if self._undo_blocked:
            return
        try:
            after = self._combo_blend_mode.currentData()
        except Exception:
            after = BlendMode.NORMAL.value
        if not isinstance(after, str) or not after:
            after = BlendMode.NORMAL.value

        scene = self._current_scene()
        try:
            selected = list(scene.selectedItems())
        except Exception:
            selected = []
        if not selected:
            item = self._selected_graphics_item()
            if item is not None:
                selected = [item]
        if not selected:
            return

        changes: list[tuple[object, str, str]] = []
        for item in selected:
            if not hasattr(item, "set_blend_mode") or not hasattr(item, "blend_mode"):
                continue
            try:
                bm = item.blend_mode()
                before = bm.value if isinstance(bm, BlendMode) else str(bm)
            except Exception:
                before = BlendMode.NORMAL.value
            if str(before) == str(after):
                continue
            changes.append((item, str(before), str(after)))

        if not changes:
            return

        monitor_index = self._current_monitor_index()
        if len(changes) == 1:
            it, before, after_s = changes[0]
            self._undo_stack.push(_SetLayerBlendModeCommand(self, monitor_index, it, before, after_s))
        else:
            self._undo_stack.push(_SetMultiLayerBlendModeCommand(self, monitor_index, changes))

    def _on_layer_name_text_edited(self, text: str) -> None:
        if self._undo_blocked:
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        gid = id(item)
        state = self._current_state()
        before_label = str(state.labels.get(gid, "Layer"))
        if self._label_baseline is None or self._label_baseline[0] != monitor_index or self._label_baseline[1] != gid:
            self._label_baseline = (monitor_index, gid, before_label)
        state.labels[gid] = str(text)
        list_item = self._list_item_by_gid.get(gid)
        if list_item:
            list_item.setText(self._layer_display_name(item, str(text)))

    def _on_opacity_changed_from_ui(self, value: int) -> None:
        if self._undo_blocked:
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        gid = id(item)
        if self._opacity_baseline is None or self._opacity_baseline[0] != monitor_index or self._opacity_baseline[1] != gid:
            try:
                self._opacity_baseline = (monitor_index, gid, float(item.opacity()))
            except Exception:
                self._opacity_baseline = None
        opacity = max(0.0, min(1.0, float(value) / 100.0))
        self._apply_layer_opacity(item, opacity)
        if not self._undo_blocked:
            self._opacity_undo_timer.start(250)

    def _on_layer_locked_toggled_from_ui(self, locked: bool) -> None:
        if self._undo_blocked:
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        try:
            before = bool(item.data(ITEM_DATA_LOCKED))
        except Exception:
            before = False
        after = bool(locked)
        if before == after:
            return
        self._undo_stack.push(_SetLayerLockedCommand(self, monitor_index, item, before, after))

    def _on_layer_hidden_toggled_from_ui(self, hidden: bool) -> None:
        if self._undo_blocked:
            return
        item = self._selected_graphics_item()
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        try:
            before = bool(item.data(ITEM_DATA_HIDDEN))
        except Exception:
            before = False
        after = bool(hidden)
        if before == after:
            return
        self._undo_stack.push(_SetLayerHiddenCommand(self, monitor_index, item, before, after))

    def _on_layer_double_clicked(self, list_item: QListWidgetItem) -> None:
        gid = list_item.data(Qt.UserRole)
        if not isinstance(gid, int):
            return
        item = self._current_state().items.get(gid)
        if item is None:
            return
        if isinstance(item, TextLayerItem):
            self._txt_text.setFocus(Qt.FocusReason.MouseFocusReason)
            try:
                self._txt_text.selectAll()
            except Exception:
                pass
        else:
            self._txt_layer_name.setFocus(Qt.FocusReason.MouseFocusReason)
            try:
                self._txt_layer_name.selectAll()
            except Exception:
                pass

    def _on_layers_context_menu(self, pos) -> None:
        list_item = self._layers_list.itemAt(pos)
        if list_item is None:
            list_item = self._layers_list.currentItem()
        if list_item is None:
            return
        self._layers_list.setCurrentItem(list_item)
        gid = list_item.data(Qt.UserRole)
        if not isinstance(gid, int):
            return
        state = self._current_state()
        item = state.items.get(gid)
        if item is None:
            return
        monitor_index = self._current_monitor_index()
        menu = QMenu(self)

        act_rename = menu.addAction("Rename")
        act_duplicate = menu.addAction("Duplicate")

        act_edit_text = None
        if isinstance(item, TextLayerItem):
            act_edit_text = menu.addAction("Edit Text")
        act_replace_source = None
        if not isinstance(item, TextLayerItem):
            kind = None
            try:
                k = item.data(ITEM_DATA_SOURCE_KIND)
                if isinstance(k, str):
                    kind = k
            except Exception:
                kind = None
            if kind in {"image", "gif", "video"}:
                act_replace_source = menu.addAction("Replace Source…")

        locked_now = False
        hidden_now = False
        try:
            locked_now = bool(item.data(ITEM_DATA_LOCKED))
        except Exception:
            locked_now = False
        try:
            hidden_now = bool(item.data(ITEM_DATA_HIDDEN))
        except Exception:
            hidden_now = False

        act_lock = menu.addAction("Unlock" if locked_now else "Lock")
        act_hide = menu.addAction("Show" if hidden_now else "Hide")

        menu.addSeparator()
        act_up = menu.addAction("Move Up")
        act_down = menu.addAction("Move Down")
        act_front = menu.addAction("Bring To Front")
        act_back = menu.addAction("Send To Back")
        menu.addSeparator()
        act_delete = menu.addAction("Delete")

        chosen = menu.exec(self._layers_list.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_delete:
            self._delete_layer()
            return
        if chosen == act_duplicate:
            self._duplicate_selected_layer()
            return
        if chosen == act_up:
            self._move_layer_up()
            return
        if chosen == act_down:
            self._move_layer_down()
            return
        if chosen == act_front:
            self._move_selected_layer_to(edge="front")
            return
        if chosen == act_back:
            self._move_selected_layer_to(edge="back")
            return
        if chosen == act_lock:
            self._undo_stack.push(_SetLayerLockedCommand(self, monitor_index, item, locked_now, not locked_now))
            return
        if chosen == act_hide:
            self._undo_stack.push(_SetLayerHiddenCommand(self, monitor_index, item, hidden_now, not hidden_now))
            return
        if act_replace_source is not None and chosen == act_replace_source:
            self._replace_layer_source(item)
            return
        if act_edit_text is not None and chosen == act_edit_text and isinstance(item, TextLayerItem):
            before_text = str(item.text())
            before_style = item.style()
            text, ok = QInputDialog.getText(self, "Edit Text", "Text:", text=before_text)
            if not ok:
                return
            after_text = str(text)
            if after_text != before_text:
                self._undo_stack.push(_SetTextCommand(self, monitor_index, item, before_text, before_style, after_text, before_style))
            return
        if chosen == act_rename:
            before = str(state.labels.get(gid, "Layer"))
            text, ok = QInputDialog.getText(self, "Rename Layer", "Name:", text=before)
            if not ok:
                return
            after = str(text).strip() or before
            if after != before:
                self._undo_stack.push(_RenameLayerLabelCommand(self, monitor_index, gid, before, after))

    def _replace_layer_source(self, item: object) -> None:
        kind = None
        try:
            k = item.data(ITEM_DATA_SOURCE_KIND)
            if isinstance(k, str):
                kind = k
        except Exception:
            kind = None
        if kind not in {"image", "gif", "video"}:
            return

        if kind == "video":
            filter_str = "Video Files (*.mp4 *.mkv *.avi *.mov *.webm);;All Files (*.*)"
        else:
            filter_str = "Image/GIF Files (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All Files (*.*)"

        path, _ = QFileDialog.getOpenFileName(self, "Replace Source", str(project_dir()), filter_str)
        if not path:
            return
        try:
            p = Path(path)
        except Exception:
            return
        if not p.exists():
            return

        ext = p.suffix.lower()
        if kind == "video":
            if ext not in {".mp4", ".mkv", ".avi", ".mov", ".webm"}:
                return
            self._replace_video_source(item, str(p))
            return

        if ext not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}:
            return
        self._replace_pixmap_source(item, str(p), is_gif=(ext == ".gif"))

    def _replace_video_source(self, item: object, file_path: str) -> None:
        if not isinstance(item, QGraphicsVideoItem):
            return
        old_center = item.sceneBoundingRect().center()
        player = None
        try:
            player = item.data(0xFEED)
        except Exception:
            player = None
        if player is not None:
            try:
                url = QUrl.fromLocalFile(str(Path(file_path).resolve()))
                player.setSource(url)
                player.play()
            except Exception:
                pass
        try:
            item.setData(ITEM_DATA_SOURCE_PATH, str(file_path))
            item.setData(ITEM_DATA_SOURCE_KIND, "video")
        except Exception:
            pass
        self._recenter_item_to(item, old_center)

    def _replace_pixmap_source(self, item: object, file_path: str, is_gif: bool) -> None:
        if not isinstance(item, QGraphicsPixmapItem):
            return
        old_rect = item.sceneBoundingRect()
        old_center = old_rect.center()
        target_w = float(old_rect.width())
        target_h = float(old_rect.height())

        old_movie = None
        try:
            old_movie = item.data(0xBEEF)
        except Exception:
            old_movie = None
        if old_movie is not None:
            try:
                old_movie.stop()
            except Exception:
                pass

        if is_gif:
            movie = QMovie(str(file_path))
            movie.setCacheMode(QMovie.CacheAll)
            applied = False

            def update_frame() -> None:
                nonlocal applied
                frame = movie.currentPixmap()
                if frame.isNull():
                    return
                item.setPixmap(frame)
                try:
                    item.setTransformOriginPoint(item.boundingRect().center())
                except Exception:
                    pass
                if not applied:
                    self._scale_item_to_target(item, target_w, target_h)
                    self._recenter_item_to(item, old_center)
                    applied = True

            movie.frameChanged.connect(lambda _i: update_frame())
            movie.start()
            update_frame()
            try:
                item.setData(0xBEEF, movie)
            except Exception:
                pass
            try:
                item.setData(ITEM_DATA_SOURCE_KIND, "gif")
            except Exception:
                pass
        else:
            pix = QPixmap(str(file_path))
            if pix.isNull():
                return
            item.setPixmap(pix)
            try:
                item.setTransformOriginPoint(item.boundingRect().center())
            except Exception:
                pass
            try:
                item.setData(0xBEEF, None)
            except Exception:
                pass
            try:
                item.setData(ITEM_DATA_SOURCE_KIND, "image")
            except Exception:
                pass
            self._scale_item_to_target(item, target_w, target_h)
            self._recenter_item_to(item, old_center)

        try:
            item.setData(ITEM_DATA_SOURCE_PATH, str(file_path))
        except Exception:
            pass

    def _scale_item_to_target(self, item: object, target_w: float, target_h: float) -> None:
        if target_w <= 0.0 or target_h <= 0.0:
            return
        try:
            rect = item.sceneBoundingRect()
        except Exception:
            return
        w = float(rect.width())
        h = float(rect.height())
        if w <= 0.0 or h <= 0.0:
            return
        factor = min(float(target_w) / w, float(target_h) / h)
        if not (factor > 0.0):
            return
        try:
            item.setScale(float(item.scale()) * float(factor))
        except Exception:
            return

    def _recenter_item_to(self, item: object, target_center: QPointF) -> None:
        try:
            current_center = item.sceneBoundingRect().center()
        except Exception:
            return
        dx = float(target_center.x() - current_center.x())
        dy = float(target_center.y() - current_center.y())
        if dx == 0.0 and dy == 0.0:
            return
        try:
            pos = item.pos()
            item.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
        except Exception:
            return

    def _sync_transform_to_ui(self, item: object) -> None:
        try:
            self._spin_x.blockSignals(True)
            self._spin_y.blockSignals(True)
            self._spin_scale.blockSignals(True)
            self._spin_rotation.blockSignals(True)

            self._spin_x.setValue(float(item.pos().x()))
            self._spin_y.setValue(float(item.pos().y()))
            self._spin_scale.setValue(float(item.scale()))
            self._spin_rotation.setValue(float(item.rotation()))
        finally:
            self._spin_x.blockSignals(False)
            self._spin_y.blockSignals(False)
            self._spin_scale.blockSignals(False)
            self._spin_rotation.blockSignals(False)

    def _apply_transform_from_ui(self) -> None:
        item = self._selected_graphics_item()
        if item is None:
            return
        try:
            movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
        except Exception:
            movable = True
        if not movable:
            return

        monitor_index = self._current_monitor_index()
        gid = id(item)
        if not self._undo_blocked:
            if (
                self._transform_baseline is None
                or self._transform_baseline[0] != monitor_index
                or self._transform_baseline[1] != gid
            ):
                try:
                    self._transform_baseline = (
                        monitor_index,
                        gid,
                        (
                            float(item.pos().x()),
                            float(item.pos().y()),
                            float(item.scale()),
                            float(item.rotation()),
                        ),
                    )
                except Exception:
                    self._transform_baseline = None
        try:
            item.setPos(self._spin_x.value(), self._spin_y.value())
            item.setScale(self._spin_scale.value())
            item.setRotation(self._spin_rotation.value())
        except Exception:
            return
        if not self._undo_blocked:
            self._transform_undo_timer.start(250)

    def _fit_selected_to_canvas(self, mode: str) -> None:
        scene = self._current_scene()
        try:
            items = [
                it for it in scene.selectedItems() if bool(it.flags() & QGraphicsItem.ItemIsMovable)
            ]
        except Exception:
            items = []
        if not items:
            return
        try:
            target = scene._anim_bounds_rect()
        except Exception:
            target = scene.sceneRect()
        if float(target.width()) <= 0.0 or float(target.height()) <= 0.0:
            return
        target_center = target.center()

        changes: list[tuple[object, tuple[float, float, float, float], tuple[float, float, float, float]]] = []
        for item in items:
            try:
                bounds = item.sceneBoundingRect()
            except Exception:
                continue
            if float(bounds.width()) <= 0.0 or float(bounds.height()) <= 0.0:
                continue
            w_ratio = float(target.width()) / float(bounds.width())
            h_ratio = float(target.height()) / float(bounds.height())
            factor = max(w_ratio, h_ratio) if mode == "fill" else min(w_ratio, h_ratio)
            if not (factor > 0.0):
                continue
            before = (
                float(item.pos().x()),
                float(item.pos().y()),
                float(item.scale()),
                float(item.rotation()),
            )
            try:
                item.setScale(max(0.01, float(item.scale()) * float(factor)))
            except Exception:
                continue
            try:
                new_bounds = item.sceneBoundingRect()
                pos = item.pos()
                item.setPos(
                    QPointF(
                        float(pos.x()) + (float(target_center.x()) - float(new_bounds.center().x())),
                        float(pos.y()) + (float(target_center.y()) - float(new_bounds.center().y())),
                    )
                )
            except Exception:
                pass
            after = (
                float(item.pos().x()),
                float(item.pos().y()),
                float(item.scale()),
                float(item.rotation()),
            )
            if after != before:
                changes.append((item, before, after))

        if not changes:
            return
        self._undo_stack.push(
            _MultiTransformCommand(self, self._current_monitor_index(), "Fit To Canvas", changes)
        )
        selected = self._selected_graphics_item()
        if selected is not None:
            self._sync_transform_to_ui(selected)

    def _align_selected(self, horizontal: str | None = None, vertical: str | None = None) -> None:
        scene = self._current_scene()

        try:
            items = list(scene.selectedItems())
        except Exception:
            items = []
        if not items:
            item = self._selected_graphics_item()
            if item is not None:
                items = [item]
        if not items:
            return

        try:
            target = self._combo_align_target.currentData()
        except Exception:
            target = "scene"
        target_rect = scene.sceneRect()
        if target == "selection":
            selection_rect = None
            for it in items:
                try:
                    r = it.sceneBoundingRect()
                except Exception:
                    continue
                if selection_rect is None:
                    selection_rect = QRectF(r)
                else:
                    selection_rect = selection_rect.united(r)
            if selection_rect is not None:
                target_rect = selection_rect

        changes: list[tuple[object, tuple[float, float, float, float], tuple[float, float, float, float]]] = []
        for item in items:
            try:
                movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
            except Exception:
                movable = True
            if not movable:
                continue
            try:
                before = (
                    float(item.pos().x()),
                    float(item.pos().y()),
                    float(item.scale()),
                    float(item.rotation()),
                )
            except Exception:
                continue

            try:
                item_rect = item.sceneBoundingRect()
            except Exception:
                continue

            x = float(before[0])
            y = float(before[1])

            if horizontal == "left":
                x += float(target_rect.left() - item_rect.left())
            elif horizontal == "center":
                x += float(target_rect.center().x() - item_rect.center().x())
            elif horizontal == "right":
                x += float(target_rect.right() - item_rect.right())

            if vertical == "top":
                y += float(target_rect.top() - item_rect.top())
            elif vertical == "middle":
                y += float(target_rect.center().y() - item_rect.center().y())
            elif vertical == "bottom":
                y += float(target_rect.bottom() - item_rect.bottom())

            after = (float(x), float(y), before[2], before[3])
            if after != before:
                changes.append((item, before, after))

        if not changes:
            return

        self._undo_stack.push(_MultiTransformCommand(self, self._current_monitor_index(), "Align", changes))

    def _distribute_selected(self, axis: str) -> None:
        scene = self._current_scene()
        try:
            items = list(scene.selectedItems())
        except Exception:
            items = []
        if len(items) < 3:
            return

        movable_items: list[QGraphicsItem] = []
        for item in items:
            try:
                movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
            except Exception:
                movable = True
            if movable:
                movable_items.append(item)
        if len(movable_items) < 3:
            return

        keyed: list[tuple[float, QGraphicsItem]] = []
        for item in movable_items:
            try:
                r = item.sceneBoundingRect()
            except Exception:
                continue
            c = r.center()
            keyed.append((float(c.x() if axis == "x" else c.y()), item))

        if len(keyed) < 3:
            return

        keyed.sort(key=lambda t: t[0])
        start = float(keyed[0][0])
        end = float(keyed[-1][0])
        if end == start:
            return
        step = (end - start) / float(len(keyed) - 1)

        changes: list[tuple[object, tuple[float, float, float, float], tuple[float, float, float, float]]] = []
        for i in range(1, len(keyed) - 1):
            target = start + (step * float(i))
            item = keyed[i][1]
            try:
                before = (
                    float(item.pos().x()),
                    float(item.pos().y()),
                    float(item.scale()),
                    float(item.rotation()),
                )
            except Exception:
                continue
            try:
                r = item.sceneBoundingRect()
                c = r.center()
            except Exception:
                continue

            x = float(before[0])
            y = float(before[1])
            if axis == "x":
                x += float(target - float(c.x()))
            else:
                y += float(target - float(c.y()))
            after = (float(x), float(y), before[2], before[3])
            if after != before:
                changes.append((item, before, after))

        if not changes:
            return

        self._undo_stack.push(_MultiTransformCommand(self, self._current_monitor_index(), "Distribute", changes))

    def _match_size_selected(self, axis: str) -> None:
        scene = self._current_scene()
        try:
            selected = list(scene.selectedItems())
        except Exception:
            selected = []
        if len(selected) < 2:
            return

        ref: object | None = None
        primary_gid = self._selection_primary_gid.get(self._current_monitor_index())
        if isinstance(primary_gid, int):
            for it in selected:
                if id(it) == primary_gid:
                    ref = it
                    break
        try:
            if ref is None:
                focus = scene.focusItem()
                if focus is not None and focus in selected:
                    ref = focus
        except Exception:
            ref = None
        if ref is None:
            ref = selected[0]

        try:
            ref_rect = ref.sceneBoundingRect()
        except Exception:
            return
        ref_w = float(ref_rect.width())
        ref_h = float(ref_rect.height())
        if ref_w <= 0.0 or ref_h <= 0.0:
            return

        changes: list[tuple[object, tuple[float, float, float, float], tuple[float, float, float, float]]] = []
        for item in selected:
            if item is ref:
                continue
            try:
                movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
            except Exception:
                movable = True
            if not movable:
                continue

            try:
                before = (
                    float(item.pos().x()),
                    float(item.pos().y()),
                    float(item.scale()),
                    float(item.rotation()),
                )
            except Exception:
                continue
            try:
                before_rect = item.sceneBoundingRect()
                before_center = before_rect.center()
                before_w = float(before_rect.width())
                before_h = float(before_rect.height())
            except Exception:
                continue
            if before_w <= 0.0 or before_h <= 0.0:
                continue

            if axis == "w":
                factor = ref_w / before_w
            else:
                factor = ref_h / before_h
            try:
                factor = float(factor)
            except Exception:
                continue
            if factor <= 0.0:
                continue

            try:
                item.setScale(float(item.scale()) * float(factor))
                after_rect = item.sceneBoundingRect()
                after_center = after_rect.center()
                dx = float(before_center.x() - after_center.x())
                dy = float(before_center.y() - after_center.y())
                pos = item.pos()
                item.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                after = (
                    float(item.pos().x()),
                    float(item.pos().y()),
                    float(item.scale()),
                    float(item.rotation()),
                )
            except Exception:
                try:
                    item.setPos(QPointF(before[0], before[1]))
                    item.setScale(float(before[2]))
                    item.setRotation(float(before[3]))
                except Exception:
                    pass
                continue

            if after != before:
                changes.append((item, before, after))

        if not changes:
            return
        self._undo_stack.push(_MultiTransformCommand(self, self._current_monitor_index(), "Match Size", changes))

    def _refresh_animation_controls(self) -> None:
        try:
            mode = str(self._combo_anim_mode.currentData() or "none").strip()
        except Exception:
            mode = "none"
        is_slide = mode in ("slide", "bounce")
        is_follow = mode == "follow_path"
        is_orbit_center = mode == "orbit_center"
        is_orbit = mode in ("orbit_edge", "orbit_center", "orbit_pulse")
        uses_angle = mode in ("drift", "zigzag", "tumble")
        uses_amp_x = mode in ("zigzag", "figure8", "lissajous", "pendulum", "shake", "glitch")
        uses_amp_y = mode in ("figure8", "lissajous", "pendulum", "shake", "float_bob", "hover_wobble")
        uses_rate = mode in ("zigzag", "figure8", "lissajous", "pendulum", "wobble", "pulse", "pop", "fade_in", "fade_out", "blink", "float_bob", "hover_wobble", "orbit_pulse", "heartbeat", "glitch", "spiral")
        uses_rate2 = mode == "lissajous"
        uses_phase = bool(uses_rate)
        uses_rot_speed = mode in ("spin", "tumble")
        uses_rot_amp = mode in ("wobble", "hover_wobble")
        uses_scale = mode in ("pulse", "pop", "orbit_pulse", "heartbeat")
        uses_opacity = mode in ("fade_in", "fade_out", "blink")
        uses_jitter = mode == "wander"
        try:
            self._combo_anim_slide_dir.setEnabled(bool(is_slide))
        except Exception:
            pass
        try:
            self._combo_anim_follow_path.setEnabled(bool(is_follow))
        except Exception:
            pass
        try:
            self._combo_anim_orbit_center.setEnabled(bool(is_orbit_center))
        except Exception:
            pass
        try:
            self._combo_anim_orbit_dir.setEnabled(bool(is_orbit))
        except Exception:
            pass
        try:
            self._spin_anim_padding.setEnabled(bool(mode in ("orbit_edge", "orbit_center", "drift", "zigzag", "wander", "tumble", "orbit_pulse")))
        except Exception:
            pass
        for w, enabled in (
            (self._spin_anim_angle, uses_angle),
            (self._spin_anim_amp_x, uses_amp_x),
            (self._spin_anim_amp_y, uses_amp_y),
            (self._spin_anim_rate, uses_rate),
            (self._spin_anim_rate2, uses_rate2),
            (self._spin_anim_phase, uses_phase),
            (self._spin_anim_rot_speed, uses_rot_speed),
            (self._spin_anim_rot_amp, uses_rot_amp),
            (self._spin_anim_scale_min, uses_scale),
            (self._spin_anim_scale_max, uses_scale),
            (self._spin_anim_opacity_min, uses_opacity),
            (self._spin_anim_opacity_max, uses_opacity),
            (self._spin_anim_jitter, uses_jitter),
        ):
            try:
                w.setEnabled(bool(enabled))
            except Exception:
                pass
        try:
            self._btn_anim_draw_path.setEnabled(bool(is_follow))
        except Exception:
            pass
        try:
            self._btn_anim_pick_center.setEnabled(bool(is_orbit_center))
        except Exception:
            pass
        try:
            self._chk_anim_avoid_taskbar.setEnabled(
                bool(
                    mode
                    in (
                        "orbit_edge",
                        "slide",
                        "bounce",
                        "orbit_center",
                        "drift",
                        "zigzag",
                        "figure8",
                        "lissajous",
                        "pendulum",
                        "wander",
                        "shake",
                        "float_bob",
                        "hover_wobble",
                        "tumble",
                        "orbit_pulse",
                    )
                )
            )
        except Exception:
            pass

    def _set_follow_path_points(self, path_id: str, points: list[QPointF]) -> None:
        pid = str(path_id or "path1")
        pts = [QPointF(float(p.x()), float(p.y())) for p in (points or [])]
        self._follow_paths[pid] = pts
        if pid == "path1":
            self._global_path_points = list(pts)
        for editor in self._monitor_editors:
            try:
                editor.scene.set_global_paths(self._follow_paths)
            except Exception:
                pass

    def _draw_follow_path(self) -> None:
        if not self._screens:
            return
        try:
            pid = str(self._combo_anim_follow_path.currentData() or "path1")
        except Exception:
            pid = "path1"
        monitor_rects = [QRectF(self._monitor_global_rects.get(i, QRectF())) for i in range(len(self._screens))]
        existing = self._follow_paths.get(pid) or []
        dlg = _AllMonitorsPathDialog(self, self._virtual_desktop_rect, monitor_rects, existing)
        if dlg.exec() != QDialog.Accepted:
            return
        pts = dlg.points()
        if len(pts) < 2:
            return
        self._set_follow_path_points(pid, pts)

    def _pick_orbit_center(self) -> None:
        try:
            cid = str(self._combo_anim_orbit_center.currentData() or "center1")
        except Exception:
            cid = "center1"
        try:
            self._current_scene().set_orbit_center_pick_enabled(True, center_id=cid)
        except Exception:
            pass

    def _start_animation_selected(self) -> None:
        scene = self._current_scene()
        try:
            selected = list(scene.selectedItems())
        except Exception:
            selected = []
        if not selected:
            return

        try:
            mode = str(self._combo_anim_mode.currentData() or "none")
        except Exception:
            mode = "none"
        mode = mode.strip()
        if mode in ("", "none"):
            return

        try:
            speed = float(self._spin_anim_speed.value())
        except Exception:
            speed = 0.0
        try:
            padding = float(self._spin_anim_padding.value())
        except Exception:
            padding = 0.0
        try:
            angle = float(self._spin_anim_angle.value())
        except Exception:
            angle = 0.0
        try:
            amp_x = float(self._spin_anim_amp_x.value())
        except Exception:
            amp_x = 0.0
        try:
            amp_y = float(self._spin_anim_amp_y.value())
        except Exception:
            amp_y = 0.0
        try:
            rate = float(self._spin_anim_rate.value())
        except Exception:
            rate = 0.0
        try:
            rate2 = float(self._spin_anim_rate2.value())
        except Exception:
            rate2 = 0.0
        try:
            phase = float(self._spin_anim_phase.value())
        except Exception:
            phase = 0.0
        try:
            rot_speed = float(self._spin_anim_rot_speed.value())
        except Exception:
            rot_speed = 0.0
        try:
            rot_amp = float(self._spin_anim_rot_amp.value())
        except Exception:
            rot_amp = 0.0
        try:
            scale_min = float(self._spin_anim_scale_min.value())
        except Exception:
            scale_min = 0.0
        try:
            scale_max = float(self._spin_anim_scale_max.value())
        except Exception:
            scale_max = 0.0
        try:
            opacity_min = float(self._spin_anim_opacity_min.value())
        except Exception:
            opacity_min = 0.0
        try:
            opacity_max = float(self._spin_anim_opacity_max.value())
        except Exception:
            opacity_max = 0.0
        try:
            jitter = float(self._spin_anim_jitter.value())
        except Exception:
            jitter = 0.0

        if mode == "follow_path":
            if speed <= 0.0:
                return
            try:
                pid = str(self._combo_anim_follow_path.currentData() or "path1")
            except Exception:
                pid = "path1"
            if len(self._follow_paths.get(pid) or []) < 2:
                self._draw_follow_path()
            if len(self._follow_paths.get(pid) or []) < 2:
                return
            mon_rect = None
            try:
                mon_rect = scene.monitor_global_rect()
            except Exception:
                mon_rect = None
            if mon_rect is None:
                return

            global_centers: dict[int, QPointF] = {}
            sum_x = 0.0
            sum_y = 0.0
            count = 0
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    gp = QPointF(float(c.x() + mon_rect.left()), float(c.y() + mon_rect.top()))
                except Exception:
                    continue
                global_centers[id(it)] = gp
                sum_x += float(gp.x())
                sum_y += float(gp.y())
                count += 1
            if count <= 0:
                return
            group_center = QPointF(float(sum_x / float(count)), float(sum_y / float(count)))
            try:
                s0 = float(scene.project_global_point_to_path(group_center, path_id=pid))
            except Exception:
                s0 = 0.0

            payloads: dict[int, dict] = {}
            for it in selected:
                gp = global_centers.get(id(it))
                if gp is None:
                    continue
                dx = float(gp.x() - group_center.x())
                dy = float(gp.y() - group_center.y())
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "path": str(pid),
                    "speed": float(speed),
                    "s": float(s0),
                    "offset": (float(dx), float(dy)),
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
            if not payloads:
                return
            try:
                scene.set_items_animation(selected, mode, payloads)
            except Exception:
                pass
            return

        payloads: dict[int, dict] = {}
        bounds_rect = scene.sceneRect()
        try:
            if bool(self._chk_anim_avoid_taskbar.isChecked()):
                wr = scene.desktop_work_rect()
                if wr is not None:
                    bounds_rect = QRectF(wr)
        except Exception:
            bounds_rect = scene.sceneRect()
        rect = bounds_rect.adjusted(padding, padding, -padding, -padding)
        left = float(rect.left())
        top = float(rect.top())
        right = float(rect.right())
        bottom = float(rect.bottom())
        w = float(rect.width())
        h = float(rect.height())

        if mode == "orbit_edge":
            try:
                orbit_dir = float(self._combo_anim_orbit_dir.currentData() or 1.0)
            except Exception:
                orbit_dir = 1.0
            if w <= 0.0 or h <= 0.0:
                return
            perim = (2.0 * w) + (2.0 * h)
            if perim <= 0.0:
                return
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    cx = float(c.x())
                    cy = float(c.y())
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0

                d_top = abs(cy - top)
                d_right = abs(cx - right)
                d_bottom = abs(cy - bottom)
                d_left = abs(cx - left)
                edge = min((d_top, "top"), (d_right, "right"), (d_bottom, "bottom"), (d_left, "left"))[1]

                x_clamped = max(left, min(right, cx))
                y_clamped = max(top, min(bottom, cy))
                if edge == "top":
                    t = x_clamped - left
                elif edge == "right":
                    t = w + (y_clamped - top)
                elif edge == "bottom":
                    t = w + h + (right - x_clamped)
                else:
                    t = w + h + w + (bottom - y_clamped)

                payloads[id(it)] = {
                    "speed": float(speed),
                    "padding": float(padding),
                    "t": float(t % perim),
                    "dir": float(orbit_dir),
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }

        elif mode == "orbit_center":
            rect = QRectF(bounds_rect)
            left = float(rect.left())
            top = float(rect.top())
            right = float(rect.right())
            bottom = float(rect.bottom())
            w = float(rect.width())
            h = float(rect.height())
            if w <= 0.0 or h <= 0.0:
                return
            try:
                orbit_dir = float(self._combo_anim_orbit_dir.currentData() or 1.0)
            except Exception:
                orbit_dir = 1.0
            try:
                center_id = str(self._combo_anim_orbit_center.currentData() or "center1")
            except Exception:
                center_id = "center1"
            center = None
            try:
                center = scene.orbit_center_point(center_id)
            except Exception:
                center = None
            picked_center = center is not None
            if center is None:
                sum_x = 0.0
                sum_y = 0.0
                count = 0
                for it in selected:
                    try:
                        movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                    except Exception:
                        movable = True
                    if not movable:
                        continue
                    try:
                        c = it.sceneBoundingRect().center()
                        sum_x += float(c.x())
                        sum_y += float(c.y())
                        count += 1
                    except Exception:
                        continue
                if count > 0:
                    center = QPointF(float(sum_x / float(count)), float(sum_y / float(count)))
                else:
                    center = rect.center()
            cx0 = float(center.x())
            cy0 = float(center.y())

            max_half_w = 0.0
            max_half_h = 0.0
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    br = it.sceneBoundingRect()
                    max_half_w = max(float(max_half_w), float(br.width()) / 2.0)
                    max_half_h = max(float(max_half_h), float(br.height()) / 2.0)
                except Exception:
                    continue

            if not picked_center:
                safe = rect.adjusted(float(max_half_w), float(max_half_h), -float(max_half_w), -float(max_half_h))
                if float(safe.width()) > 0.0 and float(safe.height()) > 0.0:
                    cx0 = max(float(safe.left()), min(float(safe.right()), float(cx0)))
                    cy0 = max(float(safe.top()), min(float(safe.bottom()), float(cy0)))

            movable_items: list[tuple[object, float, float, float, float, float]] = []
            max_r_allowed = float("inf")
            sum_r0 = 0.0
            max_extent = 0.0
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    br = it.sceneBoundingRect()
                    c = br.center()
                    ix = float(c.x())
                    iy = float(c.y())
                    width = float(br.width())
                    height = float(br.height())
                    half_w = width / 2.0
                    half_h = height / 2.0
                except Exception:
                    continue

                min_x = float(left) + float(half_w)
                max_x = float(right) - float(half_w)
                min_y = float(top) + float(half_h)
                max_y = float(bottom) - float(half_h)
                max_r = max(0.0, min(float(max_x - cx0), float(cx0 - min_x), float(max_y - cy0), float(cy0 - min_y)))
                max_r_allowed = min(float(max_r_allowed), float(max_r))

                dx = ix - cx0
                dy = iy - cy0
                r0 = math.hypot(dx, dy)
                ang0 = math.atan2(dy, dx)
                sum_r0 += float(r0)
                max_extent = max(float(max_extent), float(width), float(height))
                movable_items.append((it, float(ang0), float(r0), float(ix), float(iy), float(max_r)))

            if not movable_items:
                return

            if len(movable_items) == 1:
                it, ang0, r0, _ix, _iy, max_r = movable_items[0]
                desired_r = float(padding) if float(padding) > 0.0 else float(r0)
                if desired_r <= 0.0:
                    desired_r = float(max_r)
                r = min(float(desired_r), float(max_r))
                if r <= 0.0:
                    return
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "cx": float(cx0),
                    "cy": float(cy0),
                    "ang": float(ang0),
                    "r": float(r),
                    "desired_r": float(desired_r),
                    "use_scene_center": bool(picked_center),
                    "center": str(center_id),
                    "dir": float(orbit_dir),
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
            else:
                n = float(len(movable_items))
                min_gap = 10.0
                min_required_r = (n * (float(max_extent) + float(min_gap))) / (2.0 * math.pi)
                avg_r0 = float(sum_r0) / n if n > 0.0 else 0.0
                desired_r = float(padding) if float(padding) > 0.0 else float(avg_r0)
                if desired_r <= 0.0:
                    desired_r = float(min_required_r)
                r = max(float(desired_r), float(min_required_r))
                r = min(float(r), float(max_r_allowed))
                if r <= 0.0:
                    return

                ordered = sorted(movable_items, key=lambda t: float(t[1]))
                step = (2.0 * math.pi) / n
                offset = 0.0
                for i, (_it, ang0, _r0, _ix, _iy, _max_r) in enumerate(ordered):
                    offset += float(ang0) - (float(i) * float(step))
                offset = float(offset) / n if n > 0.0 else 0.0

                for i, (it, _ang0, _r0, _ix, _iy, _max_r) in enumerate(ordered):
                    ang = float(offset) + (float(i) * float(step))
                    try:
                        base_pos = (float(it.pos().x()), float(it.pos().y()))
                    except Exception:
                        base_pos = (0.0, 0.0)
                    try:
                        base_scale = float(it.scale())
                    except Exception:
                        base_scale = 1.0
                    try:
                        base_rot = float(it.rotation())
                    except Exception:
                        base_rot = 0.0
                    try:
                        base_opacity = float(it.opacity())
                    except Exception:
                        base_opacity = 1.0
                    payloads[id(it)] = {
                        "speed": float(speed),
                        "cx": float(cx0),
                        "cy": float(cy0),
                        "ang": float(ang),
                        "r": float(r),
                        "desired_r": float(r),
                        "use_scene_center": bool(picked_center),
                        "center": str(center_id),
                        "dir": float(orbit_dir),
                        "base_pos": base_pos,
                        "base_scale": float(base_scale),
                        "base_rot": float(base_rot),
                        "base_opacity": float(base_opacity),
                    }
                    try:
                        tx = float(cx0) + (math.cos(float(ang)) * float(r))
                        ty = float(cy0) + (math.sin(float(ang)) * float(r))
                        before_center = it.sceneBoundingRect().center()
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                    except Exception:
                        pass

        elif mode == "slide":
            try:
                direction = str(self._combo_anim_slide_dir.currentData() or "lr")
            except Exception:
                direction = "lr"
            direction = direction.strip().lower()
            if direction in ("tb", "bt"):
                axis = "y"
                mn = top
                mx = bottom
            else:
                axis = "x"
                mn = left
                mx = right
            if mx <= mn:
                return
            dir_sign = -1.0 if direction in ("rl", "bt") else 1.0

            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    cx = float(c.x())
                    cy = float(c.y())
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                if axis == "y":
                    val = max(mn, min(mx, cy))
                    payloads[id(it)] = {
                        "axis": "y",
                        "speed": float(speed),
                        "min": float(mn),
                        "max": float(mx),
                        "val": float(val),
                        "fixed": float(cx),
                        "dir": float(dir_sign),
                        "base_pos": base_pos,
                        "base_scale": float(base_scale),
                        "base_rot": float(base_rot),
                        "base_opacity": float(base_opacity),
                    }
                else:
                    val = max(mn, min(mx, cx))
                    payloads[id(it)] = {
                        "axis": "x",
                        "speed": float(speed),
                        "min": float(mn),
                        "max": float(mx),
                        "val": float(val),
                        "fixed": float(cy),
                        "dir": float(dir_sign),
                        "base_pos": base_pos,
                        "base_scale": float(base_scale),
                        "base_rot": float(base_rot),
                        "base_opacity": float(base_opacity),
                    }
        elif mode == "bounce":
            try:
                direction = str(self._combo_anim_slide_dir.currentData() or "lr")
            except Exception:
                direction = "lr"
            direction = direction.strip().lower()
            sx = float(speed)
            sy = float(speed) * 0.6
            if direction in ("tb", "bt"):
                vx = float(sy)
                vy = float(-sx if direction == "bt" else sx)
            else:
                vx = float(-sx if direction == "rl" else sx)
                vy = float(sy)
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                jitter = -1.0 if (id(it) % 2 == 0) else 1.0
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "vx": float(vx),
                    "vy": float(vy * jitter),
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "drift":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "padding": float(padding),
                    "angle": float(angle),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "zigzag":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "padding": float(padding),
                    "angle": float(angle),
                    "amp_x": float(amp_x),
                    "rate": float(rate),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "figure8":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "amp_x": float(amp_x),
                    "amp_y": float(amp_y),
                    "rate": float(rate),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "lissajous":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "amp_x": float(amp_x),
                    "amp_y": float(amp_y),
                    "rate": float(rate),
                    "rate2": float(rate2),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "pendulum":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "len": float(amp_y),
                    "range": float(amp_x),
                    "rate": float(rate),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "wander":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "padding": float(padding),
                    "jitter": float(jitter),
                    "base": [float(base[0]), float(base[1])],
                    "vx": 0.0,
                    "vy": 0.0,
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "shake":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "amp_x": float(amp_x),
                    "amp_y": float(amp_y),
                    "rate": float(rate),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "spin":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "rot_speed": float(rot_speed),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "wobble":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "rot_amp": float(rot_amp),
                    "rate": float(rate),
                    "phase": float(phase),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "tumble":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "padding": float(padding),
                    "angle": float(angle),
                    "rot_speed": float(rot_speed),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "pulse":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                if scale_min <= 0.0 and scale_max <= 0.0:
                    scale_min = float(base_scale) * 0.9
                    scale_max = float(base_scale) * 1.1
                payloads[id(it)] = {
                    "scale_min": float(scale_min),
                    "scale_max": float(scale_max),
                    "rate": float(rate),
                    "phase": float(phase),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "pop":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                if scale_min <= 0.0 and scale_max <= 0.0:
                    scale_min = float(base_scale) * 0.8
                    scale_max = float(base_scale) * 1.2
                payloads[id(it)] = {
                    "scale_min": float(scale_min),
                    "scale_max": float(scale_max),
                    "rate": float(rate),
                    "phase": float(phase),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode in ("fade_in", "fade_out"):
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "opacity_min": float(max(0.0, min(1.0, opacity_min))),
                    "opacity_max": float(max(0.0, min(1.0, opacity_max))),
                    "rate": float(rate),
                    "phase": float(phase),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "blink":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "opacity_min": float(max(0.0, min(1.0, opacity_min))),
                    "opacity_max": float(max(0.0, min(1.0, opacity_max))),
                    "rate": float(rate),
                    "phase": float(phase),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "float_bob":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "amp_y": float(amp_y),
                    "rate": float(rate),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "hover_wobble":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "amp_y": float(amp_y),
                    "rot_amp": float(rot_amp),
                    "rate": float(rate),
                    "phase": float(phase),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "orbit_pulse":
            rect = QRectF(bounds_rect)
            left = float(rect.left())
            top = float(rect.top())
            right = float(rect.right())
            bottom = float(rect.bottom())
            w = float(rect.width())
            h = float(rect.height())
            if w <= 0.0 or h <= 0.0:
                return
            try:
                orbit_dir = float(self._combo_anim_orbit_dir.currentData() or 1.0)
            except Exception:
                orbit_dir = 1.0
            try:
                center_id = str(self._combo_anim_orbit_center.currentData() or "center1")
            except Exception:
                center_id = "center1"
            center = None
            try:
                center = scene.orbit_center_point(center_id)
            except Exception:
                center = None
            picked_center = center is not None
            if center is None:
                sum_x = 0.0
                sum_y = 0.0
                count = 0
                for it in selected:
                    try:
                        movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                    except Exception:
                        movable = True
                    if not movable:
                        continue
                    try:
                        c = it.sceneBoundingRect().center()
                        sum_x += float(c.x())
                        sum_y += float(c.y())
                        count += 1
                    except Exception:
                        continue
                if count > 0:
                    center = QPointF(float(sum_x / float(count)), float(sum_y / float(count)))
                else:
                    center = rect.center()
            cx0 = float(center.x())
            cy0 = float(center.y())

            max_half_w = 0.0
            max_half_h = 0.0
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    br = it.sceneBoundingRect()
                    max_half_w = max(float(max_half_w), float(br.width()) / 2.0)
                    max_half_h = max(float(max_half_h), float(br.height()) / 2.0)
                except Exception:
                    continue

            safe = rect.adjusted(float(max_half_w), float(max_half_h), -float(max_half_w), -float(max_half_h))
            if float(safe.width()) <= 0.0 or float(safe.height()) <= 0.0:
                return
            cx0 = max(float(safe.left()), min(float(safe.right()), float(cx0)))
            cy0 = max(float(safe.top()), min(float(safe.bottom()), float(cy0)))
            if picked_center:
                try:
                    scene.set_orbit_center_point(QPointF(float(cx0), float(cy0)), center_id=center_id)
                except Exception:
                    pass

            movable_items: list[tuple[object, float, float, float, float, float]] = []
            max_r_allowed = float("inf")
            sum_r0 = 0.0
            max_extent = 0.0
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    br = it.sceneBoundingRect()
                    c = br.center()
                    ix = float(c.x())
                    iy = float(c.y())
                    width = float(br.width())
                    height = float(br.height())
                    half_w = width / 2.0
                    half_h = height / 2.0
                except Exception:
                    continue

                min_x = float(left) + float(half_w)
                max_x = float(right) - float(half_w)
                min_y = float(top) + float(half_h)
                max_y = float(bottom) - float(half_h)
                max_r = max(0.0, min(float(max_x - cx0), float(cx0 - min_x), float(max_y - cy0), float(cy0 - min_y)))
                max_r_allowed = min(float(max_r_allowed), float(max_r))

                dx = ix - cx0
                dy = iy - cy0
                r0 = math.hypot(dx, dy)
                ang0 = math.atan2(dy, dx)
                sum_r0 += float(r0)
                max_extent = max(float(max_extent), float(width), float(height))
                movable_items.append((it, float(ang0), float(r0), float(ix), float(iy), float(max_r)))

            if not movable_items:
                return

            if len(movable_items) == 1:
                it, ang0, r0, _ix, _iy, max_r = movable_items[0]
                desired_r = float(padding) if float(padding) > 0.0 else float(r0)
                if desired_r <= 0.0:
                    desired_r = float(max_r)
                r = min(float(desired_r), float(max_r))
                if r <= 0.0:
                    return
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                if scale_min <= 0.0 and scale_max <= 0.0:
                    scale_min = float(base_scale) * 0.9
                    scale_max = float(base_scale) * 1.1
                payloads[id(it)] = {
                    "speed": float(speed),
                    "cx": float(cx0),
                    "cy": float(cy0),
                    "ang": float(ang0),
                    "r": float(r),
                    "desired_r": float(desired_r),
                    "use_scene_center": bool(picked_center),
                    "center": str(center_id),
                    "dir": float(orbit_dir),
                    "scale_min": float(scale_min),
                    "scale_max": float(scale_max),
                    "rate": float(rate),
                    "phase": float(phase),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
            else:
                n = float(len(movable_items))
                min_gap = 10.0
                min_required_r = (n * (float(max_extent) + float(min_gap))) / (2.0 * math.pi)
                avg_r0 = float(sum_r0) / n if n > 0.0 else 0.0
                desired_r = float(padding) if float(padding) > 0.0 else float(avg_r0)
                if desired_r <= 0.0:
                    desired_r = float(min_required_r)
                r = max(float(desired_r), float(min_required_r))
                r = min(float(r), float(max_r_allowed))
                if r <= 0.0:
                    return

                ordered = sorted(movable_items, key=lambda t: float(t[1]))
                step = (2.0 * math.pi) / n
                offset = 0.0
                for i, (_it, ang0, _r0, _ix, _iy, _max_r) in enumerate(ordered):
                    offset += float(ang0) - (float(i) * float(step))
                offset = float(offset) / n if n > 0.0 else 0.0

                for i, (it, _ang0, _r0, _ix, _iy, _max_r) in enumerate(ordered):
                    ang = float(offset) + (float(i) * float(step))
                    try:
                        base_pos = (float(it.pos().x()), float(it.pos().y()))
                    except Exception:
                        base_pos = (0.0, 0.0)
                    try:
                        base_scale = float(it.scale())
                    except Exception:
                        base_scale = 1.0
                    try:
                        base_rot = float(it.rotation())
                    except Exception:
                        base_rot = 0.0
                    try:
                        base_opacity = float(it.opacity())
                    except Exception:
                        base_opacity = 1.0
                    if scale_min <= 0.0 and scale_max <= 0.0:
                        scale_min = float(base_scale) * 0.9
                        scale_max = float(base_scale) * 1.1
                    payloads[id(it)] = {
                        "speed": float(speed),
                        "cx": float(cx0),
                        "cy": float(cy0),
                        "ang": float(ang),
                        "r": float(r),
                        "desired_r": float(r),
                        "use_scene_center": bool(picked_center),
                        "center": str(center_id),
                        "dir": float(orbit_dir),
                        "scale_min": float(scale_min),
                        "scale_max": float(scale_max),
                        "rate": float(rate),
                        "phase": float(phase),
                        "t": 0.0,
                        "base_pos": base_pos,
                        "base_scale": float(base_scale),
                        "base_rot": float(base_rot),
                        "base_opacity": float(base_opacity),
                    }
                    try:
                        tx = float(cx0) + (math.cos(float(ang)) * float(r))
                        ty = float(cy0) + (math.sin(float(ang)) * float(r))
                        before_center = it.sceneBoundingRect().center()
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                    except Exception:
                        pass
        elif mode == "heartbeat":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                if scale_min <= 0.0 and scale_max <= 0.0:
                    scale_min = float(base_scale) * 0.9
                    scale_max = float(base_scale) * 1.1
                payloads[id(it)] = {
                    "scale_min": float(scale_min),
                    "scale_max": float(scale_max),
                    "rate": float(rate),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "glitch":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "intensity": float(amp_x),
                    "rate": float(rate),
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "rain":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        elif mode == "spiral":
            for it in selected:
                try:
                    movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
                except Exception:
                    movable = True
                if not movable:
                    continue
                try:
                    c = it.sceneBoundingRect().center()
                    base = (float(c.x()), float(c.y()))
                except Exception:
                    continue
                try:
                    base_pos = (float(it.pos().x()), float(it.pos().y()))
                except Exception:
                    base_pos = (0.0, 0.0)
                try:
                    base_scale = float(it.scale())
                except Exception:
                    base_scale = 1.0
                try:
                    base_rot = float(it.rotation())
                except Exception:
                    base_rot = 0.0
                try:
                    base_opacity = float(it.opacity())
                except Exception:
                    base_opacity = 1.0
                payloads[id(it)] = {
                    "speed": float(speed),
                    "expansion": float(rate),
                    "base": [float(base[0]), float(base[1])],
                    "t": 0.0,
                    "angle": 0.0,
                    "r": 0.0,
                    "base_pos": base_pos,
                    "base_scale": float(base_scale),
                    "base_rot": float(base_rot),
                    "base_opacity": float(base_opacity),
                }
        else:
            return

        try:
            scene.set_items_animation(selected, mode, payloads)
        except Exception:
            pass

    def _stop_animation_selected(self) -> None:
        scene = self._current_scene()
        try:
            selected = list(scene.selectedItems())
        except Exception:
            selected = []
        if not selected:
            return
        try:
            scene.clear_items_animation(selected)
        except Exception:
            pass

    @staticmethod
    def _effective_point_size(font: QFont) -> int:
        """Usable point size for a font that may be sized in pixels instead."""
        try:
            size = int(font.pointSize())
        except Exception:
            size = -1
        if size > 0:
            return size
        try:
            pixels = int(font.pixelSize())
        except Exception:
            pixels = -1
        if pixels > 0:
            # 1px == 0.75pt at the 96 DPI Qt assumes for pixel-sized fonts.
            return max(1, int(round(pixels * 0.75)))
        return 12

    def _sync_text_to_ui(self, item: object) -> None:
        is_text = isinstance(item, TextLayerItem)
        for w in (
            self._txt_text,
            self._font_combo,
            self._spin_font_size,
            self._combo_fill_mode,
            self._btn_text_color,
            self._btn_grad_start,
            self._btn_grad_end,
            self._chk_shadow,
            self._chk_glow,
            self._btn_shadow_color,
            self._spin_shadow_blur,
            self._spin_shadow_dx,
            self._spin_shadow_dy,
            self._btn_glow_color,
            self._spin_glow_blur,
            self._chk_blur,
            self._spin_blur_radius,
            self._combo_text_effect,
            self._spin_effect_speed,
            self._spin_effect_amount,
            self._combo_presets,
            self._btn_save_preset,
            self._btn_delete_preset,
        ):
            w.setEnabled(is_text)
        if not is_text:
            return

        style = item.style()
        self._txt_text.blockSignals(True)
        self._font_combo.blockSignals(True)
        self._spin_font_size.blockSignals(True)
        self._combo_fill_mode.blockSignals(True)
        self._chk_shadow.blockSignals(True)
        self._chk_glow.blockSignals(True)
        self._spin_shadow_blur.blockSignals(True)
        self._spin_shadow_dx.blockSignals(True)
        self._spin_shadow_dy.blockSignals(True)
        self._spin_glow_blur.blockSignals(True)
        self._chk_blur.blockSignals(True)
        self._spin_blur_radius.blockSignals(True)
        self._combo_text_effect.blockSignals(True)
        self._spin_effect_speed.blockSignals(True)
        self._spin_effect_amount.blockSignals(True)
        try:
            self._txt_text.setText(item.text())
            family = str(style.font.family() or "").strip()
            family_idx = self._font_combo.findText(family)
            if family_idx >= 0:
                self._font_combo.setCurrentIndex(family_idx)
            self._spin_font_size.setValue(self._effective_point_size(style.font))
            self._combo_fill_mode.setCurrentIndex(0 if style.fill_mode == FillMode.SOLID else 1)
            self._chk_shadow.setChecked(style.shadow_enabled)
            self._chk_glow.setChecked(style.glow_enabled)
            self._spin_shadow_blur.setValue(float(style.shadow_blur))
            self._spin_shadow_dx.setValue(float(style.shadow_offset.x()))
            self._spin_shadow_dy.setValue(float(style.shadow_offset.y()))
            self._spin_glow_blur.setValue(float(style.glow_blur))
            self._chk_blur.setChecked(style.blur_enabled)
            self._spin_blur_radius.setValue(float(style.blur_radius))
            if style.effect == TextEffect.RAINBOW:
                self._combo_text_effect.setCurrentIndex(1)
            elif style.effect == TextEffect.WAVE:
                self._combo_text_effect.setCurrentIndex(2)
            elif style.effect == TextEffect.TYPEWRITER:
                self._combo_text_effect.setCurrentIndex(3)
            elif style.effect == TextEffect.SCRAMBLE:
                self._combo_text_effect.setCurrentIndex(4)
            elif style.effect == TextEffect.PULSE:
                self._combo_text_effect.setCurrentIndex(5)
            else:
                self._combo_text_effect.setCurrentIndex(0)
            self._spin_effect_speed.setValue(float(style.effect_speed))
            self._spin_effect_amount.setValue(float(style.effect_amount))
        finally:
            self._txt_text.blockSignals(False)
            self._font_combo.blockSignals(False)
            self._spin_font_size.blockSignals(False)
            self._combo_fill_mode.blockSignals(False)
            self._chk_shadow.blockSignals(False)
            self._chk_glow.blockSignals(False)
            self._spin_shadow_blur.blockSignals(False)
            self._spin_shadow_dx.blockSignals(False)
            self._spin_shadow_dy.blockSignals(False)
            self._spin_glow_blur.blockSignals(False)
            self._chk_blur.blockSignals(False)
            self._spin_blur_radius.blockSignals(False)
            self._combo_text_effect.blockSignals(False)
            self._spin_effect_speed.blockSignals(False)
            self._spin_effect_amount.blockSignals(False)

    def _apply_text_from_ui(self) -> None:
        item = self._selected_graphics_item()
        if not isinstance(item, TextLayerItem):
            return

        monitor_index = self._current_monitor_index()
        gid = id(item)
        if not self._undo_blocked and (
            self._pending_text_undo is None
            or self._pending_text_undo[0] != monitor_index
            or self._pending_text_undo[1] != gid
        ):
            try:
                self._pending_text_undo = (monitor_index, gid, str(item.text()), item.style())
            except Exception:
                self._pending_text_undo = None

        style = item.style()
        family = str(self._font_combo.currentText() or "").strip()
        font = QFont(family) if family else QFont()
        font.setPointSize(int(self._spin_font_size.value()))

        fill_mode = FillMode.SOLID if self._combo_fill_mode.currentIndex() == 0 else FillMode.GRADIENT
        effect = TextEffect.NONE
        if self._combo_text_effect.currentIndex() == 1:
            effect = TextEffect.RAINBOW
        elif self._combo_text_effect.currentIndex() == 2:
            effect = TextEffect.WAVE
        elif self._combo_text_effect.currentIndex() == 3:
            effect = TextEffect.TYPEWRITER
        elif self._combo_text_effect.currentIndex() == 4:
            effect = TextEffect.SCRAMBLE
        elif self._combo_text_effect.currentIndex() == 5:
            effect = TextEffect.PULSE
        new_style = TextStyle(
            font=font,
            fill_mode=fill_mode,
            color=style.color,
            gradient_start=style.gradient_start,
            gradient_end=style.gradient_end,
            effect=effect,
            effect_speed=float(self._spin_effect_speed.value()),
            effect_amount=float(self._spin_effect_amount.value()),
            shadow_enabled=self._chk_shadow.isChecked(),
            shadow_color=style.shadow_color,
            shadow_offset=QPointF(self._spin_shadow_dx.value(), self._spin_shadow_dy.value()),
            shadow_blur=float(self._spin_shadow_blur.value()),
            glow_enabled=self._chk_glow.isChecked(),
            glow_color=style.glow_color,
            glow_blur=float(self._spin_glow_blur.value()),
            blur_enabled=self._chk_blur.isChecked(),
            blur_radius=float(self._spin_blur_radius.value()),
        )
        item.set_text(self._txt_text.text())
        item.set_style(new_style)
        self._current_scene().refresh_text_animation()

        list_item = self._list_item_by_gid.get(id(item))
        if list_item:
            fallback = self._current_state().labels.get(gid, "Text")
            list_item.setText(self._layer_display_name(item, fallback))
        if not self._undo_blocked:
            self._text_undo_timer.start(400)

    def _pick_text_color(self, mode: str) -> None:
        item = self._selected_graphics_item()
        if not isinstance(item, TextLayerItem):
            return
        monitor_index = self._current_monitor_index()
        before_text = str(item.text())
        before_style = item.style()
        style = item.style()
        if mode == "solid":
            initial = style.color
        elif mode == "grad_start":
            initial = style.gradient_start
        elif mode == "grad_end":
            initial = style.gradient_end
        elif mode == "shadow":
            initial = style.shadow_color
        else:
            initial = style.glow_color
        color = QColorDialog.getColor(initial, self, "Pick Color", QColorDialog.ShowAlphaChannel)
        if not color.isValid():
            return
        if mode == "solid":
            new_style = TextStyle(**{**style.__dict__, "color": color})
        elif mode == "grad_start":
            new_style = TextStyle(**{**style.__dict__, "gradient_start": color})
        elif mode == "grad_end":
            new_style = TextStyle(**{**style.__dict__, "gradient_end": color})
        elif mode == "shadow":
            new_style = TextStyle(**{**style.__dict__, "shadow_color": color})
        else:
            new_style = TextStyle(**{**style.__dict__, "glow_color": color})
        item.set_style(new_style)
        if not self._undo_blocked:
            self._undo_stack.push(_SetTextCommand(self, monitor_index, item, before_text, before_style, str(item.text()), item.style()))

    def _apply_preset_to_text(self) -> None:
        item = self._selected_graphics_item()
        if not isinstance(item, TextLayerItem):
            return
        monitor_index = self._current_monitor_index()
        color = self._combo_presets.currentData()
        if not isinstance(color, QColor):
            return
        before_text = str(item.text())
        before_style = item.style()
        style = item.style()
        new_style = TextStyle(**{**style.__dict__, "color": QColor(color)})
        item.set_style(new_style)
        self._combo_fill_mode.blockSignals(True)
        try:
            self._combo_fill_mode.setCurrentIndex(0)
        finally:
            self._combo_fill_mode.blockSignals(False)
        if not self._undo_blocked:
            self._undo_stack.push(_SetTextCommand(self, monitor_index, item, before_text, before_style, str(item.text()), item.style()))

    def _save_preset(self) -> None:
        item = self._selected_graphics_item()
        if not isinstance(item, TextLayerItem):
            return
        style = item.style()
        color = QColorDialog.getColor(style.color, self, "Pick Preset Color", QColorDialog.ShowAlphaChannel)
        if not color.isValid():
            return
        suggested = f"Preset {len(self._color_presets.presets) + 1}"
        name, ok = QInputDialog.getText(self, "Save Color Preset", "Name:", text=suggested)
        if not ok:
            return
        name = name.strip() or suggested
        self._color_presets.add(name, color)
        self._refresh_presets()

    def _delete_preset(self) -> None:
        idx = self._combo_presets.currentIndex()
        if idx < 0:
            return
        self._color_presets.remove(idx)
        self._refresh_presets()
