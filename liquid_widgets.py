"""
Liquid Glass UI Components:
Icon buttons, slim sliders, subtle surface cards, and audio visualizer.
"""

from PyQt6.QtWidgets import (
    QPushButton, QSlider, QFrame, QWidget, QMenu, QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
)
from PyQt6.QtGui import (
    QPainter, QColor, QPainterPath, QPen, QBrush, QLinearGradient,
    QMouseEvent, QPaintEvent, QFont, QGuiApplication, QImage, QPixmap
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, QVariantAnimation, QEasingCurve
from liquid_theme import LiquidTheme, draw_icon, ui_font
import math
import random


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _with_alpha(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(max(0, min(255, alpha)))
    return c


class LiquidGlassButton(QPushButton):
    """Icon button. Variants: 'ghost' (default), 'primary' (solid disc), 'window', 'window-close'."""

    def __init__(self, icon_name="play", size=40, is_toggle=False, variant="ghost", parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.btn_size = size
        self.is_toggle = is_toggle
        self.is_active = False
        self.variant = variant
        self.flush = False  # window buttons: square, edge-to-edge hover (maximized window)

        if variant in ("window", "window-close"):
            self.setFixedSize(int(size * 1.45), size)
        else:
            self.setFixedSize(size, size)
        self.setMouseTracking(True)
        self.is_hovered = False
        self.is_pressed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Smooth hover fade
        self._hover_t = 0.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_anim)

    def _on_hover_anim(self, value):
        self._hover_t = float(value)
        self.update()

    def _animate_hover(self, target: float):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def enterEvent(self, event):
        self.is_hovered = True
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_pressed = True
            if self.is_toggle:
                self.is_active = not self.is_active
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def set_active(self, active: bool):
        self.is_active = active
        self.update()

    def reset_hover(self):
        """Drops a hover highlight the pointer left behind without a leave event."""
        if self.is_hovered and not self.underMouse():
            self.is_hovered = False
            self._animate_hover(0.0)

    def set_icon_name(self, name: str):
        self.icon_name = name
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        t = self._hover_t

        if self.variant == "primary":
            grow = 1.0 + 0.04 * t - (0.04 if self.is_pressed else 0.0)
            r = min(rect.width(), rect.height()) / 2.0 * grow - 1
            c = rect.center()
            painter.setBrush(_mix(LiquidTheme.TEXT_PRIMARY, QColor(255, 255, 255), t))
            painter.drawEllipse(c, r, r)
            icon_size = rect.width() * 0.4
            icon_rect = QRectF(c.x() - icon_size / 2, c.y() - icon_size / 2, icon_size, icon_size)
            if self.icon_name == "play":
                icon_rect.translate(icon_size * 0.06, 0)  # optical centering
            draw_icon(painter, self.icon_name, icon_rect, LiquidTheme.TEXT_ON_LIGHT)

        elif self.variant in ("window", "window-close"):
            if t > 0 or self.is_pressed:
                if self.variant == "window-close":
                    bg = _with_alpha(LiquidTheme.DANGER, int(255 * t))
                else:
                    bg = LiquidTheme.PRESSED if self.is_pressed else _with_alpha(LiquidTheme.HOVER, int(LiquidTheme.HOVER.alpha() * t))
                painter.setBrush(bg)
                if self.flush:
                    painter.drawRect(rect)
                else:
                    painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)
            icon_size = 14.0
            icon_rect = QRectF(rect.center().x() - icon_size / 2, rect.center().y() - icon_size / 2, icon_size, icon_size)
            col = _mix(LiquidTheme.TEXT_SECONDARY, LiquidTheme.TEXT_PRIMARY, t)
            draw_icon(painter, self.icon_name, icon_rect, col, 1.6)

        else:
            if t > 0 or self.is_pressed:
                bg = LiquidTheme.PRESSED if self.is_pressed else _with_alpha(LiquidTheme.HOVER, int(LiquidTheme.HOVER.alpha() * t))
                painter.setBrush(bg)
                painter.drawEllipse(rect.center(), rect.width() / 2 - 1, rect.height() / 2 - 1)

            icon_size = round(min(rect.width(), rect.height()) * 0.5)
            icon_rect = QRectF(rect.center().x() - icon_size / 2, rect.center().y() - icon_size / 2, icon_size, icon_size)
            if self.is_active:
                col = LiquidTheme.ACCENT
            else:
                col = _mix(LiquidTheme.TEXT_SECONDARY, LiquidTheme.TEXT_PRIMARY, t)

            if self.icon_name in ("rewind", "forward"):
                draw_icon(painter, self.icon_name, icon_rect, col, 1.8)
                painter.setPen(col)
                painter.setFont(ui_font(max(7, int(icon_size * 0.36)), QFont.Weight.Bold))
                painter.drawText(icon_rect.translated(0, 0.5), Qt.AlignmentFlag.AlignCenter, "10")
            else:
                draw_icon(painter, self.icon_name, icon_rect, col, 1.9)

            # Active indicator dot
            if self.is_toggle and self.is_active:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(LiquidTheme.ACCENT)
                painter.drawEllipse(QPointF(rect.center().x(), rect.bottom() - 3), 2, 2)

        painter.end()


class LiquidGlassSlider(QSlider):
    """Slim slider: thin track, accent fill on hover, thumb that appears on interaction."""

    PADDING = 8

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None, always_show_thumb=False):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.is_hovered = False
        self.is_dragging = False
        self.always_show_thumb = always_show_thumb or orientation == Qt.Orientation.Vertical
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        if orientation == Qt.Orientation.Horizontal:
            self.setFixedHeight(20)
        else:
            self.setFixedWidth(24)

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self._set_value_from_pos(event.position().x() if self.orientation() == Qt.Orientation.Horizontal else event.position().y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging:
            self._set_value_from_pos(event.position().x() if self.orientation() == Qt.Orientation.Horizontal else event.position().y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.is_dragging = False
        self.update()
        super().mouseReleaseEvent(event)

    def _set_value_from_pos(self, pos_coord):
        if self.maximum() <= self.minimum():
            return
        padding = self.PADDING
        if self.orientation() == Qt.Orientation.Horizontal:
            track_w = max(1, self.width() - padding * 2)
            ratio = max(0.0, min(1.0, (pos_coord - padding) / track_w))
        else:
            track_h = max(1, self.height() - padding * 2)
            ratio = max(0.0, min(1.0, 1.0 - (pos_coord - padding) / track_h))

        new_val = int(round(self.minimum() + ratio * (self.maximum() - self.minimum())))
        self.setValue(new_val)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        val_range = max(1, self.maximum() - self.minimum())
        ratio = max(0.0, min(1.0, (self.value() - self.minimum()) / val_range))
        active = self.is_hovered or self.is_dragging
        fill_col = LiquidTheme.ACCENT if active or self.always_show_thumb else LiquidTheme.TEXT_PRIMARY
        padding = self.PADDING
        thick = 4.0

        if self.orientation() == Qt.Orientation.Horizontal:
            track_w = self.width() - padding * 2
            cy = self.height() / 2.0
            track_rect = QRectF(padding, cy - thick / 2, track_w, thick)
            painter.setBrush(LiquidTheme.TRACK)
            painter.drawRoundedRect(track_rect, thick / 2, thick / 2)

            if ratio > 0:
                painter.setBrush(fill_col)
                painter.drawRoundedRect(QRectF(padding, cy - thick / 2, max(thick, track_w * ratio), thick), thick / 2, thick / 2)

            thumb_center = QPointF(padding + track_w * ratio, cy)
        else:
            track_h = self.height() - padding * 2
            cx = self.width() / 2.0
            track_rect = QRectF(cx - thick / 2, padding, thick, track_h)
            painter.setBrush(LiquidTheme.TRACK)
            painter.drawRoundedRect(track_rect, thick / 2, thick / 2)

            # Bipolar ranges (e.g. -20..+20 dB) fill from the zero line
            if self.minimum() < 0 < self.maximum():
                zero_ratio = -self.minimum() / val_range
            else:
                zero_ratio = 0.0
            y_val = padding + track_h * (1.0 - ratio)
            y_zero = padding + track_h * (1.0 - zero_ratio)
            top, bottom = min(y_val, y_zero), max(y_val, y_zero)
            if bottom - top > 0.5:
                painter.setBrush(fill_col)
                painter.drawRoundedRect(QRectF(cx - thick / 2, top, thick, bottom - top), thick / 2, thick / 2)

            thumb_center = QPointF(cx, y_val)

        if self.always_show_thumb or active:
            r = 7.0 if self.is_dragging else 6.0
            painter.setBrush(QColor(0, 0, 0, 70))
            painter.drawEllipse(thumb_center + QPointF(0, 1), r + 1, r + 1)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(thumb_center, r, r)

        painter.end()


class LiquidGlassCard(QFrame):
    """Subtle raised surface with hairline border."""

    def __init__(self, radius=14, parent=None):
        super().__init__(parent)
        self.radius = radius
        self.bg_color = LiquidTheme.SURFACE
        self.border_color = LiquidTheme.BORDER

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.fillPath(path, self.bg_color)
        painter.setPen(QPen(self.border_color, 1))
        painter.drawPath(path)
        painter.end()


class VisualizerWidget(QWidget):
    """Animated spectrum-style bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.bars = 40
        self.values = [0.06] * self.bars
        self.targets = [0.06] * self.bars
        self.is_playing = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate_step)
        self.timer.start(40)  # 25 FPS

    def set_playing(self, playing: bool):
        self.is_playing = playing
        if not playing:
            self.targets = [0.06] * self.bars

    def _animate_step(self):
        if self.is_playing:
            for i in range(self.bars):
                freq_bias = 0.35 + 0.65 * math.sin((i / self.bars) * math.pi)
                self.targets[i] = freq_bias * random.uniform(0.15, 1.0)
        else:
            for i in range(self.bars):
                self.targets[i] = 0.06

        changed = False
        for i in range(self.bars):
            delta = (self.targets[i] - self.values[i]) * 0.3
            if abs(delta) > 0.001:
                changed = True
            self.values[i] += delta
        if changed:
            self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        w = self.width()
        h = self.height()
        gap = 3.0
        bar_w = max(2.0, (w - (self.bars - 1) * gap) / self.bars)

        # Fade out as bars settle so the idle state shows nothing
        level = max(self.values)
        fade = max(0.0, min(1.0, (level - 0.07) / 0.15))
        if fade <= 0.0:
            painter.end()
            return

        grad = QLinearGradient(0, h, 0, 0)
        grad.setColorAt(0.0, _with_alpha(LiquidTheme.ACCENT, int(255 * fade)))
        grad.setColorAt(1.0, _with_alpha(LiquidTheme.ACCENT_LIGHT, int(255 * fade)))
        painter.setBrush(QBrush(grad))

        for i, val in enumerate(self.values):
            x = i * (bar_w + gap)
            bar_h = max(bar_w, val * h)
            painter.drawRoundedRect(QRectF(x, (h - bar_h) / 2, bar_w, bar_h), bar_w / 2, bar_w / 2)

        painter.end()


def blur_pixmap(pm: QPixmap, radius: float) -> QPixmap:
    """Gaussian-style blur. Works on a quarter-size copy, which is both faster and smoother."""
    scale = 4
    small = pm.toImage().scaled(max(1, pm.width() // scale), max(1, pm.height() // scale),
                                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(small))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius / scale)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    out = QImage(small.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    scene.render(painter, QRectF(out.rect()), QRectF(0, 0, small.width(), small.height()))
    painter.end()
    result = QPixmap.fromImage(out.scaled(pm.width(), pm.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))
    result.setDevicePixelRatio(pm.devicePixelRatio())
    return result


class GlassMenu(QMenu):
    """Popup menu drawn as frosted glass: when it opens it captures what is behind it,
    blurs it, lays a dark tint over it and finishes with a thin light rim."""

    RADIUS = 10.0
    BLUR = 36
    _PAD = 24  # capture beyond the menu so the blur has real pixels at the edges

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._backdrop = None

    def showEvent(self, event):
        # Sent before the popup is on screen, so the capture doesn't include the menu itself
        self._backdrop = self._capture_backdrop()
        super().showEvent(event)

    def _capture_backdrop(self):
        geo = self.geometry()
        screen = QGuiApplication.screenAt(geo.center()) or self.screen()
        if screen is None or geo.isEmpty():
            return None
        sg = screen.geometry()
        pad = self._PAD
        grab = screen.grabWindow(0, geo.x() - sg.x() - pad, geo.y() - sg.y() - pad,
                                 geo.width() + pad * 2, geo.height() + pad * 2)
        if grab.isNull():
            return None
        blurred = blur_pixmap(grab, self.BLUR * grab.devicePixelRatio())
        dpr = blurred.devicePixelRatio()
        inner = blurred.copy(int(pad * dpr), int(pad * dpr), int(geo.width() * dpr), int(geo.height() * dpr))
        inner.setDevicePixelRatio(dpr)
        return inner

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r = self.RADIUS
        body = QPainterPath()
        body.addRoundedRect(rect, r, r)

        painter.save()
        painter.setClipPath(body)
        if self._backdrop is not None:
            painter.drawPixmap(self.rect(), self._backdrop)
        painter.fillRect(self.rect(), LiquidTheme.MENU_TINT)
        painter.restore()

        # Hairline rim: dark outline for separation, light inner edge brightest at the top
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 110), 1))
        painter.drawPath(body)
        rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        rim.setColorAt(0.0, QColor(255, 255, 255, 70))
        rim.setColorAt(min(1.0, 40 / max(1.0, rect.height())), QColor(255, 255, 255, 22))
        rim.setColorAt(1.0, QColor(255, 255, 255, 16))
        inner = QPainterPath()
        inner.addRoundedRect(rect.adjusted(1, 1, -1, -1), r - 1, r - 1)
        painter.setPen(QPen(QBrush(rim), 1))
        painter.drawPath(inner)
        painter.end()

        super().paintEvent(event)  # items, separators, arrows (styled by the stylesheet)
