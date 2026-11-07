from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsPixmapItem, QGraphicsBlurEffect, QGraphicsDropShadowEffect, QGraphicsColorizeEffect


class FillMode(str, Enum):
    SOLID = "solid"
    GRADIENT = "gradient"


class TextEffect(str, Enum):
    NONE = "none"
    RAINBOW = "rainbow"
    WAVE = "wave"
    TYPEWRITER = "typewriter"
    SCRAMBLE = "scramble"
    PULSE = "pulse"


class BlendMode(str, Enum):
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    DARKEN = "darken"
    LIGHTEN = "lighten"
    ADD = "add"


def _blend_mode_to_composition_mode(mode: BlendMode) -> QPainter.CompositionMode:
    if mode == BlendMode.MULTIPLY:
        return QPainter.CompositionMode_Multiply
    if mode == BlendMode.SCREEN:
        return QPainter.CompositionMode_Screen
    if mode == BlendMode.OVERLAY:
        return QPainter.CompositionMode_Overlay
    if mode == BlendMode.SOFT_LIGHT:
        return QPainter.CompositionMode_SoftLight
    if mode == BlendMode.DARKEN:
        return QPainter.CompositionMode_Darken
    if mode == BlendMode.LIGHTEN:
        return QPainter.CompositionMode_Lighten
    if mode == BlendMode.ADD:
        return QPainter.CompositionMode_Plus
    return QPainter.CompositionMode_SourceOver


def _parse_blend_mode(value: object) -> BlendMode:
    if isinstance(value, BlendMode):
        return value
    try:
        return BlendMode(str(value))
    except Exception:
        return BlendMode.NORMAL


@dataclass
class TextStyle:
    font: QFont
    fill_mode: FillMode
    color: QColor
    gradient_start: QColor
    gradient_end: QColor
    effect: TextEffect
    effect_speed: float
    effect_amount: float
    shadow_enabled: bool
    shadow_color: QColor
    shadow_offset: QPointF
    shadow_blur: float
    glow_enabled: bool
    glow_color: QColor
    glow_blur: float
    blur_enabled: bool
    blur_radius: float


def default_text_style() -> TextStyle:
    font = QFont()
    font.setPointSize(48)
    return TextStyle(
        font=font,
        fill_mode=FillMode.SOLID,
        color=QColor("#ffffff"),
        gradient_start=QColor("#ffffff"),
        gradient_end=QColor("#00e5ff"),
        effect=TextEffect.NONE,
        effect_speed=1.0,
        effect_amount=20.0,
        shadow_enabled=True,
        shadow_color=QColor(0, 0, 0, 200),
        shadow_offset=QPointF(3, 3),
        shadow_blur=12.0,
        glow_enabled=False,
        glow_color=QColor("#00e5ff"),
        glow_blur=18.0,
        blur_enabled=False,
        blur_radius=0.0,
    )


class TextLayerItem(QGraphicsObject):
    def __init__(self, text: str, text_id: int) -> None:
        super().__init__()
        self._text_id = int(text_id)
        self._text = text
        self._style = default_text_style()
        self._blend_mode = BlendMode.NORMAL
        self._anim_t = 0.0
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    def type_name(self) -> str:
        return "Text"

    def text_id(self) -> int:
        return self._text_id

    def text(self) -> str:
        return self._text

    def set_text(self, value: str) -> None:
        if self._text == value:
            return
        self.prepareGeometryChange()
        self._text = value
        self.update()

    def style(self) -> TextStyle:
        return self._style

    def set_style(self, style: TextStyle) -> None:
        self.prepareGeometryChange()
        self._style = style
        if self._style.blur_enabled and self._style.blur_radius > 0:
            eff = QGraphicsBlurEffect()
            eff.setBlurRadius(self._style.blur_radius)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)
        self.update()

    def blend_mode(self) -> BlendMode:
        return self._blend_mode

    def set_blend_mode(self, value: BlendMode | str) -> None:
        mode = _parse_blend_mode(value)
        if mode == self._blend_mode:
            return
        self._blend_mode = mode
        self.update()

    def needs_animation(self) -> bool:
        return bool(self._text) and self._style.effect in (
            TextEffect.RAINBOW,
            TextEffect.WAVE,
            TextEffect.TYPEWRITER,
            TextEffect.SCRAMBLE,
            TextEffect.PULSE,
        )

    def advance_time(self, dt: float) -> None:
        try:
            self._anim_t += max(0.0, float(dt))
        except Exception:
            pass

    def _text_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addText(0, 0, self._style.font, self._text)
        return path

    def _wave_text_path(self) -> QPainterPath:
        path = QPainterPath()
        metrics = QFontMetricsF(self._style.font)
        t = float(self._anim_t)
        speed = max(0.0, float(self._style.effect_speed))
        amp = max(0.0, float(self._style.effect_amount))
        phase_step = 0.65
        w = 2.0 * math.pi * speed
        x = 0.0
        for i, ch in enumerate(self._text):
            ch_path = QPainterPath()
            ch_path.addText(x, 0.0, self._style.font, ch)
            y = math.sin((w * t) + (i * phase_step)) * amp
            path.addPath(ch_path.translated(0.0, float(y)))
            try:
                x += float(metrics.horizontalAdvance(ch))
            except Exception:
                x += 0.0
        return path

    def _typewriter_text_path(self) -> QPainterPath:
        path = QPainterPath()
        speed = max(0.1, float(self._style.effect_speed))
        t = float(self._anim_t)
        
        # Speed 1.0 = 10 chars/sec
        chars_per_sec = speed * 10.0
        
        total_len = len(self._text)
        cycle_len = total_len + int(chars_per_sec * 2.0) # Wait 2s
        if cycle_len == 0:
            cycle_len = 1
        
        current_idx = int(t * chars_per_sec) % cycle_len
        
        if current_idx > total_len:
            visible_text = self._text
        else:
            visible_text = self._text[:current_idx]
            
        path.addText(0, 0, self._style.font, visible_text)
        return path

    def _scramble_text_path(self) -> QPainterPath:
        path = QPainterPath()
        speed = max(0.1, float(self._style.effect_speed))
        amount = max(0.0, float(self._style.effect_amount)) / 100.0
        
        # Update scramble every 0.1s / speed
        time_step = 0.1 / speed if speed > 0 else 1.0
        seed_time = int(self._anim_t / time_step)
        
        rng = random.Random(seed_time)
        
        metrics = QFontMetricsF(self._style.font)
        x = 0.0
        
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()"
        
        for ch in self._text:
            if rng.random() < amount:
                display_char = rng.choice(chars)
            else:
                display_char = ch
            
            path.addText(x, 0, self._style.font, display_char)
            try:
                x += float(metrics.horizontalAdvance(ch))
            except Exception:
                x += 0.0
            
        return path

    def _pulse_text_path(self) -> QPainterPath:
        base_path = self._text_path()
        rect = base_path.boundingRect()
        if rect.isEmpty():
            return base_path
            
        speed = max(0.1, float(self._style.effect_speed))
        amount = max(0.0, float(self._style.effect_amount)) / 100.0
        
        t = float(self._anim_t)
        scale = 1.0 + math.sin(t * speed * 2 * math.pi) * amount
        
        center = rect.center()
        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.scale(scale, scale)
        transform.translate(-center.x(), -center.y())
        
        return transform.map(base_path)

    def _get_effect_path(self) -> QPainterPath:
        if self._style.effect == TextEffect.WAVE:
            return self._wave_text_path()
        elif self._style.effect == TextEffect.TYPEWRITER:
            return self._typewriter_text_path()
        elif self._style.effect == TextEffect.SCRAMBLE:
            return self._scramble_text_path()
        elif self._style.effect == TextEffect.PULSE:
            return self._pulse_text_path()
        else:
            return self._text_path()

    def boundingRect(self) -> QRectF:
        rect = self._get_effect_path().boundingRect()
        return rect.adjusted(-60, -60, 60, 60)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.save()
        painter.setCompositionMode(_blend_mode_to_composition_mode(self._blend_mode))
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing, True)

        path = self._get_effect_path()
        rect = path.boundingRect()
        path = path.translated(-rect.left(), -rect.top())

        if self._style.glow_enabled:
            blur = max(0.0, float(self._style.glow_blur))
            widths = [max(2.0, blur * 0.55), max(1.5, blur * 0.35), max(1.0, blur * 0.2)]
            alphas = [80, 120, 180]
            for width, alpha in zip(widths, alphas, strict=False):
                glow = QColor(self._style.glow_color)
                glow.setAlpha(min(255, alpha))
                pen = QPen(glow)
                pen.setWidthF(width)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)

        if self._style.shadow_enabled:
            shadow_color = QColor(self._style.shadow_color)
            shadow_color.setAlpha(max(0, min(255, shadow_color.alpha())))
            painter.save()
            painter.translate(self._style.shadow_offset)
            blur = max(0.0, float(self._style.shadow_blur))
            if blur > 0.0:
                outline = QColor(shadow_color)
                outline.setAlpha(max(0, min(255, int(outline.alpha() * 0.55))))
                pen = QPen(outline)
                pen.setWidthF(max(1.0, blur * 0.5))
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(shadow_color)
                painter.drawPath(path)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(shadow_color)
                painter.drawPath(path)
            painter.restore()

        if self._style.effect == TextEffect.RAINBOW:
            grad = QLinearGradient(0.0, 0.0, rect.width(), 0.0)
            speed = max(0.0, float(self._style.effect_speed))
            phase = (float(self._anim_t) * speed * 0.15) % 1.0
            stops = [0.0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1.0]
            for s in stops:
                h = (float(s) + phase) % 1.0
                c = QColor.fromHsvF(h, 1.0, 1.0, 1.0)
                grad.setColorAt(float(s), c)
            painter.setBrush(grad)
        elif self._style.fill_mode == FillMode.GRADIENT:
            grad = QLinearGradient(0, 0, rect.width(), rect.height())
            grad.setColorAt(0.0, self._style.gradient_start)
            grad.setColorAt(1.0, self._style.gradient_end)
            painter.setBrush(grad)
        else:
            painter.setBrush(self._style.color)

        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
        painter.restore()


class ImageLayerItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, label: str = "Image") -> None:
        super().__init__(pixmap)
        self._label = label
        self._blend_mode = BlendMode.NORMAL
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

    def type_name(self) -> str:
        return self._label

    def blend_mode(self) -> BlendMode:
        return self._blend_mode

    def set_blend_mode(self, value: BlendMode | str) -> None:
        mode = _parse_blend_mode(value)
        if mode == self._blend_mode:
            return
        self._blend_mode = mode
        self.update()

    def set_effect(self, name: str, params: dict) -> None:
        if name == "blur":
            radius = float(params.get("radius", 0.0))
            if radius > 0:
                eff = QGraphicsBlurEffect()
                eff.setBlurRadius(radius)
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        elif name == "shadow" or name == "glow":
            radius = float(params.get("radius", 0.0))
            if radius > 0:
                eff = QGraphicsDropShadowEffect()
                eff.setBlurRadius(radius)
                c = params.get("color")
                if isinstance(c, QColor) and c.isValid():
                    eff.setColor(c)
                elif isinstance(c, str):
                    eff.setColor(QColor(c))
                offset = params.get("offset", (0, 0))
                eff.setOffset(float(offset[0]), float(offset[1]))
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        elif name == "colorize":
            eff = QGraphicsColorizeEffect()
            try:
                eff.setStrength(max(0.0, min(1.0, float(params.get("strength", 0.6)))))
            except Exception:
                eff.setStrength(0.6)
            c = params.get("color")
            if isinstance(c, QColor) and c.isValid():
                eff.setColor(c)
            elif isinstance(c, str):
                parsed = QColor(c)
                if parsed.isValid():
                    eff.setColor(parsed)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.setCompositionMode(_blend_mode_to_composition_mode(self._blend_mode))
        super().paint(painter, option, widget)
        painter.restore()


class VideoLayerItem(QGraphicsVideoItem):
    def __init__(self) -> None:
        super().__init__()
        self._blend_mode = BlendMode.NORMAL
        self._player = None
        self._audio = None

    def set_player_components(self, player, audio) -> None:
        self._player = player
        self._audio = audio

    def blend_mode(self) -> BlendMode:
        return self._blend_mode

    def set_blend_mode(self, value: BlendMode | str) -> None:
        mode = _parse_blend_mode(value)
        if mode == self._blend_mode:
            return
        self._blend_mode = mode
        self.update()

    def set_effect(self, name: str, params: dict) -> None:
        if name == "blur":
            radius = float(params.get("radius", 0.0))
            if radius > 0:
                eff = QGraphicsBlurEffect()
                eff.setBlurRadius(radius)
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        elif name == "shadow" or name == "glow":
            radius = float(params.get("radius", 0.0))
            if radius > 0:
                eff = QGraphicsDropShadowEffect()
                eff.setBlurRadius(radius)
                c = params.get("color")
                if isinstance(c, QColor) and c.isValid():
                    eff.setColor(c)
                elif isinstance(c, str):
                    eff.setColor(QColor(c))
                offset = params.get("offset", (0, 0))
                eff.setOffset(float(offset[0]), float(offset[1]))
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        elif name == "colorize":
            eff = QGraphicsColorizeEffect()
            try:
                eff.setStrength(max(0.0, min(1.0, float(params.get("strength", 0.6)))))
            except Exception:
                eff.setStrength(0.6)
            c = params.get("color")
            if isinstance(c, QColor) and c.isValid():
                eff.setColor(c)
            elif isinstance(c, str):
                parsed = QColor(c)
                if parsed.isValid():
                    eff.setColor(parsed)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.setCompositionMode(_blend_mode_to_composition_mode(self._blend_mode))
        super().paint(painter, option, widget)
        painter.restore()


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: QColor


class ParticleLayerItem(QGraphicsItem):
    def __init__(self, width: float = 400, height: float = 300) -> None:
        super().__init__()
        self._width = width
        self._height = height
        self._blend_mode = BlendMode.NORMAL
        self._particles: list[Particle] = []
        self._spawn_timer = 0.0
        
        # Settings
        self.count = 100
        self.speed = 50.0
        self.size = 3.0
        self.color = QColor(255, 255, 255)
        self.gravity_x = 0.0
        self.gravity_y = 0.0
        self.lifetime = 2.0
        self.spread = 360.0
        self.emission_mode = "point"  # "point" or "rect"
        self.direction = 0.0 # degrees, 0 = right, 90 = down
        
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        
    def type_name(self) -> str:
        return "Particles"
        
    def blend_mode(self) -> BlendMode:
        return self._blend_mode

    def set_blend_mode(self, value: BlendMode | str) -> None:
        mode = _parse_blend_mode(value)
        if mode == self._blend_mode:
            return
        self._blend_mode = mode
        self.update()

    def set_effect(self, name: str, params: dict) -> None:
        if name == "blur":
            radius = float(params.get("radius", 0.0))
            if radius > 0:
                eff = QGraphicsBlurEffect()
                eff.setBlurRadius(radius)
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        elif name == "shadow" or name == "glow":
            radius = float(params.get("radius", 0.0))
            if radius > 0:
                eff = QGraphicsDropShadowEffect()
                eff.setBlurRadius(radius)
                c = params.get("color")
                if isinstance(c, QColor) and c.isValid():
                    eff.setColor(c)
                elif isinstance(c, str):
                    eff.setColor(QColor(c))
                offset = params.get("offset", (0, 0))
                eff.setOffset(float(offset[0]), float(offset[1]))
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        elif name == "colorize":
            eff = QGraphicsColorizeEffect()
            try:
                eff.setStrength(max(0.0, min(1.0, float(params.get("strength", 0.6)))))
            except Exception:
                eff.setStrength(0.6)
            c = params.get("color")
            if isinstance(c, QColor) and c.isValid():
                eff.setColor(c)
            elif isinstance(c, str):
                parsed = QColor(c)
                if parsed.isValid():
                    eff.setColor(parsed)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

        
    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.setCompositionMode(_blend_mode_to_composition_mode(self._blend_mode))
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        painter.setPen(Qt.NoPen)
        
        for p in self._particles:
            alpha = int(255 * (p.life / p.max_life))
            c = QColor(p.color)
            c.setAlpha(alpha)
            painter.setBrush(c)
            painter.drawEllipse(QPointF(p.x, p.y), p.size/2, p.size/2)
            
        painter.restore()
        
    def advance_time(self, dt: float) -> None:
        # A long stall (minimised window, slow frame) must not spawn thousands of
        # particles in a single tick.
        step = max(0.0, min(float(dt), 0.1))
        if step <= 0.0:
            return

        lifetime = max(1e-3, float(self.lifetime))
        spawn_rate = max(0.0, float(self.count)) / lifetime
        self._spawn_timer += spawn_rate * step

        spawn_budget = max(1, int(max(1.0, float(self.count)) * 2))
        spawned = 0
        while self._spawn_timer >= 1.0 and spawned < spawn_budget:
            self._spawn_timer -= 1.0
            self._spawn_particle()
            spawned += 1
        if self._spawn_timer > 1.0:
            self._spawn_timer = 0.0

        # Filtering into a fresh list is O(n); repeatedly calling list.remove() is
        # O(n^2) and made large particle counts stall the UI thread.
        alive: list[Particle] = []
        for p in self._particles:
            p.life -= step
            if p.life <= 0.0:
                continue
            p.vx += self.gravity_x * step
            p.vy += self.gravity_y * step
            p.x += p.vx * step
            p.y += p.vy * step
            alive.append(p)

        max_alive = max(1, int(max(1.0, float(self.count)) * 3))
        if len(alive) > max_alive:
            alive = alive[-max_alive:]
        self._particles = alive

        self.update()

    def set_bounds(self, width: float, height: float) -> None:
        try:
            w = max(1.0, float(width))
            h = max(1.0, float(height))
        except Exception:
            return
        if abs(w - float(self._width)) < 0.5 and abs(h - float(self._height)) < 0.5:
            return
        self.prepareGeometryChange()
        self._width = w
        self._height = h
        self.update()
        
    def _spawn_particle(self):
        if self.emission_mode == "rect":
            cx = random.uniform(0, self._width)
            cy = random.uniform(0, self._height)
        else:
            cx, cy = self._width / 2, self._height / 2
            
        base_angle = math.radians(self.direction)
        half_spread = math.radians(self.spread) / 2
        angle = base_angle + random.uniform(-half_spread, half_spread)
        
        speed = random.uniform(self.speed * 0.5, self.speed * 1.5)
        
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        
        life = random.uniform(self.lifetime * 0.8, self.lifetime * 1.2)
        size = random.uniform(self.size * 0.5, self.size * 1.5)
        
        self._particles.append(Particle(
            x=cx, y=cy, vx=vx, vy=vy, life=life, max_life=life, size=size, color=self.color
        ))
