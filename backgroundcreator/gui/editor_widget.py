from __future__ import annotations

from math import floor

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QSizePolicy, QWidget, QVBoxLayout

from backgroundcreator.gui.scene import EditorScene


class EditorView(QGraphicsView):
    transform_committed = Signal(object, object, object)

    def __init__(self, scene: EditorScene, keep_aspect: bool = True, show_desktop_overlays: bool = True) -> None:
        super().__init__(scene)
        self._aspect_mode = Qt.KeepAspectRatio if keep_aspect else Qt.IgnoreAspectRatio
        self._grid_visible = False
        self._grid_size = 10.0
        self._grid_pen = QPen(QColor(255, 255, 255, 26))
        self._grid_pen.setCosmetic(True)
        self._desktop_overlays_visible = bool(show_desktop_overlays)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._wheel_item = None
        self._wheel_before = None
        self._wheel_timer = QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.timeout.connect(self._commit_wheel_transform)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), self._aspect_mode)

    def set_keep_aspect(self, keep_aspect: bool) -> None:
        self._aspect_mode = Qt.KeepAspectRatio if keep_aspect else Qt.IgnoreAspectRatio
        self.fitInView(self.sceneRect(), self._aspect_mode)

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = bool(visible)
        try:
            self.viewport().update()
        except Exception:
            pass

    def set_grid_size(self, size: float) -> None:
        try:
            self._grid_size = max(1.0, float(size))
        except Exception:
            self._grid_size = 10.0
        try:
            self.viewport().update()
        except Exception:
            pass

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        sr = self.sceneRect()

        if self._grid_visible:
            grid = float(self._grid_size)
            if grid > 1.0:
                left = max(float(rect.left()), float(sr.left()))
                right = min(float(rect.right()), float(sr.right()))
                top = max(float(rect.top()), float(sr.top()))
                bottom = min(float(rect.bottom()), float(sr.bottom()))
                if right > left and bottom > top:
                    ox = float(sr.left())
                    oy = float(sr.top())

                    x = ox + floor((left - ox) / grid) * grid
                    if x < left:
                        x += grid
                    y = oy + floor((top - oy) / grid) * grid
                    if y < top:
                        y += grid

                    painter.setPen(self._grid_pen)
                    xx = float(x)
                    while xx <= right:
                        painter.drawLine(xx, top, xx, bottom)
                        xx += grid
                    yy = float(y)
                    while yy <= bottom:
                        painter.drawLine(left, yy, right, yy)
                        yy += grid

        if self._desktop_overlays_visible:
            scn = self.scene()
            if isinstance(scn, EditorScene):
                try:
                    centers = scn.orbit_center_points()
                except Exception:
                    centers = {}
                if centers:
                    palette = [
                        QColor(255, 200, 80, 220),
                        QColor(80, 220, 255, 220),
                        QColor(255, 120, 220, 220),
                        QColor(120, 255, 120, 220),
                    ]
                    ids = sorted([str(k) for k in centers.keys()])
                    for i, cid in enumerate(ids):
                        p = centers.get(cid)
                        if p is None:
                            continue
                        col = palette[i % len(palette)]
                        painter.save()
                        pen = QPen(col)
                        pen.setCosmetic(True)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.setBrush(QColor(int(col.red()), int(col.green()), int(col.blue()), 40))
                        cx = float(p.x())
                        cy = float(p.y())
                        rr = 8.0
                        painter.drawEllipse(QRectF(float(cx - rr), float(cy - rr), float(rr * 2.0), float(rr * 2.0)))
                        painter.drawLine(float(cx - 18.0), float(cy), float(cx + 18.0), float(cy))
                        painter.drawLine(float(cx), float(cy - 18.0), float(cx), float(cy + 18.0))
                        painter.restore()

        if not self._desktop_overlays_visible:
            return
        scn = self.scene()
        if not isinstance(scn, EditorScene):
            return
        if not scn.desktop_preview_enabled():
            return
        work = scn.desktop_work_rect()
        if work is None:
            return
        screen = scn.desktop_screen_rect() or sr

        screen_left = float(screen.left())
        screen_top = float(screen.top())
        screen_right = float(screen.left() + screen.width())
        screen_bottom = float(screen.top() + screen.height())

        work_left = float(work.left())
        work_top = float(work.top())
        work_right = float(work.left() + work.width())
        work_bottom = float(work.top() + work.height())

        taskbars: list[QRectF] = []
        top_h = max(0.0, work_top - screen_top)
        bottom_h = max(0.0, screen_bottom - work_bottom)
        left_w = max(0.0, work_left - screen_left)
        right_w = max(0.0, screen_right - work_right)

        if top_h > 0.5:
            taskbars.append(QRectF(screen_left, screen_top, float(screen.width()), float(top_h)))
        if bottom_h > 0.5:
            taskbars.append(QRectF(screen_left, float(work_bottom), float(screen.width()), float(bottom_h)))
        if left_w > 0.5:
            taskbars.append(QRectF(screen_left, float(work_top), float(left_w), float(work.height())))
        if right_w > 0.5:
            taskbars.append(QRectF(float(work_right), float(work_top), float(right_w), float(work.height())))

        if taskbars:
            painter.save()
            pen = QPen(QColor(255, 255, 255, 140))
            pen.setStyle(Qt.DashLine)
            pen.setCosmetic(True)
            brush = QColor(0, 0, 0, 90)
            painter.setPen(pen)
            painter.setBrush(brush)
            for r in taskbars:
                painter.drawRect(r)
            painter.restore()

        margin = 24.0
        icon_size = 72.0
        spacing_x = 96.0
        spacing_y = 96.0

        max_x = (float(work.left() + work.width()) - margin - icon_size)
        max_y = (float(work.top() + work.height()) - margin - icon_size)

        painter.save()
        pen = QPen(QColor(255, 255, 255, 90))
        pen.setStyle(Qt.DotLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(255, 255, 255, 20))
        y = float(work.top() + margin)
        count = 0
        while y <= max_y and count < 60:
            x = float(work.left() + margin)
            while x <= max_x and count < 60:
                painter.drawRect(QRectF(float(x), float(y), float(icon_size), float(icon_size)))
                count += 1
                x += spacing_x
            y += spacing_y
        painter.restore()

    def _commit_wheel_transform(self) -> None:
        item = self._wheel_item
        before = self._wheel_before
        self._wheel_item = None
        self._wheel_before = None
        if item is None or before is None:
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
        if before != after:
            self.transform_committed.emit(item, before, after)

    def wheelEvent(self, event: QWheelEvent) -> None:
        item = self.scene().focusItem() or (self.scene().selectedItems()[0] if self.scene().selectedItems() else None)
        if item is not None and not (item.flags() & QGraphicsItem.ItemIsMovable):
            item = None
        if item is not None and self._wheel_before is None:
            self._wheel_item = item
            self._wheel_before = (
                float(item.pos().x()),
                float(item.pos().y()),
                float(item.scale()),
                float(item.rotation()),
            )

        if item is not None and (event.modifiers() & Qt.ControlModifier):
            delta = event.angleDelta().y()
            item.setRotation(item.rotation() + (5.0 if delta > 0 else -5.0))
            event.accept()
            self._wheel_timer.start(250)
            return
        if item is not None:
            delta = event.angleDelta().y()
            factor = 1.0 + (0.05 if delta > 0 else -0.05)
            item.setScale(max(0.05, item.scale() * factor))
            event.accept()
            self._wheel_timer.start(250)
            return
        super().wheelEvent(event)


class EditorWidget(QWidget):
    def __init__(self, scene_rect: QRectF) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)
        self.scene = EditorScene(scene_rect)
        self.view = EditorView(self.scene)
        self.scene.sceneRectChanged.connect(lambda _r: self.fit_to_scene())

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.setLayout(layout)
        self.fit_to_scene()

    def fit_to_scene(self) -> None:
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
