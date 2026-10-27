"""
Playlist Manager: handles playlist items, queue order, shuffle, repeat modes and M3U files.
"""

import os
import random
from PyQt6.QtCore import QObject, pyqtSignal

REPEAT_OFF, REPEAT_ALL, REPEAT_ONE = 0, 1, 2
PLAYLIST_EXTS = {".m3u", ".m3u8"}


class PlaylistManager(QObject):
    playlist_updated = pyqtSignal()
    track_changed = pyqtSignal(int, str) # index, file_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = [] # list of dicts: {"path": str, "title": str, "options": list}
        self.current_index = -1
        self.is_shuffle = False
        self.repeat_mode = REPEAT_OFF

    @staticmethod
    def _read_m3u(path: str) -> list:
        base = os.path.dirname(path)
        entries = []
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "://" not in line and not os.path.isabs(line):
                    line = os.path.normpath(os.path.join(base, line))
                entries.append(line)
        return entries

    def _make_item(self, path: str, title: str = None, options: list = None):
        if os.path.isfile(path):
            title = title or os.path.splitext(os.path.basename(path))[0]
        elif "://" in path:
            title = title or path.rstrip("/").rsplit("/", 1)[-1] or path
        else:
            return None
        return {"path": path, "title": title, "options": options or []}

    def add_files(self, file_paths: list, play_now: bool = False):
        """Appends local files, M3U playlists or network URLs. With play_now, jumps to the first added item."""
        first_new = len(self.items)
        for path in file_paths:
            if os.path.splitext(path)[1].lower() in PLAYLIST_EXTS and os.path.isfile(path):
                candidates = self._read_m3u(path)
            else:
                candidates = [path]
            for p in candidates:
                item = self._make_item(p)
                if item:
                    self.items.append(item)
        self._after_add(first_new, play_now)

    def add_item(self, path: str, title: str = None, options: list = None, play_now: bool = True):
        """Adds a single MRL (disc, capture device...) with optional LibVLC media options."""
        first_new = len(self.items)
        item = self._make_item(path, title, options)
        if item:
            self.items.append(item)
        self._after_add(first_new, play_now)

    def _after_add(self, first_new: int, play_now: bool):
        self.playlist_updated.emit()
        if first_new < len(self.items) and (play_now or self.current_index == -1):
            self.set_current_index(first_new)

    def play_path(self, path: str):
        """Plays an item already in the playlist, or adds and plays it."""
        for i, item in enumerate(self.items):
            if item["path"] == path:
                self.set_current_index(i)
                return
        self.add_files([path], play_now=True)

    def save_m3u(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in self.items:
                f.write(f"#EXTINF:-1,{item['title']}\n{item['path']}\n")

    def clear(self):
        self.items.clear()
        self.current_index = -1
        self.playlist_updated.emit()

    def remove_at(self, index: int):
        if 0 <= index < len(self.items):
            self.items.pop(index)
            if index < self.current_index:
                self.current_index -= 1
            elif index == self.current_index:
                self.current_index = -1
            self.playlist_updated.emit()

    def reorder(self, new_order: list):
        """new_order lists the old indices in their new positions."""
        if sorted(new_order) != list(range(len(self.items))):
            return
        self.items = [self.items[i] for i in new_order]
        if self.current_index >= 0:
            self.current_index = new_order.index(self.current_index)
        self.playlist_updated.emit()

    def sort_by_title(self):
        order = sorted(range(len(self.items)), key=lambda i: self.items[i]["title"].lower())
        self.reorder(order)

    def set_current_index(self, index: int):
        if 0 <= index < len(self.items):
            self.current_index = index
            self.track_changed.emit(self.current_index, self.items[self.current_index]["path"])

    def get_current_track(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def next_track(self, auto: bool = False):
        """auto=True when the current track finished on its own (honours repeat-one)."""
        if not self.items:
            return None
        if auto and self.repeat_mode == REPEAT_ONE and self.current_index >= 0:
            next_idx = self.current_index
        elif self.is_shuffle and len(self.items) > 1:
            next_idx = random.choice([i for i in range(len(self.items)) if i != self.current_index])
        else:
            next_idx = self.current_index + 1
            if next_idx >= len(self.items):
                if self.repeat_mode != REPEAT_OFF:
                    next_idx = 0
                else:
                    return None
        self.set_current_index(next_idx)
        return self.items[next_idx]

    def prev_track(self):
        if not self.items:
            return None
        prev_idx = self.current_index - 1
        if prev_idx < 0:
            prev_idx = len(self.items) - 1 if self.repeat_mode != REPEAT_OFF else 0
        self.set_current_index(prev_idx)
        return self.items[prev_idx]

    def toggle_shuffle(self) -> bool:
        self.is_shuffle = not self.is_shuffle
        return self.is_shuffle

    def cycle_repeat(self) -> int:
        self.repeat_mode = (self.repeat_mode + 1) % 3
        return self.repeat_mode
