"""
Prism Player - Application Entry Point
"""

import sys
import os
import ctypes

# 1. Determine base directories (PyInstaller temp folder or current script folder)
base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

# 2. Strict 64-bit VLC detection (Never 32-bit Program Files (x86)!)
candidates = [
    # Portable folder next to exe
    (os.path.join(exe_dir, "libvlc.dll"), os.path.join(exe_dir, "plugins")),
    # Standard 64-bit VLC installation
    (r"C:\Program Files\VideoLAN\VLC\libvlc.dll", r"C:\Program Files\VideoLAN\VLC\plugins"),
    # Bundle folder if plugins exist
    (os.path.join(base_dir, "libvlc.dll"), os.path.join(base_dir, "plugins")),
]

vlc_lib_file = None
vlc_plugin_dir = None
for dll_path, plug_path in candidates:
    if os.path.exists(dll_path):
        vlc_lib_file = dll_path
        if os.path.exists(plug_path):
            vlc_plugin_dir = plug_path
        break

if vlc_lib_file:
    vlc_dir = os.path.dirname(vlc_lib_file)
    core_dll = os.path.join(vlc_dir, "libvlccore.dll")

    # Pre-load libvlccore.dll if present
    if os.path.exists(core_dll):
        try:
            ctypes.CDLL(core_dll)
        except Exception:
            pass

    # Pre-load libvlc.dll
    try:
        ctypes.CDLL(vlc_lib_file)
    except Exception:
        pass

    os.environ["PYTHON_VLC_LIB_PATH"] = vlc_lib_file
    if vlc_plugin_dir:
        os.environ["PYTHON_VLC_MODULE_PATH"] = vlc_plugin_dir
        os.environ["VLC_PLUGIN_PATH"] = vlc_plugin_dir

    if vlc_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = vlc_dir + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(vlc_dir)
        except Exception:
            pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSettings

from liquid_theme import APP_NAME, app_icon, app_icon_pixmap
import win_integration as win

APP_ID = "Prism.Player"


def _log_unhandled_exception(exc_type, exc_value, exc_tb):
    # PyQt6 aborts the whole process on an exception escaping a slot/event
    # handler unless sys.excepthook is overridden; log it and keep running.
    import traceback
    if sys.stderr:
        traceback.print_exception(exc_type, exc_value, exc_tb)


def _register_app_identity():
    """Name and icon Windows shows for Prism's media session (volume flyout, lock screen)."""
    if not getattr(sys, "frozen", False):
        return  # running from source: python.exe's identity is fine
    try:
        folder = os.path.join(os.environ.get("LOCALAPPDATA", exe_dir), APP_NAME)
        os.makedirs(folder, exist_ok=True)
        icon = os.path.join(folder, "prism.png")
        if not os.path.exists(icon):
            app_icon_pixmap(64).save(icon)
        win.register_app_id(APP_ID, APP_NAME, icon)
    except OSError:
        pass


def main():
    sys.excepthook = _log_unhandled_exception

    # Own taskbar identity, so Windows shows Prism's icon instead of python.exe's
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass

    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(app_icon())

    # Run by the installer / uninstaller: file types for "Open with" and Default apps, no window
    if "--register" in sys.argv or "--unregister" in sys.argv:
        from main_window import MEDIA_EXTS
        from playlist_manager import PLAYLIST_EXTS
        if "--register" in sys.argv:
            win.register_file_types(MEDIA_EXTS | PLAYLIST_EXTS)
        else:
            win.unregister_file_types(MEDIA_EXTS | PLAYLIST_EXTS)
            win.unregister_app_id(APP_ID)
        return 0

    # Held while Prism runs, so the installer and uninstaller (AppMutex) ask to close it first
    ctypes.windll.kernel32.CreateMutexW(None, False, "Prism.Player.Running")

    # Files passed on the command line ("Open with" / drag onto the exe); absolute,
    # since a running instance has a different working directory
    args = [os.path.abspath(a) if os.path.exists(a) else a
            for a in sys.argv[1:] if os.path.exists(a) or "://" in a]

    # One player: hand the files to the running Prism and quit
    instance = None
    if QSettings(APP_NAME, APP_NAME).value("prefs/single_instance", True, type=bool):
        instance = win.SingleInstance(APP_ID)
        if instance.is_primary:
            # Listen before the slow part (LibVLC, the window), so a second launch isn't kept waiting
            instance.listen()
        elif instance.send(args):
            return 0

    _register_app_identity()

    # Modern clean font (Windows 11 variable Segoe, falls back to classic Segoe UI)
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPointSize(10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    from main_window import MainWindow
    window = MainWindow()
    if instance is not None:
        window.attach_instance(instance)

    if args:
        window.playlist_mgr.add_files(args, play_now=True)

    # Opens full size; the restore button still brings back the 1080×700 window
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
