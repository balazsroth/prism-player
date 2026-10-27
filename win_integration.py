"""
Windows shell integration: window placement, the taskbar button (thumbnail toolbar and
progress), the system media controls (media keys and the volume flyout), single-instance
hand-off and file-type registration.
"""

import ctypes
import getpass
import json
import os
import sys
import time
import winreg
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

user32 = ctypes.windll.user32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
user32.GetWindowPlacement.argtypes = (wintypes.HWND, ctypes.c_void_p)
user32.SetWindowPlacement.argtypes = (wintypes.HWND, ctypes.c_void_p)
user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.c_void_p)


# --- Window placement ---
class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT), ("showCmd", wintypes.UINT),
                ("ptMinPosition", wintypes.POINT), ("ptMaxPosition", wintypes.POINT),
                ("rcNormalPosition", wintypes.RECT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def get_placement(hwnd: int) -> WINDOWPLACEMENT:
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(wp)
    user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    return wp


def set_normal_rect(hwnd: int, rect: tuple):
    """Changes the size a maximized window restores to, without moving it."""
    wp = get_placement(hwnd)
    wp.rcNormalPosition = wintypes.RECT(*rect)
    user32.SetWindowPlacement(hwnd, ctypes.byref(wp))


def normal_rect(hwnd: int) -> tuple:
    r = get_placement(hwnd).rcNormalPosition
    return r.left, r.top, r.right, r.bottom


def maximized_normal_rect(hwnd: int) -> tuple:
    """The window's maximized area in workspace coordinates (what rcNormalPosition uses)."""
    MONITOR_DEFAULTTONEAREST, MONITOR_DEFAULTTOPRIMARY = 2, 1
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    mon = user32.MonitorFromPoint(wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2),
                                  MONITOR_DEFAULTTONEAREST)
    primary = user32.MonitorFromPoint(wintypes.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
    work, base = MONITORINFO(), MONITORINFO()
    work.cbSize = base.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(mon, ctypes.byref(work))
    user32.GetMonitorInfoW(primary, ctypes.byref(base))
    # Workspace coordinates are screen coordinates shifted by the primary monitor's work-area origin
    dx, dy = base.rcWork.left - base.rcMonitor.left, base.rcWork.top - base.rcMonitor.top
    w = work.rcWork
    return w.left - dx, w.top - dy, w.right - dx, w.bottom - dy


def read_msg(message) -> wintypes.MSG:
    """The MSG behind a QWidget.nativeEvent message pointer."""
    return wintypes.MSG.from_address(int(message))


def light_taskbar() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def bring_to_front(hwnd: int):
    """Un-minimizes (back to maximized if it was) and focuses the window."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


# --- Single instance ---
class SingleInstance(QObject):
    """
    One player per user session: a later launch hands its command line to the running
    instance over a local socket and exits. The mutex decides who is first, even when
    Explorer starts several copies at once for a multi-file selection.
    """
    received = pyqtSignal(list)

    def __init__(self, app_id: str = "Prism.Player", parent=None):
        super().__init__(parent)
        self.name = f"{app_id}-{getpass.getuser()}"
        self._mutex = kernel32.CreateMutexW(None, False, "Local\\" + self.name)
        self.is_primary = ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
        self._server = None
        self.pending = []   # arrivals before anyone connected to `received` (window still starting)

    @property
    def listening(self) -> bool:
        return self._server is not None

    def send(self, args: list, timeout: float = 20.0) -> bool:
        """Secondary side; waits for the first instance, which may still be starting up."""
        user32.AllowSetForegroundWindow(-1)  # ASFW_ANY: let it come to the front
        payload = json.dumps(args).encode("utf-8")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sock = QLocalSocket()
            sock.connectToServer(self.name)
            if not sock.waitForConnected(300):
                time.sleep(0.1)
                continue
            sock.write(payload)
            # The write completes only once the other side reads it, i.e. when its event loop
            # runs again; it may still be building its window
            ok = sock.waitForBytesWritten(max(1, int((deadline - time.monotonic()) * 1000)))
            sock.disconnectFromServer()
            if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                sock.waitForDisconnected(1000)
            return ok
        return False

    def listen(self) -> bool:
        QLocalServer.removeServer(self.name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        return self._server.listen(self.name)

    def close(self):
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._mutex:
            kernel32.CloseHandle(self._mutex)
            self._mutex = None

    def _on_connection(self):
        while self._server is not None and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            buf = bytearray()
            sock.readyRead.connect(lambda s=sock, b=buf: b.extend(bytes(s.readAll())))
            sock.disconnected.connect(lambda s=sock, b=buf: self._finish(s, b))

    def _finish(self, sock, buf: bytearray):
        buf.extend(bytes(sock.readAll()))
        sock.deleteLater()
        try:
            args = json.loads(buf.decode("utf-8"))
        except ValueError:
            return
        if not isinstance(args, list):
            return
        args = [str(a) for a in args]
        if self.receivers(self.received):
            self.received.emit(args)
        else:
            self.pending += args


# --- Taskbar button: thumbnail toolbar and progress (ITaskbarList3) ---
ole32 = ctypes.windll.ole32


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> GUID:
    g = GUID()
    ole32.CLSIDFromString(wintypes.LPCWSTR(text), ctypes.byref(g))
    return g


class THUMBBUTTON(ctypes.Structure):
    _fields_ = [("dwMask", wintypes.DWORD), ("iId", wintypes.UINT), ("iBitmap", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 260), ("dwFlags", wintypes.DWORD)]


WM_COMMAND = 0x0111
THBN_CLICKED = 0x1800
TBPF_NOPROGRESS, TBPF_NORMAL, TBPF_PAUSED = 0, 2, 8
_THB_ICON, _THB_TOOLTIP, _THB_FLAGS = 0x2, 0x4, 0x8
TASKBAR_CREATED = user32.RegisterWindowMessageW("TaskbarButtonCreated")


class TaskbarButton:
    """The window's taskbar icon: buttons in its thumbnail preview and a progress bar."""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(_guid("{56FDF344-FD6D-11d0-958A-006097C9A090}")), None, 1,
                                    ctypes.byref(_guid("{ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf}")),
                                    ctypes.byref(self._ptr))
        if hr != 0 or not self._ptr:
            self._ptr = None
        else:
            self._call(3)  # HrInit
        self._buttons = []      # [(id, hicon, tooltip)]
        self._added = False
        self._progress = None   # last (state, value, total) sent

    def _call(self, index: int, argtypes=(), *args) -> int:
        if not self._ptr:
            return -1
        vtbl = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
        return proto(vtbl[index])(self._ptr, *args)

    def button_created(self):
        """Explorer (re)created the taskbar button: everything has to be sent again."""
        self._added = False
        self._progress = None
        if self._buttons:
            self.set_buttons(self._buttons)

    def set_buttons(self, buttons: list):
        self._buttons = list(buttons)
        arr = (THUMBBUTTON * len(buttons))()
        for slot, (bid, hicon, tip) in zip(arr, buttons):
            slot.dwMask = _THB_ICON | _THB_TOOLTIP | _THB_FLAGS
            slot.iId, slot.hIcon, slot.szTip, slot.dwFlags = bid, hicon, tip[:259], 0
        args = ((wintypes.HWND, wintypes.UINT, ctypes.POINTER(THUMBBUTTON)), self.hwnd, len(buttons), arr)
        if self._added:
            self._call(16, *args)          # ThumbBarUpdateButtons
        elif self._call(15, *args) == 0:  # ThumbBarAddButtons (only once per taskbar button)
            self._added = True

    def set_progress(self, state: int, value: int = 0, total: int = 0):
        if state == TBPF_NOPROGRESS:
            value = total = 0
        elif total > 0:
            value = value * 1000 // total  # coarse steps: the taskbar can't show finer anyway
            total = 1000
        if (state, value, total) == self._progress:
            return
        if self._progress is None or self._progress[0] != state:
            self._call(10, (wintypes.HWND, ctypes.c_int), self.hwnd, state)  # SetProgressState
        if state != TBPF_NOPROGRESS and total > 0:
            self._call(9, (wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong), self.hwnd, value, total)
        self._progress = (state, value, total)

    def release(self):
        if self._ptr:
            self._call(2)  # IUnknown::Release
            self._ptr = None


# --- System media controls (media keys, volume flyout, lock screen) ---
class MediaSession(QObject):
    """
    A Windows media session through WinRT's SystemMediaTransportControls. A MediaPlayer with its
    command manager off is the documented way for a desktop app to own one without a UWP window.
    """
    button = pyqtSignal(str)   # play, pause, stop, next, previous

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = self._smtc = None
        self._started = False
        self._media = None          # last set_media/set_status, replayed once started
        self._status = "closed"

    def start(self):
        """Loading WinRT takes about half a second, so the window comes up first and calls this after."""
        if self._started:
            return
        self._started = True
        try:
            from winrt.windows.media.playback import MediaPlayer
            from winrt.windows.media import (MediaPlaybackStatus, MediaPlaybackType,
                                             SystemMediaTransportControlsButton as B)
        except ImportError:
            return
        self._status_values = {"playing": MediaPlaybackStatus.PLAYING, "paused": MediaPlaybackStatus.PAUSED,
                               "stopped": MediaPlaybackStatus.STOPPED, "closed": MediaPlaybackStatus.CLOSED}
        self._types = (MediaPlaybackType.MUSIC, MediaPlaybackType.VIDEO)
        self._names = {B.PLAY: "play", B.PAUSE: "pause", B.STOP: "stop", B.NEXT: "next", B.PREVIOUS: "previous"}
        try:
            self._player = MediaPlayer()
            self._player.command_manager.is_enabled = False
            s = self._smtc = self._player.system_media_transport_controls
            s.is_play_enabled = s.is_pause_enabled = s.is_stop_enabled = True
            s.is_next_enabled = s.is_previous_enabled = True
            s.playback_status = MediaPlaybackStatus.CLOSED
            s.is_enabled = True
            s.add_button_pressed(self._on_button)
        except OSError:
            self._player = self._smtc = None
            return
        if self._media:
            self.set_media(*self._media)
        self.set_status(self._status)

    @property
    def available(self) -> bool:
        return self._smtc is not None

    def _on_button(self, sender, args):
        name = self._names.get(args.button)
        if name:
            self.button.emit(name)  # from a WinRT thread; queued over to the Qt thread

    def set_media(self, title: str, artist: str, is_video: bool):
        self._media = (title, artist, is_video)
        if not self._smtc:
            return
        d = self._smtc.display_updater
        d.clear_all()
        d.type = self._types[1] if is_video else self._types[0]
        props = d.video_properties if is_video else d.music_properties
        props.title = title or ""
        if is_video:
            props.subtitle = artist or ""
        else:
            props.artist = artist or ""
        d.update()

    def set_status(self, status: str):
        self._status = status
        if self._smtc:
            self._smtc.playback_status = self._status_values[status]

    def close(self):
        self._started = True  # closing before the deferred start: don't start afterwards
        if self._smtc:
            self._smtc.is_enabled = False
        if self._player:
            self._player.close()
        self._player = self._smtc = None


# --- File types ("Open with", Default apps) ---
PROG_ID = "Prism.Media"
REG_NAME = "Prism"


def launch_command() -> tuple:
    """(open command, icon) for this copy of the player: the EXE, or pythonw + main.py when run from source."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"', f'"{sys.executable}",0'
    here = os.path.dirname(os.path.abspath(__file__))
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return f'"{pyw}" "{os.path.join(here, "main.py")}" "%1"', os.path.join(here, "prism.ico")


def _set_value(path: str, name: str, value: str):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _delete_value(path: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, name)
    except OSError:
        pass


def _delete_tree(path: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(f"{path}\\{child}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


def _notify_shell():
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED


def _set_friendly_name(classes: str, command: str, icon: str):
    """
    "Prism" instead of "Prism.exe" in the Open with list. Explorer caches the name it read from the
    EXE in MuiCache, so a stale "Prism.exe" entry from an earlier build is overwritten as well.
    """
    if not getattr(sys, "frozen", False):
        return  # from source the command is pythonw.exe, whose name isn't ours to change
    app = rf"{classes}\Applications\{os.path.basename(sys.executable)}"
    _set_value(app, "FriendlyAppName", REG_NAME)
    _set_value(app + r"\DefaultIcon", "", icon)
    _set_value(app + r"\shell\open\command", "", command)
    _set_value(classes + r"\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
               sys.executable + ".FriendlyAppName", REG_NAME)


def register_file_types(exts, base: str = "Software"):
    """
    Per-user registration (no admin rights): a ProgID, an "Open with" entry for each extension and
    Default-apps capabilities. Windows lets only the user pick the default player, so this never
    takes over a file type by itself.
    """
    command, icon = launch_command()
    classes = base + r"\Classes"
    prog = f"{classes}\\{PROG_ID}"
    _set_value(prog, "", "Prism médiafájl")
    _set_value(prog + r"\DefaultIcon", "", icon)
    _set_value(prog + r"\shell\open", "", "Lejátszás a Prismmel")
    _set_value(prog + r"\shell\open", "FriendlyAppName", REG_NAME)
    _set_value(prog + r"\shell\open\command", "", command)
    _set_friendly_name(classes, command, icon)
    caps = f"{base}\\PrismPlayer\\Capabilities"
    _set_value(caps, "ApplicationName", "Prism")
    _set_value(caps, "ApplicationDescription", "Prism médialejátszó")
    _set_value(caps, "ApplicationIcon", icon)
    for ext in exts:
        _set_value(f"{classes}\\{ext}\\OpenWithProgids", PROG_ID, "")
        _set_value(caps + r"\FileAssociations", ext, PROG_ID)
    _set_value(base + r"\RegisteredApplications", REG_NAME, caps)  # path under HKCU
    _notify_shell()


def unregister_file_types(exts, base: str = "Software"):
    classes = base + r"\Classes"
    for ext in exts:
        _delete_value(f"{classes}\\{ext}\\OpenWithProgids", PROG_ID)
    _delete_tree(f"{classes}\\{PROG_ID}")
    if getattr(sys, "frozen", False):
        _delete_tree(rf"{classes}\Applications\{os.path.basename(sys.executable)}")
    _delete_tree(f"{base}\\PrismPlayer")
    _delete_value(base + r"\RegisteredApplications", REG_NAME)
    _notify_shell()


def file_types_registered(base: str = "Software") -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + r"\RegisteredApplications") as key:
            winreg.QueryValueEx(key, REG_NAME)
        return True
    except OSError:
        return False


def open_default_apps():
    """Windows Settings → Default apps, opened on Prism's page where supported."""
    try:
        os.startfile(f"ms-settings:defaultapps?registeredAppUser={REG_NAME}")
    except OSError:
        os.startfile("ms-settings:defaultapps")


def register_app_id(app_id: str, display_name: str, icon_path: str = ""):
    """Name (and icon) Windows shows for the AppUserModelID, e.g. in the media flyout."""
    path = rf"Software\Classes\AppUserModelId\{app_id}"
    _set_value(path, "DisplayName", display_name)
    if icon_path:
        _set_value(path, "IconUri", icon_path)


def unregister_app_id(app_id: str):
    _delete_tree(rf"Software\Classes\AppUserModelId\{app_id}")
