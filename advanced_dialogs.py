"""
Prism dialogs for the advanced VLC features: subtitle appearance, online subtitle search,
teletext, network/local media discovery, LibVLC messages and hotkey customization.
"""

import ctypes
import os
import tempfile
import threading

import vlc
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QColorDialog, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QKeySequenceEdit, QAbstractItemView, QApplication, QLineEdit
)
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QKeySequence
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal

from liquid_theme import LiquidTheme, ui_font, rgba
from dialogs import (
    GlassDialog, SCROLLBAR_STYLE, field_label, styled_combo, styled_line_edit, styled_spin, styled_check,
    primary_button, secondary_button, ParamSlider
)
from vlc_player import SUBTITLE_STYLE_DEFAULTS, LOG_LEVELS


def list_style() -> str:
    return f"""
        QTreeWidget, QListWidget, QTableWidget, QPlainTextEdit {{
            background: {rgba(LiquidTheme.SURFACE)};
            color: {LiquidTheme.TEXT_PRIMARY.name()};
            border: 1px solid {rgba(LiquidTheme.BORDER)};
            border-radius: 10px;
            outline: none;
            gridline-color: transparent;
        }}
        QTreeWidget::item, QListWidget::item, QTableWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
        QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
            background: {rgba(LiquidTheme.ACCENT_SOFT)}; color: {LiquidTheme.ACCENT.name()};
        }}
        QHeaderView, QTableCornerButton::section {{ background: transparent; border: none; }}
        QHeaderView::section {{
            background: transparent; color: {LiquidTheme.TEXT_SECONDARY.name()};
            border: none; padding: 6px; font-weight: 600;
        }}
        QKeySequenceEdit QLineEdit {{
            background: {rgba(LiquidTheme.SURFACE_RAISED)}; color: {LiquidTheme.ACCENT.name()};
            border: 1px solid {rgba(LiquidTheme.BORDER)}; border-radius: 6px; padding: 3px 8px;
        }}
    """ + SCROLLBAR_STYLE


class _Signal(QObject):
    """Delivers a worker thread's result on the Qt thread."""
    done = pyqtSignal(object, str)


def run_in_thread(func, on_done):
    """func() runs off the UI thread; on_done(result, error_message) runs back on it."""
    bridge = _Signal()
    bridge.done.connect(on_done)

    # Imported here: its network modules (urllib, http, email) would add ~0.2 s to every start-up
    from subtitle_search import SubtitleError

    def work():
        try:
            bridge.done.emit(func(), "")
        except SubtitleError as e:
            bridge.done.emit(None, str(e))
        except Exception as e:  # network stacks raise a wide variety
            bridge.done.emit(None, f"Hiba: {e}")

    threading.Thread(target=work, daemon=True).start()
    return bridge  # caller keeps it alive until done


class ColorButton(QPushButton):
    """Swatch button holding a 0xRRGGBB colour."""

    def __init__(self, rgb: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self.set_rgb(rgb)

    def set_rgb(self, rgb: int):
        self.rgb = int(rgb) & 0xFFFFFF
        self.setStyleSheet(f"background: #{self.rgb:06X}; border: 1px solid {rgba(LiquidTheme.BORDER)}; "
                           "border-radius: 6px;")

    def _pick(self):
        color = QColorDialog.getColor(QColor(f"#{self.rgb:06X}"), self, "Szín kiválasztása")
        if color.isValid():
            self.set_rgb(color.rgb())


ENCODINGS = [("Automatikus (UTF-8 / rendszer)", ""), ("UTF-8", "UTF-8"),
             ("Közép-európai (Windows-1250)", "CP1250"), ("Közép-európai (ISO-8859-2)", "ISO-8859-2"),
             ("Nyugat-európai (Windows-1252)", "CP1252"), ("Cirill (Windows-1251)", "CP1251"),
             ("Görög (Windows-1253)", "CP1253"), ("Török (Windows-1254)", "CP1254"),
             ("Héber (Windows-1255)", "CP1255"), ("Arab (Windows-1256)", "CP1256"),
             ("Kínai egyszerűsített (GB18030)", "GB18030"), ("Kínai hagyományos (Big5)", "BIG5"),
             ("Japán (Shift-JIS)", "SHIFT_JIS"), ("Koreai (EUC-KR)", "EUC-KR")]
OUTLINES = [("Nincs", 0), ("Vékony", 2), ("Normál", 4), ("Vastag", 6)]


class SubtitleStyleDialog(GlassDialog):
    """Subtitle font, colours, outline, background, size, position and text encoding."""

    def __init__(self, style: dict, parent=None):
        super().__init__("Felirat megjelenése", 560, 560, parent)
        self.style = dict(style)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        row = 0

        self.size_slider = ParamSlider("Méret (%)", "i", 30, 300, style["sub-text-scale"], 5, lambda _: None)
        grid.addWidget(self.size_slider, row, 0, 1, 2)
        row += 1
        self.margin_slider = ParamSlider("Távolság alulról (px)", "i", 0, 400, style["sub-margin"], 2, lambda _: None)
        grid.addWidget(self.margin_slider, row, 0, 1, 2)
        row += 1

        self.font_combo = styled_combo([("Alapértelmezett", "")] + [(f, f) for f in QFontDatabase.families()])
        self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(style["freetype-font"])))
        grid.addWidget(field_label("Betűtípus"), row, 0)
        grid.addWidget(self.font_combo, row, 1)
        row += 1

        self.bold_check = styled_check("Félkövér", style["freetype-bold"])
        grid.addWidget(self.bold_check, row, 1)
        row += 1

        self.text_color = ColorButton(style["freetype-color"])
        self.text_opacity = ParamSlider("Átlátszatlanság", "i", 0, 255, style["freetype-opacity"], 1, lambda _: None)
        grid.addWidget(field_label("Szövegszín"), row, 0)
        color_row = QHBoxLayout()
        color_row.setSpacing(14)
        color_row.addWidget(self.text_color)
        color_row.addWidget(self.text_opacity, stretch=1)
        grid.addLayout(color_row, row, 1)
        row += 1

        self.outline_combo = styled_combo(OUTLINES)
        self.outline_combo.setCurrentIndex(max(0, self.outline_combo.findData(style["freetype-outline-thickness"])))
        self.outline_color = ColorButton(style["freetype-outline-color"])
        outline_row = QHBoxLayout()
        outline_row.addWidget(self.outline_combo)
        outline_row.addWidget(self.outline_color)
        outline_row.addStretch()
        grid.addWidget(field_label("Körvonal"), row, 0)
        grid.addLayout(outline_row, row, 1)
        row += 1

        self.bg_color = ColorButton(style["freetype-background-color"])
        self.bg_opacity = ParamSlider("Átlátszatlanság", "i", 0, 255, style["freetype-background-opacity"], 1,
                                      lambda _: None)
        bg_row = QHBoxLayout()
        bg_row.setSpacing(14)
        bg_row.addWidget(self.bg_color)
        bg_row.addWidget(self.bg_opacity, stretch=1)
        grid.addWidget(field_label("Háttér"), row, 0)
        grid.addLayout(bg_row, row, 1)
        row += 1

        self.encoding_combo = styled_combo(ENCODINGS)
        self.encoding_combo.setCurrentIndex(max(0, self.encoding_combo.findData(style["subsdec-encoding"])))
        grid.addWidget(field_label("Karakterkódolás"), row, 0)
        grid.addWidget(self.encoding_combo, row, 1)
        self.body.addLayout(grid)

        hint = field_label("A méret és a távolság azonnal változik; a többi beállításhoz a lejátszás "
                           "a jelenlegi pozíciótól újraindul. Ékezethibás magyar feliratnál válaszd a Windows-1250-et.")
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        self.body.addStretch()

        reset_btn = secondary_button("Alaphelyzet")
        reset_btn.clicked.connect(self._reset)
        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = primary_button("Alkalmazás")
        apply_btn.clicked.connect(self._on_apply)
        self.add_button_row(reset_btn, cancel_btn, apply_btn)

    def _reset(self):
        d = SUBTITLE_STYLE_DEFAULTS
        self.size_slider.set_value(d["sub-text-scale"])
        self.margin_slider.set_value(d["sub-margin"])
        self.font_combo.setCurrentIndex(0)
        self.bold_check.setChecked(d["freetype-bold"])
        self.text_color.set_rgb(d["freetype-color"])
        self.text_opacity.set_value(d["freetype-opacity"])
        self.outline_combo.setCurrentIndex(self.outline_combo.findData(d["freetype-outline-thickness"]))
        self.outline_color.set_rgb(d["freetype-outline-color"])
        self.bg_color.set_rgb(d["freetype-background-color"])
        self.bg_opacity.set_value(d["freetype-background-opacity"])
        self.encoding_combo.setCurrentIndex(0)

    def _on_apply(self):
        self.style.update({
            "sub-text-scale": self.size_slider.value(),
            "sub-margin": self.margin_slider.value(),
            "freetype-font": self.font_combo.currentData(),
            "freetype-bold": self.bold_check.isChecked(),
            "freetype-color": self.text_color.rgb,
            "freetype-opacity": self.text_opacity.value(),
            "freetype-outline-thickness": self.outline_combo.currentData(),
            "freetype-outline-color": self.outline_color.rgb,
            "freetype-background-color": self.bg_color.rgb,
            "freetype-background-opacity": self.bg_opacity.value(),
            "subsdec-encoding": self.encoding_combo.currentData(),
        })
        self.accept()


class TeletextDialog(GlassDialog):
    def __init__(self, page: int, parent=None):
        super().__init__("Teletext oldal", 360, 200, parent)
        self.page = None
        self.spin = styled_spin(100, 899, page if 100 <= page <= 899 else 100)
        self.spin.setFont(ui_font(16, QFont.Weight.Bold))
        self.body.addWidget(self.spin)
        self.body.addStretch()
        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = primary_button("Megjelenítés")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(lambda: (setattr(self, "page", self.spin.value()), self.accept()))
        self.add_button_row(cancel_btn, ok_btn)


class DiscoveryDialog(GlassDialog):
    """Browses LibVLC's service discovery: local media folders, UPnP/DLNA servers, SAP streams, podcasts…"""

    CATEGORIES = [(3, "Saját mappák"), (1, "Helyi hálózat"), (2, "Internet"), (0, "Eszközök")]
    BROWSABLE = (vlc.MediaType.directory, vlc.MediaType.playlist, vlc.MediaType.disc)

    def __init__(self, instance, play, parent=None):
        """play(mrl, title, play_now) adds an item to the playlist."""
        super().__init__("Hálózati források és médiatár", 820, 560, parent)
        self.setModal(False)
        self.instance, self.play = instance, play
        self.discoverers = {}     # service name -> MediaDiscoverer
        self.current = None
        self._pending = []        # (tree item, media) waiting for parsing

        split = QHBoxLayout()
        split.setSpacing(12)
        self.services = QListWidget()
        self.services.setFixedWidth(230)
        self.services.setFont(ui_font(13))
        self.services.setStyleSheet(list_style())
        for cat, title in self.CATEGORIES:
            head = QListWidgetItem(title.upper())
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            head.setFont(ui_font(11, QFont.Weight.DemiBold))
            head.setForeground(LiquidTheme.TEXT_MUTED)
            self.services.addItem(head)
            for name, longname in self._services(cat):
                item = QListWidgetItem(longname)
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.services.addItem(item)
        self.services.currentItemChanged.connect(self._on_service)
        split.addWidget(self.services)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(ui_font(13))
        self.tree.setStyleSheet(list_style())
        self.tree.setExpandsOnDoubleClick(False)  # folders toggle in _activate
        self.tree.itemExpanded.connect(self._on_expand)
        self.tree.itemDoubleClicked.connect(lambda item, _: self._activate(item, True))
        split.addWidget(self.tree, stretch=1)
        self.body.addLayout(split, stretch=1)

        self.status = field_label("Válassz forrást a bal oldalon.")
        self.body.addWidget(self.status)
        close_btn = secondary_button("Bezárás")
        close_btn.clicked.connect(self.reject)
        add_btn = secondary_button("Hozzáadás a listához")
        add_btn.clicked.connect(lambda: self._activate(self.tree.currentItem(), False))
        play_btn = primary_button("Lejátszás")
        play_btn.clicked.connect(lambda: self._activate(self.tree.currentItem(), True))
        self.add_button_row(close_btn, add_btn, play_btn)

        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self._refresh)

    def _services(self, category: int) -> list:
        class _Desc(ctypes.Structure):
            _fields_ = [("name", ctypes.c_char_p), ("longname", ctypes.c_char_p), ("cat", ctypes.c_int)]
        get = vlc.dll.libvlc_media_discoverer_list_get
        get.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_Desc)))]
        get.restype = ctypes.c_size_t
        out = ctypes.POINTER(ctypes.POINTER(_Desc))()
        n = get(self.instance._as_parameter_, category, ctypes.byref(out))
        result = [(out[i].contents.name.decode(), (out[i].contents.longname or out[i].contents.name).decode())
                  for i in range(n)]
        if n:
            release = vlc.dll.libvlc_media_discoverer_list_release
            release.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            release(out, n)
        names = {"video_dir": "Saját videók", "audio_dir": "Saját zenék", "picture_dir": "Saját képek",
                 "upnp": "UPnP / DLNA médiaszerverek", "sap": "Hálózati adatfolyamok (SAP)",
                 "microdns": "mDNS hálózati felderítés", "podcast": "Podcastok", "disc": "Lemezek",
                 "windrive": "Meghajtók"}
        return [(name, names.get(name, longname)) for name, longname in result]

    def _on_service(self, item, _prev=None):
        name = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not name:
            return
        md = self.discoverers.get(name)
        if md is None:
            md = self.instance.media_discoverer_new(name)
            if md is None or md.start() != 0:
                self.status.setText("Ez a forrás nem indítható.")
                return
            self.discoverers[name] = md
        self.current = md
        self.tree.clear()
        self.status.setText("Keresés…")
        self._refresh()
        self.timer.start()

    @staticmethod
    def _media_items(media_list) -> list:
        if media_list is None:
            return []
        media_list.lock()
        try:
            return [media_list.item_at_index(i) for i in range(media_list.count())]
        finally:
            media_list.unlock()

    def _make_item(self, media) -> QTreeWidgetItem:
        title = media.get_meta(vlc.Meta.Title) or media.get_mrl()
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.ItemDataRole.UserRole, media)
        item.setToolTip(0, media.get_mrl())
        if media.get_type() in self.BROWSABLE:
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        return item

    def _refresh(self):
        # Discovered items keep arriving; append the new ones at the top level
        if self.current is not None:
            medias = self._media_items(self.current.media_list())
            known = {self.tree.topLevelItem(i).toolTip(0) for i in range(self.tree.topLevelItemCount())}
            for m in medias:
                if m.get_mrl() not in known:
                    self.tree.addTopLevelItem(self._make_item(m))
            count = self.tree.topLevelItemCount()
            self.status.setText(f"{count} elem" if count else "Keresés… (a hálózati eszközök megjelenése eltarthat egy ideig)")
        # Folders being opened
        for item, media in list(self._pending):
            if media.get_parsed_status() in (vlc.MediaParsedStatus.done, vlc.MediaParsedStatus.failed,
                                             vlc.MediaParsedStatus.timeout, vlc.MediaParsedStatus.skipped):
                self._pending.remove((item, media))
                item.takeChildren()
                for child in self._media_items(media.subitems()):
                    item.addChild(self._make_item(child))
                if item.childCount() == 0:
                    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
        if not self._pending and self.current is None:
            self.timer.stop()

    def _on_expand(self, item):
        media = item.data(0, Qt.ItemDataRole.UserRole)
        if media is None or item.childCount() or any(p[0] is item for p in self._pending):
            return
        loading = QTreeWidgetItem(["Betöltés…"])
        loading.setFlags(Qt.ItemFlag.NoItemFlags)
        item.addChild(loading)
        media.parse_with_options(vlc.MediaParseFlag.network, 8000)
        self._pending.append((item, media))
        self.timer.start()

    def _activate(self, item, play_now: bool):
        if item is None:
            return
        media = item.data(0, Qt.ItemDataRole.UserRole)
        if media is None:
            return
        if media.get_type() == vlc.MediaType.directory:
            item.setExpanded(not item.isExpanded())
            return
        self.play(media.get_mrl(), item.text(0), play_now)
        self.status.setText(f"Hozzáadva: {item.text(0)}")

    def done(self, result):
        self.timer.stop()
        for md in self.discoverers.values():
            md.stop()
        self.discoverers.clear()
        super().done(result)


class LogDialog(GlassDialog):
    """LibVLC's messages (VLC's Tools → Messages)."""

    LEVELS = [("Hibák", 4), ("Figyelmeztetések", 3), ("Információk", 2), ("Hibakeresés (minden)", 0)]

    def __init__(self, log, parent=None):
        super().__init__("Üzenetek", 820, 560, parent)
        self.setModal(False)
        self.log = log
        self._shown = None

        top = QHBoxLayout()
        top.addWidget(field_label("Részletesség"))
        self.level_combo = styled_combo(self.LEVELS)
        self.level_combo.setCurrentIndex(2)
        self.level_combo.currentIndexChanged.connect(lambda _: self._refresh(force=True))
        top.addWidget(self.level_combo)
        top.addStretch()
        self.follow_check = styled_check("Görgetés a legújabbra", True)
        top.addWidget(self.follow_check)
        self.body.addLayout(top)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont()
        mono.setFamilies(["Cascadia Mono", "Consolas", "Courier New"])
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPixelSize(12)
        self.text.setFont(mono)
        self.text.setStyleSheet(list_style())
        self.body.addWidget(self.text, stretch=1)

        clear_btn = secondary_button("Törlés")
        clear_btn.clicked.connect(lambda: (self.log.clear(), self._refresh(force=True)))
        copy_btn = secondary_button("Másolás")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        save_btn = secondary_button("Mentés...")
        save_btn.clicked.connect(self._save)
        close_btn = primary_button("Bezárás")
        close_btn.clicked.connect(self.reject)
        self.add_button_row(clear_btn, copy_btn, save_btn, close_btn)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(700)
        self._refresh(force=True)

    def _lines(self) -> list:
        min_level = self.level_combo.currentData()
        return [f"[{LOG_LEVELS.get(level, level):7}] {module}: {text}"
                for level, module, text in self.log.snapshot() if level >= min_level]

    def _refresh(self, force: bool = False):
        lines = self._lines()
        key = (len(lines), lines[-1] if lines else "")
        if not force and key == self._shown:
            return
        self._shown = key
        bar = self.text.verticalScrollBar()
        pos = bar.value()
        self.text.setPlainText("\n".join(lines) if lines else "Nincs üzenet ezen a szinten.")
        if self.follow_check.isChecked():
            bar.setValue(bar.maximum())
        else:
            bar.setValue(pos)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Üzenetek mentése", "prism_uzenetek.txt", "Szöveg (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._lines()))

    def done(self, result):
        self.timer.stop()
        super().done(result)


class HotkeysDialog(GlassDialog):
    """Lets every menu action's keyboard shortcut be changed."""

    def __init__(self, actions, defaults: dict, parent=None):
        """actions: [(key, label, QAction)]; defaults: key -> default shortcut text."""
        super().__init__("Billentyűparancsok testreszabása", 640, 600, parent)
        self.actions, self.defaults = actions, defaults
        self.result_map = {}

        self.body.addWidget(field_label("Kattints a billentyű mezőbe, és nyomd le az új kombinációt. "
                                        "Az × gomb eltávolítja a parancsot."))
        self.table = QTableWidget(len(actions), 2)
        self.table.setHorizontalHeaderLabels(["Művelet", "Billentyű"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 210)
        self.table.setFont(ui_font(12))
        self.table.setStyleSheet(list_style())
        self.editors = {}
        for row, (key, label, action) in enumerate(actions):
            self.table.setItem(row, 0, QTableWidgetItem(label))
            editor = QKeySequenceEdit(action.shortcut())
            editor.setMaximumSequenceLength(1)
            editor.setClearButtonEnabled(True)
            editor.findChild(QLineEdit).setPlaceholderText("nincs")
            self.table.setCellWidget(row, 1, editor)
            self.editors[key] = editor
        self.table.resizeRowsToContents()
        self.body.addWidget(self.table, stretch=1)

        self.warning = field_label("")
        self.body.addWidget(self.warning)
        reset_btn = secondary_button("Alapértelmezések")
        reset_btn.clicked.connect(self._reset)
        cancel_btn = secondary_button("Mégse")
        cancel_btn.clicked.connect(self.reject)
        save_btn = primary_button("Mentés")
        save_btn.clicked.connect(self._on_save)
        self.add_button_row(reset_btn, cancel_btn, save_btn)

    def _reset(self):
        for key, editor in self.editors.items():
            editor.setKeySequence(QKeySequence(self.defaults.get(key, "")))

    def _on_save(self):
        seen = {}
        for key, label, _ in self.actions:
            seq = self.editors[key].keySequence().toString()
            if seq and seq in seen:
                self.warning.setText(f"Ütközés: „{seq}” két műveletnél is szerepel ({seen[seq]}, {label}).")
                self.warning.setStyleSheet(f"color: {LiquidTheme.DANGER.lighter(150).name()};")
                return
            seen[seq] = label
            self.result_map[key] = seq
        self.accept()


class SubtitleSearchDialog(GlassDialog):
    """Searches OpenSubtitles.com and loads the chosen subtitle into the current video."""

    def __init__(self, prefs: dict, media_path: str, title: str, load_subtitle, parent=None):
        super().__init__("Feliratok keresése online", 720, 520, parent)
        self.setModal(False)
        self.prefs, self.media_path, self.load_subtitle = prefs, media_path, load_subtitle
        self.results = []
        self._bridge = None

        row = QHBoxLayout()
        self.query_edit = styled_line_edit(title, "Film vagy sorozat címe")
        self.lang_edit = styled_line_edit(prefs["sub_languages"], "hu,en")
        self.lang_edit.setFixedWidth(110)
        self.search_btn = primary_button("Keresés")
        self.search_btn.clicked.connect(self._search)
        self.query_edit.returnPressed.connect(self._search)
        row.addWidget(self.query_edit, stretch=1)
        row.addWidget(self.lang_edit)
        row.addWidget(self.search_btn)
        self.body.addLayout(row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Nyelv", "Kiadás", "Letöltések"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setFont(ui_font(12))
        self.table.setStyleSheet(list_style())
        self.table.doubleClicked.connect(lambda _: self._download())
        self.body.addWidget(self.table, stretch=1)

        self.status = field_label("A ✓ jelölés: a felirat pontosan ehhez a videófájlhoz készült (hash egyezés).")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        close_btn = secondary_button("Bezárás")
        close_btn.clicked.connect(self.reject)
        self.download_btn = primary_button("Letöltés és betöltés")
        self.download_btn.clicked.connect(self._download)
        self.add_button_row(close_btn, self.download_btn)

    def _client(self):
        from subtitle_search import OpenSubtitlesClient
        return OpenSubtitlesClient(self.prefs["os_api_key"], self.prefs["os_user"], self.prefs["os_password"])

    def _busy(self, busy: bool, text: str = ""):
        self.search_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        if text:
            self.status.setText(text)

    def _search(self):
        query = self.query_edit.text().strip()
        if not query:
            return
        langs = self.lang_edit.text().strip().replace(" ", "") or "hu,en"
        self._busy(True, "Keresés…")
        path = self.media_path if self.media_path and os.path.isfile(self.media_path) else ""
        self._bridge = run_in_thread(lambda: self._client().search(query, langs, path), self._on_results)

    def _on_results(self, results, error: str):
        self._busy(False, error)
        if error:
            return
        self.results = results or []
        self.table.setRowCount(len(self.results))
        for row, r in enumerate(self.results):
            self.table.setItem(row, 0, QTableWidgetItem(r["language"]))
            self.table.setItem(row, 1, QTableWidgetItem(("✓ " if r["hash_match"] else "") + r["release"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(r["downloads"])))
        self.table.resizeColumnToContents(0)
        self.status.setText(f"{len(self.results)} találat." if self.results else "Nincs találat.")

    def _download(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self.results)):
            self.status.setText("Válassz egy feliratot a listából.")
            return
        r = self.results[row]
        if self.media_path and os.path.isfile(self.media_path):
            folder = os.path.dirname(self.media_path)
            base = f"{os.path.splitext(os.path.basename(self.media_path))[0]}.{r['language']}"
        else:
            folder, base = tempfile.gettempdir(), f"prism_felirat_{r['file_id']}"
        if not os.access(folder, os.W_OK):
            folder = tempfile.gettempdir()
        self._busy(True, "Letöltés…")
        self._bridge = run_in_thread(lambda: self._client().download(r["file_id"], folder, base), self._on_downloaded)

    def _on_downloaded(self, path, error: str):
        self._busy(False, error)
        if path:
            self.load_subtitle(path)
            self.status.setText(f"Betöltve: {os.path.basename(path)}")
