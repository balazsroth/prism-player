"""
Main Window for Prism:
Frameless dark UI with LibVLC hardware-accelerated video rendering,
audio visualizer, playlist drawer and a full VLC-style menu bar.
"""

import json
import os
import shlex
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QDialog, QStackedWidget, QFrame,
    QGraphicsDropShadowEffect, QSizePolicy, QPushButton, QMenuBar, QMenu, QAbstractItemView, QColorDialog
)
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QPainterPath, QPen, QFont, QMouseEvent, QKeyEvent,
    QDragEnterEvent, QDropEvent, QCursor, QAction, QActionGroup, QKeySequence, QBrush
)
from PyQt6.QtCore import Qt, QRectF, QPoint, QPointF, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QSettings

from liquid_theme import LiquidTheme, APP_NAME, ACCENT_PRESETS, ui_font, icon_pixmap, rgba, app_icon, app_icon_pixmap
from liquid_widgets import LiquidGlassButton, LiquidGlassSlider, LiquidGlassCard, VisualizerWidget, GlassMenu
from vlc_player import (VLCPlayerEngine, DEINTERLACE_MODES, SUBTITLE_STYLE_DEFAULTS,
                        NAV_ACTIVATE, NAV_UP, NAV_DOWN, NAV_LEFT, NAV_RIGHT, NAV_POPUP)
from playlist_manager import PlaylistManager, PLAYLIST_EXTS, REPEAT_OFF, REPEAT_ALL, REPEAT_ONE
from dialogs import (
    SCROLLBAR_STYLE, NetworkStreamDialog, DiscDialog, CaptureDialog, JumpToTimeDialog,
    MediaInfoDialog, ShortcutsDialog, AboutDialog, EffectsDialog, ConvertDialog,
    PreferencesDialog, RESTART_PREFS, format_ms, local_ip
)
from advanced_dialogs import (
    SubtitleStyleDialog, TeletextDialog, DiscoveryDialog, LogDialog, HotkeysDialog, SubtitleSearchDialog
)
from remote_control import RemoteServer
import win_integration as win


def menu_style() -> str:
    """Menu bar + popup styling. The popup glass itself is painted by GlassMenu;
    here the items get flat, softly lit pills (no gradients)."""
    return f"""
    QMenuBar {{
        background: transparent;
        color: {LiquidTheme.TEXT_SECONDARY.name()};
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        font-size: 13px;
        spacing: 2px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 5px 9px;
        border-radius: 7px;
        color: {LiquidTheme.TEXT_SECONDARY.name()};
    }}
    QMenuBar::item:selected {{
        background: rgba(255, 255, 255, 16);
        color: {LiquidTheme.TEXT_PRIMARY.name()};
    }}
    QMenuBar::item:pressed {{
        background: rgba(255, 255, 255, 26);
        color: {LiquidTheme.TEXT_PRIMARY.name()};
    }}
    QMenu {{
        background: transparent;
        border: none;
        padding: 5px;
        color: {LiquidTheme.TEXT_PRIMARY.name()};
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        font-size: 13px;
    }}
    QMenu::item {{
        padding: 6px 28px 6px 12px;
        border-radius: 6px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: rgba(255, 255, 255, 22);
        color: #FFFFFF;
    }}
    QMenu::item:disabled {{
        color: rgba(255, 255, 255, 60);
    }}
    QMenu::separator {{
        height: 1px;
        background: rgba(255, 255, 255, 22);
        margin: 4px 10px;
    }}
"""


MEDIA_EXTS = {
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv', '.flv', '.m4v', '.ts', '.m2ts', '.mts', '.mpg', '.mpeg',
    '.3gp', '.ogv', '.vob', '.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.alac', '.ape',
    '.mka', '.ac3', '.dts',
}
MEDIA_FILTER = ("Médiafájlok (" + " ".join(f"*{e}" for e in sorted(MEDIA_EXTS)) + ");;"
                "Lejátszási listák (*.m3u *.m3u8);;Minden fájl (*.*)")

SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0, 4.0]
ASPECTS = [("Alapértelmezett", None), ("16:9", "16:9"), ("4:3", "4:3"), ("1:1", "1:1"), ("16:10", "16:10"),
           ("2.21:1", "221:100"), ("2.35:1", "235:100"), ("2.39:1", "239:100"), ("5:4", "5:4")]
CROPS = [("Alapértelmezett", None), ("16:9", "16:9"), ("16:10", "16:10"), ("4:3", "4:3"), ("1:1", "1:1"),
         ("5:4", "5:4"), ("1.85:1", "185:100"), ("2.21:1", "221:100"), ("2.35:1", "235:100"), ("2.39:1", "239:100")]
ZOOMS = [("Ablakhoz igazítás", 0.0), ("1:4 (negyed)", 0.25), ("1:2 (fél)", 0.5), ("1:1 (eredeti)", 1.0), ("2:1 (dupla)", 2.0)]
DEINTERLACE = [("Ki", None)] + [(m, m) for m in DEINTERLACE_MODES]
STEREO = [("Sztereó", 1), ("Fordított sztereó", 2), ("Bal csatorna", 3), ("Jobb csatorna", 4), ("Dolby Surround", 5)]
REPEAT_LABELS = {REPEAT_OFF: "Ismétlés: ki", REPEAT_ALL: "Ismétlés: összes", REPEAT_ONE: "Ismétlés: egy szám"}

DEFAULT_PREFS = {
    "snapshot_dir": os.path.join(os.path.expanduser("~"), "Pictures", "Prism"),
    "record_dir": os.path.join(os.path.expanduser("~"), "Videos", "Prism"),
    "jump_sec": 10,
    "autohide_sec": 3,
    "resume": True,
    "remember_recent": True,
    "hw_decoding": True,
    "single_instance": True,
    # Advanced LibVLC options (applied at start-up)
    "aout": "",
    "vout": "",
    "network_caching": 1000,
    "file_caching": 1000,
    "time_stretch": True,
    "sub_autodetect": True,
    "extra_args": "",
    # Web remote & online subtitles
    "web_remote": False,
    "web_port": 8090,
    "web_password": "",
    "os_api_key": "",
    "os_user": "",
    "os_password": "",
    "sub_languages": "hu,en",
}


def vlc_args(prefs: dict) -> list:
    """LibVLC command-line options from the advanced preferences."""
    args = [f"--network-caching={prefs['network_caching']}", f"--file-caching={prefs['file_caching']}"]
    if prefs["aout"]:
        args.append(f"--aout={prefs['aout']}")
    if prefs["vout"]:
        args.append(f"--vout={prefs['vout']}")
    if not prefs["time_stretch"]:
        args.append("--no-audio-time-stretch")
    if not prefs["sub_autodetect"]:
        args.append("--no-sub-autodetect-file")
    try:
        # posix=False keeps Windows backslashes; drop the quotes it leaves around tokens
        args += [a.strip('"') for a in shlex.split(prefs["extra_args"], posix=False)]
    except ValueError:
        pass
    return args


class ControlOverlay(QWidget):
    """
    Frameless window that floats the control dock above the video.
    LibVLC renders into a native child HWND that ordinary Qt widgets cannot
    paint over, so the dock has to live in its own (owned) top-level window.
    """
    def __init__(self, owner: QWidget):
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._target_opacity = 0.0
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

    def _animate_to(self, target: float):
        self._target_opacity = target
        self._anim.stop()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(target)
        self._anim.start()

    def fade_in(self):
        if self.isVisible() and self._target_opacity == 1.0:
            return
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
        self._animate_to(1.0)

    def fade_out(self):
        if self.isVisible() and self._target_opacity != 0.0:
            self._animate_to(0.0)

    def hide_now(self):
        self._anim.stop()
        self._target_opacity = 0.0
        self.hide()

    def _on_anim_finished(self):
        if self._target_opacity == 0.0:
            self.hide()


class MainWindow(QMainWindow):
    """Prism Player Main Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Player")
        self.setWindowIcon(app_icon())
        self.resize(1080, 700)
        self.setMinimumSize(780, 520)

        # Frameless translucent window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)

        # Window Dragging state
        self.drag_position = QPoint()

        # Persistent settings
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.prefs = {k: self.settings.value(f"prefs/{k}", d, type=type(d)) for k, d in DEFAULT_PREFS.items()}
        saved_accent = QColor(self.settings.value("accent", "", type=str))
        if saved_accent.isValid():
            LiquidTheme.set_accent(saved_accent)  # before any widget reads the colours

        # Playlist & Engine
        self.playlist_mgr = PlaylistManager(self)
        self.player_engine = VLCPlayerEngine(hw_decoding=self.prefs["hw_decoding"],
                                             extra_args=vlc_args(self.prefs), parent=self)
        self.player_engine.set_record_dir(self.prefs["record_dir"])
        saved_style = self._load_json("subtitle_style", {})
        self.player_engine.set_subtitle_style({k: type(v)(saved_style.get(k, v))
                                               for k, v in SUBTITLE_STYLE_DEFAULTS.items()})

        # Web remote (served from worker threads, commands arrive here as signals)
        self.remote = RemoteServer(self)
        self.remote.command.connect(self._on_remote_command)
        self.remote_timer = QTimer(self)
        self.remote_timer.setInterval(500)
        self.remote_timer.timeout.connect(self._update_remote_status)

        # Windows shell: media keys / volume-flyout session and the taskbar button
        self.media_session = win.MediaSession(self)
        self.media_session.button.connect(
            lambda name: self._on_remote_command("prev" if name == "previous" else name, ""))
        self.taskbar = None             # created when Explorer announces the taskbar button
        self._thumb_icons = {}
        self._thumb_playing = None      # play/pause state the thumbnail button shows
        self._player_state = "stopped"
        # Single instance: files opened from Explorer while running (see attach_instance)
        self.instance = None
        self._incoming = []
        self._incoming_timer = QTimer(self)
        self._incoming_timer.setSingleShot(True)
        self._incoming_timer.setInterval(400)  # Explorer starts one process per selected file
        self._incoming_timer.timeout.connect(self._open_incoming)

        # Connect signals
        self.player_engine.position_changed.connect(self._on_position_changed)
        self.player_engine.state_changed.connect(self._on_state_changed)
        self.player_engine.media_changed.connect(self._on_media_changed)
        self.player_engine.media_ended.connect(self._on_media_ended)
        self.playlist_mgr.track_changed.connect(self._on_track_changed)
        self.playlist_mgr.playlist_updated.connect(self._on_playlist_updated)

        # Auto-hide dock timer for video playback
        self.autohide_timer = QTimer(self)
        self.autohide_timer.setInterval(self.prefs["autohide_sec"] * 1000)
        self.autohide_timer.timeout.connect(self._fade_dock_out)


        # LibVLC's video window swallows mouse moves, so watch the cursor directly
        self._last_cursor_pos = QPoint()
        self.cursor_poll_timer = QTimer(self)
        self.cursor_poll_timer.setInterval(120)
        self.cursor_poll_timer.timeout.connect(self._poll_cursor)
        self.cursor_poll_timer.start()

        self.is_video_mode = False
        self._fs_normal_rect = None    # maximized window's own restore size while fullscreen
        self.dock_visible = True
        self._is_playing = False
        self.is_minimal_view = False
        self._current_path = None
        self._pending_resume_ms = None
        self.recent_files = self._load_json("recent", []) if self.prefs["remember_recent"] else []
        self.positions = self._load_json("positions", {})
        self.bookmarks = {}           # path -> [ms]
        self.ab_points = [None, None]
        self.aspect_ratio = None
        self.crop = None
        self.zoom = 0.0
        self.deinterlace = None
        self._last_deinterlace = "yadif"
        self._effects_dlg = None
        self._convert_dlgs = []
        self._tool_dlgs = {}            # non-modal tool windows kept alive while open
        self._hotkey_actions = []       # (key, label, QAction) for the hotkey editor
        self._hotkey_defaults = {}

        self._first_painted = False     # media controls and web remote start after the first frame
        self._init_ui()
        self._restore_session()

    # --- Settings persistence ---
    def _load_json(self, key: str, default):
        try:
            value = json.loads(self.settings.value(key, "", type=str) or "null")
        except ValueError:
            value = None
        return value if isinstance(value, type(default)) else default

    def _save_json(self, key: str, value):
        self.settings.setValue(key, json.dumps(value))

    def _restore_session(self):
        self.vol_slider.setValue(self.settings.value("volume", 100, type=int))
        self._set_repeat_mode(self.settings.value("repeat_mode", REPEAT_OFF, type=int), announce=False)
        if self.settings.value("shuffle", False, type=bool):
            self._toggle_shuffle(announce=False)

    def _save_session(self):
        self._remember_position()
        self.settings.setValue("volume", self.vol_slider.value())
        self.settings.setValue("repeat_mode", self.playlist_mgr.repeat_mode)
        self.settings.setValue("shuffle", self.playlist_mgr.is_shuffle)
        self._save_json("recent", self.recent_files if self.prefs["remember_recent"] else [])
        self._save_json("positions", self.positions)
        for k, v in self.prefs.items():
            self.settings.setValue(f"prefs/{k}", v)

    # --- UI construction ---
    def _init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content container (window background is painted in paintEvent)
        self.outer_card = QWidget(central)
        card_layout = QVBoxLayout(self.outer_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 1. Custom Title Bar (hidden in fullscreen)
        self.titlebar_area = QWidget()
        tb_layout = QVBoxLayout(self.titlebar_area)
        tb_layout.setContentsMargins(16, 6, 10, 6)
        self.tb_layout = tb_layout
        tb_layout.addWidget(self._create_titlebar())
        card_layout.addWidget(self.titlebar_area)

        # Body: viewport + playlist, then the dock (margins depend on window/video state)
        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(12)
        card_layout.addLayout(self.body_layout, stretch=1)

        # 2. Main Center Area (Split: Left Viewport, Right Playlist Drawer)
        center_split = QHBoxLayout()
        center_split.setContentsMargins(0, 0, 0, 0)
        center_split.setSpacing(12)
        self.center_split = center_split

        # Center Viewport Stack: Video HWND vs Audio Album Art
        self.viewport_stack = QStackedWidget()

        # Page 0: Audio Album Art + Visualizer
        self.audio_page = self._create_audio_view()
        self.viewport_stack.addWidget(self.audio_page)

        # Page 1: Video Viewport
        self.video_surface = QFrame()
        self.video_surface.setStyleSheet("background-color: #000000; border-radius: 12px;")
        self.video_surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.viewport_stack.addWidget(self.video_surface)

        center_split.addWidget(self.viewport_stack, stretch=1)

        # Playlist Drawer (Collapsible)
        self.playlist_drawer = self._create_playlist_drawer()
        self.playlist_drawer.setVisible(False)
        center_split.addWidget(self.playlist_drawer)

        self.body_layout.addLayout(center_split, stretch=1)

        # 3. Control Dock (docked in audio mode, floating overlay in video mode)
        self.control_dock = self._create_control_dock()
        self.body_layout.addWidget(self.control_dock)
        self.overlay = ControlOverlay(self)

        main_layout.addWidget(self.outer_card)

        # Built last: the menus reference widgets created above
        self.menubar_slot.addWidget(self._create_menubar(), alignment=Qt.AlignmentFlag.AlignVCenter)
        self._update_chrome()

        # Bind video surface HWND once window is ready
        QTimer.singleShot(100, lambda: self.player_engine.set_video_hwnd(int(self.video_surface.winId())))

    def _create_titlebar(self) -> QWidget:
        tb = QWidget()
        tb.setFixedHeight(40)
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # App badge
        self.badge = QLabel()
        self.badge.setFixedSize(22, 22)
        self.badge.setPixmap(app_icon_pixmap(22))
        layout.addWidget(self.badge)
        layout.addSpacing(4)

        title_lbl = QLabel(APP_NAME)
        title_lbl.setFont(ui_font(13, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(f"color: {LiquidTheme.TEXT_PRIMARY.name()};")
        layout.addWidget(title_lbl)
        layout.addSpacing(8)

        # Felső navigációs menüsor (Top Navigation Bar) – filled in by _init_ui
        self.menubar_slot = QHBoxLayout()
        self.menubar_slot.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.menubar_slot)

        layout.addStretch()

        # Quick option buttons
        self.speed_btn = QPushButton("1x")
        self.aspect_btn = QPushButton("Képarány")
        self.sub_btn = QPushButton("Felirat")
        for btn, handler, tip in ((self.speed_btn, self._cycle_speed, "Lejátszási sebesség"),
                                  (self.aspect_btn, self._cycle_aspect, "Képarány váltása (A)"),
                                  (self.sub_btn, self._open_subtitle_file, "Feliratfájl betöltése")):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setFont(ui_font(12, QFont.Weight.DemiBold))
            btn.setStyleSheet(self._pill_btn_style())
            btn.setToolTip(tip)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

        divider = QFrame()
        divider.setFixedSize(1, 18)
        divider.setStyleSheet(f"background: {rgba(LiquidTheme.BORDER)};")
        layout.addSpacing(6)
        layout.addWidget(divider)
        layout.addSpacing(6)

        # Window controls
        min_btn = LiquidGlassButton(icon_name="minimize", size=30, variant="window")
        min_btn.clicked.connect(self.showMinimized)

        self.max_btn = LiquidGlassButton(icon_name="maximize", size=30, variant="window")
        self.max_btn.clicked.connect(self._toggle_maximize)

        close_btn = LiquidGlassButton(icon_name="close", size=30, variant="window-close")
        close_btn.clicked.connect(self.close)

        self.window_btns = (min_btn, self.max_btn, close_btn)
        self.window_btn_layout = layout
        layout.setSpacing(2)
        for b in self.window_btns:
            layout.addWidget(b)

        return tb

    def _create_audio_view(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(0)

        # Artwork placeholder
        self.album_art = QLabel(widget)
        self.album_art.setFixedSize(208, 208)
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art.setPixmap(icon_pixmap("music", QColor(255, 255, 255, 150), 64, 1.5))
        self.album_art.setStyleSheet(self._album_art_style())
        shadow = QGraphicsDropShadowEffect(self.album_art)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 140))
        self.album_art.setGraphicsEffect(shadow)

        layout.addWidget(self.album_art, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(28)

        # Track Title & Artist
        self.track_title_lbl = QLabel("Húzz ide médiát")
        self.track_title_lbl.setFont(ui_font(22, QFont.Weight.DemiBold))
        self.track_title_lbl.setStyleSheet(f"color: {LiquidTheme.TEXT_PRIMARY.name()};")
        self.track_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.track_title_lbl)
        layout.addSpacing(6)

        self.track_artist_lbl = QLabel("vagy nyiss meg fájlokat – minden formátum, amit a VLC ismer")
        self.track_artist_lbl.setFont(ui_font(14))
        self.track_artist_lbl.setStyleSheet(f"color: {LiquidTheme.TEXT_SECONDARY.name()};")
        self.track_artist_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.track_artist_lbl)
        layout.addSpacing(28)

        # Visualizer
        self.visualizer = VisualizerWidget(widget)
        self.visualizer.setFixedWidth(300)
        layout.addWidget(self.visualizer, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)

        # On-screen messages in audio mode (video mode uses LibVLC's marquee)
        self.osd_lbl = QLabel("")
        self.osd_lbl.setFixedHeight(24)
        self.osd_lbl.setFont(ui_font(13, QFont.Weight.DemiBold))
        self.osd_lbl.setStyleSheet(f"color: {LiquidTheme.ACCENT.name()};")
        self.osd_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.osd_lbl)
        self.osd_timer = QTimer(self)
        self.osd_timer.setSingleShot(True)
        self.osd_timer.timeout.connect(lambda: self.osd_lbl.setText(""))

        return widget

    def _create_playlist_drawer(self) -> QWidget:
        drawer = LiquidGlassCard(radius=14, parent=self)
        drawer.setFixedWidth(300)
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(16, 12, 8, 8)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(2)
        title = QLabel("Lejátszási lista")
        title.setFont(ui_font(14, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {LiquidTheme.TEXT_PRIMARY.name()};")

        self.playlist_count_lbl = QLabel("")
        self.playlist_count_lbl.setFont(ui_font(12))
        self.playlist_count_lbl.setStyleSheet(f"color: {LiquidTheme.TEXT_MUTED.name()}; padding-left: 6px;")

        add_btn = LiquidGlassButton(icon_name="plus", size=32)
        add_btn.setToolTip("Fájlok hozzáadása")
        add_btn.clicked.connect(self._enqueue_files_dialog)

        clear_btn = LiquidGlassButton(icon_name="trash", size=32)
        clear_btn.setToolTip("Lista törlése")
        clear_btn.clicked.connect(self.playlist_mgr.clear)

        # Only hides the drawer; the playlist itself stays intact
        hide_btn = LiquidGlassButton(icon_name="close", size=32)
        hide_btn.setToolTip("Lejátszási lista elrejtése (Ctrl+L)")
        hide_btn.clicked.connect(lambda: self._set_playlist_visible(False))

        head.addWidget(title)
        head.addWidget(self.playlist_count_lbl)
        head.addStretch()
        head.addWidget(add_btn)
        head.addWidget(clear_btn)
        head.addWidget(hide_btn)
        layout.addLayout(head)

        self.playlist_list = QListWidget()
        self.playlist_list.setFont(ui_font(13))
        self.playlist_list.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.playlist_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.playlist_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.playlist_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._playlist_context_menu)
        self.playlist_list.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._sync_playlist_order))
        self.playlist_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                color: {LiquidTheme.TEXT_PRIMARY.name()};
                outline: none;
            }}
            QListWidget::item {{
                padding: 9px 10px;
                border-radius: 8px;
                margin: 1px 6px 1px 0;
            }}
            QListWidget::item:hover {{
                background: rgba(255, 255, 255, 12);
            }}
            QListWidget::item:selected {{
                background: rgba(255, 255, 255, 22);
            }}
        """ + SCROLLBAR_STYLE)
        self.playlist_list.itemDoubleClicked.connect(self._on_playlist_item_double_clicked)

        remove_act = QAction("Eltávolítás", self.playlist_list)
        remove_act.setShortcut(QKeySequence.StandardKey.Delete)
        remove_act.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        remove_act.triggered.connect(self._remove_selected_playlist_items)
        self.playlist_list.addAction(remove_act)
        layout.addWidget(self.playlist_list)

        return drawer

    def _create_control_dock(self) -> QWidget:
        dock = LiquidGlassCard(radius=16, parent=self)
        dock_layout = QVBoxLayout(dock)
        dock_layout.setContentsMargins(18, 12, 18, 12)
        dock_layout.setSpacing(4)

        # 1. Timeline Seeker Row
        time_row = QHBoxLayout()
        time_row.setSpacing(10)

        self.cur_time_lbl = QLabel("0:00")
        self.total_time_lbl = QLabel("0:00")
        for lbl, align in ((self.cur_time_lbl, Qt.AlignmentFlag.AlignRight),
                           (self.total_time_lbl, Qt.AlignmentFlag.AlignLeft)):
            lbl.setFont(ui_font(12))
            lbl.setFixedWidth(52)
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"color: {LiquidTheme.TEXT_SECONDARY.name()};")

        self.progress_slider = LiquidGlassSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.valueChanged.connect(self._on_seek_requested)

        time_row.addWidget(self.cur_time_lbl)
        time_row.addWidget(self.progress_slider, stretch=1)
        time_row.addWidget(self.total_time_lbl)
        dock_layout.addLayout(time_row)

        # 2. Main Control Buttons Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)

        # Left cluster: Open, Shuffle, Repeat
        self.open_btn = LiquidGlassButton(icon_name="folder", size=38)
        self.open_btn.setToolTip("Fájl megnyitása")
        self.open_btn.clicked.connect(lambda: self._open_files_dialog())

        self.shuffle_btn = LiquidGlassButton(icon_name="shuffle", size=38, is_toggle=True)
        self.shuffle_btn.setToolTip("Véletlenszerű lejátszás (R)")
        self.shuffle_btn.clicked.connect(lambda: self._toggle_shuffle())

        self.repeat_btn = LiquidGlassButton(icon_name="repeat", size=38, is_toggle=True)
        self.repeat_btn.setToolTip("Ismétlés: ki / összes / egy szám (L)")
        self.repeat_btn.clicked.connect(self._cycle_repeat)

        self.record_btn = LiquidGlassButton(icon_name="record", size=38, is_toggle=True)
        self.record_btn.setToolTip("Felvétel (Shift+R)")
        self.record_btn.clicked.connect(self._toggle_recording)

        left = QHBoxLayout()
        left.setSpacing(4)
        left.addWidget(self.open_btn)
        left.addWidget(self.shuffle_btn)
        left.addWidget(self.repeat_btn)
        left.addWidget(self.record_btn)
        left.addStretch()

        # Center cluster: Rewind, Prev, PLAY/PAUSE, Next, Forward
        self.rewind_btn = LiquidGlassButton(icon_name="rewind", size=38)
        self.rewind_btn.setToolTip("Vissza 10 másodpercet")
        self.rewind_btn.clicked.connect(lambda: self.player_engine.jump_seconds(-10))

        self.prev_btn = LiquidGlassButton(icon_name="prev", size=42)
        self.prev_btn.setToolTip("Előző (P)")
        self.prev_btn.clicked.connect(self.playlist_mgr.prev_track)

        self.play_btn = LiquidGlassButton(icon_name="play", size=50, variant="primary")
        self.play_btn.setToolTip("Lejátszás / Szünet (Szóköz)")
        self.play_btn.clicked.connect(self.player_engine.toggle_play_pause)

        self.next_btn = LiquidGlassButton(icon_name="next", size=42)
        self.next_btn.setToolTip("Következő (N)")
        self.next_btn.clicked.connect(self.playlist_mgr.next_track)

        self.forward_btn = LiquidGlassButton(icon_name="forward", size=38)
        self.forward_btn.setToolTip("Előre 10 másodpercet")
        self.forward_btn.clicked.connect(lambda: self.player_engine.jump_seconds(10))

        center = QHBoxLayout()
        center.setSpacing(10)
        for b in (self.rewind_btn, self.prev_btn, self.play_btn, self.next_btn, self.forward_btn):
            center.addWidget(b)

        # Right cluster: Volume, Effects, Playlist, Fullscreen
        self.mute_btn = LiquidGlassButton(icon_name="volume", size=38)
        self.mute_btn.setToolTip("Némítás (M)")
        self.mute_btn.clicked.connect(self._toggle_mute)

        self.vol_slider = LiquidGlassSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(96)
        self.vol_slider.valueChanged.connect(self.player_engine.set_volume)
        self.vol_slider.valueChanged.connect(lambda v: self.vol_slider.setToolTip(f"Hangerő: {v}%"))

        self.eq_btn = LiquidGlassButton(icon_name="equalizer", size=38)
        self.eq_btn.setToolTip("Effektek és szűrők (Ctrl+E)")
        self.eq_btn.clicked.connect(lambda: self._show_effects(EffectsDialog.TAB_EQ))

        self.playlist_toggle_btn = LiquidGlassButton(icon_name="playlist", size=38, is_toggle=True)
        self.playlist_toggle_btn.setToolTip("Lejátszási lista (Ctrl+L)")
        self.playlist_toggle_btn.clicked.connect(self._toggle_playlist_drawer)

        self.fullscreen_btn = LiquidGlassButton(icon_name="fullscreen", size=38)
        self.fullscreen_btn.setToolTip("Teljes képernyő (F)")
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)

        right = QHBoxLayout()
        right.setSpacing(4)
        right.addStretch()
        right.addWidget(self.mute_btn)
        right.addWidget(self.vol_slider)
        right.addSpacing(8)
        right.addWidget(self.eq_btn)
        right.addWidget(self.playlist_toggle_btn)
        right.addWidget(self.fullscreen_btn)

        # Equal-width side clusters keep the transport controls truly centered
        ctrl_row.addLayout(left, stretch=1)
        ctrl_row.addLayout(center)
        ctrl_row.addLayout(right, stretch=1)

        dock_layout.addLayout(ctrl_row)
        return dock

    def _pill_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {LiquidTheme.TEXT_SECONDARY.name()};
                border: none;
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QPushButton:hover {{
                background: {rgba(LiquidTheme.HOVER)};
                color: {LiquidTheme.TEXT_PRIMARY.name()};
            }}
            QPushButton:pressed {{
                background: {rgba(LiquidTheme.PRESSED)};
            }}
        """

    # --- Menu bar ---
    def _add_action(self, menu: QMenu, text: str, slot=None, shortcut=None, checkable=False) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.setCheckable(checkable)
        if slot:
            act.triggered.connect(slot)
        menu.addAction(act)
        self._register_hotkey(menu, act)
        return act

    def _register_hotkey(self, menu: QMenu, act: QAction):
        """Makes the action's shortcut customizable (Tools → Customize shortcuts)."""
        key = f"{menu.title()}/{act.text()}"
        self._hotkey_actions.append((key, f"{menu.title()} › {act.text().rstrip('.')}", act))
        self._hotkey_defaults[key] = act.shortcut().toString()

    def _glass_menu(self, title: str = "") -> GlassMenu:
        menu = GlassMenu(title, self)
        menu.setStyleSheet(menu_style())
        return menu

    def _submenu(self, parent: QMenu, title: str) -> QMenu:
        menu = self._glass_menu(title)
        parent.addMenu(menu)
        return menu

    def _radio_menu(self, parent: QMenu, title: str, options, on_select, current) -> QMenu:
        """Fixed choices; current() decides which one is ticked when the menu opens."""
        menu = self._submenu(parent, title)
        group = QActionGroup(menu)
        for label, value in options:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setData(value)
            group.addAction(act)
            act.triggered.connect(lambda _=False, v=value: on_select(v))
        menu.aboutToShow.connect(lambda: [a.setChecked(a.data() == current()) for a in group.actions()])
        return menu

    def _dynamic_menu(self, parent: QMenu, title: str, provider, on_select, empty_text="Nem elérhető") -> QMenu:
        """Choices fetched on open: provider() -> ([(value, label)], current_value)."""
        menu = self._submenu(parent, title)

        def fill():
            menu.clear()
            items, current = provider()
            if not items:
                menu.addAction(empty_text).setEnabled(False)
                return
            group = QActionGroup(menu)
            for value, label in items:
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(value == current)
                group.addAction(act)
                act.triggered.connect(lambda _=False, v=value: on_select(v))

        menu.aboutToShow.connect(fill)
        return menu

    def _create_menubar(self) -> QMenuBar:
        menubar = QMenuBar()
        menubar.setStyleSheet(menu_style())
        self.menubar = menubar
        engine = self.player_engine

        def top(title):
            menu = self._glass_menu(title)
            menubar.addMenu(menu)
            return menu

        # 1. Média
        m = top("Média")
        self._add_action(m, "Fájl megnyitása...", lambda: self._open_files_dialog(), "Ctrl+O")
        self._add_action(m, "Fájlok hozzáadása a listához...", self._enqueue_files_dialog, "Ctrl+Shift+O")
        self._add_action(m, "Mappa megnyitása...", self._open_folder_dialog, "Ctrl+F")
        self._add_action(m, "Lemez megnyitása...", self._open_disc_dialog, "Ctrl+D")
        self._add_action(m, "Hálózati adatfolyam megnyitása...", lambda: self._open_network_dialog(), "Ctrl+N")
        self._add_action(m, "Rögzítőeszköz megnyitása...", self._open_capture_dialog, "Ctrl+C")
        self._add_action(m, "Hely megnyitása a vágólapról", self._open_from_clipboard, "Ctrl+V")
        self._add_action(m, "Hálózati források és médiatár...", self._show_discovery, "Ctrl+Shift+N")
        self.recent_menu = self._submenu(m, "Legutóbbi média")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        m.addSeparator()
        self._add_action(m, "Lejátszási lista mentése fájlba...", self._save_playlist, "Ctrl+Y")
        self._add_action(m, "Konvertálás / Mentés...", lambda: self._open_convert_dialog(False), "Ctrl+R")
        self._add_action(m, "Adatfolyam küldése (Stream)...", lambda: self._open_convert_dialog(True), "Ctrl+S")
        m.addSeparator()
        self.exit_at_end_act = self._add_action(m, "Kilépés a lejátszási lista végén", checkable=True)
        self._add_action(m, "Kilépés", self.close, "Ctrl+Q")

        # 2. Lejátszás
        m = top("Lejátszás")
        self._dynamic_menu(m, "Cím", lambda: (engine.get_titles(), engine.get_current_title()), engine.set_title)
        self._dynamic_menu(m, "Fejezet", lambda: (engine.get_chapters(), engine.get_current_chapter()), engine.set_chapter)
        self._dynamic_menu(m, "Program", self._program_choices, self._set_program)
        nav = self._submenu(m, "Lemezmenü (DVD / Blu-ray)")
        self._add_action(nav, "Lemezmenü megnyitása", self._disc_menu, "Shift+M")
        self._add_action(nav, "Felugró menü (Blu-ray)", lambda: engine.navigate(NAV_POPUP))
        nav.addSeparator()
        self._add_action(nav, "Fel", lambda: engine.navigate(NAV_UP), "Alt+Up")
        self._add_action(nav, "Le", lambda: engine.navigate(NAV_DOWN), "Alt+Down")
        self._add_action(nav, "Balra", lambda: engine.navigate(NAV_LEFT), "Alt+Left")
        self._add_action(nav, "Jobbra", lambda: engine.navigate(NAV_RIGHT), "Alt+Right")
        self._add_action(nav, "Kiválasztás", lambda: engine.navigate(NAV_ACTIVATE), "Alt+Return")
        self.bookmarks_menu = self._submenu(m, "Egyéni könyvjelzők")
        self.bookmark_add_act = QAction("Könyvjelző hozzáadása", self)
        self.bookmark_add_act.setShortcut(QKeySequence("Ctrl+B"))
        self.bookmark_add_act.triggered.connect(self._add_bookmark)
        self._register_hotkey(self.bookmarks_menu, self.bookmark_add_act)
        self.bookmarks_menu.aboutToShow.connect(self._populate_bookmarks_menu)
        self._populate_bookmarks_menu()
        m.addSeparator()
        speed = self._submenu(m, "Sebesség")
        self._add_action(speed, "Gyorsabb", lambda: self._step_speed(1), "]")
        self._add_action(speed, "Normál sebesség", lambda: self._set_speed(1.0), "=")
        self._add_action(speed, "Lassabb", lambda: self._step_speed(-1), "[")
        speed.addSeparator()
        group = QActionGroup(speed)
        for s in SPEEDS:
            act = speed.addAction(f"{s:g}x")
            act.setCheckable(True)
            act.setData(s)
            group.addAction(act)
            act.triggered.connect(lambda _=False, v=s: self._set_speed(v))
        speed.aboutToShow.connect(lambda: [a.setChecked(abs(a.data() - engine.get_rate()) < 0.01) for a in group.actions()])
        m.addSeparator()
        self._add_action(m, "Ugrás előre", lambda: self._jump(self.prefs["jump_sec"]), "Right")
        self._add_action(m, "Ugrás hátra", lambda: self._jump(-self.prefs["jump_sec"]), "Left")
        self._add_action(m, "Kis ugrás előre (3 mp)", lambda: self._jump(3), "Shift+Right")
        self._add_action(m, "Kis ugrás hátra (3 mp)", lambda: self._jump(-3), "Shift+Left")
        self._add_action(m, "Nagy ugrás előre (1 perc)", lambda: self._jump(60), "Ctrl+Right")
        self._add_action(m, "Nagy ugrás hátra (1 perc)", lambda: self._jump(-60), "Ctrl+Left")
        self._add_action(m, "Ugrás adott időpontra...", self._show_jump_time_dialog, "Ctrl+T")
        self._add_action(m, "Következő képkocka", engine.next_frame, "E")
        m.addSeparator()
        self._add_action(m, "Lejátszás / Szünet", engine.toggle_play_pause, "Space")
        self._add_action(m, "Leállítás", self._stop, "S")
        self._add_action(m, "Előző", self.playlist_mgr.prev_track, "P")
        self._add_action(m, "Következő", self.playlist_mgr.next_track, "N")
        m.addSeparator()
        self.repeat_menu = self._radio_menu(m, "Ismétlés", [("Ki", REPEAT_OFF), ("Összes", REPEAT_ALL), ("Egy szám", REPEAT_ONE)],
                                            self._set_repeat_mode, lambda: self.playlist_mgr.repeat_mode)
        self._add_action(m, "Ismétlési mód váltása", self._cycle_repeat, "L")
        self.menu_shuffle_act = self._add_action(m, "Véletlenszerű lejátszás", lambda: self._toggle_shuffle(), "R", checkable=True)
        self.ab_act = self._add_action(m, "A-B ismétlés: A pont beállítása", self._ab_repeat)
        m.addSeparator()
        self.record_act = self._add_action(m, "Felvétel", self._toggle_recording, "Shift+R", checkable=True)
        self._dynamic_menu(m, "Lejátszás eszközön (Chromecast)", self._renderer_choices, self._set_renderer)

        # 3. Hang
        m = top("Hang")
        self._dynamic_menu(m, "Hangsáv", lambda: (engine.get_audio_tracks(), engine.get_current_audio_track()),
                           engine.set_audio_track)
        self._add_action(m, "Hangsáv váltása", lambda: self._cycle_track(engine.get_audio_tracks(), engine.get_current_audio_track(),
                                                                      engine.set_audio_track, "Hangsáv"), "B")
        self._dynamic_menu(m, "Hangeszköz", lambda: (engine.get_audio_devices(), engine.get_audio_device()),
                           engine.set_audio_device)
        self._radio_menu(m, "Sztereó mód", STEREO, self._set_stereo, engine.get_stereo_mode)
        self.visualizer_act = self._add_action(m, "Spektrum vizualizáció", self.visualizer.setVisible, checkable=True)
        self.visualizer_act.setChecked(True)
        m.addSeparator()
        self._add_action(m, "Hangerő növelése", lambda: self._change_volume(5), "Up")
        self._add_action(m, "Hangerő csökkentése", lambda: self._change_volume(-5), "Down")
        self._add_action(m, "Némítás", self._toggle_mute, "M")
        m.addSeparator()
        self._add_action(m, "Hangszínszabályzó...", lambda: self._show_effects(EffectsDialog.TAB_EQ))
        self._add_action(m, "Hangeffektek...", lambda: self._show_effects(EffectsDialog.TAB_AUDIO))
        self._add_action(m, "Hang késleltetés növelése (+50 ms)", lambda: self._adjust_audio_delay(50), "K")
        self._add_action(m, "Hang késleltetés csökkentése (−50 ms)", lambda: self._adjust_audio_delay(-50), "J")
        self._add_action(m, "Hang késleltetés visszaállítása", lambda: self._adjust_audio_delay(None))

        # 4. Videó
        m = top("Videó")
        self._dynamic_menu(m, "Videósáv", lambda: (engine.get_video_tracks(), engine.get_current_video_track()),
                           engine.set_video_track)
        self.fullscreen_act = self._add_action(m, "Teljes képernyő", self._toggle_fullscreen, "F")
        self.ontop_act = self._add_action(m, "Mindig legfelül", self._toggle_always_on_top, checkable=True)
        m.addSeparator()
        self._radio_menu(m, "Nagyítás", ZOOMS, self._set_zoom, lambda: self.zoom)
        self._radio_menu(m, "Képarány", ASPECTS, self._set_aspect, lambda: self.aspect_ratio)
        self._radio_menu(m, "Levágás", CROPS, self._set_crop, lambda: self.crop)
        self._radio_menu(m, "Deinterlace", DEINTERLACE, self._set_deinterlace, lambda: self.deinterlace)
        self._add_action(m, "Nagyítás váltása", lambda: self._cycle_option(ZOOMS, self.zoom, self._set_zoom), "Z")
        self._add_action(m, "Képarány váltása", self._cycle_aspect, "A")
        self._add_action(m, "Levágás váltása", lambda: self._cycle_option(CROPS, self.crop, self._set_crop), "C")
        self._add_action(m, "Deinterlace ki/be", self._toggle_deinterlace, "D")
        m.addSeparator()
        self._add_action(m, "Képbeállítások...", lambda: self._show_effects(EffectsDialog.TAB_VIDEO))
        self._add_action(m, "Forgatás és tükrözés...", lambda: self._show_effects(EffectsDialog.TAB_GEOMETRY))
        self._add_action(m, "Videószűrők...", lambda: self._show_effects(EffectsDialog.TAB_FILTERS))
        self._add_action(m, "Logó a videón...", lambda: self._show_effects(EffectsDialog.TAB_OVERLAY))
        m.addSeparator()
        self._add_action(m, "Pillanatkép készítése", self._take_snapshot, "Shift+S")
        self._add_action(m, "Pillanatképek mappájának megnyitása", self._open_snapshot_dir)

        # 5. Felirat
        m = top("Felirat")
        self._add_action(m, "Feliratfájl hozzáadása...", self._open_subtitle_file)
        self._add_action(m, "Feliratok keresése online...", self._show_subtitle_search, "Ctrl+Shift+S")
        self._dynamic_menu(m, "Feliratsáv", lambda: (engine.get_subtitle_tracks(), engine.get_current_spu()),
                           engine.set_subtitle_track)
        self._add_action(m, "Feliratsáv váltása", lambda: self._cycle_track(engine.get_subtitle_tracks(), engine.get_current_spu(),
                                                                         engine.set_subtitle_track, "Felirat"), "V")
        m.addSeparator()
        self._add_action(m, "Felirat késleltetés növelése (+50 ms)", lambda: self._adjust_sub_delay(50), "H")
        self._add_action(m, "Felirat késleltetés csökkentése (−50 ms)", lambda: self._adjust_sub_delay(-50), "G")
        self._add_action(m, "Felirat késleltetés visszaállítása", lambda: self._adjust_sub_delay(None))
        m.addSeparator()
        self._add_action(m, "Felirat megjelenése...", self._show_subtitle_style)
        teletext = self._submenu(m, "Teletext")
        self._add_action(teletext, "Teletext megjelenítése", lambda: self._set_teletext(100))
        self._add_action(teletext, "Oldal megadása...", self._ask_teletext_page)
        self._add_action(teletext, "Teletext elrejtése", lambda: self._set_teletext(0))

        # 6. Eszközök
        m = top("Eszközök")
        self._add_action(m, "Effektek és szűrők...", lambda: self._show_effects(EffectsDialog.TAB_EQ), "Ctrl+E")
        self._add_action(m, "Sávszinkronizálás...", lambda: self._show_effects(EffectsDialog.TAB_SYNC))
        self._add_action(m, "Média információk...", lambda: self._show_media_info(0), "Ctrl+I")
        self._add_action(m, "Kodek információk...", lambda: self._show_media_info(1), "Ctrl+J")
        self._add_action(m, "Üzenetek...", self._show_log, "Ctrl+M")
        m.addSeparator()
        self.web_remote_act = self._add_action(m, "Webes távirányító", self._set_web_remote, checkable=True)
        self._add_action(m, "Billentyűparancsok testreszabása...", self._customize_hotkeys)
        self._add_action(m, "Beállítások...", self._show_preferences, "Ctrl+P")

        # 7. Nézet
        m = top("Nézet")
        self.menu_playlist_act = self._add_action(m, "Lejátszási lista", self._toggle_playlist_drawer, "Ctrl+L", checkable=True)
        self.menu_minimal_act = self._add_action(m, "Minimalista nézet", self._toggle_minimal_view, "Ctrl+H", checkable=True)
        m.addAction(self.fullscreen_act)
        m.addAction(self.ontop_act)
        m.addSeparator()
        scheme = self._radio_menu(m, "Színséma", ACCENT_PRESETS, self._set_accent,
                                  lambda: LiquidTheme.ACCENT.name().upper())
        scheme.addSeparator()
        scheme.addAction("Egyéni szín...", self._pick_custom_accent)

        # 8. Súgó
        m = top("Súgó")
        self._add_action(m, "Billentyűparancsok...", self._show_shortcuts, "F1")
        self._add_action(m, f"Névjegy – {APP_NAME}...", lambda: AboutDialog(self).exec())

        self._apply_hotkey_overrides(self._load_json("hotkeys", {}))
        # The menubar is hidden in fullscreen, which would disable its shortcuts;
        # attaching the actions to the window keeps them live everywhere (customized ones too).
        self.addActions([act for _, _, act in self._hotkey_actions])
        return menubar

    # --- Window dragging & events ---
    def _is_in_titlebar(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        if child is not None and (child is self.titlebar_area or self.titlebar_area.isAncestorOf(child)):
            if isinstance(child, (QMenuBar, QPushButton, QMenu)):
                return False
            p = child.parent()
            while p is not None and p is not self.titlebar_area:
                if isinstance(p, (QMenuBar, QPushButton, QMenu)):
                    return False
                p = p.parent()
            return True
        return False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._is_in_titlebar(event.position().toPoint()) \
                and not (self.isMaximized() or self.isFullScreen()):
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            self.drag_position = QPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

        # Wake up control dock if in video mode
        if self.is_video_mode:
            self._show_dock()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_position = QPoint()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        if self._is_in_titlebar(pos):
            self._toggle_maximize()
        elif self.is_video_mode and self.childAt(pos) is self.video_surface:
            self._toggle_fullscreen()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._position_overlay()

    def changeEvent(self, event):
        super().changeEvent(event)
        if not hasattr(self, "overlay"):
            return  # UI not built yet
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_chrome()
            if self.isMinimized():
                self.overlay.hide_now()
            else:
                QTimer.singleShot(0, self._position_overlay)
        elif event.type() == QEvent.Type.ActivationChange:
            # Don't leave the floating dock above other apps' windows
            if not self.isActiveWindow() and self.is_video_mode:
                self.overlay.hide_now()

    def closeEvent(self, event):
        self._save_session()
        for dlg in self._convert_dlgs:
            dlg.converter.cancel()
        for dlg in list(self._tool_dlgs.values()):
            dlg.reject()
        self.remote.stop()
        self.media_session.close()
        if self.taskbar is not None:
            self.taskbar.set_progress(win.TBPF_NOPROGRESS)
            self.taskbar.release()
        if self.instance is not None:
            self.instance.close()
        self.player_engine.shutdown()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = []
        for u in event.mimeData().urls():
            if u.isLocalFile():
                local = u.toLocalFile()
                if os.path.isdir(local):
                    paths.extend(self._media_in_folder(local))
                elif os.path.exists(local):
                    paths.append(local)
            elif u.scheme():
                paths.append(u.toString())
        if paths:
            self.playlist_mgr.add_files(paths, play_now=True)

    def keyPressEvent(self, event: QKeyEvent):
        # Every other key is a menu action shortcut (see _create_menubar)
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
        super().keyPressEvent(event)

    # --- Paint Window Background ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        radius = 0 if (self.isMaximized() or self.isFullScreen()) else 12

        bg_path = QPainterPath()
        if radius:
            # Half-pixel inset keeps the 1px rim crisp on the rounded window
            bg_path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
        else:
            # Maximized/fullscreen: cover every edge pixel, or the translucent window
            # lets the desktop show through as a thin line along the screen edges
            bg_path.addRect(QRectF(0, 0, w, h))
        painter.fillPath(bg_path, LiquidTheme.BG_DARK)

        # Soft warm ambient light from the top
        glow = QRadialGradient(QPointF(w * 0.35, -h * 0.15), max(w, h) * 0.75)
        a = LiquidTheme.ACCENT
        glow.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 26))
        glow.setColorAt(1.0, QColor(a.red(), a.green(), a.blue(), 0))
        painter.fillPath(bg_path, glow)

        if radius:
            painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
            painter.drawPath(bg_path)

        painter.end()
        if not self._first_painted:
            self._first_painted = True
            QTimer.singleShot(0, self._finish_startup)  # runs once this first frame is on screen

    def _finish_startup(self):
        """The slower start-up work that can wait until the window is visible."""
        self.media_session.start()
        if self.prefs["web_remote"]:
            self._set_web_remote(True, announce=False)

    # --- On-screen messages ---
    def osd(self, text: str):
        if self.is_video_mode:
            self.player_engine.show_osd(text)
        else:
            self.osd_lbl.setText(text)
            self.osd_timer.start(1600)

    # --- Player Callbacks ---
    def _on_position_changed(self, pos, cur_ms, total_ms):
        if self._pending_resume_ms and cur_ms > 0:
            target, self._pending_resume_ms = self._pending_resume_ms, None
            self.player_engine.set_time(target)
            self.osd(f"Folytatás innen: {format_ms(target)}")
            return
        a, b = self.ab_points
        if a is not None and b is not None and cur_ms >= b:
            self.player_engine.set_time(a)
        if not self.progress_slider.is_dragging:
            self.progress_slider.setValue(int(pos * 1000))
        self.cur_time_lbl.setText(format_ms(cur_ms))
        self.total_time_lbl.setText(format_ms(total_ms))
        self._update_taskbar(cur_ms, total_ms)

    def _on_seek_requested(self, val):
        if self.progress_slider.is_dragging:
            self.player_engine.seek(val / 1000.0)

    def _on_state_changed(self, state):
        was_playing = self._is_playing
        self._is_playing = state == "playing"
        self._player_state = state
        self.media_session.set_status(state)
        self._update_taskbar()
        if state == "playing":
            self.play_btn.set_icon_name("pause")
            self.visualizer.set_playing(True)
            if self.is_video_mode and not was_playing:
                self._show_dock()  # brief reveal, then auto-hide
        else:
            self.play_btn.set_icon_name("play")
            self.visualizer.set_playing(False)
            if was_playing:
                self._show_dock()

    def _on_media_changed(self, meta):
        title = meta.get("title", "Ismeretlen")
        artist = meta.get("artist", "")
        self.track_title_lbl.setText(title)
        self.track_artist_lbl.setText(artist)
        self.setWindowTitle(f"{title} – {APP_NAME}")
        self._set_video_mode(meta.get("is_video", False))
        self.media_session.set_media(title, artist, meta.get("is_video", False))

    def _on_media_ended(self):
        if self._current_path:
            self.positions.pop(self._current_path, None)  # finished: start from the top next time
        if self.playlist_mgr.next_track(auto=True) is None and self.exit_at_end_act.isChecked():
            self.close()

    def _on_track_changed(self, index, path):
        self._remember_position()
        self._mark_current_row()
        self.ab_points = [None, None]
        self._update_ab_action()
        item = self.playlist_mgr.items[index]
        if not self.player_engine.load_media(path, item.get("options")):
            self._current_path = None
            self._set_video_mode(False)
            self.track_title_lbl.setText("Ez a fájl nem nyitható meg")
            self.track_artist_lbl.setText(os.path.basename(path))
            return
        self._current_path = path
        self._pending_resume_ms = self.positions.get(path) if self.prefs["resume"] else None
        self.player_engine.play()
        self._sync_record_ui()  # a new input is never recording
        if self.prefs["remember_recent"] and not item.get("options"):
            if path in self.recent_files:
                self.recent_files.remove(path)
            self.recent_files.insert(0, path)
            del self.recent_files[15:]
            self._save_json("recent", self.recent_files)

    def _remember_position(self):
        path = self._current_path
        if not path or not self.prefs["resume"]:
            return
        cur, length = self.player_engine.get_time(), self.player_engine.get_length()
        self.positions.pop(path, None)
        if length > 60000 and 10000 < cur < length - 15000:
            self.positions[path] = cur  # re-inserted last, so the oldest entries get trimmed
            while len(self.positions) > 200:
                self.positions.pop(next(iter(self.positions)))

    # --- Playlist ---
    def _on_playlist_updated(self):
        self.playlist_list.clear()
        for i, item in enumerate(self.playlist_mgr.items):
            row = QListWidgetItem(item["title"])
            row.setData(Qt.ItemDataRole.UserRole, i)
            row.setToolTip(item["path"])
            self.playlist_list.addItem(row)
        count = len(self.playlist_mgr.items)
        self.playlist_count_lbl.setText(str(count) if count else "")
        self._mark_current_row()

    def _mark_current_row(self):
        current = self.playlist_mgr.current_index
        for i in range(self.playlist_list.count()):
            row = self.playlist_list.item(i)
            font = ui_font(13, QFont.Weight.DemiBold if i == current else QFont.Weight.Normal)
            row.setFont(font)
            row.setForeground(QBrush(LiquidTheme.ACCENT if i == current else LiquidTheme.TEXT_PRIMARY))

    def _sync_playlist_order(self):
        order = [self.playlist_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.playlist_list.count())]
        if order != list(range(len(order))):
            self.playlist_mgr.reorder(order)

    def _on_playlist_item_double_clicked(self, item):
        self.playlist_mgr.set_current_index(self.playlist_list.row(item))

    def _remove_selected_playlist_items(self):
        rows = sorted((self.playlist_list.row(i) for i in self.playlist_list.selectedItems()), reverse=True)
        for r in rows:
            self.playlist_mgr.remove_at(r)

    def _playlist_context_menu(self, pos):
        item = self.playlist_list.itemAt(pos)
        menu = self._glass_menu()
        if item is not None:
            row = self.playlist_list.row(item)
            path = self.playlist_mgr.items[row]["path"]
            menu.addAction("Lejátszás", lambda: self.playlist_mgr.set_current_index(row))
            menu.addAction("Eltávolítás", self._remove_selected_playlist_items)
            if os.path.exists(path):
                menu.addAction("Megjelenítés a mappában", lambda: subprocess.Popen(["explorer", "/select,", os.path.normpath(path)]))
            menu.addSeparator()
        menu.addAction("Fájlok hozzáadása...", self._enqueue_files_dialog)
        menu.addAction("Rendezés cím szerint", self.playlist_mgr.sort_by_title)
        menu.addAction("Lista mentése...", self._save_playlist)
        menu.addAction("Lista törlése", self.playlist_mgr.clear)
        menu.exec(self.playlist_list.viewport().mapToGlobal(pos))

    # --- Media menu ---
    def _open_files_dialog(self, play: bool = True):
        files, _ = QFileDialog.getOpenFileNames(self, "Médiafájlok megnyitása", "", MEDIA_FILTER)
        if files:
            self.playlist_mgr.add_files(files, play_now=play)

    def _enqueue_files_dialog(self):
        self._open_files_dialog(play=False)

    @staticmethod
    def _media_in_folder(folder: str) -> list:
        files = []
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                if os.path.splitext(f)[1].lower() in MEDIA_EXTS:
                    files.append(os.path.normpath(os.path.join(root, f)))
        return sorted(files)

    def _open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Mappa megnyitása")
        if folder:
            files = self._media_in_folder(folder)
            if files:
                self.playlist_mgr.add_files(files, play_now=True)
            else:
                self.osd("Nincs lejátszható fájl a mappában")

    def _open_disc_dialog(self):
        dlg = DiscDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.mrl:
            self.playlist_mgr.add_item(dlg.mrl, dlg.title)

    def _open_capture_dialog(self):
        dlg = CaptureDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.mrl:
            self.playlist_mgr.add_item(dlg.mrl, dlg.title, dlg.options)

    def _open_network_dialog(self, initial: str = ""):
        dlg = NetworkStreamDialog(initial, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.url:
            self.playlist_mgr.add_files([dlg.url], play_now=True)

    def _open_from_clipboard(self):
        text = QApplication.clipboard().text().strip().strip('"')
        if text and ("://" in text or os.path.exists(text)):
            self.playlist_mgr.add_files([text], play_now=True)
        else:
            self._open_network_dialog(text)

    def _populate_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            self.recent_menu.addAction("Nincsenek legutóbbi fájlok").setEnabled(False)
            return
        for p in self.recent_files:
            act = self.recent_menu.addAction(os.path.basename(p.rstrip("/\\")) or p)
            act.setToolTip(p)
            act.triggered.connect(lambda _=False, path=p: self.playlist_mgr.play_path(path))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Lista törlése", self._clear_recent)

    def _clear_recent(self):
        self.recent_files.clear()
        self._save_json("recent", [])

    def _save_playlist(self):
        if not self.playlist_mgr.items:
            self.osd("A lejátszási lista üres")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Lejátszási lista mentése", "lejatszasi_lista.m3u8",
                                              "M3U lejátszási lista (*.m3u8 *.m3u)")
        if path:
            self.playlist_mgr.save_m3u(path)
            self.osd("Lejátszási lista mentve")

    def _open_convert_dialog(self, stream: bool):
        source = self._current_path or ""
        dlg = ConvertDialog(self.player_engine, source, stream, self)
        dlg.finished.connect(lambda _=0, d=dlg: self._convert_dlgs.remove(d) if d in self._convert_dlgs else None)
        self._convert_dlgs.append(dlg)
        dlg.show()

    # --- Playback ---
    def _stop(self):
        self._remember_position()
        self.player_engine.stop()
        self._sync_record_ui()

    def _jump(self, seconds: int):
        self.player_engine.jump_seconds(seconds)

    def _set_speed(self, val: float):
        self.speed_btn.setText(f"{val:g}x")
        self.player_engine.set_rate(val)
        self.osd(f"Sebesség: {val:g}x")

    def _step_speed(self, direction: int):
        cur = self.player_engine.get_rate()
        options = [s for s in SPEEDS if (s > cur + 0.01 if direction > 0 else s < cur - 0.01)]
        if options:
            self._set_speed(options[0] if direction > 0 else options[-1])

    def _cycle_speed(self):
        cur = self.player_engine.get_rate()
        faster = [s for s in SPEEDS if 0.5 <= s <= 2.0 and s > cur + 0.01]
        self._set_speed(faster[0] if faster else 0.5)

    def _show_jump_time_dialog(self):
        dlg = JumpToTimeDialog(max(0, self.player_engine.get_time()), max(0, self.player_engine.get_length()), self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.target_ms is not None:
            self.player_engine.set_time(dlg.target_ms)

    def _add_bookmark(self):
        t = self.player_engine.get_time()
        if not self._current_path or t < 0:
            self.osd("Nincs lejátszott média")
            return
        marks = self.bookmarks.setdefault(self._current_path, [])
        marks.append(t)
        marks.sort()
        self.osd(f"Könyvjelző: {format_ms(t)}")

    def _populate_bookmarks_menu(self):
        menu = self.bookmarks_menu
        menu.clear()
        menu.addAction(self.bookmark_add_act)
        marks = self.bookmarks.get(self._current_path, [])
        if marks:
            menu.addSeparator()
            for i, ms in enumerate(marks, 1):
                menu.addAction(f"{i}. könyvjelző – {format_ms(ms)}", lambda _=False, t=ms: self.player_engine.set_time(t))
            menu.addSeparator()
            menu.addAction("Könyvjelzők törlése", lambda: self.bookmarks.pop(self._current_path, None))

    def _ab_repeat(self):
        a, b = self.ab_points
        t = self.player_engine.get_time()
        if t < 0:
            return
        if a is None:
            self.ab_points = [t, None]
            self.osd(f"A pont: {format_ms(t)}")
        elif b is None and t > a:
            self.ab_points = [a, t]
            self.osd(f"A-B ismétlés: {format_ms(a)} – {format_ms(t)}")
        else:
            self.ab_points = [None, None]
            self.osd("A-B ismétlés kikapcsolva")
        self._update_ab_action()

    def _update_ab_action(self):
        a, b = self.ab_points
        if a is None:
            self.ab_act.setText("A-B ismétlés: A pont beállítása")
        elif b is None:
            self.ab_act.setText("A-B ismétlés: B pont beállítása")
        else:
            self.ab_act.setText("A-B ismétlés kikapcsolása")

    def _toggle_shuffle(self, announce: bool = True):
        is_shuf = self.playlist_mgr.toggle_shuffle()
        self.shuffle_btn.set_active(is_shuf)
        self.menu_shuffle_act.setChecked(is_shuf)
        if announce:
            self.osd("Véletlenszerű: be" if is_shuf else "Véletlenszerű: ki")

    def _cycle_repeat(self):
        self._set_repeat_mode((self.playlist_mgr.repeat_mode + 1) % 3)

    def _set_repeat_mode(self, mode: int, announce: bool = True):
        self.playlist_mgr.repeat_mode = mode
        self.repeat_btn.set_icon_name("repeat-one" if mode == REPEAT_ONE else "repeat")
        self.repeat_btn.set_active(mode != REPEAT_OFF)
        if announce:
            self.osd(REPEAT_LABELS[mode])

    def _cycle_track(self, items, current, setter, label: str):
        if not items:
            self.osd(f"{label}: nem elérhető")
            return
        ids = [tid for tid, _ in items]
        idx = ids.index(current) if current in ids else -1
        tid, name = items[(idx + 1) % len(items)]
        setter(tid)
        self.osd(f"{label}: {name}")

    @staticmethod
    def _cycle_option(options, current, apply):
        values = [v for _, v in options]
        idx = values.index(current) if current in values else -1
        apply(options[(idx + 1) % len(options)][1])

    # --- Audio ---
    def _toggle_mute(self):
        is_muted = self.player_engine.toggle_mute()
        self.mute_btn.set_icon_name("mute" if is_muted else "volume")
        self.osd("Némítva" if is_muted else f"Hangerő: {self.vol_slider.value()}%")

    def _change_volume(self, delta: int):
        self.vol_slider.setValue(max(0, min(200, self.vol_slider.value() + delta)))
        self.osd(f"Hangerő: {self.vol_slider.value()}%")

    def _set_stereo(self, mode: int):
        self.player_engine.set_stereo_mode(mode)
        self.osd(f"Sztereó mód: {dict((v, k) for k, v in STEREO)[mode]}")

    def _adjust_audio_delay(self, delta_ms):
        ms = 0 if delta_ms is None else self.player_engine.get_audio_delay() + delta_ms
        self.player_engine.set_audio_delay(ms)
        self.osd(f"Hang késleltetés: {ms} ms")
        if self._effects_dlg:
            self._effects_dlg.refresh_sync()

    def _adjust_sub_delay(self, delta_ms):
        ms = 0 if delta_ms is None else self.player_engine.get_spu_delay() + delta_ms
        self.player_engine.set_spu_delay(ms)
        self.osd(f"Felirat késleltetés: {ms} ms")
        if self._effects_dlg:
            self._effects_dlg.refresh_sync()

    # --- Video ---
    def _set_aspect(self, val):
        self.aspect_ratio = val
        self.player_engine.set_aspect_ratio(val)
        label = dict((v, k) for k, v in ASPECTS)[val]
        self.aspect_btn.setText(label if val else "Képarány")
        self.osd(f"Képarány: {label}")

    def _cycle_aspect(self):
        self._cycle_option(ASPECTS, self.aspect_ratio, self._set_aspect)

    def _set_crop(self, val):
        self.crop = val
        self.player_engine.set_crop_geometry(val)
        self.osd(f"Levágás: {dict((v, k) for k, v in CROPS)[val]}")

    def _set_zoom(self, val: float):
        self.zoom = val
        self.player_engine.set_scale(val)
        self.osd(f"Nagyítás: {dict((v, k) for k, v in ZOOMS)[val]}")

    def _set_deinterlace(self, mode):
        self.deinterlace = mode
        if mode:
            self._last_deinterlace = mode
        self.player_engine.set_deinterlace(mode)
        self.osd(f"Deinterlace: {mode or 'ki'}")

    def _toggle_deinterlace(self):
        self._set_deinterlace(None if self.deinterlace else self._last_deinterlace)

    def _take_snapshot(self):
        if not self.is_video_mode:
            self.osd("Pillanatkép csak videónál készíthető")
            return
        fname = f"prism_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        full_path = os.path.join(self.prefs["snapshot_dir"], fname)
        self.osd(f"Pillanatkép mentve: {fname}" if self.player_engine.take_snapshot(full_path) else "Pillanatkép sikertelen")

    def _open_snapshot_dir(self):
        os.makedirs(self.prefs["snapshot_dir"], exist_ok=True)
        os.startfile(self.prefs["snapshot_dir"])

    def _toggle_always_on_top(self, checked: bool):
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        # Changing window flags recreates the native windows, so LibVLC's
        # target HWND is gone; hand it the new one.
        QTimer.singleShot(0, lambda: self.player_engine.set_video_hwnd(int(self.video_surface.winId())))

    # --- Subtitles ---
    def _open_subtitle_file(self):
        srt, _ = QFileDialog.getOpenFileName(
            self, "Feliratfájl betöltése", "", "Feliratok (*.srt *.sub *.vtt *.ass *.ssa *.idx *.smi);;Minden fájl (*.*)"
        )
        if srt:
            self.player_engine.add_subtitle_file(srt)
            self.osd(f"Felirat betöltve: {os.path.basename(srt)}")

    def _show_subtitle_style(self):
        dlg = SubtitleStyleDialog(self.player_engine.subtitle_style, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_json("subtitle_style", dlg.style)
        if self.player_engine.set_subtitle_style(dlg.style) and self._current_path:
            self.player_engine.restart_media()
        self.osd("Felirat megjelenése frissítve")

    def _show_subtitle_search(self):
        title = self.player_engine.current_meta.get("title", "") if self._current_path else ""
        query = os.path.splitext(title)[0] if title else ""
        self._show_tool("subsearch", lambda: SubtitleSearchDialog(
            self.prefs, self._current_path or "", query, self._load_downloaded_subtitle, self))

    def _load_downloaded_subtitle(self, path: str):
        self.player_engine.add_subtitle_file(path)
        self.osd(f"Felirat betöltve: {os.path.basename(path)}")

    def _set_teletext(self, page: int):
        self.player_engine.set_teletext(page)
        self.osd(f"Teletext: {page}. oldal" if page else "Teletext elrejtve")

    def _ask_teletext_page(self):
        dlg = TeletextDialog(self.player_engine.get_teletext(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.page:
            self._set_teletext(dlg.page)

    # --- Programs, disc menus, recording, renderers ---
    def _program_choices(self):
        programs, current = self.player_engine.get_programs()
        return (programs if len(programs) > 1 else []), current

    def _set_program(self, program: int):
        self.player_engine.set_program(program)
        self.osd(f"Program: {program}")

    def _disc_menu(self):
        self.player_engine.disc_menu()
        self.osd("Lemezmenü")

    def _toggle_recording(self):
        engine = self.player_engine
        if engine.recording:
            engine.set_recording(False)
            self.osd(f"Felvétel mentve ide: {self.prefs['record_dir']}")
        elif not self._current_path:
            self.osd("Nincs lejátszott média")
        elif not engine.can_record():
            self.osd("Ez a forrás nem rögzíthető")
        else:
            os.makedirs(self.prefs["record_dir"], exist_ok=True)
            engine.set_record_dir(self.prefs["record_dir"])
            self.osd("Felvétel folyamatban" if engine.set_recording(True) else "A felvétel nem indítható")
        self._sync_record_ui()

    def _sync_record_ui(self):
        on = self.player_engine.recording
        self.record_btn.set_active(on)
        self.record_act.setChecked(on)

    def _renderer_choices(self):
        scanner = self.player_engine.renderers
        scanner.start()  # first open starts the network scan; devices show up on later opens
        items = [(None, "Ez a számítógép")]
        items += [(ptr, f"{name} ({kind})" if kind else name) for ptr, name, kind in scanner.list()]
        if len(items) == 1:
            items.append(("scanning", "Eszközök keresése… (nyisd meg újra a menüt)"))
        return items, self.player_engine.renderer

    def _set_renderer(self, item):
        if item == "scanning":
            return
        self.player_engine.set_renderer(item)
        self.osd("Lejátszás ezen a számítógépen" if item is None else "Lejátszás a kiválasztott eszközön")

    # --- Web remote ---
    def _set_web_remote(self, on: bool, announce: bool = True):
        if on:
            self.remote.accent = LiquidTheme.ACCENT.name()
            ok = self.remote.start(self.prefs["web_port"], self.prefs["web_password"])
            if ok:
                self.remote_timer.start()
                if announce:
                    self.osd(f"Távirányító: http://{local_ip()}:{self.prefs['web_port']}/")
            elif announce:
                self.osd(f"A {self.prefs['web_port']}-es port foglalt")
            on = ok
        else:
            self.remote.stop()
            self.remote_timer.stop()
            if announce:
                self.osd("Webes távirányító kikapcsolva")
        self.web_remote_act.setChecked(on)
        if self.prefs["web_remote"] != on:
            self.prefs["web_remote"] = on
            self.settings.setValue("prefs/web_remote", on)

    def _update_remote_status(self):
        engine = self.player_engine
        self.remote.status = {
            "title": self.track_title_lbl.text() if self._current_path else "",
            "playing": self._is_playing,
            "time": max(0, engine.get_time()),
            "length": max(0, engine.get_length()),
            "position": max(0.0, engine.player.get_position()),
            "volume": self.vol_slider.value(),
        }

    def _on_remote_command(self, action: str, value: str):
        engine = self.player_engine
        try:
            if action == "toggle":
                engine.toggle_play_pause()
            elif action == "play":
                engine.play()
            elif action == "pause":
                engine.pause()
            elif action == "stop":
                self._stop()
            elif action == "next":
                self.playlist_mgr.next_track()
            elif action == "prev":
                self.playlist_mgr.prev_track()
            elif action == "volume":
                self.vol_slider.setValue(max(0, min(200, int(float(value)))))
            elif action == "seek":
                engine.seek(float(value))
            elif action == "jump":
                engine.jump_seconds(int(float(value)))
            elif action == "fullscreen":
                self._toggle_fullscreen()
            elif action == "mute":
                self._toggle_mute()
        except ValueError:
            pass  # malformed value from the page
        self._update_remote_status()

    # --- Windows shell: taskbar button, single instance ---
    THUMB_PREV, THUMB_PLAY, THUMB_NEXT = 1, 2, 3

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = win.read_msg(message)
            if msg.message == win.TASKBAR_CREATED:
                self._on_taskbar_created()
            elif msg.message == win.WM_COMMAND and (msg.wParam >> 16) & 0xFFFF == win.THBN_CLICKED:
                button = msg.wParam & 0xFFFF
                if button == self.THUMB_PREV:
                    self.playlist_mgr.prev_track()
                elif button == self.THUMB_PLAY:
                    self.player_engine.toggle_play_pause()
                elif button == self.THUMB_NEXT:
                    self.playlist_mgr.next_track()
                return True, 0
        # Not super().nativeEvent(): with PyQt6 6.11 that call crashes, and QWidget's version only returns False
        return False, 0

    def _on_taskbar_created(self):
        if self.taskbar is None:
            self.taskbar = win.TaskbarButton(int(self.winId()))
        self.taskbar.button_created()
        self._sync_thumb_buttons()
        self._update_taskbar()

    def _thumb_icon(self, name: str) -> int:
        if name not in self._thumb_icons:
            color = QColor(30, 30, 30) if win.light_taskbar() else QColor(255, 255, 255)
            pm = icon_pixmap(name, color, 16, dpr=self.devicePixelRatioF())
            self._thumb_icons[name] = int(pm.toImage().toHICON())
        return self._thumb_icons[name]

    def _sync_thumb_buttons(self):
        if self.taskbar is None:
            return
        playing = self._thumb_playing = self._is_playing
        self.taskbar.set_buttons([
            (self.THUMB_PREV, self._thumb_icon("prev"), "Előző"),
            (self.THUMB_PLAY, self._thumb_icon("pause" if playing else "play"), "Szünet" if playing else "Lejátszás"),
            (self.THUMB_NEXT, self._thumb_icon("next"), "Következő"),
        ])

    def _update_taskbar(self, cur_ms=None, total_ms=None):
        if self.taskbar is None:
            return
        if cur_ms is None:
            cur_ms, total_ms = self.player_engine.get_time(), self.player_engine.get_length()
        if self._current_path is None or self._player_state == "stopped" or total_ms <= 0:
            self.taskbar.set_progress(win.TBPF_NOPROGRESS)
        else:
            state = win.TBPF_NORMAL if self._is_playing else win.TBPF_PAUSED
            self.taskbar.set_progress(state, max(0, cur_ms), total_ms)
        if self._thumb_playing != self._is_playing:
            self._sync_thumb_buttons()

    def attach_instance(self, instance):
        """Takes over the single-instance hand-off set up in main.py."""
        self.instance = instance
        instance.setParent(self)
        instance.received.connect(self._on_instance_args)
        if instance.is_primary and not instance.listening:
            instance.listen()
        if instance.pending:  # launched while this window was still being built
            args, instance.pending = instance.pending, []
            self._on_instance_args(args)

    def _set_single_instance(self, on: bool):
        if on and self.instance is None:
            instance = win.SingleInstance()
            if instance.is_primary:
                self.attach_instance(instance)
            else:
                instance.close()  # another Prism already owns it
        elif not on and self.instance is not None:
            self.instance.close()
            self.instance = None

    def _on_instance_args(self, args: list):
        self._incoming += args
        self._incoming_timer.start()
        win.bring_to_front(int(self.winId()))

    def _open_incoming(self):
        batch, self._incoming = self._incoming, []
        if batch:
            self.playlist_mgr.add_files(batch, play_now=True)

    # --- Hotkeys ---
    def _apply_hotkey_overrides(self, overrides: dict):
        for key, _, act in self._hotkey_actions:
            if key in overrides:
                act.setShortcut(QKeySequence(overrides[key]))

    def _customize_hotkeys(self):
        dlg = HotkeysDialog(self._hotkey_actions, self._hotkey_defaults, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_hotkey_overrides(dlg.result_map)
        changed = {k: v for k, v in dlg.result_map.items() if v != self._hotkey_defaults.get(k, "")}
        self._save_json("hotkeys", changed)
        self.osd("Billentyűparancsok mentve")

    def _show_shortcuts(self):
        entries = [(act.shortcut().toString(QKeySequence.SequenceFormat.NativeText), label)
                   for _, label, act in self._hotkey_actions if not act.shortcut().isEmpty()]
        entries.append(("Escape", "Teljes képernyő elhagyása"))
        ShortcutsDialog(self, entries).exec()

    # --- Tools ---
    def _show_tool(self, key: str, factory):
        """Opens (or raises) a non-modal tool window."""
        dlg = self._tool_dlgs.get(key)
        if dlg is None:
            dlg = factory()
            dlg.finished.connect(lambda _=0, k=key: self._tool_dlgs.pop(k, None))
            self._tool_dlgs[key] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _show_log(self):
        self._show_tool("log", lambda: LogDialog(self.player_engine.log, self))

    def _show_discovery(self):
        def play(mrl, title, play_now):
            self.playlist_mgr.add_item(mrl, title, play_now=play_now)
        self._show_tool("discovery", lambda: DiscoveryDialog(self.player_engine.instance, play, self))

    def _show_effects(self, tab: int):
        if self._effects_dlg is None:
            self._effects_dlg = EffectsDialog(self.player_engine, self.osd, self)
        self._effects_dlg.tabs.setCurrentIndex(tab)
        self._effects_dlg.refresh_sync()
        self._effects_dlg.show()
        self._effects_dlg.raise_()
        self._effects_dlg.activateWindow()

    def _show_media_info(self, tab: int):
        try:
            vsize = self.player_engine.get_video_size()
        except Exception:
            vsize = None  # no video output yet
        MediaInfoDialog(self.player_engine.get_media_details(), vsize, tab, self).exec()

    def _show_preferences(self):
        dlg = PreferencesDialog(self.prefs, self, MEDIA_EXTS | PLAYLIST_EXTS)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        old = self.prefs
        if dlg.prefs["single_instance"] != old["single_instance"]:
            self._set_single_instance(dlg.prefs["single_instance"])
        restart_needed = any(dlg.prefs[k] != old[k] for k in RESTART_PREFS)
        remote_changed = any(dlg.prefs[k] != old[k] for k in ("web_remote", "web_port", "web_password"))
        self.prefs = dlg.prefs
        self.autohide_timer.setInterval(self.prefs["autohide_sec"] * 1000)
        self.player_engine.set_record_dir(self.prefs["record_dir"])
        if not self.prefs["remember_recent"]:
            self.recent_files.clear()
        if not self.prefs["resume"]:
            self.positions.clear()
        self._save_session()
        if remote_changed:
            self._set_web_remote(self.prefs["web_remote"])
        self.osd("Egyes beállítások újraindítás után érvényesek" if restart_needed else "Beállítások mentve")

    # --- View ---
    @staticmethod
    def _album_art_style() -> str:
        a = LiquidTheme.ACCENT
        deep = a.darker(210)
        return f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba({a.red()}, {a.green()}, {a.blue()}, 70),
                stop:0.55 rgba({deep.red()}, {deep.green()}, {deep.blue()}, 45), stop:1 rgba(255, 255, 255, 8));
            border: 1px solid {rgba(LiquidTheme.BORDER)};
            border-radius: 20px;
        """

    def _set_accent(self, hex_color: str):
        LiquidTheme.set_accent(QColor(hex_color))
        self.settings.setValue("accent", LiquidTheme.ACCENT.name().upper())
        self._apply_accent()

    def _pick_custom_accent(self):
        color = QColorDialog.getColor(LiquidTheme.ACCENT, self, "Egyéni kiemelőszín")
        if color.isValid():
            self._set_accent(color.name())

    def _apply_accent(self):
        """Re-skins everything that baked the accent colour into a stylesheet or pixmap."""
        style = menu_style()
        self.menubar.setStyleSheet(style)
        for menu in self.findChildren(GlassMenu):
            menu.setStyleSheet(style)
        self.album_art.setStyleSheet(self._album_art_style())
        self.osd_lbl.setStyleSheet(f"color: {LiquidTheme.ACCENT.name()};")
        self.badge.setPixmap(app_icon_pixmap(22))
        self.setWindowIcon(app_icon())
        QApplication.instance().setWindowIcon(app_icon())
        self._mark_current_row()
        if self._effects_dlg is not None:  # rebuilt with the new colours next time it opens
            self._effects_dlg.close()
            self._effects_dlg.deleteLater()
            self._effects_dlg = None
        for w in [self] + self.findChildren(QWidget):
            w.update()
        self.overlay.update()

    def _toggle_playlist_drawer(self):
        self._set_playlist_visible(not self.playlist_drawer.isVisible())

    def _set_playlist_visible(self, vis: bool):
        self.playlist_drawer.setVisible(vis)
        self.playlist_toggle_btn.set_active(vis)
        self.menu_playlist_act.setChecked(vis)
        QTimer.singleShot(0, self._position_overlay)

    def _toggle_minimal_view(self, checked: bool):
        self.is_minimal_view = checked
        if checked:
            self.autohide_timer.stop()
            self.overlay.hide_now()
            self.control_dock.setVisible(False)
            self._set_playlist_visible(False)
        else:
            self.control_dock.setVisible(True)
            self._show_dock()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _toggle_fullscreen(self):
        # Read the real window state: Windows can leave fullscreen on its own (Win+Down, display change)
        # Leaving fullscreen, Qt first restores the normal window and only then maximizes it again,
        # so a maximized window flashed at its small size. While fullscreen, the normal size is
        # parked on the maximized area (no visible jump) and put back once maximized again.
        hwnd = int(self.winId())
        if not self.isFullScreen():
            self._fs_normal_rect = None
            if self.isMaximized():
                self._fs_normal_rect = win.normal_rect(hwnd)
                win.set_normal_rect(hwnd, win.maximized_normal_rect(hwnd))
            self.showFullScreen()
        elif self._fs_normal_rect:
            self.showMaximized()
            win.set_normal_rect(hwnd, self._fs_normal_rect)
            self._fs_normal_rect = None
        else:
            self.showNormal()

    # --- Window chrome & floating dock ---
    def _set_video_mode(self, is_video: bool):
        self.is_video_mode = is_video
        self.viewport_stack.setCurrentIndex(1 if is_video else 0)
        dock = self.control_dock
        if is_video and dock.parent() is not self.overlay:
            self.body_layout.removeWidget(dock)
            self.overlay.layout().addWidget(dock)
            dock.bg_color = QColor(22, 23, 28, 232)
            dock.setVisible(not self.is_minimal_view)
        elif not is_video and dock.parent() is self.overlay:
            self.overlay.layout().removeWidget(dock)
            self.overlay.hide_now()
            self.body_layout.addWidget(dock)
            dock.bg_color = LiquidTheme.SURFACE
            dock.setVisible(not self.is_minimal_view)
        self._update_chrome()
        if is_video:
            QTimer.singleShot(0, self._show_dock)
        else:
            self.autohide_timer.stop()

    def _update_chrome(self):
        """Edge-to-edge layout when maximized/fullscreen or showing video."""
        edge = self.isMaximized() or self.isFullScreen()
        self.titlebar_area.setVisible(not self.isFullScreen())
        # Maximized: caption buttons sit flush in the corner, like native Windows ones
        maximized = self.isMaximized()
        if maximized:
            self.tb_layout.setContentsMargins(16, 0, 0, 0)
        else:
            self.tb_layout.setContentsMargins(16, 6, 10, 6)
        self.window_btn_layout.setSpacing(0 if maximized else 2)
        for b in self.window_btns:
            b.flush = maximized
            if maximized:
                b.setFixedSize(46, 40)
            else:
                b.setFixedSize(int(30 * 1.45), 30)
        self.max_btn.set_icon_name("restore" if maximized else "maximize")
        self.max_btn.setToolTip("Előző méret" if maximized else "Teljes méret")
        full = self.isFullScreen()
        self.fullscreen_btn.set_icon_name("fullscreen-exit" if full else "fullscreen")
        self.fullscreen_btn.setToolTip("Kilépés a teljes képernyőből (F / Esc)" if full else "Teljes képernyő (F)")
        self.fullscreen_act.setText("Kilépés a teljes képernyőből" if full else "Teljes képernyő")
        # The window resized under the pointer, so the button may never get its leave event
        self.fullscreen_btn.reset_hover()
        if self.is_video_mode:
            m = 0 if edge else 8
            self.body_layout.setContentsMargins(m, 0, m, m)
            self.center_split.setContentsMargins(0, 0, 0, 0)
            radius = 0 if edge else 8
            self.control_dock.radius = 16
        elif edge:
            # Dock becomes a full-width bar flush with the bottom of the screen
            self.body_layout.setContentsMargins(0, 6, 0, 0)
            self.center_split.setContentsMargins(16, 0, 16, 0)
            radius = 12
            self.control_dock.radius = 0
        else:
            self.body_layout.setContentsMargins(16, 6, 16, 16)
            self.center_split.setContentsMargins(0, 0, 0, 0)
            radius = 12
            self.control_dock.radius = 16
        self.video_surface.setStyleSheet(f"background-color: #000000; border-radius: {radius}px;")
        self.control_dock.update()
        self.update()

    def _position_overlay(self):
        if not hasattr(self, "overlay"):
            return  # UI not built yet
        if self.control_dock.parent() is not self.overlay or not self.video_surface.isVisible():
            return
        vs = self.video_surface
        top_left = vs.mapToGlobal(QPoint(0, 0))
        margin = 20
        h = self.control_dock.sizeHint().height()
        w = min(vs.width() - margin * 2, 1100)
        w = max(w, self.control_dock.minimumSizeHint().width())
        x = top_left.x() + (vs.width() - w) // 2
        y = top_left.y() + vs.height() - h - margin
        self.overlay.setGeometry(x, y, w, h)

    def _poll_cursor(self):
        if not self.is_video_mode or self.isMinimized():
            return
        pos = QCursor.pos()
        if pos == self._last_cursor_pos:
            return
        self._last_cursor_pos = pos
        if QApplication.activeWindow() is self and self.frameGeometry().contains(pos):
            self._show_dock()

    def _show_dock(self):
        if self.is_minimal_view:
            return
        if not self.is_video_mode:
            self.control_dock.setVisible(True)
            return
        if QApplication.activeWindow() is not self:
            return
        self._position_overlay()
        self.overlay.fade_in()
        if self._is_playing:
            self.autohide_timer.start()
        else:
            self.autohide_timer.stop()

    def _fade_dock_out(self):
        self.autohide_timer.stop()
        if not (self.is_video_mode and self._is_playing):
            return
        # Keep the dock up while the pointer rests on it
        if self.overlay.geometry().contains(QCursor.pos()):
            self.autohide_timer.start()
            return
        self.overlay.fade_out()
