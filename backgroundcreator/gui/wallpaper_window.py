from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QWidget, QVBoxLayout

from backgroundcreator.gui.editor_widget import EditorView
from backgroundcreator.gui.scene import EditorScene
from backgroundcreator.win32.wallpaper_host import attach_window_to_desktop


class WallpaperWindow(QWidget):
    def __init__(self, scene: EditorScene) -> None:
        super().__init__(None)
        self.setObjectName("wallpaperWindow")
        self._scene = scene
        self._view = EditorView(scene, keep_aspect=False, show_desktop_overlays=False)
        self._view.setObjectName("wallpaperView")
        self._view.setInteractive(False)
        self._view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setStyleSheet(
            """
            #wallpaperWindow { background: #000000; }
            QGraphicsView#wallpaperView { border: 0px; border-radius: 0px; background: #000000; }
            """
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self.setLayout(layout)

        self.setWindowTitle("BackgroundCreator Wallpaper")
        self.setWindowFlag(self.windowFlags() | self.windowFlags().FramelessWindowHint)

    def show_on_desktop(self, screen: QScreen) -> bool:
        geo: QRect = screen.geometry()
        self.setGeometry(geo)
        self._scene.setSceneRect(0, 0, geo.width(), geo.height())
        self._view.fitInView(self._scene.sceneRect(), Qt.IgnoreAspectRatio)
        self.show()
        self.raise_()
        self.lower()
        hwnd = int(self.winId())
        return attach_window_to_desktop(
            hwnd,
            x=int(geo.x()),
            y=int(geo.y()),
            width=int(geo.width()),
            height=int(geo.height()),
        )
