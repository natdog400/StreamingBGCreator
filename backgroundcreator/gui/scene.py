from __future__ import annotations

import math
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QObject, QRectF, Signal, QSizeF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QMovie, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QMessageBox

from backgroundcreator.gui.layers import ImageLayerItem, TextLayerItem, VideoLayerItem, ParticleLayerItem


ITEM_DATA_SOURCE_PATH = 0xBC01
ITEM_DATA_SOURCE_KIND = 0xBC02
ITEM_DATA_ANIM_MODE = 0xBC20
ITEM_DATA_ANIM_PAYLOAD = 0xBC21


@dataclass(frozen=True)
class BackgroundState:
    path: Path | None
    kind: str | None


class EditorScene(QGraphicsScene):
    selection_changed = Signal()
    background_changed = Signal(BackgroundState)
    item_transform_committed = Signal(object, object, object)

    def __init__(self, scene_rect: QRectF) -> None:
        super().__init__(scene_rect)
        self._background_item: QGraphicsItem | None = None
        self._background_movie: QMovie | None = None
        self._background_player: QMediaPlayer | None = None
        self._background_audio: QAudioOutput | None = None
        self._background_state = BackgroundState(path=None, kind=None)
        self._z_counter = 0.0
        self._text_id_counter = 1
        self._desktop_preview_enabled = False
        self._desktop_screen_rect: QRectF | None = None
        self._desktop_work_rect: QRectF | None = None
        self._snap_grid_enabled = False
        self._snap_grid_size = 10.0
        self._snap_center_enabled = False
        self._snap_center_threshold = 8.0
        self._taskbar_overlay: QGraphicsRectItem | None = None
        self._icon_overlays: list[QGraphicsRectItem] = []
        self._drag_item: QGraphicsItem | None = None
        self._drag_before: tuple[float, float, float, float] | None = None
        self._path_draw_enabled = False
        self._path_drawing = False
        self._path_points: list[QPointF] = []
        self._path_item: QGraphicsPathItem | None = None
        self._monitor_index: int | None = None
        self._monitor_global_rect: QRectF | None = None
        self._virtual_desktop_rect: QRectF | None = None
        self._scenes_registry: dict[int, "EditorScene"] | None = None
        self._global_paths: dict[str, list[QPointF]] = {"path1": []}
        self._global_path_segment_lengths: dict[str, list[float]] = {"path1": []}
        self._global_path_total_length: dict[str, float] = {"path1": 0.0}
        self._anim_avoid_taskbar = False
        self._orbit_center_pick_enabled = False
        self._orbit_center_pick_id = "center1"
        self._orbit_centers_point: dict[str, QPointF] = {}
        self._orbit_centers_norm: dict[str, tuple[float, float]] = {}
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_last = time.monotonic()
        self.selectionChanged.connect(self.selection_changed)
        self.sceneRectChanged.connect(lambda _r: self._resize_background_to_scene())

    def configure_virtual_desktop(
        self,
        monitor_index: int,
        monitor_global_rect: QRectF,
        virtual_desktop_rect: QRectF,
        scenes_registry: dict[int, "EditorScene"],
    ) -> None:
        self._monitor_index = int(monitor_index)
        self._monitor_global_rect = QRectF(monitor_global_rect)
        self._virtual_desktop_rect = QRectF(virtual_desktop_rect)
        self._scenes_registry = dict(scenes_registry)

    def monitor_global_rect(self) -> QRectF | None:
        if self._monitor_global_rect is None:
            return None
        return QRectF(self._monitor_global_rect)

    def set_global_paths(self, paths: dict[str, list[QPointF]]) -> None:
        norm_paths: dict[str, list[QPointF]] = {}
        for k, pts in (paths or {}).items():
            if not isinstance(k, str) or not k:
                continue
            norm: list[QPointF] = []
            for p in pts or []:
                try:
                    norm.append(QPointF(float(p.x()), float(p.y())))
                except Exception:
                    continue
            norm_paths[str(k)] = norm
        if "path1" not in norm_paths:
            norm_paths["path1"] = []
        self._global_paths = norm_paths
        self._rebuild_global_path_cache()
        self.refresh_animation()

    def set_global_path_points(self, points: list[QPointF]) -> None:
        self.set_global_paths({"path1": list(points or [])})

    def global_path_points(self, path_id: str = "path1") -> list[QPointF]:
        pid = str(path_id or "path1")
        pts = self._global_paths.get(pid) or []
        return [QPointF(float(p.x()), float(p.y())) for p in pts]

    def project_global_point_to_path(self, point: QPointF, path_id: str = "path1") -> float:
        pid = str(path_id or "path1")
        pts = self._global_paths.get(pid) or []
        if not pts or len(pts) < 2:
            return 0.0
        total_len = float(self._global_path_total_length.get(pid) or 0.0)
        if total_len <= 0.0:
            return 0.0

        px = float(point.x())
        py = float(point.y())
        best_s = 0.0
        best_d2 = float("inf")
        acc = 0.0
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            ax = float(a.x())
            ay = float(a.y())
            bx = float(b.x())
            by = float(b.y())
            vx = bx - ax
            vy = by - ay
            seg_len2 = (vx * vx) + (vy * vy)
            if seg_len2 <= 0.0:
                continue
            t = ((px - ax) * vx + (py - ay) * vy) / seg_len2
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            qx = ax + (vx * t)
            qy = ay + (vy * t)
            dx = px - qx
            dy = py - qy
            d2 = (dx * dx) + (dy * dy)
            if d2 < best_d2:
                seg_len = math.sqrt(seg_len2)
                best_d2 = d2
                best_s = acc + (seg_len * t)
            try:
                acc += float((self._global_path_segment_lengths.get(pid) or [])[i])
            except Exception:
                acc += math.sqrt(seg_len2)
        if best_s < 0.0:
            return 0.0
        if best_s > total_len:
            return float(total_len)
        return float(best_s)

    def _rebuild_global_path_cache(self) -> None:
        segs: dict[str, list[float]] = {}
        totals: dict[str, float] = {}
        for pid, pts in (self._global_paths or {}).items():
            lens: list[float] = []
            total = 0.0
            for i in range(len(pts) - 1):
                a = pts[i]
                b = pts[i + 1]
                dx = float(b.x() - a.x())
                dy = float(b.y() - a.y())
                seg = math.hypot(dx, dy)
                lens.append(float(seg))
                total += float(seg)
            segs[str(pid)] = lens
            totals[str(pid)] = float(total)
        if "path1" not in segs:
            segs["path1"] = []
            totals["path1"] = 0.0
        self._global_path_segment_lengths = segs
        self._global_path_total_length = totals

    def _global_path_point_at(self, s: float, path_id: str = "path1") -> QPointF | None:
        pid = str(path_id or "path1")
        pts = self._global_paths.get(pid) or []
        if not pts or len(pts) < 2:
            return None
        total = float(self._global_path_total_length.get(pid) or 0.0)
        if total <= 0.0:
            return QPointF(float(pts[0].x()), float(pts[0].y()))
        ss = float(s) % total
        acc = 0.0
        for i in range(len(pts) - 1):
            seg = 0.0
            try:
                seg = float((self._global_path_segment_lengths.get(pid) or [])[i])
            except Exception:
                a = pts[i]
                b = pts[i + 1]
                seg = math.hypot(float(b.x() - a.x()), float(b.y() - a.y()))
            if seg <= 0.0:
                continue
            if (acc + seg) >= ss:
                t = (ss - acc) / seg
                a = pts[i]
                b = pts[i + 1]
                x = float(a.x()) + ((float(b.x() - a.x())) * t)
                y = float(a.y()) + ((float(b.y() - a.y())) * t)
                return QPointF(float(x), float(y))
            acc += seg
        last = pts[-1]
        return QPointF(float(last.x()), float(last.y()))

    def _scene_for_global_point(self, p: QPointF) -> "EditorScene":
        registry = self._scenes_registry
        if not isinstance(registry, dict) or not registry:
            return self
        for sc in registry.values():
            r = getattr(sc, "_monitor_global_rect", None)
            if isinstance(r, QRectF) and r.contains(p):
                return sc
        best_sc = self
        best_d2 = float("inf")
        px = float(p.x())
        py = float(p.y())
        for sc in registry.values():
            r = getattr(sc, "_monitor_global_rect", None)
            if not isinstance(r, QRectF):
                continue
            cx = min(max(px, float(r.left())), float(r.right()))
            cy = min(max(py, float(r.top())), float(r.bottom()))
            dx = px - cx
            dy = py - cy
            d2 = (dx * dx) + (dy * dy)
            if d2 < best_d2:
                best_d2 = d2
                best_sc = sc
        return best_sc

    def background_state(self) -> BackgroundState:
        return self._background_state

    def clear_background(self) -> None:
        if self._background_item is not None:
            self.removeItem(self._background_item)
        try:
            if self._background_movie is not None:
                self._background_movie.stop()
        except Exception:
            pass
        try:
            if self._background_player is not None:
                self._background_player.stop()
        except Exception:
            pass
        self._background_item = None
        self._background_movie = None
        self._background_player = None
        self._background_audio = None
        self._background_state = BackgroundState(path=None, kind=None)
        self.background_changed.emit(self._background_state)

    def set_desktop_preview(self, enabled: bool, screen_rect: QRectF | None = None, work_rect: QRectF | None = None) -> None:
        self._desktop_preview_enabled = enabled
        self._clear_desktop_overlays()
        if enabled and screen_rect is not None:
            self.setSceneRect(screen_rect)
            self._resize_background_to_scene()
            self._desktop_screen_rect = QRectF(screen_rect)
            if work_rect is not None:
                self._desktop_work_rect = QRectF(work_rect)
            else:
                self._desktop_work_rect = None
        else:
            self._desktop_screen_rect = None
            self._desktop_work_rect = None
            self._clear_desktop_overlays()

    def desktop_preview_enabled(self) -> bool:
        return bool(self._desktop_preview_enabled)

    def desktop_work_rect(self) -> QRectF | None:
        if self._desktop_work_rect is None:
            return None
        return QRectF(self._desktop_work_rect)

    def desktop_screen_rect(self) -> QRectF | None:
        if self._desktop_screen_rect is None:
            return None
        return QRectF(self._desktop_screen_rect)

    def set_anim_avoid_taskbar(self, enabled: bool) -> None:
        self._anim_avoid_taskbar = bool(enabled)

    def _anim_bounds_rect(self) -> QRectF:
        if self._anim_avoid_taskbar and self._desktop_preview_enabled and self._desktop_work_rect is not None:
            return QRectF(self._desktop_work_rect)
        return self.sceneRect()

    def set_orbit_center_pick_enabled(self, enabled: bool, center_id: str = "center1") -> None:
        self._orbit_center_pick_enabled = bool(enabled)
        cid = str(center_id or "center1").strip() or "center1"
        self._orbit_center_pick_id = cid

    def set_orbit_center_point(self, point: QPointF | None, center_id: str = "center1") -> None:
        cid = str(center_id or "center1").strip() or "center1"
        if point is None:
            self._orbit_centers_point.pop(cid, None)
            self._orbit_centers_norm.pop(cid, None)
            try:
                self.update()
            except Exception:
                pass
            return
        try:
            p = QPointF(float(point.x()), float(point.y()))
        except Exception:
            return
        self._orbit_centers_point[cid] = p
        try:
            b = self._anim_bounds_rect()
            if float(b.width()) > 0.0 and float(b.height()) > 0.0:
                nx = (float(p.x()) - float(b.left())) / float(b.width())
                ny = (float(p.y()) - float(b.top())) / float(b.height())
                nx = max(0.0, min(1.0, float(nx)))
                ny = max(0.0, min(1.0, float(ny)))
                self._orbit_centers_norm[cid] = (float(nx), float(ny))
            else:
                self._orbit_centers_norm.pop(cid, None)
        except Exception:
            self._orbit_centers_norm.pop(cid, None)
        try:
            self.update()
        except Exception:
            pass

    def orbit_center_point(self, center_id: str = "center1") -> QPointF | None:
        cid = str(center_id or "center1").strip() or "center1"
        norm = self._orbit_centers_norm.get(cid)
        if norm is not None:
            try:
                nx, ny = norm
                b = self._anim_bounds_rect()
                return QPointF(float(b.left() + (float(nx) * float(b.width()))), float(b.top() + (float(ny) * float(b.height()))))
            except Exception:
                pass
        p = self._orbit_centers_point.get(cid)
        if p is None:
            return None
        return QPointF(float(p.x()), float(p.y()))

    def orbit_center_points(self) -> dict[str, QPointF]:
        ids = set(self._orbit_centers_point.keys()) | set(self._orbit_centers_norm.keys())
        out: dict[str, QPointF] = {}
        for cid in ids:
            p = self.orbit_center_point(cid)
            if p is not None:
                out[str(cid)] = p
        return out

    def orbit_center_norms(self) -> dict[str, tuple[float, float]]:
        out: dict[str, tuple[float, float]] = {}
        for k, v in (self._orbit_centers_norm or {}).items():
            if not isinstance(k, str) or not k:
                continue
            try:
                out[str(k)] = (float(v[0]), float(v[1]))
            except Exception:
                continue
        return out

    def set_orbit_center_norms(self, norms: dict[str, object]) -> None:
        if not isinstance(norms, dict):
            return
        cleaned: dict[str, tuple[float, float]] = {}
        for cid, v in norms.items():
            if not isinstance(cid, str) or not cid:
                continue
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                try:
                    nx = max(0.0, min(1.0, float(v[0])))
                    ny = max(0.0, min(1.0, float(v[1])))
                except Exception:
                    continue
                cleaned[str(cid)] = (float(nx), float(ny))
        self._orbit_centers_norm = cleaned
        try:
            self.update()
        except Exception:
            pass

    def set_background(self, file_path: str) -> None:
        path = Path(file_path)
        ext = path.suffix.lower()

        self.clear_background()
        self.setSceneRect(self.sceneRect())

        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            pix = QPixmap(str(path))
            item = QGraphicsPixmapItem(pix)
            item.setZValue(-10_000)
            item.setFlags(QGraphicsItem.GraphicsItemFlag(0))
            self._background_item = item
            self.addItem(item)
            self._stretch_pixmap_item(item)
            self._background_state = BackgroundState(path=path, kind="image")

        elif ext in {".gif"}:
            movie = QMovie(str(path))
            movie.setCacheMode(QMovie.CacheAll)
            pix = QPixmap()
            item = QGraphicsPixmapItem(pix)
            item.setZValue(-10_000)
            item.setFlags(QGraphicsItem.GraphicsItemFlag(0))
            self._background_item = item
            self._background_movie = movie
            self.addItem(item)

            def update_frame() -> None:
                if self._background_item is None or self._background_movie is None:
                    return
                frame = self._background_movie.currentPixmap()
                if isinstance(self._background_item, QGraphicsPixmapItem):
                    self._background_item.setPixmap(frame)
                    self._stretch_pixmap_item(self._background_item)

            movie.frameChanged.connect(lambda _i: update_frame())
            movie.start()
            self._background_state = BackgroundState(path=path, kind="gif")

        else:
            abs_path = path.resolve()
            if not abs_path.exists() or not abs_path.is_file():
                print(f"ERROR: Video background file not found: {abs_path}", file=sys.stderr, flush=True)
                return

            url = QUrl.fromLocalFile(str(abs_path))
            print(f"DEBUG: Loading video background from: {abs_path}", file=sys.stderr, flush=True)
            print(f"DEBUG: URL: {url.toString()}", file=sys.stderr, flush=True)
            print(f"DEBUG: Encoded URL: {url.toEncoded()}", file=sys.stderr, flush=True)
            print(f"DEBUG: URL Valid: {url.isValid()}", file=sys.stderr, flush=True)

            video_item = QGraphicsVideoItem()
            video_item.setZValue(-10_000)
            video_item.setSize(QSizeF(self.sceneRect().size()))
            video_item.setPos(self.sceneRect().topLeft())
            try:
                video_item.setAspectRatioMode(Qt.KeepAspectRatio)
            except Exception:
                pass

            player = QMediaPlayer()
            audio = QAudioOutput()
            player.setAudioOutput(audio)
            player.setVideoOutput(video_item)
            try:
                audio.setMuted(True)
            except Exception:
                pass
            
            def on_error():
                err_str = player.errorString()
                print(f"ERROR: MediaPlayer error: {err_str}", file=sys.stderr, flush=True)
                print(f"ERROR: MediaPlayer error code: {player.error()}", file=sys.stderr, flush=True)
                try:
                    mb = QMessageBox()
                    mb.setIcon(QMessageBox.Icon.Warning)
                    mb.setWindowTitle("Background Video Error")
                    mb.setText("Could not open background media.")
                    mb.setInformativeText(str(err_str or "Unknown error"))
                    mb.exec()
                except Exception:
                    pass

            player.errorOccurred.connect(on_error)
            player.setSource(url)
            player.setLoops(QMediaPlayer.Loops.Infinite)
            player.play()

            self._background_item = video_item
            self._background_player = player
            self._background_audio = audio
            self.addItem(video_item)
            self._background_state = BackgroundState(path=path, kind="video")

        self.background_changed.emit(self._background_state)

    def set_snap_grid(self, enabled: bool, grid_size: float | None = None) -> None:
        self._snap_grid_enabled = bool(enabled)
        if grid_size is not None:
            try:
                self._snap_grid_size = max(1.0, float(grid_size))
            except Exception:
                pass

    def set_snap_center(self, enabled: bool, threshold: float | None = None) -> None:
        self._snap_center_enabled = bool(enabled)
        if threshold is not None:
            try:
                self._snap_center_threshold = max(0.0, float(threshold))
            except Exception:
                pass

    def snap_position(self, item: QGraphicsItem, proposed_pos: QPointF) -> QPointF:
        pos = QPointF(float(proposed_pos.x()), float(proposed_pos.y()))
        if not self._snap_grid_enabled and not self._snap_center_enabled:
            return pos

        scene_rect = self.sceneRect()
        if self._snap_grid_enabled:
            grid = float(self._snap_grid_size)
            ox = float(scene_rect.left())
            oy = float(scene_rect.top())
            x = ox + round((pos.x() - ox) / grid) * grid
            y = oy + round((pos.y() - oy) / grid) * grid
            pos = QPointF(float(x), float(y))

        if self._snap_center_enabled:
            try:
                current = item.pos()
                dx = float(pos.x() - current.x())
                dy = float(pos.y() - current.y())
                rect = item.sceneBoundingRect().translated(dx, dy)
                sc = scene_rect.center()
                c = rect.center()
                tx = float(sc.x() - c.x())
                ty = float(sc.y() - c.y())
                thresh = float(self._snap_center_threshold)
                if abs(tx) <= thresh:
                    pos.setX(float(pos.x() + tx))
                if abs(ty) <= thresh:
                    pos.setY(float(pos.y() + ty))
            except Exception:
                pass

        return pos

    def refresh_text_animation(self) -> None:
        self.refresh_animation()

    def refresh_animation(self) -> None:
        any_anim = False
        try:
            for it in self.items():
                if isinstance(it, ParticleLayerItem):
                    any_anim = True
                    break
                if isinstance(it, TextLayerItem) and it.needs_animation():
                    any_anim = True
                    break
                try:
                    mode = it.data(ITEM_DATA_ANIM_MODE)
                except Exception:
                    mode = None
                if isinstance(mode, str) and mode:
                    any_anim = True
                    break
        except Exception:
            any_anim = False
        if any_anim:
            if not self._anim_timer.isActive():
                self._anim_last = time.monotonic()
                self._anim_timer.start()
        else:
            if self._anim_timer.isActive():
                self._anim_timer.stop()

    def _on_anim_tick(self) -> None:
        now = time.monotonic()
        dt = max(0.0, float(now - self._anim_last))
        self._anim_last = now
        any_anim = False
        try:
            for it in self.items():
                if isinstance(it, ParticleLayerItem):
                    any_anim = True
                    it.advance_time(dt)
                    it.update()
                    continue

                if isinstance(it, TextLayerItem) and it.needs_animation():
                    any_anim = True
                    it.advance_time(dt)
                    it.update()

                try:
                    mode = it.data(ITEM_DATA_ANIM_MODE)
                    payload = it.data(ITEM_DATA_ANIM_PAYLOAD)
                except Exception:
                    mode = None
                    payload = None
                if not isinstance(mode, str) or not mode:
                    continue
                if not isinstance(payload, dict):
                    payload = {}

                if mode == "orbit_edge":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        direction = float(payload.get("dir", payload.get("direction", 1.0)))
                    except Exception:
                        direction = 1.0

                    try:
                        br = it.sceneBoundingRect()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue

                    pad_x = float(padding) + float(half_w)
                    pad_y = float(padding) + float(half_h)
                    rect = self._anim_bounds_rect().adjusted(pad_x, pad_y, -pad_x, -pad_y)
                    w = float(rect.width())
                    h = float(rect.height())
                    if w <= 0.0 or h <= 0.0:
                        continue
                    perim = (2.0 * w) + (2.0 * h)
                    if perim <= 0.0:
                        continue

                    t = (t + (direction * speed * dt)) % perim
                    payload["t"] = float(t)

                    left = float(rect.left())
                    top = float(rect.top())
                    right = float(rect.right())
                    bottom = float(rect.bottom())

                    if t <= w:
                        cx = left + t
                        cy = top
                    elif t <= (w + h):
                        cx = right
                        cy = top + (t - w)
                    elif t <= (w + h + w):
                        cx = right - (t - (w + h))
                        cy = bottom
                    else:
                        cx = left
                        cy = bottom - (t - (w + h + w))

                    try:
                        before_center = br.center()
                        dx = float(cx - float(before_center.x()))
                        dy = float(cy - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "orbit_center":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 0.0))
                        ang = float(payload.get("ang", 0.0))
                        desired_r = float(payload.get("desired_r", payload.get("r", 0.0)))
                        r = float(payload.get("r", 0.0))
                        use_scene_center = bool(payload.get("use_scene_center", False))
                    except Exception:
                        continue
                    if speed <= 0.0:
                        continue
                    try:
                        direction = float(payload.get("dir", payload.get("direction", 1.0)))
                    except Exception:
                        direction = 1.0

                    try:
                        br = it.sceneBoundingRect()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue

                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w)
                    max_x = float(sr.right()) - float(half_w)
                    min_y = float(sr.top()) + float(half_h)
                    max_y = float(sr.bottom()) - float(half_h)
                    if max_x <= min_x or max_y <= min_y:
                        continue
                    if use_scene_center:
                        try:
                            center_id = str(payload.get("center") or "center1")
                        except Exception:
                            center_id = "center1"
                        c = self.orbit_center_point(center_id)
                        if c is None:
                            continue
                        cx0 = float(c.x())
                        cy0 = float(c.y())
                    else:
                        cx0 = float(payload.get("cx", 0.0))
                        cy0 = float(payload.get("cy", 0.0))

                    max_r = max(0.0, min(float(max_x - cx0), float(cx0 - min_x), float(max_y - cy0), float(cy0 - min_y)))
                    if max_r <= 0.0:
                        continue

                    if desired_r <= 0.0:
                        desired_r = float(max_r)
                    r = min(float(desired_r), float(max_r))
                    if r <= 0.0:
                        continue

                    ang = float(ang) + (direction * (float(speed) / float(r)) * float(dt))
                    if ang > (2.0 * math.pi) or ang < (-2.0 * math.pi):
                        try:
                            ang = float(math.fmod(ang, 2.0 * math.pi))
                        except Exception:
                            pass
                    payload["ang"] = float(ang)
                    payload["r"] = float(r)
                    payload["desired_r"] = float(desired_r)

                    tx = float(cx0) + (math.cos(float(ang)) * float(r))
                    ty = float(cy0) + (math.sin(float(ang)) * float(r))
                    try:
                        before_center = br.center()
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "slide":
                    any_anim = True
                    try:
                        axis = str(payload.get("axis", "x"))
                        speed = float(payload.get("speed", 0.0))
                        mn = float(payload.get("min", 0.0))
                        mx = float(payload.get("max", 0.0))
                        val = float(payload.get("val", mn))
                        fixed = float(payload.get("fixed", 0.0))
                        direction = float(payload.get("dir", 1.0))
                    except Exception:
                        continue
                    if mx <= mn or speed <= 0.0:
                        continue

                    try:
                        br = it.sceneBoundingRect()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue

                    sr = self._anim_bounds_rect()
                    if axis == "y":
                        mn = max(float(mn), float(sr.top()) + float(half_h))
                        mx = min(float(mx), float(sr.bottom()) - float(half_h))
                        fixed = max(float(sr.left()) + float(half_w), min(float(sr.right()) - float(half_w), float(fixed)))
                    else:
                        mn = max(float(mn), float(sr.left()) + float(half_w))
                        mx = min(float(mx), float(sr.right()) - float(half_w))
                        fixed = max(float(sr.top()) + float(half_h), min(float(sr.bottom()) - float(half_h), float(fixed)))
                    if mx <= mn:
                        continue

                    val = max(float(mn), min(float(mx), float(val)))
                    val = val + (direction * speed * dt)
                    while val > mx:
                        overshoot = val - mx
                        val = mx - overshoot
                        direction = -direction
                    while val < mn:
                        overshoot = mn - val
                        val = mn + overshoot
                        direction = -direction

                    payload["val"] = float(val)
                    payload["dir"] = float(direction)

                    try:
                        before_center = br.center()
                        if axis == "y":
                            cx = float(fixed)
                            cy = float(val)
                        else:
                            cx = float(val)
                            cy = float(fixed)
                        dx = float(cx - float(before_center.x()))
                        dy = float(cy - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "bounce":
                    any_anim = True
                    try:
                        vx = float(payload.get("vx", 0.0))
                        vy = float(payload.get("vy", 0.0))
                    except Exception:
                        continue
                    if vx == 0.0 and vy == 0.0:
                        continue

                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        cx0 = float(before_center.x())
                        cy0 = float(before_center.y())
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue

                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w)
                    max_x = float(sr.right()) - float(half_w)
                    min_y = float(sr.top()) + float(half_h)
                    max_y = float(sr.bottom()) - float(half_h)
                    if max_x <= min_x or max_y <= min_y:
                        continue

                    cx = float(cx0) + (float(vx) * float(dt))
                    cy = float(cy0) + (float(vy) * float(dt))
                    while cx > max_x:
                        overshoot = cx - max_x
                        cx = max_x - overshoot
                        vx = -vx
                    while cx < min_x:
                        overshoot = min_x - cx
                        cx = min_x + overshoot
                        vx = -vx
                    while cy > max_y:
                        overshoot = cy - max_y
                        cy = max_y - overshoot
                        vy = -vy
                    while cy < min_y:
                        overshoot = min_y - cy
                        cy = min_y + overshoot
                        vy = -vy

                    payload["vx"] = float(vx)
                    payload["vy"] = float(vy)
                    try:
                        dx = float(cx - float(cx0))
                        dy = float(cy - float(cy0))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "follow_path":
                    any_anim = True
                    if self._monitor_global_rect is None:
                        continue
                    try:
                        path_id = str(payload.get("path") or "path1")
                    except Exception:
                        path_id = "path1"
                    pts = self._global_paths.get(path_id) or []
                    total_len = float(self._global_path_total_length.get(path_id) or 0.0)
                    if len(pts) < 2 or total_len <= 0.0:
                        continue
                    try:
                        speed = float(payload.get("speed", 0.0))
                        s = float(payload.get("s", 0.0))
                        off = payload.get("offset", (0.0, 0.0))
                        if isinstance(off, (list, tuple)) and len(off) >= 2:
                            ox = float(off[0])
                            oy = float(off[1])
                        elif isinstance(off, QPointF):
                            ox = float(off.x())
                            oy = float(off.y())
                        else:
                            ox = 0.0
                            oy = 0.0
                    except Exception:
                        continue
                    if speed <= 0.0:
                        continue
                    s = (s + (speed * dt)) % float(total_len)
                    payload["s"] = float(s)

                    base = self._global_path_point_at(s, path_id=path_id)
                    if base is None:
                        continue
                    gp = QPointF(float(base.x()) + float(ox), float(base.y()) + float(oy))
                    target_scene = self._scene_for_global_point(gp)
                    r = getattr(target_scene, "_monitor_global_rect", None)
                    if not isinstance(r, QRectF):
                        r = self._monitor_global_rect
                        target_scene = self
                    local_target = QPointF(float(gp.x() - float(r.left())), float(gp.y() - float(r.top())))

                    moved_scene = False
                    if target_scene is not self:
                        try:
                            was_selected = bool(it.isSelected())
                        except Exception:
                            was_selected = False
                        try:
                            self.removeItem(it)
                            target_scene.addItem(it)
                            target_scene.refresh_animation()
                            moved_scene = True
                        except Exception:
                            target_scene = self
                            r = self._monitor_global_rect
                            local_target = QPointF(float(gp.x() - float(r.left())), float(gp.y() - float(r.top())))
                        else:
                            try:
                                it.setSelected(bool(was_selected))
                            except Exception:
                                pass

                    try:
                        before_center = it.sceneBoundingRect().center()
                        dx = float(local_target.x() - float(before_center.x()))
                        dy = float(local_target.y() - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass
                    if moved_scene:
                        try:
                            self.refresh_animation()
                        except Exception:
                            pass

                elif mode == "drift":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        angle = float(payload.get("angle", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    ang = math.radians(float(angle))
                    bx = float(bx) + (math.cos(ang) * float(speed) * float(dt))
                    by = float(by) + (math.sin(ang) * float(speed) * float(dt))

                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        if bx > max_x:
                            bx = float(min_x)
                        elif bx < min_x:
                            bx = float(max_x)
                    if max_y > min_y:
                        if by > max_y:
                            by = float(min_y)
                        elif by < min_y:
                            by = float(max_y)

                    payload["t"] = float(t)
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(bx - float(before_center.x()))
                        dy = float(by - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "zigzag":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        angle = float(payload.get("angle", 0.0))
                        amp = float(payload.get("amp", 20.0))
                        freq = float(payload.get("freq", 1.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue

                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        bx = float(base[0])
                        by = float(base[1])
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t += dt
                    ang_rad = math.radians(angle)
                    bx += math.cos(ang_rad) * speed * dt
                    by += math.sin(ang_rad) * speed * dt

                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + half_w + padding
                    max_x = float(sr.right()) - half_w - padding
                    min_y = float(sr.top()) + half_h + padding
                    max_y = float(sr.bottom()) - half_h - padding
                    
                    if max_x > min_x:
                        if bx > max_x: bx = min_x
                        elif bx < min_x: bx = max_x
                    if max_y > min_y:
                        if by > max_y: by = min_y
                        elif by < min_y: by = max_y

                    perp_ang = ang_rad + (math.pi / 2.0)
                    offset = math.sin(t * freq * math.pi * 2.0) * amp
                    tx = bx + (math.cos(perp_ang) * offset)
                    ty = by + (math.sin(perp_ang) * offset)

                    payload["t"] = float(t)
                    payload["base"] = [float(bx), float(by)]
                    
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass



                elif mode == "figure8":
                    any_anim = True
                    try:
                        amp_x = float(payload.get("amp_x", payload.get("ax", 0.0)))
                        amp_y = float(payload.get("amp_y", payload.get("ay", 0.0)))
                        padding = float(payload.get("padding", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    ox = math.sin((float(w) * float(t)) + float(ph)) * float(amp_x)
                    oy = math.sin((2.0 * float(w) * float(t)) + float(ph)) * float(amp_y)
                    tx = float(bx) + float(ox)
                    ty = float(by) + float(oy)
                    payload["t"] = float(t)
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        tx = max(float(min_x), min(float(max_x), float(tx)))
                        bx = max(float(min_x), min(float(max_x), float(bx)))
                    if max_y > min_y:
                        ty = max(float(min_y), min(float(max_y), float(ty)))
                        by = max(float(min_y), min(float(max_y), float(by)))
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "lissajous":
                    any_anim = True
                    try:
                        amp_x = float(payload.get("amp_x", payload.get("ax", 0.0)))
                        amp_y = float(payload.get("amp_y", payload.get("ay", 0.0)))
                        padding = float(payload.get("padding", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        rate2 = float(payload.get("rate2", payload.get("freq2", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    w1 = 2.0 * math.pi * float(rate)
                    w2 = 2.0 * math.pi * float(rate2 if rate2 > 0.0 else rate)
                    ph = math.radians(float(phase))
                    ox = math.sin((float(w1) * float(t)) + float(ph)) * float(amp_x)
                    oy = math.sin(float(w2) * float(t)) * float(amp_y)
                    tx = float(bx) + float(ox)
                    ty = float(by) + float(oy)
                    payload["t"] = float(t)
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        tx = max(float(min_x), min(float(max_x), float(tx)))
                        bx = max(float(min_x), min(float(max_x), float(bx)))
                    if max_y > min_y:
                        ty = max(float(min_y), min(float(max_y), float(ty)))
                        by = max(float(min_y), min(float(max_y), float(by)))
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "pendulum":
                    any_anim = True
                    try:
                        length = float(payload.get("len", 0.0))
                        angle_range = float(payload.get("range", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    theta = math.sin((float(w) * float(t)) + float(ph)) * math.radians(float(angle_range))
                    ox = math.sin(float(theta)) * float(length)
                    oy = (math.cos(float(theta)) * float(length)) - float(length)
                    tx = float(bx) + float(ox)
                    ty = float(by) + float(oy)
                    payload["t"] = float(t)
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        tx = max(float(min_x), min(float(max_x), float(tx)))
                        bx = max(float(min_x), min(float(max_x), float(bx)))
                    if max_y > min_y:
                        ty = max(float(min_y), min(float(max_y), float(ty)))
                        by = max(float(min_y), min(float(max_y), float(by)))
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "wander":
                    any_anim = True
                    try:
                        max_speed = float(payload.get("speed", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        jitter = float(payload.get("jitter", payload.get("noise", 0.0)))
                        vx = float(payload.get("vx", 0.0))
                        vy = float(payload.get("vy", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    ax = (random.random() - 0.5) * 2.0 * float(jitter)
                    ay = (random.random() - 0.5) * 2.0 * float(jitter)
                    vx = float(vx) + (float(ax) * float(dt))
                    vy = float(vy) + (float(ay) * float(dt))
                    vmag = math.hypot(float(vx), float(vy))
                    if float(max_speed) > 0.0 and float(vmag) > float(max_speed):
                        scale = float(max_speed) / float(vmag) if float(vmag) > 0.0 else 0.0
                        vx = float(vx) * float(scale)
                        vy = float(vy) * float(scale)

                    bx = float(bx) + (float(vx) * float(dt))
                    by = float(by) + (float(vy) * float(dt))

                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        if bx > max_x:
                            bx = float(max_x)
                            vx = -float(vx)
                        elif bx < min_x:
                            bx = float(min_x)
                            vx = -float(vx)
                    if max_y > min_y:
                        if by > max_y:
                            by = float(max_y)
                            vy = -float(vy)
                        elif by < min_y:
                            by = float(min_y)
                            vy = -float(vy)

                    payload["t"] = float(t)
                    payload["vx"] = float(vx)
                    payload["vy"] = float(vy)
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(bx - float(before_center.x()))
                        dy = float(by - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "shake":
                    any_anim = True
                    try:
                        amp_x = float(payload.get("amp_x", payload.get("ax", 0.0)))
                        amp_y = float(payload.get("amp_y", payload.get("ay", 0.0)))
                        padding = float(payload.get("padding", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    ox = math.sin((float(w) * float(t)) + float(ph)) * float(amp_x)
                    oy = math.sin((1.37 * float(w) * float(t)) + float(ph) + 1.0) * float(amp_y)
                    tx = float(bx) + float(ox)
                    ty = float(by) + float(oy)
                    payload["t"] = float(t)
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        tx = max(float(min_x), min(float(max_x), float(tx)))
                        bx = max(float(min_x), min(float(max_x), float(bx)))
                    if max_y > min_y:
                        ty = max(float(min_y), min(float(max_y), float(ty)))
                        by = max(float(min_y), min(float(max_y), float(by)))
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "spin":
                    any_anim = True
                    try:
                        rot_speed = float(payload.get("rot_speed", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    if rot_speed == 0.0:
                        continue
                    t = float(t) + float(dt)
                    try:
                        base_rot = float(payload.get("base_rot", it.rotation()))
                    except Exception:
                        base_rot = 0.0
                    rot = float(base_rot) + (float(rot_speed) * float(t))
                    payload["t"] = float(t)
                    try:
                        it.setRotation(float(rot))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "wobble":
                    any_anim = True
                    try:
                        rot_amp = float(payload.get("rot_amp", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    t = float(t) + float(dt)
                    try:
                        base_rot = float(payload.get("base_rot", it.rotation()))
                    except Exception:
                        base_rot = 0.0
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    rot = float(base_rot) + (math.sin((float(w) * float(t)) + float(ph)) * float(rot_amp))
                    payload["t"] = float(t)
                    try:
                        it.setRotation(float(rot))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "tumble":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        angle = float(payload.get("angle", 0.0))
                        rot_speed = float(payload.get("rot_speed", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    ang = math.radians(float(angle))
                    bx = float(bx) + (math.cos(ang) * float(speed) * float(dt))
                    by = float(by) + (math.sin(ang) * float(speed) * float(dt))

                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        if bx > max_x:
                            bx = float(min_x)
                        elif bx < min_x:
                            bx = float(max_x)
                    if max_y > min_y:
                        if by > max_y:
                            by = float(min_y)
                        elif by < min_y:
                            by = float(max_y)

                    try:
                        base_rot = float(payload.get("base_rot", it.rotation()))
                    except Exception:
                        base_rot = 0.0
                    rot = float(base_rot) + (float(rot_speed) * float(t))

                    payload["t"] = float(t)
                    payload["base"] = [float(bx), float(by)]
                    try:
                        it.setRotation(float(rot))
                    except Exception:
                        pass
                    try:
                        dx = float(bx - float(before_center.x()))
                        dy = float(by - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "pulse":
                    any_anim = True
                    try:
                        scale_min = float(payload.get("scale_min", 1.0))
                        scale_max = float(payload.get("scale_max", 1.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    s = (math.sin((float(w) * float(t)) + float(ph)) + 1.0) / 2.0
                    scale = float(scale_min) + (float(s) * (float(scale_max) - float(scale_min)))
                    payload["t"] = float(t)
                    try:
                        it.setScale(float(scale))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "pop":
                    any_anim = True
                    try:
                        scale_min = float(payload.get("scale_min", 1.0))
                        scale_max = float(payload.get("scale_max", 1.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    if rate <= 0.0:
                        continue
                    t = float(t) + float(dt)
                    p = (float(rate) * float(t)) + (float(phase) / 360.0)
                    p = float(p) - math.floor(float(p))
                    tri = 1.0 - (2.0 * abs(float(p) - 0.5))
                    scale = float(scale_min) + (float(tri) * (float(scale_max) - float(scale_min)))
                    payload["t"] = float(t)
                    try:
                        it.setScale(float(scale))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode in ("fade_in", "fade_out"):
                    any_anim = True
                    try:
                        opacity_min = float(payload.get("opacity_min", 0.0))
                        opacity_max = float(payload.get("opacity_max", 1.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    s = (math.sin((float(w) * float(t)) + float(ph)) + 1.0) / 2.0
                    if mode == "fade_out":
                        s = 1.0 - float(s)
                    opacity = float(opacity_min) + (float(s) * (float(opacity_max) - float(opacity_min)))
                    payload["t"] = float(t)
                    try:
                        it.setOpacity(float(opacity))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "blink":
                    any_anim = True
                    try:
                        opacity_min = float(payload.get("opacity_min", 0.0))
                        opacity_max = float(payload.get("opacity_max", 1.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    on = math.sin((float(w) * float(t)) + float(ph)) >= 0.0
                    opacity = float(opacity_max) if on else float(opacity_min)
                    payload["t"] = float(t)
                    try:
                        it.setOpacity(float(opacity))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "float_bob":
                    any_anim = True
                    try:
                        amp_y = float(payload.get("amp_y", payload.get("ay", 0.0)))
                        padding = float(payload.get("padding", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())
                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    ty = float(by) + (math.sin((float(w) * float(t)) + float(ph)) * float(amp_y))
                    tx = float(bx)
                    payload["t"] = float(t)
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        tx = max(float(min_x), min(float(max_x), float(tx)))
                        bx = max(float(min_x), min(float(max_x), float(bx)))
                    if max_y > min_y:
                        ty = max(float(min_y), min(float(max_y), float(ty)))
                        by = max(float(min_y), min(float(max_y), float(by)))
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "hover_wobble":
                    any_anim = True
                    try:
                        amp_y = float(payload.get("amp_y", payload.get("ay", 0.0)))
                        rot_amp = float(payload.get("rot_amp", 0.0))
                        padding = float(payload.get("padding", 0.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        try:
                            bx = float(base[0])
                            by = float(base[1])
                        except Exception:
                            bx = float(before_center.x())
                            by = float(before_center.y())
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())
                    t = float(t) + float(dt)
                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    ty = float(by) + (math.sin((float(w) * float(t)) + float(ph)) * float(amp_y))
                    tx = float(bx)
                    try:
                        base_rot = float(payload.get("base_rot", it.rotation()))
                    except Exception:
                        base_rot = 0.0
                    rot = float(base_rot) + (math.sin((float(w) * float(t)) + float(ph)) * float(rot_amp))
                    payload["t"] = float(t)
                    try:
                        it.setRotation(float(rot))
                    except Exception:
                        pass
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w) + float(padding)
                    max_x = float(sr.right()) - float(half_w) - float(padding)
                    min_y = float(sr.top()) + float(half_h) + float(padding)
                    max_y = float(sr.bottom()) - float(half_h) - float(padding)
                    if max_x > min_x:
                        tx = max(float(min_x), min(float(max_x), float(tx)))
                        bx = max(float(min_x), min(float(max_x), float(bx)))
                    if max_y > min_y:
                        ty = max(float(min_y), min(float(max_y), float(ty)))
                        by = max(float(min_y), min(float(max_y), float(by)))
                    payload["base"] = [float(bx), float(by)]
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "orbit_pulse":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 0.0))
                        ang = float(payload.get("ang", 0.0))
                        desired_r = float(payload.get("desired_r", payload.get("r", 0.0)))
                        r = float(payload.get("r", 0.0))
                        use_scene_center = bool(payload.get("use_scene_center", False))
                        scale_min = float(payload.get("scale_min", 1.0))
                        scale_max = float(payload.get("scale_max", 1.0))
                        rate = float(payload.get("rate", payload.get("freq", 0.0)))
                        phase = float(payload.get("phase", 0.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    if speed <= 0.0:
                        continue
                    try:
                        direction = float(payload.get("dir", payload.get("direction", 1.0)))
                    except Exception:
                        direction = 1.0
                    try:
                        br = it.sceneBoundingRect()
                        half_w = float(br.width()) / 2.0
                        half_h = float(br.height()) / 2.0
                    except Exception:
                        continue
                    sr = self._anim_bounds_rect()
                    min_x = float(sr.left()) + float(half_w)
                    max_x = float(sr.right()) - float(half_w)
                    min_y = float(sr.top()) + float(half_h)
                    max_y = float(sr.bottom()) - float(half_h)
                    if max_x <= min_x or max_y <= min_y:
                        continue
                    if use_scene_center:
                        try:
                            center_id = str(payload.get("center") or "center1")
                        except Exception:
                            center_id = "center1"
                        c = self.orbit_center_point(center_id)
                        if c is None:
                            continue
                        cx0 = float(c.x())
                        cy0 = float(c.y())
                    else:
                        cx0 = float(payload.get("cx", 0.0))
                        cy0 = float(payload.get("cy", 0.0))

                    max_r = max(0.0, min(float(max_x - cx0), float(cx0 - min_x), float(max_y - cy0), float(cy0 - min_y)))
                    if max_r <= 0.0:
                        continue

                    if desired_r <= 0.0:
                        desired_r = float(max_r)
                    r = min(float(desired_r), float(max_r))
                    if r <= 0.0:
                        continue

                    t = float(t) + float(dt)
                    ang = float(ang) + (direction * (float(speed) / float(r)) * float(dt))
                    if ang > (2.0 * math.pi) or ang < (-2.0 * math.pi):
                        try:
                            ang = float(math.fmod(ang, 2.0 * math.pi))
                        except Exception:
                            pass
                    payload["ang"] = float(ang)
                    payload["r"] = float(r)
                    payload["desired_r"] = float(desired_r)
                    payload["t"] = float(t)

                    tx = float(cx0) + (math.cos(float(ang)) * float(r))
                    ty = float(cy0) + (math.sin(float(ang)) * float(r))
                    try:
                        before_center = br.center()
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                    except Exception:
                        pass

                    w = 2.0 * math.pi * float(rate)
                    ph = math.radians(float(phase))
                    s = (math.sin((float(w) * float(t)) + float(ph)) + 1.0) / 2.0
                    scale = float(scale_min) + (float(s) * (float(scale_max) - float(scale_min)))
                    try:
                        it.setScale(float(scale))
                    except Exception:
                        pass
                    try:
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "heartbeat":
                    any_anim = True
                    try:
                        scale_min = float(payload.get("scale_min", 1.0))
                        scale_max = float(payload.get("scale_max", 1.2))
                        rate = float(payload.get("rate", payload.get("freq", 1.0)))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    t = float(t) + float(dt)
                    
                    cycle = (t * rate) % 1.0
                    if cycle < 0.2:
                        p = math.sin(cycle * 5.0 * math.pi) 
                        s = p if p > 0 else 0.0
                    elif cycle < 0.3:
                        s = 0.0
                    elif cycle < 0.5:
                        p = math.sin((cycle - 0.3) * 5.0 * math.pi) * 0.8
                        s = p if p > 0 else 0.0
                    else:
                        s = 0.0
                        
                    scale = float(scale_min) + (float(s) * (float(scale_max) - float(scale_min)))
                    payload["t"] = float(t)
                    try:
                        it.setScale(float(scale))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "glitch":
                    any_anim = True
                    try:
                        intensity = float(payload.get("intensity", 10.0))
                        prob = float(payload.get("prob", 0.1))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                    except Exception:
                        continue

                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        bx = float(base[0])
                        by = float(base[1])
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())
                        
                    t = float(t) + float(dt)
                    
                    if random.random() < prob:
                        ox = (random.random() - 0.5) * 2.0 * intensity
                        oy = (random.random() - 0.5) * 2.0 * intensity
                        op = random.random() * 0.5 + 0.5
                    else:
                        ox = 0.0
                        oy = 0.0
                        op = 1.0
                        
                    tx = bx + ox
                    ty = by + oy
                    
                    payload["t"] = float(t)
                    payload["base"] = [float(bx), float(by)]
                    
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setOpacity(op)
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "rain":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 100.0))
                        t = float(payload.get("t", 0.0))
                    except Exception:
                        continue
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                        h = float(br.height())
                    except Exception:
                        continue
                    
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        bx = float(base[0])
                        by = float(base[1])
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())

                    t = float(t) + float(dt)
                    by += speed * dt
                    
                    sr = self._anim_bounds_rect()
                    min_y = float(sr.top()) - h
                    max_y = float(sr.bottom()) + h
                    
                    if by > max_y:
                        by = min_y
                    
                    payload["t"] = float(t)
                    payload["base"] = [float(bx), float(by)]
                    
                    try:
                        dx = float(bx - float(before_center.x()))
                        dy = float(by - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass

                elif mode == "spiral":
                    any_anim = True
                    try:
                        speed = float(payload.get("speed", 2.0))
                        expansion = float(payload.get("expansion", 50.0))
                        t = float(payload.get("t", 0.0))
                        angle = float(payload.get("angle", 0.0))
                        r = float(payload.get("r", 0.0))
                    except Exception:
                        continue
                        
                    try:
                        br = it.sceneBoundingRect()
                        before_center = br.center()
                    except Exception:
                        continue
                        
                    base = payload.get("base")
                    if isinstance(base, (list, tuple)) and len(base) >= 2:
                        bx = float(base[0])
                        by = float(base[1])
                    else:
                        bx = float(before_center.x())
                        by = float(before_center.y())
                        
                    t += dt
                    angle += speed * dt
                    r += expansion * dt
                    
                    sr = self._anim_bounds_rect()
                    max_dim = max(float(sr.width()), float(sr.height()))
                    if r > max_dim / 2.0:
                        r = 0.0
                        
                    tx = bx + math.cos(angle) * r
                    ty = by + math.sin(angle) * r
                    
                    payload["t"] = float(t)
                    payload["angle"] = float(angle)
                    payload["r"] = float(r)
                    payload["base"] = [float(bx), float(by)]
                    
                    try:
                        dx = float(tx - float(before_center.x()))
                        dy = float(ty - float(before_center.y()))
                        pos = it.pos()
                        it.setPos(QPointF(float(pos.x()) + dx, float(pos.y()) + dy))
                        it.setData(ITEM_DATA_ANIM_PAYLOAD, payload)
                    except Exception:
                        pass
        except Exception:
            any_anim = False
        if not any_anim:
            self._anim_timer.stop()

    def set_items_animation(self, items: list[QGraphicsItem], mode: str, payloads: dict[int, dict]) -> None:
        mode = str(mode or "").strip()
        if not mode:
            return
        for it in items:
            try:
                movable = bool(it.flags() & QGraphicsItem.ItemIsMovable)
            except Exception:
                movable = True
            if not movable:
                continue
            data = payloads.get(id(it), {})
            if not isinstance(data, dict):
                data = {}
            try:
                it.setData(ITEM_DATA_ANIM_MODE, mode)
                it.setData(ITEM_DATA_ANIM_PAYLOAD, dict(data))
            except Exception:
                pass
        self.refresh_animation()

    def clear_items_animation(self, items: list[QGraphicsItem]) -> None:
        for it in items:
            payload = None
            try:
                payload = it.data(ITEM_DATA_ANIM_PAYLOAD)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                bp = payload.get("base_pos")
                if isinstance(bp, (list, tuple)) and len(bp) >= 2:
                    try:
                        it.setPos(QPointF(float(bp[0]), float(bp[1])))
                    except Exception:
                        pass
                try:
                    bs = payload.get("base_scale")
                    if bs is not None:
                        it.setScale(float(bs))
                except Exception:
                    pass
                try:
                    br = payload.get("base_rot")
                    if br is not None:
                        it.setRotation(float(br))
                except Exception:
                    pass
                try:
                    bo = payload.get("base_opacity")
                    if bo is not None:
                        it.setOpacity(float(bo))
                except Exception:
                    pass
            try:
                it.setData(ITEM_DATA_ANIM_MODE, None)
                it.setData(ITEM_DATA_ANIM_PAYLOAD, None)
            except Exception:
                pass
        self.refresh_animation()

    def set_path_draw_enabled(self, enabled: bool) -> None:
        self._path_draw_enabled = bool(enabled)
        if self._path_item is None:
            item = QGraphicsPathItem()
            pen = QPen(QColor(255, 255, 255, 220))
            pen.setWidth(3)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setZValue(2_000_000_000)
            item.setFlags(QGraphicsItem.GraphicsItemFlag(0))
            item.setAcceptedMouseButtons(Qt.NoButton)
            self.addItem(item)
            self._path_item = item
        self._update_path_item()

    def clear_drawn_path(self) -> None:
        self._path_points = []
        self._path_drawing = False
        self._update_path_item()

    def drawn_path_points(self) -> list[QPointF]:
        return [QPointF(float(p.x()), float(p.y())) for p in self._path_points]

    def _update_path_item(self) -> None:
        if self._path_item is None:
            return
        path = QPainterPath()
        if self._path_points:
            first = self._path_points[0]
            path.moveTo(first)
            for p in self._path_points[1:]:
                path.lineTo(p)
        self._path_item.setPath(path)

    def reset_text_id_counter(self) -> None:
        self._text_id_counter = 1

    def add_text_layer(self, text_id: int | None = None) -> TextLayerItem:
        if text_id is None:
            text_id = self._text_id_counter
            self._text_id_counter += 1
        else:
            text_id = int(text_id)
            if text_id >= self._text_id_counter:
                self._text_id_counter = text_id + 1

        item = TextLayerItem("Text", text_id=text_id)
        item.setPos(self.sceneRect().center())
        item.setZValue(self._next_z())
        self.addItem(item)
        self.refresh_text_animation()
        return item

    def add_image_layer(self, file_path: str) -> ImageLayerItem:
        pix = QPixmap(file_path)
        item = ImageLayerItem(pix, label="Image")
        item.setPos(self.sceneRect().center())
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setZValue(self._next_z())
        item.setData(ITEM_DATA_SOURCE_PATH, file_path)
        item.setData(ITEM_DATA_SOURCE_KIND, "image")
        self.addItem(item)
        return item

    def add_gif_layer(self, file_path: str) -> ImageLayerItem:
        movie = QMovie(file_path)
        movie.setCacheMode(QMovie.CacheAll)
        pix = QPixmap()
        item = ImageLayerItem(pix, label="GIF")
        item.setPos(self.sceneRect().center())
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setZValue(self._next_z())
        self.addItem(item)

        def update_frame() -> None:
            frame = movie.currentPixmap()
            item.setPixmap(frame)
            item.setTransformOriginPoint(item.boundingRect().center())

        movie.frameChanged.connect(lambda _i: update_frame())
        movie.start()
        item.setData(0xBEEF, movie)
        item.setData(ITEM_DATA_SOURCE_PATH, file_path)
        item.setData(ITEM_DATA_SOURCE_KIND, "gif")
        return item

    def add_video_layer(self, file_path: str) -> QGraphicsVideoItem:
        video_item = VideoLayerItem()
        video_item.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        video_item.setPos(self.sceneRect().center())
        video_item.setSize(QSizeF(640, 360))
        video_item.setTransformOriginPoint(video_item.boundingRect().center())
        video_item.setZValue(self._next_z())
        self.addItem(video_item)
        try:
            video_item.setAspectRatioMode(Qt.KeepAspectRatio)
        except Exception:
            pass

        player = QMediaPlayer()
        audio = QAudioOutput()
        player.setAudioOutput(audio)
        player.setVideoOutput(video_item)
        try:
            audio.setVolume(0.5)
        except Exception:
            pass
        
        abs_path = Path(file_path).resolve()
        url = QUrl.fromLocalFile(str(abs_path))
        print(f"DEBUG: Adding video layer from: {abs_path}", file=sys.stderr, flush=True)
        print(f"DEBUG: Layer URL: {url.toString()}", file=sys.stderr, flush=True)
        
        def on_error():
            err_str = player.errorString()
            print(f"ERROR: MediaPlayer error: {err_str}", file=sys.stderr, flush=True)
            print(f"ERROR: MediaPlayer error code: {player.error()}", file=sys.stderr, flush=True)
            try:
                mb = QMessageBox()
                mb.setIcon(QMessageBox.Icon.Warning)
                mb.setWindowTitle("Video Layer Error")
                mb.setText("Could not open media for this layer.")
                mb.setInformativeText(str(err_str or "Unknown error"))
                mb.exec()
            except Exception:
                pass

        player.errorOccurred.connect(on_error)
        player.setSource(url)
        player.setLoops(QMediaPlayer.Loops.Infinite)
        player.play()
         
        # Keep references to prevent garbage collection
        video_item.set_player_components(player, audio)
        
        video_item.setData(0xFEED, player)
        video_item.setData(0xFEED + 1, audio)
        video_item.setData(ITEM_DATA_SOURCE_PATH, file_path)
        video_item.setData(ITEM_DATA_SOURCE_KIND, "video")
        return video_item

    def add_particle_layer(self) -> ParticleLayerItem:
        item = ParticleLayerItem(width=self.sceneRect().width(), height=self.sceneRect().height())
        item.setPos(0, 0)
        item.setZValue(self._next_z())
        self.addItem(item)
        self.refresh_animation()
        return item

    def mousePressEvent(self, event) -> None:
        if self._orbit_center_pick_enabled and event.button() == Qt.LeftButton:
            try:
                cid = str(self._orbit_center_pick_id or "center1").strip() or "center1"
            except Exception:
                cid = "center1"
            try:
                p = event.scenePos()
                self._orbit_centers_point[cid] = QPointF(float(p.x()), float(p.y()))
                try:
                    b = self._anim_bounds_rect()
                    if float(b.width()) > 0.0 and float(b.height()) > 0.0:
                        nx = (float(p.x()) - float(b.left())) / float(b.width())
                        ny = (float(p.y()) - float(b.top())) / float(b.height())
                        nx = max(0.0, min(1.0, float(nx)))
                        ny = max(0.0, min(1.0, float(ny)))
                        self._orbit_centers_norm[cid] = (float(nx), float(ny))
                except Exception:
                    self._orbit_centers_norm.pop(cid, None)
            except Exception:
                self._orbit_centers_point.pop(cid, None)
                self._orbit_centers_norm.pop(cid, None)
            self._orbit_center_pick_enabled = False
            try:
                self.update()
            except Exception:
                pass
            event.accept()
            return
        if self._path_draw_enabled and event.button() == Qt.LeftButton:
            self._path_drawing = True
            try:
                p = event.scenePos()
                self._path_points.append(QPointF(float(p.x()), float(p.y())))
                self._update_path_item()
            except Exception:
                pass
            event.accept()
            return
        try:
            if event.button() == Qt.LeftButton:
                item = self.itemAt(event.scenePos(), QTransform())
                if item is not None and (item.flags() & QGraphicsItem.ItemIsMovable):
                    self._drag_item = item
                    self._drag_before = (
                        float(item.pos().x()),
                        float(item.pos().y()),
                        float(item.scale()),
                        float(item.rotation()),
                    )
        except Exception:
            self._drag_item = None
            self._drag_before = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._path_draw_enabled and self._path_drawing:
            try:
                p = event.scenePos()
                if not self._path_points:
                    self._path_points.append(QPointF(float(p.x()), float(p.y())))
                    self._update_path_item()
                    event.accept()
                    return
                last = self._path_points[-1]
                dx = float(p.x() - last.x())
                dy = float(p.y() - last.y())
                if (dx * dx) + (dy * dy) >= (3.0 * 3.0):
                    self._path_points.append(QPointF(float(p.x()), float(p.y())))
                    self._update_path_item()
                event.accept()
                return
            except Exception:
                event.accept()
                return
        super().mouseMoveEvent(event)
        item = self._drag_item
        if item is None:
            return
        try:
            movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
        except Exception:
            movable = True
        if not movable:
            return
        if not self._snap_grid_enabled and not self._snap_center_enabled:
            return
        try:
            snapped = self.snap_position(item, item.pos())
            if snapped != item.pos():
                item.setPos(snapped)
        except Exception:
            pass

    def mouseReleaseEvent(self, event) -> None:
        if self._path_draw_enabled and self._path_drawing and event.button() == Qt.LeftButton:
            self._path_drawing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        item = self._drag_item
        before = self._drag_before
        self._drag_item = None
        self._drag_before = None
        if item is None or before is None:
            return
        if self._snap_grid_enabled or self._snap_center_enabled:
            try:
                movable = bool(item.flags() & QGraphicsItem.ItemIsMovable)
            except Exception:
                movable = True
            if movable:
                try:
                    snapped = self.snap_position(item, item.pos())
                    if snapped != item.pos():
                        item.setPos(snapped)
                except Exception:
                    pass
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
            self.item_transform_committed.emit(item, before, after)

    def _next_z(self) -> float:
        value = self._z_counter
        self._z_counter += 1.0
        return value

    def _stretch_pixmap_item(self, item: QGraphicsPixmapItem) -> None:
        pix = item.pixmap()
        if pix.isNull():
            return
        rect = self.sceneRect()
        w = pix.width()
        h = pix.height()
        if w == 0 or h == 0:
            return
        bleed = 2.0
        sx = (rect.width() + bleed) / w
        sy = (rect.height() + bleed) / h
        item.setTransform(QTransform.fromScale(sx, sy))
        item.setTransformOriginPoint(0, 0)
        item.setPos(rect.left() - (bleed / 2.0), rect.top() - (bleed / 2.0))

    def _resize_background_to_scene(self) -> None:
        if self._background_item is None:
            return
        rect = self.sceneRect()
        if isinstance(self._background_item, QGraphicsVideoItem):
            bleed = 2.0
            self._background_item.setSize(QSizeF(rect.width() + bleed, rect.height() + bleed))
            self._background_item.setPos(rect.left() - (bleed / 2.0), rect.top() - (bleed / 2.0))
        elif isinstance(self._background_item, QGraphicsPixmapItem):
            self._stretch_pixmap_item(self._background_item)

    def _clear_desktop_overlays(self) -> None:
        if self._taskbar_overlay is not None:
            self.removeItem(self._taskbar_overlay)
            self._taskbar_overlay = None
        for icon in self._icon_overlays:
            self.removeItem(icon)
        self._icon_overlays = []

    def _update_desktop_overlays(self, screen: QRectF, work: QRectF) -> None:
        self._clear_desktop_overlays()

        screen_left = screen.left()
        screen_top = screen.top()
        screen_right = screen.left() + screen.width()
        screen_bottom = screen.top() + screen.height()

        work_left = work.left()
        work_top = work.top()
        work_right = work.left() + work.width()
        work_bottom = work.top() + work.height()

        taskbars: list[QRectF] = []
        top_h = max(0.0, work_top - screen_top)
        bottom_h = max(0.0, screen_bottom - work_bottom)
        left_w = max(0.0, work_left - screen_left)
        right_w = max(0.0, screen_right - work_right)

        if top_h > 0.5:
            taskbars.append(QRectF(screen_left, screen_top, screen.width(), top_h))
        if bottom_h > 0.5:
            taskbars.append(QRectF(screen_left, work_bottom, screen.width(), bottom_h))
        if left_w > 0.5:
            taskbars.append(QRectF(screen_left, work_top, left_w, work.height()))
        if right_w > 0.5:
            taskbars.append(QRectF(work_right, work_top, right_w, work.height()))

        if taskbars:
            rect = taskbars[0]
            item = QGraphicsRectItem(rect)
            item.setBrush(QColor(0, 0, 0, 90))
            pen = QPen(QColor(255, 255, 255, 140))
            pen.setStyle(Qt.DashLine)
            item.setPen(pen)
            item.setZValue(1_000_000_000)
            item.setFlags(QGraphicsItem.GraphicsItemFlag(0))
            item.setAcceptedMouseButtons(Qt.NoButton)
            self.addItem(item)
            self._taskbar_overlay = item

        margin = 24.0
        icon_size = 72.0
        spacing_x = 96.0
        spacing_y = 96.0

        max_x = (work.left() + work.width()) - margin - icon_size
        max_y = (work.top() + work.height()) - margin - icon_size

        y = work.top() + margin
        count = 0
        while y <= max_y and count < 60:
            x = work.left() + margin
            while x <= max_x and count < 60:
                r = QRectF(x, y, icon_size, icon_size)
                icon = QGraphicsRectItem(r)
                pen = QPen(QColor(255, 255, 255, 90))
                pen.setStyle(Qt.DotLine)
                icon.setPen(pen)
                icon.setBrush(QColor(255, 255, 255, 20))
                icon.setZValue(1_000_000_001)
                icon.setFlags(QGraphicsItem.GraphicsItemFlag(0))
                icon.setAcceptedMouseButtons(Qt.NoButton)
                self.addItem(icon)
                self._icon_overlays.append(icon)
                count += 1
                x += spacing_x
            y += spacing_y
