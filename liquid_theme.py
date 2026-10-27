"""
Liquid Glass Theme & Visual Styling Engine
Modern dark palette, typography helpers and a crisp vector (SVG) icon set.
"""

import os
import tempfile

from PyQt6.QtGui import QColor, QPainter, QPixmap, QFont, QIcon, QLinearGradient, QPainterPath
from PyQt6.QtCore import QRectF, QByteArray, Qt
from PyQt6.QtSvg import QSvgRenderer


APP_NAME = "Prism"
APP_VERSION = "3.0"


class LiquidTheme:
    # Background & Surfaces
    BG_DARK = QColor(15, 16, 20)
    SURFACE = QColor(255, 255, 255, 9)
    SURFACE_RAISED = QColor(255, 255, 255, 14)
    BORDER = QColor(255, 255, 255, 18)
    HOVER = QColor(255, 255, 255, 20)
    PRESSED = QColor(255, 255, 255, 32)
    TRACK = QColor(255, 255, 255, 34)

    # Accent (VLC orange by default; see set_accent / ACCENT_PRESETS)
    ACCENT = QColor(255, 136, 0)
    ACCENT_SOFT = QColor(255, 136, 0, 40)
    ACCENT_HOVER = QColor(255, 163, 51)
    ACCENT_LIGHT = QColor(255, 196, 120)
    TEXT_ON_ACCENT = QColor(0, 0, 0)
    DANGER = QColor(196, 43, 28)

    # Popup menus: tint laid over the blurred backdrop
    MENU_TINT = QColor(30, 30, 33, 172)

    # Text colors
    TEXT_PRIMARY = QColor(242, 243, 245)
    TEXT_SECONDARY = QColor(154, 160, 170)
    TEXT_MUTED = QColor(95, 101, 112)
    TEXT_ON_LIGHT = QColor(15, 16, 20)

    FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]

    @classmethod
    def set_accent(cls, color: QColor):
        """Switches the colour scheme; everything accent-coloured derives from this."""
        c = QColor(color.red(), color.green(), color.blue())
        cls.ACCENT = c
        cls.ACCENT_SOFT = QColor(c.red(), c.green(), c.blue(), 40)
        cls.ACCENT_HOVER = c.lighter(118)
        cls.ACCENT_LIGHT = _mix_rgb(c, QColor(255, 255, 255), 0.45)
        luminance = (0.2126 * c.redF() ** 2.2 + 0.7152 * c.greenF() ** 2.2 + 0.0722 * c.blueF() ** 2.2)
        cls.TEXT_ON_ACCENT = QColor(0, 0, 0) if luminance > 0.3 else QColor(255, 255, 255)


ACCENT_PRESETS = [
    ("Narancs (VLC)", "#FF8800"),
    ("Kék", "#0A84FF"),
    ("Lila", "#BF5AF2"),
    ("Rózsaszín", "#FF375F"),
    ("Piros", "#FF453A"),
    ("Zöld", "#30D158"),
    ("Türkiz", "#40C8E0"),
    ("Arany", "#FFD60A"),
]


def _mix_rgb(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def ui_font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Application font at an exact pixel size."""
    font = QFont()
    font.setFamilies(LiquidTheme.FONT_FAMILIES)
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


def icon_file(name: str, color: QColor, stroke: float = 2.0) -> str:
    """Writes an icon as an .svg file (for stylesheet url() use) and returns its path."""
    hex_col = color.name(QColor.NameFormat.HexRgb)
    path = os.path.join(tempfile.gettempdir(), f"vlc_lg_{name}_{hex_col[1:]}.svg")
    if not os.path.exists(path):
        body = ICONS[name].replace("currentColor", hex_col)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{hex_col}" '
                    f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    return path.replace("\\", "/")


def rgba(color: QColor) -> str:
    """QColor -> Qt stylesheet rgba() string."""
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


# Icon set: 24x24 stroke paths (Lucide-style, ISC licensed shapes)
_SPEAKER = ('<path d="M11 4.7a.7.7 0 0 0-1.2-.5L6.4 7.6A1.4 1.4 0 0 1 5.4 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.4'
            'a1.4 1.4 0 0 1 1 .4l3.4 3.4a.7.7 0 0 0 1.2-.5z"/>')

ICONS = {
    "play": '<path d="M7 4.6v14.8a1 1 0 0 0 1.5.9l12.2-7.4a1 1 0 0 0 0-1.8L8.5 3.7A1 1 0 0 0 7 4.6z" fill="currentColor" stroke="none"/>',
    "pause": ('<rect x="6" y="4" width="4.2" height="16" rx="1.2" fill="currentColor" stroke="none"/>'
              '<rect x="13.8" y="4" width="4.2" height="16" rx="1.2" fill="currentColor" stroke="none"/>'),
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2.5" fill="currentColor" stroke="none"/>',
    "prev": '<path d="M19 19.2V4.8a.8.8 0 0 0-1.3-.6L8.6 11.4a.8.8 0 0 0 0 1.2l9.1 7.2a.8.8 0 0 0 1.3-.6z" fill="currentColor" stroke="none"/><path d="M5 5v14"/>',
    "next": '<path d="M5 4.8v14.4a.8.8 0 0 0 1.3.6l9.1-7.2a.8.8 0 0 0 0-1.2L6.3 4.2a.8.8 0 0 0-1.3.6z" fill="currentColor" stroke="none"/><path d="M19 5v14"/>',
    "rewind": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "forward": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
    "shuffle": ('<path d="m18 14 4 4-4 4"/><path d="m18 2 4 4-4 4"/>'
                '<path d="M2 18h2a4 4 0 0 0 3.3-1.7l5.4-8.6A4 4 0 0 1 16 6h6"/>'
                '<path d="M2 6h2a4 4 0 0 1 3.6 2.2"/><path d="M22 18h-6a4 4 0 0 1-3.3-1.8l-.4-.4"/>'),
    "repeat": ('<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/>'
               '<path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>'),
    "folder": ('<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4'
               'a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'),
    "volume": _SPEAKER + '<path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.4 18.4a9 9 0 0 0 0-12.8"/>',
    "mute": _SPEAKER + '<path d="m22 9-6 6"/><path d="m16 9 6 6"/>',
    "equalizer": ('<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/>'
                  '<path d="M20 21v-5"/><path d="M20 12V3"/><path d="M2 14h4"/><path d="M10 8h4"/><path d="M18 16h4"/>'),
    "playlist": ('<path d="M21 15V6"/><circle cx="18.5" cy="15.5" r="2.5"/>'
                 '<path d="M12 12H3"/><path d="M16 6H3"/><path d="M12 18H3"/>'),
    "fullscreen": ('<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/>'
                   '<path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'),
    "fullscreen-exit": ('<path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/>'
                        '<path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/>'),
    "minimize": '<path d="M5 12h14"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "restore": '<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>',
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "trash": ('<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
              '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'),
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "subtitles":'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h4"/><path d="M15 15h2"/><path d="M7 11h2"/><path d="M13 11h4"/>',
    "record": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none"/>',
}
ICONS["open"] = ICONS["folder"]
ICONS["repeat-one"] = ICONS["repeat"] + '<path d="M11 10h1v4"/>'

_renderer_cache = {}


def _renderer(name: str, color: QColor, stroke: float) -> QSvgRenderer:
    key = (name, color.rgba(), stroke)
    renderer = _renderer_cache.get(key)
    if renderer is None:
        hex_col = color.name(QColor.NameFormat.HexRgb)
        body = ICONS.get(name, ICONS["stop"]).replace("currentColor", hex_col)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
               f'stroke="{hex_col}" stroke-width="{stroke}" stroke-linecap="round" '
               f'stroke-linejoin="round" opacity="{color.alphaF():.3f}">{body}</svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        _renderer_cache[key] = renderer
    return renderer


def draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, stroke: float = 2.0):
    """Renders a named vector icon into rect."""
    _renderer(name, color, stroke).render(painter, rect)


def icon_pixmap(name: str, color: QColor, size: int, stroke: float = 2.0, dpr: float = 2.0) -> QPixmap:
    """Renders a named icon to a HiDPI pixmap (for QLabel use)."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_icon(painter, name, QRectF(0, 0, size * dpr, size * dpr), color, stroke)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


# Fraction of the icon width to move the "play" glyph left so it looks centred
PLAY_OPTICAL_SHIFT = 0.055


def app_icon_pixmap(size: int) -> QPixmap:
    """Prism logo: warm gradient tile with a dark play prism."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, LiquidTheme.ACCENT.lighter(125))
    grad.setColorAt(0.55, LiquidTheme.ACCENT)
    grad.setColorAt(1.0, LiquidTheme.ACCENT.darker(118))
    painter.fillPath(tile, grad)
    # The play glyph's box sits right of its 24x24 viewBox centre; pull it back so the
    # triangle reads as centred (bbox a hair right of centre, the usual optical correction).
    inset = size * 0.25
    glyph = size - inset * 2
    draw_icon(painter, "play", QRectF(inset - glyph * PLAY_OPTICAL_SHIFT, inset, glyph, glyph), LiquidTheme.TEXT_ON_ACCENT)
    painter.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_icon_pixmap(s))
    return icon
