"""
Prism dialogs: frameless glass modals for opening media, effects, conversion,
media information, preferences and help.
"""

import ctypes
import os
import socket
import string

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QSpinBox, QCheckBox, QTabWidget, QScrollArea,
    QProgressBar, QFileDialog, QFrame
)
from PyQt6.QtGui import QColor, QFont, QMouseEvent
from PyQt6.QtCore import Qt, QPoint

from liquid_theme import LiquidTheme, APP_NAME, APP_VERSION, ui_font, icon_file, rgba, app_icon_pixmap
from liquid_widgets import LiquidGlassButton, LiquidGlassSlider, LiquidGlassCard
import win_integration as win
from vlc_player import (VLCPlayerEngine, MediaConverter, VIDEO_ADJUST_DEFAULTS, AUDIO_EFFECTS, VIDEO_EFFECTS,
                        TRANSFORMS, LOGO_POSITIONS, PITCH_RANGE)


def combo_style() -> str:
    # Built on demand so it follows the current colour scheme
    return f"""
    QComboBox {{
        background: {rgba(LiquidTheme.SURFACE_RAISED)};
        color: {LiquidTheme.TEXT_PRIMARY.name()};
        border: 1px solid {rgba(LiquidTheme.BORDER)};
        border-radius: 8px;
        padding: 6px 12px;
        min-width: 180px;
    }}
    QComboBox:hover {{ border-color: rgba(255, 255, 255, 40); }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url("{icon_file("chevron-down", LiquidTheme.TEXT_SECONDARY)}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{
        background: #1A1B21;
        color: {LiquidTheme.TEXT_PRIMARY.name()};
        selection-background-color: {rgba(LiquidTheme.ACCENT_SOFT)};
        selection-color: {LiquidTheme.ACCENT.name()};
        border: 1px solid {rgba(LiquidTheme.BORDER)};
        outline: none;
        padding: 4px;
    }}
"""

SCROLLBAR_STYLE = """
    QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
    QScrollBar::handle:vertical { background: rgba(255, 255, 255, 40); border-radius: 3px; min-height: 24px; }
    QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 70); }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

def line_edit_style() -> str:
    # Built on demand so it follows the current colour scheme
    return f"""
    QLineEdit {{
        background: {rgba(LiquidTheme.SURFACE_RAISED)};
        color: {LiquidTheme.TEXT_PRIMARY.name()};
        border: 1px solid {rgba(LiquidTheme.BORDER)};
        border-radius: 8px;
        padding: 7px 12px;
    }}
    QLineEdit:focus {{ border-color: {LiquidTheme.ACCENT.name()}; }}
"""

def spin_style() -> str:
    # Built on demand so it follows the current colour scheme
    return f"""
    QSpinBox {{
        background: {rgba(LiquidTheme.SURFACE_RAISED)};
        color: {LiquidTheme.TEXT_PRIMARY.name()};
        border: 1px solid {rgba(LiquidTheme.BORDER)};
        border-radius: 8px;
        padding: 6px 8px;
    }}
    QSpinBox:focus {{ border-color: {LiquidTheme.ACCENT.name()}; }}
"""

def check_style() -> str:
    # Built on demand so it follows the current colour scheme
    return f"""
    QCheckBox {{ color: {LiquidTheme.TEXT_PRIMARY.name()}; spacing: 10px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 5px;
        border: 1px solid rgba(255, 255, 255, 60); background: {rgba(LiquidTheme.SURFACE_RAISED)};
    }}
    QCheckBox::indicator:checked {{
        background: {LiquidTheme.ACCENT.name()}; border-color: {LiquidTheme.ACCENT.name()};
        image: url("{icon_file("check", LiquidTheme.TEXT_ON_ACCENT, 3.0)}");
    }}
"""

def tab_style() -> str:
    # Built on demand so it follows the current colour scheme
    return f"""
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{
        background: transparent; color: {LiquidTheme.TEXT_SECONDARY.name()};
        padding: 7px 14px; margin-right: 4px; border-radius: 8px;
    }}
    QTabBar::tab:hover {{ background: rgba(255, 255, 255, 12); color: {LiquidTheme.TEXT_PRIMARY.name()}; }}
    QTabBar::tab:selected {{ background: {rgba(LiquidTheme.ACCENT_SOFT)}; color: {LiquidTheme.ACCENT.name()}; }}
"""

def progress_style() -> str:
    # Built on demand so it follows the current colour scheme
    return f"""
    QProgressBar {{
        background: {rgba(LiquidTheme.TRACK)}; border: none; border-radius: 3px; height: 6px;
    }}
    QProgressBar::chunk {{ background: {LiquidTheme.ACCENT.name()}; border-radius: 3px; }}
"""


def secondary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFont(ui_font(12))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent;
            color: {LiquidTheme.TEXT_SECONDARY.name()};
            border: 1px solid {rgba(LiquidTheme.BORDER)};
            border-radius: 8px;
            padding: 6px 16px;
        }}
        QPushButton:hover {{ background: rgba(255, 255, 255, 10); color: #FFF; }}
        QPushButton:disabled {{ color: rgba(255, 255, 255, 50); }}
    """)
    return btn


def primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFont(ui_font(12, QFont.Weight.DemiBold))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {LiquidTheme.ACCENT.name()};
            color: {LiquidTheme.TEXT_ON_ACCENT.name()};
            border: none;
            border-radius: 8px;
            padding: 6px 20px;
        }}
        QPushButton:hover {{ background: {LiquidTheme.ACCENT_HOVER.name()}; }}
        QPushButton:disabled {{ background: {rgba(QColor(LiquidTheme.ACCENT.red(), LiquidTheme.ACCENT.green(), LiquidTheme.ACCENT.blue(), 80))}; }}
    """)
    return btn


def field_label(text: str, secondary=True) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(ui_font(12))
    color = LiquidTheme.TEXT_SECONDARY if secondary else LiquidTheme.TEXT_PRIMARY
    lbl.setStyleSheet(f"color: {color.name()};")
    return lbl


def styled_combo(items=()) -> QComboBox:
    combo = QComboBox()
    combo.setFont(ui_font(13))
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    combo.setStyleSheet(combo_style())
    for label, data in items:
        combo.addItem(label, data)
    return combo


def styled_line_edit(text="", placeholder="") -> QLineEdit:
    edit = QLineEdit(text)
    edit.setFont(ui_font(13))
    edit.setPlaceholderText(placeholder)
    edit.setStyleSheet(line_edit_style())
    return edit


def styled_spin(lo: int, hi: int, value: int, step=1, suffix="") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(lo, hi)
    spin.setSingleStep(step)
    spin.setValue(value)
    spin.setSuffix(suffix)
    spin.setFont(ui_font(13))
    spin.setStyleSheet(spin_style())
    return spin


def styled_check(text: str, checked=False) -> QCheckBox:
    box = QCheckBox(text)
    box.setFont(ui_font(13))
    box.setChecked(checked)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    box.setStyleSheet(check_style())
    return box


def format_ms(ms: int) -> str:
    s = max(0, ms // 1000)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class GlassDialog(QDialog):
    """Frameless dark card with a draggable title row and a close button."""

    HEADER_HEIGHT = 48

    def __init__(self, title: str, width: int, height: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(width, height)
        self._drag_offset = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card = LiquidGlassCard(radius=14, parent=self)
        card.bg_color = QColor(24, 25, 31)
        layout.addWidget(card)

        self.body = QVBoxLayout(card)
        self.body.setContentsMargins(22, 16, 18, 20)
        self.body.setSpacing(14)

        head = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(ui_font(15, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(f"color: {LiquidTheme.TEXT_PRIMARY.name()};")
        close_btn = LiquidGlassButton(icon_name="close", size=28, variant="window-close")
        close_btn.clicked.connect(self.reject)
        head.addWidget(title_lbl)
        head.addStretch()
        head.addWidget(close_btn)
        self.body.addLayout(head)

    def add_button_row(self, *buttons):
        row = QHBoxLayout()
        row.addStretch()
        for b in buttons:
            row.addWidget(b)
        self.body.addLayout(row)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < self.HEADER_HEIGHT:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class NetworkStreamDialog(GlassDialog):
    """Open Network Stream (URL) modal."""
    def __init__(self, initial_url: str = "", parent=None):
        super().__init__("Hálózati adatfolyam megnyitása", 520, 220, parent)
        self.url = ""

        self.body.addWidget(field_label("Add meg a lejátszandó hálózati URL-t (HTTP, HTTPS, RTSP, RTMP, HLS m3u8, YouTube):"))
        self.url_edit = styled_line_edit(initial_url, "https://example.com/stream.m3u8")
        self.body.addWidget(self.url_edit)
        self.body.addStretch()

        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        play_btn = primary_button("Lejátszás")
        play_btn.setDefault(True)
        play_btn.clicked.connect(self._on_play)
        self.add_button_row(cancel_btn, play_btn)

    def _on_play(self):
        text = self.url_edit.text().strip()
        if text:
            self.url = text
            self.accept()
        else:
            self.reject()


def optical_drives() -> list:
    """Drive letters Windows reports as CD/DVD/Blu-ray drives."""
    drives = []
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i) and ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 5:
                drives.append(f"{letter}:")
    except (AttributeError, OSError):
        pass
    return drives


class DiscDialog(GlassDialog):
    """Open DVD / Blu-ray / Audio CD / VCD from a drive or a ripped folder."""

    DISC_TYPES = [("DVD (menükkel)", "dvd"), ("Blu-ray", "bluray"), ("Audio CD", "cdda"), ("VCD / SVCD", "vcd")]

    def __init__(self, parent=None):
        super().__init__("Lemez megnyitása", 500, 290, parent)
        self.mrl = ""
        self.title = ""

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.type_combo = styled_combo(self.DISC_TYPES)
        grid.addWidget(field_label("Lemez típusa"), 0, 0)
        grid.addWidget(self.type_combo, 0, 1)

        drives = optical_drives()
        self.drive_combo = styled_combo([(d, d) for d in drives])
        self.drive_combo.setEditable(True)
        if not drives:
            self.drive_combo.lineEdit().setPlaceholderText("Nincs optikai meghajtó – tallózz mappát")
        browse_btn = secondary_button("Tallózás...")
        browse_btn.clicked.connect(self._browse)
        drive_row = QHBoxLayout()
        drive_row.addWidget(self.drive_combo, stretch=1)
        drive_row.addWidget(browse_btn)
        grid.addWidget(field_label("Meghajtó / mappa"), 1, 0)
        grid.addLayout(drive_row, 1, 1)
        self.body.addLayout(grid)

        hint = field_label("Mappa esetén a VIDEO_TS (DVD) vagy BDMV (Blu-ray) szülőmappáját válaszd.")
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        self.body.addStretch()

        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        play_btn = primary_button("Lejátszás")
        play_btn.clicked.connect(self._on_play)
        self.add_button_row(cancel_btn, play_btn)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Lemezmappa kiválasztása")
        if folder:
            self.drive_combo.setEditText(os.path.normpath(folder))

    def _on_play(self):
        target = self.drive_combo.currentText().strip()
        if not target:
            return
        kind = self.type_combo.currentData()
        path = target.replace("\\", "/")
        if not path.endswith("/"):
            path += "/"
        self.mrl = f"{kind}:///{path}"
        self.title = f"{self.type_combo.currentText().split(' (')[0]} – {target}"
        self.accept()


class CaptureDialog(GlassDialog):
    """Open a capture source: the desktop or a DirectShow camera."""

    def __init__(self, parent=None):
        super().__init__("Rögzítőeszköz megnyitása", 460, 260, parent)
        self.mrl = ""
        self.title = ""
        self.options = []

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.mode_combo = styled_combo([("Képernyő (asztal)", "screen"), ("Webkamera / rögzítőkártya", "dshow")])
        self.fps_spin = styled_spin(1, 60, 30, suffix=" fps")
        grid.addWidget(field_label("Forrás"), 0, 0)
        grid.addWidget(self.mode_combo, 0, 1)
        grid.addWidget(field_label("Képkockasebesség"), 1, 0)
        grid.addWidget(self.fps_spin, 1, 1)
        self.body.addLayout(grid)
        self.mode_combo.currentIndexChanged.connect(lambda: self.fps_spin.setEnabled(self.mode_combo.currentData() == "screen"))

        hint = field_label("A webkamera módban a Windows alapértelmezett eszköze nyílik meg.")
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        self.body.addStretch()

        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        play_btn = primary_button("Lejátszás")
        play_btn.clicked.connect(self._on_play)
        self.add_button_row(cancel_btn, play_btn)

    def _on_play(self):
        if self.mode_combo.currentData() == "screen":
            self.mrl = "screen://"
            self.title = "Képernyő"
            self.options = [f":screen-fps={self.fps_spin.value()}", ":live-caching=300"]
        else:
            self.mrl = "dshow://"
            self.title = "Webkamera"
            self.options = [":live-caching=300"]
        self.accept()


class JumpToTimeDialog(GlassDialog):
    """Jump to specific timestamp dialog."""
    def __init__(self, current_ms: int, total_ms: int, parent=None):
        super().__init__("Ugrás időpontra", 380, 220, parent)
        self.target_ms = None

        cur_sec = current_ms // 1000
        spin_row = QHBoxLayout()
        spin_row.setSpacing(8)
        self.h_spin = styled_spin(0, 99, cur_sec // 3600)
        self.m_spin = styled_spin(0, 59, (cur_sec % 3600) // 60)
        self.s_spin = styled_spin(0, 59, cur_sec % 60)
        for spin, unit in [(self.h_spin, "óra"), (self.m_spin, "perc"), (self.s_spin, "mp")]:
            spin.setFont(ui_font(15, QFont.Weight.Bold))
            box = QVBoxLayout()
            box.addWidget(spin)
            lbl = field_label(unit)
            lbl.setFont(ui_font(10))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(lbl)
            spin_row.addLayout(box)
        self.body.addLayout(spin_row)
        if total_ms > 0:
            self.body.addWidget(field_label(f"Teljes hossz: {format_ms(total_ms)}"))

        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        jump_btn = primary_button("Ugrás")
        jump_btn.setDefault(True)
        jump_btn.clicked.connect(self._on_jump)
        self.add_button_row(cancel_btn, jump_btn)

    def _on_jump(self):
        sec = self.h_spin.value() * 3600 + self.m_spin.value() * 60 + self.s_spin.value()
        self.target_ms = sec * 1000
        self.accept()


def _scroll_page(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(inner)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }" + SCROLLBAR_STYLE)
    return area


def _info_rows(rows, layout: QVBoxLayout):
    for k, v in rows:
        row = QHBoxLayout()
        lbl_k = field_label(k)
        lbl_k.setFixedWidth(130)
        lbl_k.setFont(ui_font(12, QFont.Weight.DemiBold))
        lbl_v = field_label(str(v), secondary=False)
        lbl_v.setWordWrap(True)
        lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(lbl_k, alignment=Qt.AlignmentFlag.AlignTop)
        row.addWidget(lbl_v, stretch=1)
        layout.addLayout(row)


class MediaInfoDialog(GlassDialog):
    """Media metadata and per-track codec details."""

    META_LABELS = [("title", "Cím"), ("artist", "Előadó"), ("album", "Album"), ("genre", "Műfaj"),
                   ("date", "Dátum"), ("track", "Sorszám"), ("description", "Leírás"),
                   ("copyright", "Szerzői jog"), ("publisher", "Kiadó"), ("encoded_by", "Kódolta"),
                   ("language", "Nyelv")]

    def __init__(self, details: dict, video_size, start_tab: int = 0, parent=None):
        super().__init__("Média információk", 560, 460, parent)

        tabs = QTabWidget()
        tabs.setFont(ui_font(12))
        tabs.setStyleSheet(tab_style())

        # General
        general = QWidget()
        g_layout = QVBoxLayout(general)
        g_layout.setContentsMargins(0, 10, 8, 0)
        g_layout.setSpacing(10)
        path = details.get("path") or "Nincs betöltve"
        rows = [("Fájlnév", os.path.basename(path.rstrip("/\\")) or path)]
        meta = details.get("meta", {})
        rows += [(label, meta[key]) for key, label in self.META_LABELS if key in meta]
        if details.get("duration_ms"):
            rows.append(("Hossz", format_ms(details["duration_ms"])))
        if video_size and video_size[0] > 0:
            rows.append(("Felbontás", f"{video_size[0]} × {video_size[1]}"))
        rows.append(("Hely", path))
        _info_rows(rows, g_layout)
        g_layout.addStretch()
        tabs.addTab(_scroll_page(general), "Általános")

        # Codecs
        codecs = QWidget()
        c_layout = QVBoxLayout(codecs)
        c_layout.setContentsMargins(0, 10, 8, 0)
        c_layout.setSpacing(10)
        tracks = details.get("tracks", [])
        if not tracks:
            c_layout.addWidget(field_label("A kodekadatok lejátszás közben érhetők el."))
        kind_names = {"video": "Videó", "audio": "Hang", "subtitle": "Felirat"}
        for i, t in enumerate(tracks):
            heading = QLabel(f"{i + 1}. sáv – {kind_names[t['kind']]}")
            heading.setFont(ui_font(13, QFont.Weight.DemiBold))
            heading.setStyleSheet(f"color: {LiquidTheme.ACCENT.name()};")
            c_layout.addWidget(heading)
            rows = [("Kodek", t["codec"] or "ismeretlen")]
            if t["kind"] == "video":
                rows.append(("Felbontás", f"{t['width']} × {t['height']}"))
                if t["fps"]:
                    rows.append(("Képkocka/mp", f"{t['fps']:.3f}".rstrip("0").rstrip(".")))
            elif t["kind"] == "audio":
                rows.append(("Csatornák", t["channels"]))
                rows.append(("Mintavétel", f"{t['rate']} Hz"))
            if t["bitrate"]:
                rows.append(("Bitráta", f"{t['bitrate'] // 1000} kb/s"))
            if t["language"]:
                rows.append(("Nyelv", t["language"]))
            if t["description"]:
                rows.append(("Leírás", t["description"]))
            _info_rows(rows, c_layout)
        c_layout.addStretch()
        tabs.addTab(_scroll_page(codecs), "Kodekek")

        tabs.setCurrentIndex(start_tab)
        self.body.addWidget(tabs, stretch=1)

        ok_btn = primary_button("Rendben")
        ok_btn.clicked.connect(self.accept)
        self.add_button_row(ok_btn)


SHORTCUTS = [
    ("Szóköz", "Lejátszás / Szünet"),
    ("S", "Leállítás"),
    ("N / P", "Következő / Előző szám"),
    ("E", "Következő képkocka"),
    ("Balra / Jobbra", "Ugrás hátra / előre (alapból 10 mp)"),
    ("Shift + Balra / Jobbra", "Kis ugrás (3 mp)"),
    ("Ctrl + Balra / Jobbra", "Nagy ugrás (1 perc)"),
    ("[ / ] / =", "Lassabb / Gyorsabb / Normál sebesség"),
    ("Felfelé / Lefelé", "Hangerő növelése / csökkentése"),
    ("M", "Némítás ki/be"),
    ("L", "Ismétlési mód váltása"),
    ("R", "Véletlenszerű lejátszás ki/be"),
    ("B", "Hangsáv váltása"),
    ("V", "Feliratsáv váltása"),
    ("A / C / Z", "Képarány / Levágás / Nagyítás váltása"),
    ("D", "Deinterlace ki/be"),
    ("F", "Teljes képernyő"),
    ("Escape", "Teljes képernyő elhagyása"),
    ("G / H", "Felirat késleltetés −50 / +50 ms"),
    ("J / K", "Hang késleltetés −50 / +50 ms"),
    ("Shift + S", "Pillanatkép"),
    ("Ctrl + O", "Fájl megnyitása"),
    ("Ctrl + Shift + O", "Fájlok hozzáadása a listához"),
    ("Ctrl + F", "Mappa megnyitása"),
    ("Ctrl + D", "Lemez megnyitása"),
    ("Ctrl + N", "Hálózati adatfolyam"),
    ("Ctrl + C", "Rögzítőeszköz (képernyő, webkamera)"),
    ("Ctrl + V", "URL megnyitása a vágólapról"),
    ("Ctrl + Y", "Lejátszási lista mentése"),
    ("Ctrl + R", "Konvertálás / Mentés"),
    ("Ctrl + S", "Adatfolyam küldése (Stream)"),
    ("Ctrl + B", "Könyvjelző hozzáadása"),
    ("Ctrl + T", "Ugrás időpontra"),
    ("Ctrl + E", "Effektek és szűrők"),
    ("Ctrl + I / Ctrl + J", "Média információk / Kodekek"),
    ("Ctrl + L", "Lejátszási lista"),
    ("Ctrl + H", "Minimalista nézet"),
    ("Ctrl + P", "Beállítások"),
    ("Ctrl + Q", "Kilépés"),
]


class ShortcutsDialog(GlassDialog):
    """Keyboard shortcuts modal; entries default to the built-in list."""
    def __init__(self, parent=None, entries=None):
        super().__init__("Billentyűparancsok", 560, 540, parent)

        inner = QWidget()
        grid = QVBoxLayout(inner)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(6)
        for key, desc in entries or SHORTCUTS:
            row = QHBoxLayout()
            k_lbl = QLabel(key)
            k_lbl.setFixedWidth(170)
            k_lbl.setFont(ui_font(12, QFont.Weight.DemiBold))
            k_lbl.setStyleSheet(f"""
                background: {rgba(LiquidTheme.SURFACE_RAISED)};
                color: {LiquidTheme.ACCENT.name()};
                padding: 3px 8px;
                border-radius: 4px;
                border: 1px solid {rgba(LiquidTheme.BORDER)};
            """)
            row.addWidget(k_lbl)
            row.addWidget(field_label(desc, secondary=False), stretch=1)
            grid.addLayout(row)
        grid.addStretch()
        self.body.addWidget(_scroll_page(inner), stretch=1)

        ok_btn = primary_button("Bezárás")
        ok_btn.clicked.connect(self.accept)
        self.add_button_row(ok_btn)


class AboutDialog(GlassDialog):
    """About Prism modal."""
    def __init__(self, parent=None):
        super().__init__("Névjegy", 460, 290, parent)

        head = QHBoxLayout()
        head.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(app_icon_pixmap(64))
        head.addWidget(logo)
        names = QVBoxLayout()
        app_title = QLabel(f"{APP_NAME} Player")
        app_title.setFont(ui_font(22, QFont.Weight.Bold))
        app_title.setStyleSheet(f"color: {LiquidTheme.ACCENT.name()};")
        names.addWidget(app_title)
        names.addWidget(field_label(f"Verzió {APP_VERSION} · Liquid Glass Edition"))
        head.addLayout(names)
        head.addStretch()
        self.body.addLayout(head)

        desc = field_label(
            "Motor: hivatalos 64-bites VideoLAN LibVLC\n"
            "Felület: PyQt6 Liquid Glass & SVG vektoros ikonok\n\n"
            "Minden formátum, amit a VLC ismer, hardveres gyorsítással.",
            secondary=False)
        self.body.addWidget(desc)
        self.body.addStretch()

        ok_btn = primary_button("Rendben")
        ok_btn.clicked.connect(self.accept)
        self.add_button_row(ok_btn)


class ParamSlider(QWidget):
    """Labelled slider for one float/int filter option; emits the converted value."""

    def __init__(self, label: str, kind: str, lo, hi, value, step, on_change, parent=None):
        super().__init__(parent)
        self.kind, self.step = kind, step
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        name = field_label(label)
        name.setFixedWidth(150)
        self.slider = LiquidGlassSlider(Qt.Orientation.Horizontal, always_show_thumb=True)
        self.slider.setRange(round(lo / step), round(hi / step))
        self.value_lbl = field_label("")
        self.value_lbl.setFixedWidth(52)
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(name)
        row.addWidget(self.slider, stretch=1)
        row.addWidget(self.value_lbl)
        self.set_value(value)
        self.slider.valueChanged.connect(lambda _: (self._show(), on_change(self.value())))

    def value(self):
        v = self.slider.value() * self.step
        return int(round(v)) if self.kind == "i" else round(float(v), 4)

    def set_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round(value / self.step))
        self.slider.blockSignals(False)
        self.slider.update()
        self._show()

    def _show(self):
        v = self.value()
        self.value_lbl.setText(str(v) if self.kind == "i" else f"{v:.2f}".rstrip("0").rstrip("."))


class EffectPanel(QWidget):
    """On/off switch plus option sliders for each filter of an AUDIO_EFFECTS/VIDEO_EFFECTS list."""

    def __init__(self, effects, active: set, params: dict, set_effect, set_param, parent=None):
        super().__init__(parent)
        self.effects, self.active, self.params = effects, active, params
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 8, 4)
        layout.setSpacing(8)
        self.checks, self.sliders = {}, {}
        for name, label, options in effects:
            check = styled_check(label, name in active)
            check.setFont(ui_font(13, QFont.Weight.DemiBold))
            check.toggled.connect(lambda on, n=name: set_effect(n, on))
            layout.addWidget(check)
            self.checks[name] = check
            for var, opt_label, kind, lo, hi, default, step in options:
                slider = ParamSlider(opt_label, kind, lo, hi, params.get(var, default), step,
                                     lambda v, n=var: set_param(n, v))
                slider.setContentsMargins(26, 0, 0, 0)
                layout.addWidget(slider)
                self.sliders[var] = slider
            layout.addSpacing(4)
        layout.addStretch()

    def refresh(self):
        for name, check in self.checks.items():
            check.blockSignals(True)
            check.setChecked(name in self.active)
            check.blockSignals(False)
        for var, slider in self.sliders.items():
            slider.set_value(self.params[var])


class EffectsDialog(GlassDialog):
    """Equalizer, audio effects, video adjustments/geometry/filters, logo overlay and track sync (non-modal)."""

    TAB_EQ, TAB_AUDIO, TAB_VIDEO, TAB_GEOMETRY, TAB_FILTERS, TAB_OVERLAY, TAB_SYNC = range(7)

    def __init__(self, player_engine: VLCPlayerEngine, osd=None, parent=None):
        super().__init__("Effektek és szűrők", 760, 540, parent)
        self.setModal(False)
        self.player_engine = player_engine
        self.osd = osd or (lambda text: None)
        self._resetting = False

        self.tabs = QTabWidget()
        self.tabs.setFont(ui_font(12))
        self.tabs.setStyleSheet(tab_style())
        self.tabs.addTab(self._build_eq_tab(), "Hangszínszabályzó")
        self.tabs.addTab(self._build_audio_effects_tab(), "Hangeffektek")
        self.tabs.addTab(self._build_video_tab(), "Képbeállítások")
        self.tabs.addTab(self._build_geometry_tab(), "Geometria")
        self.tabs.addTab(self._build_filters_tab(), "Videószűrők")
        self.tabs.addTab(self._build_overlay_tab(), "Logó")
        self.tabs.addTab(self._build_sync_tab(), "Szinkronizálás")
        self.body.addWidget(self.tabs, stretch=1)

    # --- Audio effects ---
    def _build_audio_effects_tab(self) -> QWidget:
        engine = self.player_engine
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.pitch_slider = ParamSlider("Hangmagasság (félhang)", "f", PITCH_RANGE[0], PITCH_RANGE[1],
                                        engine.pitch, 0.5, self._on_pitch)
        reset_btn = secondary_button("Alaphelyzet")
        reset_btn.clicked.connect(self._reset_audio_effects)
        top.addWidget(self.pitch_slider, stretch=1)
        top.addSpacing(10)
        top.addWidget(reset_btn)
        layout.addLayout(top)

        self.audio_panel = EffectPanel(AUDIO_EFFECTS, engine.audio_effects, engine.audio_params,
                                       self._on_audio_effect, engine.set_audio_param)
        layout.addWidget(_scroll_page(self.audio_panel), stretch=1)
        return page

    def _on_pitch(self, semitones: float):
        self.player_engine.set_pitch(semitones)
        self.osd(f"Hangmagasság: {semitones:+g} félhang")

    def _on_audio_effect(self, name: str, on: bool):
        self.player_engine.set_audio_effect(name, on)
        label = next(l for n, l, _ in AUDIO_EFFECTS if n == name)
        self.osd(f"{label.split(' (')[0]}: {'be' if on else 'ki'}")

    def _reset_audio_effects(self):
        self.player_engine.reset_effects(audio=True, video=False)
        self.audio_panel.params = self.player_engine.audio_params
        self.audio_panel.refresh()
        self.pitch_slider.set_value(0.0)

    # --- Geometry ---
    def _build_geometry_tab(self) -> QWidget:
        engine = self.player_engine
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 8, 0)
        layout.setSpacing(14)

        row = QHBoxLayout()
        row.addWidget(field_label("Forgatás / tükrözés"))
        self.transform_combo = styled_combo(TRANSFORMS)
        self.transform_combo.setCurrentIndex(max(0, self.transform_combo.findData(engine.transform)))
        self.transform_combo.currentIndexChanged.connect(
            lambda _: self._on_transform(self.transform_combo.currentData()))
        row.addWidget(self.transform_combo)
        row.addStretch()
        layout.addLayout(row)

        self.rotate_check = styled_check("Szabad forgatás", engine.rotate_enabled)
        self.rotate_check.toggled.connect(lambda on: engine.set_rotation(on))
        layout.addWidget(self.rotate_check)
        self.rotate_slider = ParamSlider("Szög (fok)", "f", 0, 359, engine.rotate_angle, 1, self._on_rotate_angle)
        layout.addWidget(self.rotate_slider)

        hint = field_label("A forgatás és tükrözés azonnal érvényes; a 90°-os forgatás a képarányt is megfordítja.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        return page

    def _on_rotate_angle(self, angle: float):
        # Moving the slider implies "on"
        self.player_engine.set_rotation(True, angle)
        if not self.rotate_check.isChecked():
            self.rotate_check.blockSignals(True)
            self.rotate_check.setChecked(True)
            self.rotate_check.blockSignals(False)

    def _on_transform(self, kind):
        self.player_engine.set_transform(kind)
        self.osd(f"Geometria: {self.transform_combo.currentText()}")

    # --- Video filters ---
    def _build_filters_tab(self) -> QWidget:
        engine = self.player_engine
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(field_label("A szűrők lejátszás közben, azonnal kapcsolhatók."))
        top.addStretch()
        reset_btn = secondary_button("Mind kikapcsolása")
        reset_btn.clicked.connect(self._reset_video_filters)
        top.addWidget(reset_btn)
        layout.addLayout(top)
        self.video_panel = EffectPanel(VIDEO_EFFECTS, engine.video_effects, engine.video_params,
                                       self._on_video_effect, engine.set_video_param)
        layout.addWidget(_scroll_page(self.video_panel), stretch=1)
        return page

    def _on_video_effect(self, name: str, on: bool):
        self.player_engine.set_video_effect(name, on)
        label = next(l for n, l, _ in VIDEO_EFFECTS if n == name)
        self.osd(f"{label}: {'be' if on else 'ki'}")

    def _reset_video_filters(self):
        self.player_engine.clear_video_effects()
        self.video_panel.refresh()

    # --- Logo overlay ---
    def _build_overlay_tab(self) -> QWidget:
        logo = self.player_engine.logo
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 8, 0)
        layout.setSpacing(12)

        self.logo_check = styled_check("Logó megjelenítése a videón", logo["enabled"])
        self.logo_check.toggled.connect(lambda _: self._apply_logo())
        layout.addWidget(self.logo_check)

        file_row = QHBoxLayout()
        self.logo_edit = styled_line_edit(logo["file"], "PNG kép (átlátszósággal)")
        self.logo_edit.editingFinished.connect(self._apply_logo)
        browse = secondary_button("Tallózás...")
        browse.clicked.connect(self._browse_logo)
        file_row.addWidget(self.logo_edit, stretch=1)
        file_row.addWidget(browse)
        layout.addLayout(file_row)

        pos_row = QHBoxLayout()
        pos_row.addWidget(field_label("Pozíció"))
        self.logo_pos = styled_combo(LOGO_POSITIONS)
        self.logo_pos.setCurrentIndex(max(0, self.logo_pos.findData(logo["position"])))
        self.logo_pos.currentIndexChanged.connect(lambda _: self._apply_logo())
        pos_row.addWidget(self.logo_pos)
        pos_row.addStretch()
        layout.addLayout(pos_row)

        self.logo_opacity = ParamSlider("Átlátszatlanság", "i", 0, 255, logo["opacity"], 1, lambda _: self._apply_logo())
        layout.addWidget(self.logo_opacity)
        self.logo_margin = ParamSlider("Margó (px)", "i", 0, 200, logo["x"], 1, lambda _: self._apply_logo())
        layout.addWidget(self.logo_margin)
        layout.addStretch()
        return page

    def _browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Logó kiválasztása", "", "Képek (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.logo_edit.setText(os.path.normpath(path))
            if not self.logo_check.isChecked():
                self.logo_check.setChecked(True)  # toggled applies it
            else:
                self._apply_logo()

    def _apply_logo(self):
        margin = self.logo_margin.value()
        self.player_engine.set_logo(self.logo_check.isChecked(), self.logo_edit.text().strip(),
                                    self.logo_opacity.value(), self.logo_pos.currentData(), margin, margin)

    # --- Equalizer ---
    def _build_eq_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.eq_enable = styled_check("Bekapcsolva", self.player_engine.eq_enabled)
        self.eq_enable.toggled.connect(self.player_engine.set_equalizer_enabled)
        self.preset_combo = styled_combo([("Egyéni", None)] + [(n, i) for i, n in self.player_engine.get_equalizer_presets()])
        current = self.preset_combo.findData(self.player_engine.eq_preset_index)
        self.preset_combo.setCurrentIndex(max(0, current))
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        top.addWidget(self.eq_enable)
        top.addStretch()
        top.addWidget(field_label("Előbeállítás"))
        top.addWidget(self.preset_combo)
        layout.addLayout(top)

        sliders_layout = QHBoxLayout()
        sliders_layout.setSpacing(6)
        self.preamp_slider = self._eq_column(sliders_layout, "Erősítés", round(self.player_engine.get_equalizer_preamp()))
        self.preamp_slider.valueChanged.connect(self.player_engine.set_equalizer_preamp)
        sliders_layout.addSpacing(10)

        self.band_sliders = []
        bands = self.player_engine.get_equalizer_bands()
        for band, freq in enumerate(["60", "170", "310", "600", "1k", "3k", "6k", "12k", "14k", "16k"]):
            slider = self._eq_column(sliders_layout, freq, round(bands[band]) if band < len(bands) else 0)
            slider.valueChanged.connect(lambda val, b=band: self._on_band_changed(b, val))
            self.band_sliders.append(slider)
        layout.addLayout(sliders_layout)
        return page

    @staticmethod
    def _eq_column(row: QHBoxLayout, label: str, value: int) -> LiquidGlassSlider:
        v_box = QVBoxLayout()
        v_box.setSpacing(6)
        slider = LiquidGlassSlider(orientation=Qt.Orientation.Vertical)
        slider.setRange(-20, 20)
        slider.setValue(value)
        slider.setFixedHeight(170)
        slider.setToolTip(f"{label}: {value} dB")
        slider.valueChanged.connect(lambda v, s=slider, l=label: s.setToolTip(f"{l}: {v} dB"))
        lbl = field_label(label)
        lbl.setFont(ui_font(11))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_box.addWidget(slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        v_box.addWidget(lbl)
        row.addLayout(v_box)
        return slider

    def _on_preset_selected(self, index):
        preset_id = self.preset_combo.currentData()
        if preset_id is None:
            return
        self.player_engine.set_equalizer_preset(preset_id)
        # Mirror the preset's curve on the sliders without re-applying it
        values = [(self.preamp_slider, self.player_engine.get_equalizer_preamp())]
        values += list(zip(self.band_sliders, self.player_engine.get_equalizer_bands()))
        for slider, amp in values:
            slider.blockSignals(True)
            slider.setValue(round(amp))
            slider.blockSignals(False)
            slider.update()
        self.eq_enable.setChecked(True)

    def _on_band_changed(self, band: int, value: int):
        self.player_engine.set_equalizer_band(band, value)
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)  # manual tweak -> custom curve
        self.preset_combo.blockSignals(False)

    # --- Video adjustments ---
    VIDEO_SLIDERS = [
        # key, label, slider range, slider->value factor
        ("contrast", "Kontraszt", (0, 200), 0.01),
        ("brightness", "Fényerő", (0, 200), 0.01),
        ("hue", "Színárnyalat", (-180, 180), 1.0),
        ("saturation", "Telítettség", (0, 300), 0.01),
        ("gamma", "Gamma", (1, 1000), 0.01),
    ]

    def _build_video_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 8, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.adjust_enable = styled_check("Képbeállítások engedélyezése", self.player_engine.video_adjust_enabled)
        self.adjust_enable.toggled.connect(lambda _: self._apply_video())
        reset_btn = secondary_button("Alaphelyzet")
        reset_btn.clicked.connect(self._reset_video)
        top.addWidget(self.adjust_enable)
        top.addStretch()
        top.addWidget(reset_btn)
        layout.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self.video_sliders = {}
        for row, (key, label, (lo, hi), factor) in enumerate(self.VIDEO_SLIDERS):
            slider = LiquidGlassSlider(Qt.Orientation.Horizontal, always_show_thumb=True)
            slider.setRange(lo, hi)
            slider.setValue(round(self.player_engine.video_adjust[key] / factor))
            value_lbl = field_label("")
            value_lbl.setFixedWidth(48)
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            slider.valueChanged.connect(lambda v, l=value_lbl, f=factor: l.setText(f"{v * f:.2f}" if f < 1 else f"{v}°"))
            slider.valueChanged.connect(lambda _: self._apply_video())
            value_lbl.setText(f"{slider.value() * factor:.2f}" if factor < 1 else f"{slider.value()}°")
            grid.addWidget(field_label(label), row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value_lbl, row, 2)
            self.video_sliders[key] = (slider, factor)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _apply_video(self):
        if self._resetting:
            return
        values = {key: slider.value() * factor for key, (slider, factor) in self.video_sliders.items()}
        if self.sender() is not self.adjust_enable and not self.adjust_enable.isChecked():
            self.adjust_enable.setChecked(True)  # moving a slider implies "on"; toggled re-enters here
            return
        self.player_engine.set_video_adjust(self.adjust_enable.isChecked(), **values)

    def _reset_video(self):
        self._resetting = True
        for key, (slider, factor) in self.video_sliders.items():
            slider.setValue(round(VIDEO_ADJUST_DEFAULTS[key] / factor))
        self._resetting = False
        self.adjust_enable.setChecked(False)
        self.player_engine.set_video_adjust(False, **VIDEO_ADJUST_DEFAULTS)

    # --- Synchronisation ---
    def _build_sync_tab(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 16, 8, 0)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(14)

        self.audio_delay_spin = styled_spin(-10000, 10000, self.player_engine.get_audio_delay(), 50, " ms")
        self.audio_delay_spin.valueChanged.connect(self._on_audio_delay)
        self.sub_delay_spin = styled_spin(-60000, 60000, self.player_engine.get_spu_delay(), 50, " ms")
        self.sub_delay_spin.valueChanged.connect(self._on_sub_delay)

        layout.addWidget(field_label("Hang késleltetés"), 0, 0)
        layout.addWidget(self.audio_delay_spin, 0, 1)
        layout.addWidget(field_label("Felirat késleltetés"), 1, 0)
        layout.addWidget(self.sub_delay_spin, 1, 1)
        hint = field_label("Pozitív érték: a hang / felirat később jelenik meg a képhez képest.")
        hint.setWordWrap(True)
        layout.addWidget(hint, 2, 0, 1, 2)
        reset_btn = secondary_button("Visszaállítás")
        reset_btn.clicked.connect(lambda: (self.audio_delay_spin.setValue(0), self.sub_delay_spin.setValue(0)))
        layout.addWidget(reset_btn, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setRowStretch(4, 1)
        layout.setColumnStretch(1, 1)
        return page

    def _on_audio_delay(self, ms: int):
        self.player_engine.set_audio_delay(ms)
        self.osd(f"Hang késleltetés: {ms} ms")

    def _on_sub_delay(self, ms: int):
        self.player_engine.set_spu_delay(ms)
        self.osd(f"Felirat késleltetés: {ms} ms")

    def refresh_sync(self):
        for spin, value in ((self.audio_delay_spin, self.player_engine.get_audio_delay()),
                            (self.sub_delay_spin, self.player_engine.get_spu_delay())):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class ConvertDialog(GlassDialog):
    """Transcode a file (Convert/Save) or serve it as an HTTP stream (non-modal)."""

    _A = "channels=2,samplerate=44100"
    FILE_PROFILES = [
        # label, extension, transcode chain, mux
        ("Videó – H.264 + AAC (MP4)", "mp4", f"#transcode{{vcodec=h264,vb=2500,acodec=mp4a,ab=192,{_A}}}", "mp4"),
        ("Videó – H.264 + MP3 (TS)", "ts", f"#transcode{{vcodec=h264,vb=2500,acodec=mpga,ab=192,{_A}}}", "ts"),
        ("Hang – MP3", "mp3", f"#transcode{{vcodec=none,acodec=mp3,ab=192,{_A}}}", "raw"),
        ("Hang – AAC (M4A)", "m4a", f"#transcode{{vcodec=none,acodec=mp4a,ab=192,{_A}}}", "mp4"),
        ("Hang – FLAC (veszteségmentes)", "flac", f"#transcode{{vcodec=none,acodec=flac,{_A}}}", "raw"),
        ("Hang – OGG Vorbis", "ogg", f"#transcode{{vcodec=none,acodec=vorb,ab=192,{_A}}}", "ogg"),
        ("Hang – WAV", "wav", f"#transcode{{vcodec=none,acodec=s16l,{_A}}}", "wav"),
    ]
    AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".ape", ".mka", ".ac3", ".dts"}
    STREAM_PROFILES = [
        ("Videó – H.264 + MP3 (TS)", "", f"#transcode{{vcodec=h264,vb=2000,acodec=mpga,ab=160,{_A}}}", "ts"),
        ("Hang – MP3", "", f"#transcode{{vcodec=none,acodec=mp3,ab=192,{_A}}}", "raw"),
    ]

    def __init__(self, player_engine: VLCPlayerEngine, source: str = "", stream: bool = False, parent=None):
        super().__init__("Adatfolyam küldése" if stream else "Konvertálás / Mentés", 560, 330, parent)
        self.setModal(False)
        self.stream = stream
        self.converter = MediaConverter(player_engine.instance, self)
        self.converter.progress.connect(self._on_progress)
        self.converter.finished.connect(self._on_finished)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.source_edit = styled_line_edit(source, "Fájl vagy URL")
        src_btn = secondary_button("Tallózás...")
        src_btn.clicked.connect(self._browse_source)
        src_row = QHBoxLayout()
        src_row.addWidget(self.source_edit, stretch=1)
        src_row.addWidget(src_btn)
        grid.addWidget(field_label("Forrás"), 0, 0)
        grid.addLayout(src_row, 0, 1)

        profiles = self.STREAM_PROFILES if stream else self.FILE_PROFILES
        self.profile_combo = styled_combo([(p[0], p) for p in profiles])
        if os.path.splitext(source)[1].lower() in self.AUDIO_EXTS:
            self.profile_combo.setCurrentIndex(next(i for i, p in enumerate(profiles) if p[0].startswith("Hang")))
        grid.addWidget(field_label("Profil"), 1, 0)
        grid.addWidget(self.profile_combo, 1, 1)

        if stream:
            self.port_spin = styled_spin(1024, 65535, 8080)
            grid.addWidget(field_label("HTTP port"), 2, 0)
            grid.addWidget(self.port_spin, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        else:
            self.dest_edit = styled_line_edit("", "Célfájl")
            dst_btn = secondary_button("Mentés másként...")
            dst_btn.clicked.connect(self._browse_dest)
            dst_row = QHBoxLayout()
            dst_row.addWidget(self.dest_edit, stretch=1)
            dst_row.addWidget(dst_btn)
            grid.addWidget(field_label("Cél"), 2, 0)
            grid.addLayout(dst_row, 2, 1)
            self.profile_combo.currentIndexChanged.connect(self._suggest_dest)
            self.source_edit.textChanged.connect(self._suggest_dest)
            self._suggest_dest()
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet(progress_style())
        self.progress.setVisible(not stream)
        self.body.addWidget(self.progress)
        self.status_lbl = field_label("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(self.status_lbl)
        self.body.addStretch()

        self.close_btn = secondary_button("Bezárás")
        self.close_btn.clicked.connect(self.reject)
        self.start_btn = primary_button("Indítás")
        self.start_btn.clicked.connect(self._toggle)
        self.add_button_row(self.close_btn, self.start_btn)

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Forrás kiválasztása", "", "Minden fájl (*.*)")
        if path:
            self.source_edit.setText(os.path.normpath(path))

    def _browse_dest(self):
        ext = self.profile_combo.currentData()[1]
        path, _ = QFileDialog.getSaveFileName(self, "Mentés másként", self.dest_edit.text(), f"*.{ext}")
        if path:
            self.dest_edit.setText(os.path.normpath(path))

    def _suggest_dest(self):
        src = self.source_edit.text().strip()
        ext = self.profile_combo.currentData()[1]
        if src and os.path.exists(src):
            base = os.path.splitext(src)[0]
            candidate = f"{base}.{ext}"
            if os.path.normcase(candidate) == os.path.normcase(src):
                candidate = f"{base} (konvertált).{ext}"
            self.dest_edit.setText(candidate)

    def _toggle(self):
        if self.converter.is_running():
            self.converter.cancel()
            self._set_running(False)
            self.status_lbl.setText("Megszakítva.")
            return
        src = self.source_edit.text().strip()
        if not src:
            self.status_lbl.setText("Adj meg egy forrást.")
            return
        _, _, transcode, mux = self.profile_combo.currentData()
        if self.stream:
            port = self.port_spin.value()
            sout = f"{transcode}:http{{mux={mux},dst=:{port}/}}"
            started_msg = f"Adatfolyam fut:  http://{local_ip()}:{port}/\nNyisd meg ezt a címet egy másik eszközön (pl. VLC-ben)."
        else:
            dst = self.dest_edit.text().strip()
            if not dst:
                self.status_lbl.setText("Adj meg egy célfájlt.")
                return
            # LibVLC's option parser eats backslashes inside quoted values
            sout = f"{transcode}:std{{access=file,mux={mux},dst='{dst.replace(chr(92), '/')}'}}"
            started_msg = "Konvertálás folyamatban..."
        if not self.converter.start(src, sout):
            self.status_lbl.setText("A forrás nem nyitható meg.")
            return
        self.progress.setValue(0)
        self.status_lbl.setText(started_msg)
        self._set_running(True)

    def _set_running(self, running: bool):
        self.start_btn.setText("Leállítás" if running else "Indítás")
        self.profile_combo.setEnabled(not running)
        self.source_edit.setEnabled(not running)

    def _on_progress(self, pos: float):
        self.progress.setValue(int(pos * 1000))

    def _on_finished(self, ok: bool, message: str):
        self._set_running(False)
        if self.stream:
            self.status_lbl.setText("Az adatfolyam véget ért." if ok else f"Hiba: {message}")
        elif ok:
            self.progress.setValue(1000)
            self.status_lbl.setText(f"Kész: {self.dest_edit.text()}")
        else:
            self.status_lbl.setText(f"Hiba: {message}")

    def reject(self):
        self.converter.cancel()
        super().reject()


AUDIO_OUTPUTS = [("Automatikus", ""), ("WASAPI (MMDevice)", "mmdevice"), ("DirectSound", "directsound"),
                 ("WaveOut", "waveout")]
VIDEO_OUTPUTS = [("Automatikus", ""), ("Direct3D 11", "direct3d11"), ("Direct3D 9", "direct3d9"),
                 ("OpenGL", "gl"), ("Windows GDI", "wingdi")]

# Prefs that only take effect when LibVLC starts
RESTART_PREFS = {"hw_decoding", "network_caching", "file_caching", "aout", "vout", "time_stretch",
                 "sub_autodetect", "extra_args"}


class PreferencesDialog(GlassDialog):
    """Persistent application settings: general, advanced LibVLC options, remote control and online services."""

    def __init__(self, prefs: dict, parent=None, file_exts=()):
        super().__init__("Beállítások", 620, 560, parent)
        self.prefs = dict(prefs)
        self.file_exts = sorted(file_exts)

        tabs = QTabWidget()
        tabs.setFont(ui_font(12))
        tabs.setStyleSheet(tab_style())
        tabs.addTab(self._general_tab(prefs), "Általános")
        tabs.addTab(self._advanced_tab(prefs), "Haladó")
        tabs.addTab(self._remote_tab(prefs), "Távvezérlés és online")
        self.body.addWidget(tabs, stretch=1)

        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        save_btn = primary_button("Mentés")
        save_btn.clicked.connect(self._on_save)
        self.add_button_row(cancel_btn, save_btn)

    @staticmethod
    def _page():
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 8, 0)
        layout.setSpacing(12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return page, layout, grid

    def _folder_row(self, value: str, title: str) -> tuple:
        edit = styled_line_edit(value)
        btn = secondary_button("Tallózás...")
        btn.clicked.connect(lambda: self._browse_folder(edit, title))
        row = QHBoxLayout()
        row.addWidget(edit, stretch=1)
        row.addWidget(btn)
        return edit, row

    def _general_tab(self, prefs) -> QWidget:
        page, layout, grid = self._page()
        self.snap_edit, snap_row = self._folder_row(prefs["snapshot_dir"], "Pillanatképek mappája")
        grid.addWidget(field_label("Pillanatképek mappája"), 0, 0)
        grid.addLayout(snap_row, 0, 1)
        self.record_edit, record_row = self._folder_row(prefs["record_dir"], "Felvételek mappája")
        grid.addWidget(field_label("Felvételek mappája"), 1, 0)
        grid.addLayout(record_row, 1, 1)

        self.jump_spin = styled_spin(1, 120, prefs["jump_sec"], suffix=" mp")
        grid.addWidget(field_label("Ugrás nyilakkal"), 2, 0)
        grid.addWidget(self.jump_spin, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)

        self.autohide_spin = styled_spin(1, 30, prefs["autohide_sec"], suffix=" mp")
        grid.addWidget(field_label("Vezérlők elrejtése videónál"), 3, 0)
        grid.addWidget(self.autohide_spin, 3, 1, alignment=Qt.AlignmentFlag.AlignLeft)

        self.resume_check = styled_check("Folytatás ott, ahol abbahagytam", prefs["resume"])
        self.recent_check = styled_check("Legutóbbi média megjegyzése", prefs["remember_recent"])
        self.hw_check = styled_check("Hardveres dekódolás (újraindítás után érvényes)", prefs["hw_decoding"])
        self.single_check = styled_check("Csak egy Prism-ablak: a megnyitott fájlok a futó lejátszóba kerülnek",
                                         prefs["single_instance"])
        for box in (self.resume_check, self.recent_check, self.hw_check, self.single_check):
            layout.addWidget(box)

        heading = QLabel("Fájltársítás")
        heading.setFont(ui_font(13, QFont.Weight.DemiBold))
        heading.setStyleSheet(f"color: {LiquidTheme.ACCENT.name()};")
        layout.addSpacing(6)
        layout.addWidget(heading)
        self.assoc_label = field_label("")
        self.assoc_label.setWordWrap(True)
        layout.addWidget(self.assoc_label)
        self.assoc_btn = secondary_button("")
        self.assoc_btn.clicked.connect(self._toggle_file_types)
        defaults_btn = secondary_button("Alapértelmezett alkalmazások...")
        defaults_btn.setToolTip("Windows Gépház: itt választható a Prism alapértelmezett lejátszónak")
        defaults_btn.clicked.connect(win.open_default_apps)
        row = QHBoxLayout()
        row.addWidget(self.assoc_btn)
        row.addWidget(defaults_btn)
        row.addStretch()
        layout.addLayout(row)
        self._sync_file_types()
        layout.addStretch()
        return page

    def _sync_file_types(self):
        registered = win.file_types_registered()
        self.assoc_label.setText(
            "A Prism szerepel a „Társítás” menüben és az alapértelmezett alkalmazások között. "
            "Alapértelmezett lejátszónak a Windows Gépházban lehet beállítani." if registered else
            "A Prism hozzáadható a fájlok „Társítás” menüjéhez és a Windows alapértelmezett alkalmazásaihoz. "
            "Nem veszi át egyik fájltípust sem, azt a Gépházban te döntöd el.")
        self.assoc_btn.setText("Eltávolítás a Windowsból" if registered else "Hozzáadás a Windowshoz")

    def _toggle_file_types(self):
        try:
            if win.file_types_registered():
                win.unregister_file_types(self.file_exts)
            else:
                win.register_file_types(self.file_exts)
        except OSError as e:
            self.assoc_label.setText(f"Nem sikerült módosítani a regisztrációt: {e}")
            return
        self._sync_file_types()

    def _advanced_tab(self, prefs) -> QWidget:
        page, layout, grid = self._page()
        self.aout_combo = styled_combo(AUDIO_OUTPUTS)
        self.aout_combo.setCurrentIndex(max(0, self.aout_combo.findData(prefs["aout"])))
        grid.addWidget(field_label("Hangkimenet"), 0, 0)
        grid.addWidget(self.aout_combo, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.vout_combo = styled_combo(VIDEO_OUTPUTS)
        self.vout_combo.setCurrentIndex(max(0, self.vout_combo.findData(prefs["vout"])))
        grid.addWidget(field_label("Videókimenet"), 1, 0)
        grid.addWidget(self.vout_combo, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.net_cache_spin = styled_spin(0, 60000, prefs["network_caching"], 100, " ms")
        grid.addWidget(field_label("Hálózati gyorsítótár"), 2, 0)
        grid.addWidget(self.net_cache_spin, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.file_cache_spin = styled_spin(0, 60000, prefs["file_caching"], 100, " ms")
        grid.addWidget(field_label("Fájl gyorsítótár"), 3, 0)
        grid.addWidget(self.file_cache_spin, 3, 1, alignment=Qt.AlignmentFlag.AlignLeft)

        self.stretch_check = styled_check("Hangmagasság megtartása gyorsításkor / lassításkor", prefs["time_stretch"])
        self.autosub_check = styled_check("Feliratfájlok automatikus betöltése a videó mellől", prefs["sub_autodetect"])
        layout.addWidget(self.stretch_check)
        layout.addWidget(self.autosub_check)

        layout.addWidget(field_label("További VLC parancssori kapcsolók (szóközzel elválasztva):"))
        self.extra_edit = styled_line_edit(prefs["extra_args"], "pl. --sub-text-scale=120 --no-osd")
        layout.addWidget(self.extra_edit)
        hint = field_label("Ezen a lapon minden beállítás a program újraindítása után érvényes. "
                           "A teljes kapcsolólista: vlc --help --advanced.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        return page

    def _remote_tab(self, prefs) -> QWidget:
        page, layout, grid = self._page()
        self.web_check = styled_check("Webes távirányító bekapcsolása (telefonról, böngészőből)", prefs["web_remote"])
        grid.addWidget(self.web_check, 0, 0, 1, 2)
        self.web_port_spin = styled_spin(1024, 65535, prefs["web_port"])
        grid.addWidget(field_label("Port"), 1, 0)
        grid.addWidget(self.web_port_spin, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.web_pass_edit = styled_line_edit(prefs["web_password"], "üresen hagyva nincs jelszó")
        self.web_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(field_label("Jelszó"), 2, 0)
        grid.addWidget(self.web_pass_edit, 2, 1)

        heading = QLabel("OpenSubtitles.com (online feliratkeresés)")
        heading.setFont(ui_font(13, QFont.Weight.DemiBold))
        heading.setStyleSheet(f"color: {LiquidTheme.ACCENT.name()};")
        grid.addWidget(heading, 3, 0, 1, 2)
        self.os_key_edit = styled_line_edit(prefs["os_api_key"], "ingyenes API-kulcs: opensubtitles.com/consumers")
        grid.addWidget(field_label("API-kulcs"), 4, 0)
        grid.addWidget(self.os_key_edit, 4, 1)
        self.os_user_edit = styled_line_edit(prefs["os_user"], "a letöltéshez")
        grid.addWidget(field_label("Felhasználónév"), 5, 0)
        grid.addWidget(self.os_user_edit, 5, 1)
        self.os_pass_edit = styled_line_edit(prefs["os_password"])
        self.os_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(field_label("Jelszó"), 6, 0)
        grid.addWidget(self.os_pass_edit, 6, 1)
        self.sub_lang_edit = styled_line_edit(prefs["sub_languages"], "hu,en")
        grid.addWidget(field_label("Feliratnyelvek"), 7, 0)
        grid.addWidget(self.sub_lang_edit, 7, 1)
        layout.addStretch()
        return page

    def _browse_folder(self, edit: QLineEdit, title: str):
        folder = QFileDialog.getExistingDirectory(self, title, edit.text())
        if folder:
            edit.setText(os.path.normpath(folder))

    def _on_save(self):
        self.prefs.update(
            snapshot_dir=self.snap_edit.text().strip() or self.prefs["snapshot_dir"],
            record_dir=self.record_edit.text().strip() or self.prefs["record_dir"],
            jump_sec=self.jump_spin.value(),
            autohide_sec=self.autohide_spin.value(),
            resume=self.resume_check.isChecked(),
            remember_recent=self.recent_check.isChecked(),
            hw_decoding=self.hw_check.isChecked(),
            single_instance=self.single_check.isChecked(),
            aout=self.aout_combo.currentData(),
            vout=self.vout_combo.currentData(),
            network_caching=self.net_cache_spin.value(),
            file_caching=self.file_cache_spin.value(),
            time_stretch=self.stretch_check.isChecked(),
            sub_autodetect=self.autosub_check.isChecked(),
            extra_args=self.extra_edit.text().strip(),
            web_remote=self.web_check.isChecked(),
            web_port=self.web_port_spin.value(),
            web_password=self.web_pass_edit.text(),
            os_api_key=self.os_key_edit.text().strip(),
            os_user=self.os_user_edit.text().strip(),
            os_password=self.os_pass_edit.text(),
            sub_languages=self.sub_lang_edit.text().strip().replace(" ", "") or "hu,en",
        )
        self.accept()
