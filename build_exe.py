"""
Build script to compile Prism Player into dist/Prism/ (Prism.exe with its libraries and LibVLC)
"""

import shutil
import subprocess
import sys
import os

# LibVLC copied next to the EXE: libvlc.dll, libvlccore.dll and plugins/ (with plugins.dat)
VLC_RUNTIME = "vlc_runtime"


def make_icon(path: str):
    """Renders the Prism logo into a multi-size Windows .ico."""
    from PyQt6.QtGui import QGuiApplication
    from liquid_theme import app_icon_pixmap
    app = QGuiApplication.instance() or QGuiApplication([])
    # Qt's ICO writer stores one image per file, so build the container by hand from PNGs
    import struct
    from PyQt6.QtCore import QBuffer, QIODevice
    sizes = [16, 24, 32, 48, 64, 128, 256]
    blobs = []
    for s in sizes:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        app_icon_pixmap(s).save(buf, "PNG")
        blobs.append(bytes(buf.data()))
    offset = 6 + 16 * len(sizes)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        for s, blob in zip(sizes, blobs):
            f.write(struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset))
            offset += len(blob)
        for blob in blobs:
            f.write(blob)


def make_version_file(path: str):
    """
    Version resource for the EXE. Windows names the app in "Open with" after its FileDescription;
    without one it falls back to the file name, "Prism.exe".
    """
    from liquid_theme import APP_NAME, APP_VERSION
    nums = ([int(n) for n in APP_VERSION.split(".") if n.isdigit()] + [0, 0, 0, 0])[:4]
    strings = {"CompanyName": APP_NAME, "FileDescription": APP_NAME, "FileVersion": APP_VERSION,
               "InternalName": APP_NAME, "OriginalFilename": f"{APP_NAME}.exe",
               "ProductName": APP_NAME, "ProductVersion": APP_VERSION}
    entries = ",\n          ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(nums)}, prodvers={tuple(nums)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
          {entries}])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
""")


def build():
    print("=" * 60)
    print("Building Prism Player (folder build)")
    print("=" * 60)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(script_dir, "main.py")
    icon_path = os.path.join(script_dir, "prism.ico")
    sys.path.insert(0, script_dir)
    make_icon(icon_path)
    version_path = os.path.join(script_dir, "build", "version_info.txt")
    os.makedirs(os.path.dirname(version_path), exist_ok=True)
    make_version_file(version_path)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        # A folder, not --onefile: a single-file EXE unpacks ~100 MB to %TEMP% on every start
        # (seconds, plus a virus scan of each file) and leaves it behind when it doesn't exit cleanly
        "--onedir",
        "--windowed",
        "--name", "Prism",
        "--icon", icon_path,
        "--version-file", version_path,
        "--collect-all", "winrt",  # WinRT media controls: native modules PyInstaller can't trace
        main_py
    ]

    print("Running PyInstaller command:")
    print(" ".join(cmd))
    ret = subprocess.run(cmd, cwd=script_dir)
    if ret.returncode == 0:
        dist_dir = os.path.join(script_dir, "dist", "Prism")
        dist_exe = os.path.join(dist_dir, "Prism.exe")
        if os.path.exists(dist_exe):
            if not copy_vlc_runtime(os.path.join(script_dir, VLC_RUNTIME), dist_dir):
                return
            size_mb = sum(os.path.getsize(os.path.join(root, f))
                          for root, _, files in os.walk(dist_dir) for f in files) / (1024 * 1024)
            print("=" * 60)
            print(f"SUCCESS! Player generated at:")
            print(f" -> {dist_exe}")
            print(f" -> Folder size: {size_mb:.2f} MB")
            print("=" * 60)
            build_installer(script_dir)
        else:
            print("Build completed but dist/Prism/Prism.exe was not found.")
    else:
        print(f"Build failed with exit code: {ret.returncode}")


def copy_vlc_runtime(src: str, dest: str) -> bool:
    """LibVLC goes next to Prism.exe, where main.py looks for it first."""
    names = ("libvlc.dll", "libvlccore.dll", "plugins")
    missing = [n for n in names if not os.path.exists(os.path.join(src, n))]
    if missing:
        print(f"Missing from {src}: {', '.join(missing)} (copy them from a 64-bit VLC 3 install)")
        return False
    for name in names:
        path = os.path.join(src, name)
        if os.path.isdir(path):
            # copy2 keeps the timestamps plugins.dat was built against, so LibVLC trusts the cache
            shutil.copytree(path, os.path.join(dest, name), copy_function=shutil.copy2, dirs_exist_ok=True)
        else:
            shutil.copy2(path, dest)
    return True


def find_iscc():
    """ISCC.exe from a per-user or machine-wide Inno Setup 6 install."""
    for root in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
                 os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        path = os.path.join(root, "Inno Setup 6", "ISCC.exe")
        if root and os.path.exists(path):
            return path
    return None


def build_installer(script_dir: str):
    """Packs dist/ into installer/Prism-Setup-<version>.exe with Inno Setup (Prism.iss)."""
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup 6 not found, skipping the installer (winget install JRSoftware.InnoSetup)")
        return
    from liquid_theme import APP_VERSION
    print("Building installer...")
    ret = subprocess.run([iscc, "/Q", f"/DAppVersion={APP_VERSION}", "Prism.iss"], cwd=script_dir)
    if ret.returncode == 0:
        setup = os.path.join(script_dir, "installer", f"Prism-Setup-{APP_VERSION}.exe")
        print(f"Installer: {setup} ({os.path.getsize(setup) / (1024 * 1024):.2f} MB)")
    else:
        print(f"Installer build failed with exit code: {ret.returncode}")

if __name__ == "__main__":
    build()
