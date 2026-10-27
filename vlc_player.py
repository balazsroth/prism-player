"""
VLC Player Engine: Wraps LibVLC providing full codec support, hardware acceleration,
audio/video/subtitle track control, 10-band equalizer, audio & video effect filters,
video adjustments, logo overlay, subtitle styling, recording, titles/chapters/programs,
disc menus, teletext, renderers (Chromecast), log capture, on-screen display and transcoding.
"""

import collections
import ctypes
import threading
import vlc
import os
import struct
import sys
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

import vlc_vars


def _descriptions(tracks):
    """LibVLC track description list -> [(id, name)]."""
    result = []
    for t in tracks or []:
        name = t[1].decode("utf-8", errors="ignore") if isinstance(t[1], bytes) else (t[1] or "")
        result.append((t[0], name))
    return result


def _fourcc(code: int) -> str:
    return struct.pack("<I", code).decode("ascii", errors="replace").strip("\x00 ")


class _MediaTrack(ctypes.Structure):
    """libvlc_media_track_t as LibVLC 3 lays it out. python-vlc's MediaTrack lists the
    audio/video/subtitle union as three separate pointers, which shifts every later
    field and makes reading language/description dereference garbage."""
    _fields_ = [("codec", ctypes.c_uint32), ("original_fourcc", ctypes.c_uint32),
                ("id", ctypes.c_int), ("type", ctypes.c_int), ("profile", ctypes.c_int),
                ("level", ctypes.c_int), ("detail", ctypes.c_void_p), ("bitrate", ctypes.c_uint),
                ("language", ctypes.c_char_p), ("description", ctypes.c_char_p)]


def _media_tracks(media) -> list:
    # python-vlc declares the out-parameter one pointer level short; mirror its own
    # tracks_get() call and reinterpret the returned array.
    out = ctypes.POINTER(vlc.MediaTrack)()
    n = vlc.libvlc_media_tracks_get(media, ctypes.byref(out))
    array = ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(_MediaTrack)))
    tracks = []
    for i in range(n):
        t = array[i].contents
        track = {
            "type": t.type,
            "codec": _fourcc(t.codec),
            "language": (t.language or b"").decode("utf-8", errors="ignore"),
            "description": (t.description or b"").decode("utf-8", errors="ignore"),
            "bitrate": t.bitrate,
        }
        if t.type == vlc.TrackType.video and t.detail:
            v = ctypes.cast(t.detail, ctypes.POINTER(vlc.VideoTrack)).contents
            track.update(kind="video", width=v.width, height=v.height,
                         fps=(v.frame_rate_num / v.frame_rate_den) if v.frame_rate_den else 0)
        elif t.type == vlc.TrackType.audio and t.detail:
            a = ctypes.cast(t.detail, ctypes.POINTER(vlc.AudioTrack)).contents
            track.update(kind="audio", channels=a.channels, rate=a.rate)
        else:
            track.update(kind="subtitle" if t.type == vlc.TrackType.ext else "other")
        tracks.append(track)
    if n > 0:
        vlc.libvlc_media_tracks_release(ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(vlc.MediaTrack))), n)
    return tracks


DEINTERLACE_MODES = ["blend", "bob", "discard", "linear", "mean", "x", "yadif", "yadif2x", "phosphor", "ivtc"]
VIDEO_ADJUST_DEFAULTS = {"contrast": 1.0, "brightness": 1.0, "hue": 0.0, "saturation": 1.0, "gamma": 1.0}

# User filters as (module, label, [(variable, label, "f"/"i", min, max, default, step)]).
# Variable types must match the module's own option type, or VLC won't inherit them.
AUDIO_EFFECTS = [
    ("compressor", "Kompresszor (dinamikatömörítés)", [
        ("compressor-rms-peak", "RMS / csúcs", "f", 0.0, 1.0, 0.2, 0.01),
        ("compressor-attack", "Felfutás (ms)", "f", 1.5, 400.0, 25.0, 0.5),
        ("compressor-release", "Lecsengés (ms)", "f", 2.0, 800.0, 100.0, 1.0),
        ("compressor-threshold", "Küszöb (dB)", "f", -30.0, 0.0, -11.0, 0.5),
        ("compressor-ratio", "Arány (n:1)", "f", 1.0, 20.0, 4.0, 0.1),
        ("compressor-knee", "Térd (dB)", "f", 1.0, 10.0, 5.0, 0.1),
        ("compressor-makeup-gain", "Utóerősítés (dB)", "f", 0.0, 24.0, 7.0, 0.1),
    ]),
    ("spatializer", "Térhatás (spatializer)", [
        ("spatializer-roomsize", "Teremméret", "f", 0.0, 1.1, 0.85, 0.01),
        ("spatializer-width", "Szélesség", "f", 0.0, 1.0, 1.0, 0.01),
        ("spatializer-wet", "Effekt arány", "f", 0.0, 1.0, 0.4, 0.01),
        ("spatializer-dry", "Eredeti arány", "f", 0.0, 1.0, 0.5, 0.01),
        ("spatializer-damp", "Csillapítás", "f", 0.0, 1.0, 0.5, 0.01),
    ]),
    ("normvol", "Hangerő-normalizálás", [
        ("norm-max-level", "Maximális szint", "f", 0.0, 10.0, 2.0, 0.1),
    ]),
    ("karaoke", "Karaoke (énekhang csökkentése)", []),
    ("mono", "Mono lekeverés", []),
]
PITCH_RANGE = (-12.0, 12.0)  # semitones, scaletempo_pitch

TRANSFORMS = [("Nincs", None), ("Forgatás 90°", "90"), ("Forgatás 180°", "180"), ("Forgatás 270°", "270"),
              ("Vízszintes tükrözés", "hflip"), ("Függőleges tükrözés", "vflip"),
              ("Transzponálás", "transpose"), ("Antitranszponálás", "antitranspose")]

VIDEO_EFFECTS = [
    ("sharpen", "Élesítés", [("sharpen-sigma", "Erősség", "f", 0.0, 2.0, 0.05, 0.01)]),
    ("hqdn3d", "Zajszűrés (HQ 3D)", [
        ("hqdn3d-luma-spat", "Térbeli", "f", 0.0, 50.0, 4.0, 0.5),
        ("hqdn3d-luma-temp", "Időbeli", "f", 0.0, 50.0, 6.0, 0.5),
    ]),
    ("gradfun", "Színsávosodás csökkentése", [("gradfun-strength", "Erősség", "f", 0.51, 10.0, 1.2, 0.01)]),
    ("grain", "Filmszemcse", [("grain-variance", "Erősség", "f", 0.0, 10.0, 2.0, 0.1)]),
    ("antiflicker", "Villódzáscsökkentés", []),
    ("invert", "Színinvertálás", []),
    ("sepia", "Szépia", [("sepia-intensity", "Intenzitás", "i", 0, 255, 120, 1)]),
    ("posterize", "Poszterizálás", [("posterize-level", "Színszintek", "i", 2, 64, 6, 1)]),
    ("motionblur", "Mozgási elmosás", [("blur-factor", "Erősség", "i", 1, 127, 80, 1)]),
    ("gaussianblur", "Gauss-elmosás", [("gaussianblur-sigma", "Szigma", "f", 0.1, 10.0, 2.0, 0.1)]),
    ("edgedetection", "Élkiemelés", []),
    ("anaglyph", "Anaglif 3D", []),
    ("oldmovie", "Régi film", []),
    ("vhs", "VHS", []),
    ("wave", "Hullám", []),
    ("psychedelic", "Pszichedelikus", []),
]

# Options a filter reads only when it opens (no live callback): parameter -> filter
REBUILD_PARAMS = {"gaussianblur-sigma": "gaussianblur"}

LOGO_POSITIONS = [("Középen", 0), ("Balra", 1), ("Jobbra", 2), ("Fent", 4), ("Lent", 8),
                  ("Bal felső", 5), ("Jobb felső", 6), ("Bal alsó", 9), ("Jobb alsó", 10)]

SUBTITLE_STYLE_DEFAULTS = {
    "sub-text-scale": 100,                 # %, live
    "sub-margin": 0,                       # px from the bottom, live
    "freetype-font": "",
    "freetype-color": 0xFFFFFF,
    "freetype-opacity": 255,
    "freetype-bold": False,
    "freetype-outline-thickness": 4,
    "freetype-outline-color": 0x000000,
    "freetype-background-opacity": 0,
    "freetype-background-color": 0x000000,
    "subsdec-encoding": "",
}
LIVE_SUBTITLE_VARS = {"sub-text-scale", "sub-margin"}

NAV_ACTIVATE, NAV_UP, NAV_DOWN, NAV_LEFT, NAV_RIGHT, NAV_POPUP = range(6)

LOG_LEVELS = {0: "debug", 2: "info", 3: "warning", 4: "error"}


def _effect_defaults(effects) -> dict:
    return {var: default for _, _, params in effects for var, _, _, _, _, default, _ in params}


class LogCapture:
    """Collects LibVLC's log messages (from any thread) into a bounded buffer."""

    def __init__(self, maxlen: int = 4000):
        self.messages = collections.deque(maxlen=maxlen)
        self.lock = threading.Lock()
        self._instance = None
        self._callback = None
        try:
            # getattr: a literal __name inside a class body would be name-mangled
            fmt = getattr(ctypes.CDLL("ucrtbase"), "__stdio_common_vsprintf")
            fmt.argtypes = [ctypes.c_ulonglong, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
                            ctypes.c_void_p, ctypes.c_void_p]
            self._format = fmt
            ctx = vlc.dll.libvlc_log_get_context
            ctx.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p),
                            ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_uint)]
            ctx.restype = None
            self._context = ctx
        except (AttributeError, OSError):
            self._format = None

    def install(self, instance):
        if self._format is None:
            return

        @vlc.CallbackDecorators.LogCb
        def on_log(_data, level, ctx, fmt, args):
            buf = ctypes.create_string_buffer(1024)
            # 2 = standard snprintf truncation; LibVLC's va_list is a plain pointer on Win64
            self._format(2, buf, 1024, fmt, None, ctypes.cast(args, ctypes.c_void_p))
            module = ctypes.c_char_p()
            self._context(ctypes.cast(ctx, ctypes.c_void_p), ctypes.byref(module), ctypes.byref(ctypes.c_char_p()),
                          ctypes.byref(ctypes.c_uint()))
            entry = (level, (module.value or b"").decode("utf-8", errors="replace"),
                     buf.value.decode("utf-8", errors="replace"))
            with self.lock:
                self.messages.append(entry)

        self._callback = on_log  # must outlive LibVLC's use of it
        self._instance = instance
        instance.log_set(on_log, None)

    def uninstall(self):
        if self._instance is not None:
            self._instance.log_unset()
            self._instance = None

    def snapshot(self) -> list:
        with self.lock:
            return list(self.messages)

    def clear(self):
        with self.lock:
            self.messages.clear()


class RendererScanner:
    """Finds Chromecast-style renderers with LibVLC's renderer discoverers."""

    def __init__(self, instance):
        self.instance = instance
        self.discoverers = []
        self.items = {}           # item pointer -> (name, type)
        self.lock = threading.Lock()
        d = vlc.dll
        for fn, res, args in (("libvlc_renderer_item_hold", ctypes.c_void_p, [ctypes.c_void_p]),
                              ("libvlc_renderer_item_release", None, [ctypes.c_void_p]),
                              ("libvlc_renderer_item_name", ctypes.c_char_p, [ctypes.c_void_p]),
                              ("libvlc_renderer_item_type", ctypes.c_char_p, [ctypes.c_void_p]),
                              ("libvlc_media_player_set_renderer", ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p])):
            getattr(d, fn).restype = res
            getattr(d, fn).argtypes = args

    def start(self):
        if self.discoverers:
            return
        class _Desc(ctypes.Structure):
            _fields_ = [("name", ctypes.c_char_p), ("longname", ctypes.c_char_p)]
        list_get = vlc.dll.libvlc_renderer_discoverer_list_get
        list_get.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_Desc)))]
        list_get.restype = ctypes.c_size_t
        services = ctypes.POINTER(ctypes.POINTER(_Desc))()
        names = []
        count = list_get(vlc_vars.object_of(self.instance), ctypes.byref(services))
        for i in range(count):
            names.append(services[i].contents.name)
        if count:
            release = vlc.dll.libvlc_renderer_discoverer_list_release
            release.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            release(services, count)
        for name in names:
            rd = self.instance.renderer_discoverer_new(name)
            if rd is None:
                continue
            em = rd.event_manager()
            em.event_attach(vlc.EventType.RendererDiscovererItemAdded, self._on_event, True)
            em.event_attach(vlc.EventType.RendererDiscovererItemDeleted, self._on_event, False)
            rd.start()
            self.discoverers.append(rd)

    @staticmethod
    def _event_item(event) -> int:
        ev = event.contents if hasattr(event, "contents") else event
        return ctypes.c_void_p.from_address(ctypes.addressof(ev.u)).value or 0

    def _on_event(self, event, added):
        item = self._event_item(event)
        if not item:
            return
        d = vlc.dll
        with self.lock:
            if added:
                held = d.libvlc_renderer_item_hold(item)
                self.items[held] = ((d.libvlc_renderer_item_name(item) or b"").decode("utf-8", errors="ignore"),
                                    (d.libvlc_renderer_item_type(item) or b"").decode("utf-8", errors="ignore"))
            elif item in self.items:
                self.items.pop(item)
                d.libvlc_renderer_item_release(item)

    def list(self) -> list:
        with self.lock:
            return [(ptr, name, kind) for ptr, (name, kind) in self.items.items()]

    def stop(self):
        for rd in self.discoverers:
            rd.stop()
        self.discoverers = []


class VLCPlayerEngine(QObject):
    """Encapsulates LibVLC operations and state synchronization."""

    # Signals
    position_changed = pyqtSignal(float, int, int) # pos (0..1), current_ms, total_ms
    state_changed = pyqtSignal(str) # 'playing', 'paused', 'stopped'
    media_ended = pyqtSignal()
    media_changed = pyqtSignal(dict) # title, artist, is_video, etc.
    volume_changed = pyqtSignal(int)

    def __init__(self, hwnd=None, hw_decoding=True, extra_args=(), parent=None):
        super().__init__(parent)
        self.hwnd = hwnd

        # Initialize LibVLC with safe flags (plus the user's advanced options)
        vlc_args = ["--no-video-title-show", f"--avcodec-hw={'any' if hw_decoding else 'none'}"] + list(extra_args)
        try:
            self.instance = vlc.Instance(vlc_args)
        except Exception:
            self.instance = None

        if self.instance is None:
            self.instance = vlc.Instance(vlc_args[:2])  # a bad advanced option must not stop playback

        if self.instance is None:
            raise RuntimeError("LibVLC motor inicializálása sikertelen. Kérlek ellenőrizd a 64-bites VLC telepítést.")

        self.log = LogCapture()
        self.log.install(self.instance)
        self.player = self.instance.media_player_new()
        self.renderers = RendererScanner(self.instance)
        self.renderer = None

        if self.hwnd:
            self.player.set_hwnd(self.hwnd)

        self.current_media = None
        self.current_meta = {
            "title": "No Media Loaded",
            "artist": "",
            "is_video": False,
            "duration": 0
        }

        # Equalizer
        self.equalizer = None
        self.eq_preset_index = None
        self.eq_enabled = True
        self._init_equalizer()
        self.video_adjust = dict(VIDEO_ADJUST_DEFAULTS)
        self.video_adjust_enabled = False
        self._last_state = None

        # Effects, overlays and subtitle style (re-applied to every new audio/video output)
        self.audio_effects = set()
        self.audio_params = _effect_defaults(AUDIO_EFFECTS)
        self.pitch = 0.0
        self.video_effects = set()
        self.video_params = _effect_defaults(VIDEO_EFFECTS)
        self.transform = None
        self.rotate_enabled = False
        self.rotate_angle = 0.0
        self.logo = {"enabled": False, "file": "", "opacity": 255, "position": 10, "x": 16, "y": 16}
        self.subtitle_style = dict(SUBTITLE_STYLE_DEFAULTS)
        self.recording = False
        self._restart_seek = None
        self._restart_paused = False
        if not vlc_vars.available():
            print("libvlccore not reachable: effects, recording and programs are disabled")
        # Chromecast: never block on VLC's transcoding performance question (no dialog provider here)
        vlc_vars.set_var(self._mp, "sout-chromecast-show-perf-warning", 0)

        # Periodic state poll timer (50ms for smooth scrub & time updates)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_status)
        self.poll_timer.start(50)

    @property
    def _mp(self) -> int:
        return vlc_vars.object_of(self.player)

    def shutdown(self):
        """Stops playback and detaches callbacks before the interpreter goes away."""
        self.poll_timer.stop()
        self.renderers.stop()
        self.player.stop()
        self.log.uninstall()

    def set_video_hwnd(self, hwnd):
        self.hwnd = hwnd
        if self.player:
            self.player.set_hwnd(hwnd)
            # Let mouse/keyboard reach the Qt window (shortcuts, double-click fullscreen)
            self.player.video_set_mouse_input(False)
            self.player.video_set_key_input(False)

    # --- Equalizer ---
    def _init_equalizer(self):
        try:
            self.equalizer = vlc.libvlc_audio_equalizer_new()
            vlc.libvlc_media_player_set_equalizer(self.player, self.equalizer)
        except Exception as e:
            print("Equalizer init warning:", e)

    def get_equalizer_presets(self):
        presets = []
        try:
            count = vlc.libvlc_audio_equalizer_get_preset_count()
            for i in range(count):
                name = vlc.libvlc_audio_equalizer_get_preset_name(i).decode('utf-8', errors='ignore')
                presets.append((i, name))
        except Exception as e:
            print("Failed getting presets:", e)
        return presets

    def _apply_equalizer(self):
        if not vlc_vars.available():
            vlc.libvlc_media_player_set_equalizer(self.player, self.equalizer if self.eq_enabled else None)
            return
        # LibVLC's own setter would overwrite the whole "audio-filter" chain with just
        # "equalizer", dropping the user's audio effects; drive the equalizer's variables instead.
        if self.equalizer:
            bands = " ".join(f"{amp:.2f}" for amp in self.get_equalizer_bands())
            self._set_audio_var("equalizer-bands", bands)
            self._set_audio_var("equalizer-preamp", float(self.get_equalizer_preamp()))
        self._apply_audio_filters()

    def set_equalizer_preset(self, index: int):
        try:
            if self.equalizer:
                vlc.libvlc_audio_equalizer_release(self.equalizer)
            self.equalizer = vlc.libvlc_audio_equalizer_new_from_preset(index)
            self._apply_equalizer()
            self.eq_preset_index = index
        except Exception as e:
            print("Failed setting equalizer preset:", e)

    def set_equalizer_enabled(self, enabled: bool):
        self.eq_enabled = enabled
        self._apply_equalizer()

    def get_equalizer_bands(self):
        """Current amplification of the 10 bands in dB."""
        if not self.equalizer:
            return [0.0] * 10
        count = vlc.libvlc_audio_equalizer_get_band_count()
        return [vlc.libvlc_audio_equalizer_get_amp_at_index(self.equalizer, i) for i in range(count)]

    def set_equalizer_band(self, band: int, amp_db: float):
        try:
            if not self.equalizer:
                self.equalizer = vlc.libvlc_audio_equalizer_new()
            vlc.libvlc_audio_equalizer_set_amp_at_index(self.equalizer, float(amp_db), band)
            self._apply_equalizer()
            self.eq_preset_index = None
        except Exception as e:
            print("Failed setting equalizer band:", e)

    def get_equalizer_preamp(self) -> float:
        return vlc.libvlc_audio_equalizer_get_preamp(self.equalizer) if self.equalizer else 0.0

    def set_equalizer_preamp(self, amp_db: float):
        if self.equalizer:
            vlc.libvlc_audio_equalizer_set_preamp(self.equalizer, float(amp_db))
            self._apply_equalizer()

    # --- Media loading & transport ---
    def load_media(self, file_path_or_url: str, options: list = None) -> bool:
        """Loads a file or URL. Returns False if LibVLC cannot open it."""
        if not file_path_or_url:
            return False

        if os.path.exists(file_path_or_url):
            # Qt dialogs / drag & drop give "C:/..." paths; LibVLC on Windows
            # returns NULL for forward-slash paths, so normalize to backslashes.
            file_path_or_url = os.path.normpath(file_path_or_url)
            self.current_media = self.instance.media_new_path(file_path_or_url)
        else:
            self.current_media = self.instance.media_new_location(file_path_or_url)

        if self.current_media is None:
            return False

        for opt in options or []:
            self.current_media.add_option(opt)

        self.current_media.parse_with_options(vlc.MediaParseFlag.local, 1000)
        self.player.set_media(self.current_media)
        self.recording = False
        self._restart_seek = None

        # Extract metadata
        filename = os.path.basename(file_path_or_url) if os.path.exists(file_path_or_url) else file_path_or_url
        title = self.current_media.get_meta(vlc.Meta.Title) or filename
        artist = self.current_media.get_meta(vlc.Meta.Artist) or ""

        # Determine if video
        tracks = _media_tracks(self.current_media)
        is_video = any(t["kind"] == "video" for t in tracks)
        if not tracks:
            ext = os.path.splitext(file_path_or_url)[1].lower()
            if ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv', '.flv', '.m4v', '.ts', '.mpg', '.mpeg', '.3gp']:
                is_video = True
            elif file_path_or_url.split("://")[0] in ("dvd", "bluray", "vcd", "dshow", "screen"):
                is_video = True

        self.current_meta = {
            "title": title,
            "artist": artist,
            "is_video": is_video,
            "path": file_path_or_url
        }
        self.media_changed.emit(self.current_meta)
        return True

    def play(self):
        if self.player.get_media() is None:
            return
        if self.player.get_state() == vlc.State.Ended:
            self.player.stop()  # an ended player won't restart without a stop
        self.player.play()
        self.state_changed.emit("playing")

    def pause(self):
        self.player.pause()
        self.state_changed.emit("paused")

    def toggle_play_pause(self):
        if self.player.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self):
        self.player.stop()
        self.recording = False
        self.state_changed.emit("stopped")
        self.position_changed.emit(0.0, 0, max(0, self.player.get_length()))

    def seek(self, position_ratio: float):
        """Seek to relative position 0.0 .. 1.0"""
        self.player.set_position(max(0.0, min(1.0, position_ratio)))

    def jump_seconds(self, delta_sec: int):
        cur_time = self.player.get_time()
        if cur_time >= 0:
            target = max(0, cur_time + delta_sec * 1000)
            self.player.set_time(target)

    def next_frame(self):
        self.player.next_frame()

    # --- Audio ---
    def set_volume(self, volume: int):
        """Volume 0 to 200 (supports VLC boost)"""
        vol = max(0, min(200, volume))
        self.player.audio_set_volume(vol)
        self.volume_changed.emit(vol)

    def get_volume(self) -> int:
        return self.player.audio_get_volume()

    def toggle_mute(self):
        is_muted = self.player.audio_get_mute()
        self.player.audio_set_mute(not is_muted)
        return not is_muted

    def set_audio_track(self, track_id: int):
        self.player.audio_set_track(track_id)

    def get_audio_tracks(self):
        return _descriptions(self.player.audio_get_track_description())

    def get_current_audio_track(self) -> int:
        return self.player.audio_get_track()

    def get_audio_devices(self):
        """[(device_id, description)] for the current audio output."""
        devices = []
        head = self.player.audio_output_device_enum()
        node = head
        while node:
            dev = node.contents
            devices.append(((dev.device or b"").decode("utf-8", errors="ignore"),
                            (dev.description or b"").decode("utf-8", errors="ignore")))
            node = dev.next
        if head:
            vlc.libvlc_audio_output_device_list_release(head)
        return devices

    def get_audio_device(self) -> str:
        dev = self.player.audio_output_device_get()
        return dev.decode("utf-8", errors="ignore") if isinstance(dev, bytes) else (dev or "")

    def set_audio_device(self, device_id: str):
        self.player.audio_output_device_set(None, device_id)

    def get_stereo_mode(self) -> int:
        return self.player.audio_get_channel()

    def set_stereo_mode(self, mode: int):
        self.player.audio_set_channel(mode)

    def set_audio_delay(self, delay_ms: int):
        self.player.audio_set_delay(delay_ms * 1000)

    def get_audio_delay(self) -> int:
        return self.player.audio_get_delay() // 1000

    # --- Playback rate ---
    def set_rate(self, rate: float):
        self.player.set_rate(rate)

    def get_rate(self) -> float:
        return self.player.get_rate()

    # --- Video ---
    def set_aspect_ratio(self, ratio_str: str):
        # e.g. "16:9", "4:3", or None for default
        self.player.video_set_aspect_ratio(ratio_str.encode('utf-8') if ratio_str else None)

    def set_crop_geometry(self, crop_str: str):
        self.player.video_set_crop_geometry(crop_str.encode('utf-8') if crop_str else None)

    def set_scale(self, scale: float):
        """0 = fit to window, otherwise zoom factor."""
        self.player.video_set_scale(scale)

    def set_deinterlace(self, mode: str):
        self.player.video_set_deinterlace(mode.encode("utf-8") if mode else None)

    def get_video_tracks(self):
        return _descriptions(self.player.video_get_track_description())

    def get_current_video_track(self) -> int:
        return self.player.video_get_track()

    def set_video_track(self, track_id: int):
        self.player.video_set_track(track_id)

    def set_video_adjust(self, enabled: bool, **values):
        """Contrast/brightness/saturation/gamma are factors (1.0 = neutral), hue is in degrees."""
        self.video_adjust_enabled = enabled
        self.video_adjust.update(values)
        opt = vlc.VideoAdjustOption
        self.player.video_set_adjust_int(opt.Enable, 1 if enabled else 0)
        self.player.video_set_adjust_float(opt.Contrast, self.video_adjust["contrast"])
        self.player.video_set_adjust_float(opt.Brightness, self.video_adjust["brightness"])
        self.player.video_set_adjust_float(opt.Hue, self.video_adjust["hue"])
        self.player.video_set_adjust_float(opt.Saturation, self.video_adjust["saturation"])
        self.player.video_set_adjust_float(opt.Gamma, self.video_adjust["gamma"])
        self._apply_video_filters()

    # --- Audio & video effect filters (live, through the outputs' variables) ---
    def _set_on_outputs(self, object_type: bytes, name: str, value):
        """Sets a variable on the player (inherited by future outputs) and on the live outputs."""
        vlc_vars.set_var(self._mp, name, value)
        with vlc_vars.held_objects(self._mp, object_type) as outputs:
            for obj in outputs:
                vlc_vars.set_var(obj, name, value)

    def _set_audio_var(self, name: str, value):
        self._set_on_outputs(vlc_vars.AUDIO_OUTPUT, name, value)

    def _set_video_var(self, name: str, value):
        self._set_on_outputs(vlc_vars.VIDEO_OUTPUT, name, value)

    def _sync_chain(self, object_type: bytes, name: str, chain: str):
        """Changing a filter chain restarts it, so only touch outputs whose chain differs."""
        vlc_vars.set_var(self._mp, name, chain)
        with vlc_vars.held_objects(self._mp, object_type) as outputs:
            for obj in outputs:
                if vlc_vars.get_var(obj, name, "") != chain:
                    vlc_vars.set_var(obj, name, chain)

    def audio_filter_chain(self) -> str:
        chain = ["equalizer"] if self.eq_enabled and self.equalizer else []
        chain += [name for name, _, _ in AUDIO_EFFECTS if name in self.audio_effects]
        if abs(self.pitch) > 0.01:
            chain.append("scaletempo_pitch")
        return ":".join(chain)

    def video_filter_chain(self) -> str:
        chain = []
        if self.transform:
            chain.append("transform")
        if self.rotate_enabled:
            chain.append("rotate")
        chain += [name for name, _, _ in VIDEO_EFFECTS if name in self.video_effects]
        if self.video_adjust_enabled:
            chain.append("adjust")
        return ":".join(chain)

    def _apply_audio_filters(self):
        for name, value in self.audio_params.items():
            self._set_audio_var(name, value)
        self._set_audio_var("pitch-shift", float(self.pitch))
        self._sync_chain(vlc_vars.AUDIO_OUTPUT, "audio-filter", self.audio_filter_chain())

    def _apply_video_filters(self):
        if not vlc_vars.available():
            return
        for name, value in self.video_params.items():
            self._set_video_var(name, value)
        if self.transform:
            self._set_video_var("transform-type", self.transform)
        self._set_video_var("rotate-angle", float(self.rotate_angle))
        self._sync_chain(vlc_vars.VIDEO_OUTPUT, "video-filter", self.video_filter_chain())

    def set_audio_effect(self, name: str, enabled: bool):
        (self.audio_effects.add if enabled else self.audio_effects.discard)(name)
        self._apply_audio_filters()

    def set_audio_param(self, name: str, value):
        self.audio_params[name] = value
        self._set_audio_var(name, value)

    def set_pitch(self, semitones: float):
        was_on = abs(self.pitch) > 0.01
        self.pitch = float(semitones)
        self._set_audio_var("pitch-shift", self.pitch)
        if was_on != (abs(self.pitch) > 0.01):
            self._apply_audio_filters()

    def set_video_effect(self, name: str, enabled: bool):
        (self.video_effects.add if enabled else self.video_effects.discard)(name)
        self._apply_video_filters()

    def clear_video_effects(self):
        self.video_effects.clear()
        self._apply_video_filters()

    def _rebuild_video_chain(self, without: str):
        """Filters that read an option only when opened need their chain rebuilt to see a new value."""
        chain = self.video_filter_chain()
        self._sync_chain(vlc_vars.VIDEO_OUTPUT, "video-filter",
                         ":".join(f for f in chain.split(":") if f != without))
        self._sync_chain(vlc_vars.VIDEO_OUTPUT, "video-filter", chain)

    def set_video_param(self, name: str, value):
        self.video_params[name] = value
        self._set_video_var(name, value)
        if name in REBUILD_PARAMS and REBUILD_PARAMS[name] in self.video_effects:
            self._rebuild_video_chain(REBUILD_PARAMS[name])

    def set_transform(self, kind):
        was_active = self.transform is not None
        self.transform = kind
        if kind:
            self._set_video_var("transform-type", kind)
        if was_active and kind:
            self._rebuild_video_chain("transform")
        else:
            self._apply_video_filters()

    def set_rotation(self, enabled: bool, angle: float = None):
        if angle is not None:
            self.rotate_angle = float(angle)
            self._set_video_var("rotate-angle", self.rotate_angle)
        if enabled != self.rotate_enabled:
            self.rotate_enabled = enabled
            self._apply_video_filters()

    def reset_effects(self, audio: bool = True, video: bool = True):
        if audio:
            self.audio_effects.clear()
            self.audio_params = _effect_defaults(AUDIO_EFFECTS)
            self.pitch = 0.0
            self._apply_audio_filters()
        if video:
            self.video_effects.clear()
            self.video_params = _effect_defaults(VIDEO_EFFECTS)
            self.transform = None
            self.rotate_enabled = False
            self.rotate_angle = 0.0
            self._apply_video_filters()

    def _reapply_effects(self):
        """New audio/video outputs inherit the player's variables; make sure the chains match."""
        if not vlc_vars.available():
            return
        self._sync_chain(vlc_vars.AUDIO_OUTPUT, "audio-filter", self.audio_filter_chain())
        self._sync_chain(vlc_vars.VIDEO_OUTPUT, "video-filter", self.video_filter_chain())
        if self.logo["enabled"]:
            with vlc_vars.held_objects(self._mp, vlc_vars.VIDEO_OUTPUT) as vouts:
                missing = any("logo" not in vlc_vars.get_var(v, "sub-source", "") for v in vouts)
            if missing:
                self.set_logo(**self.logo)

    # --- Logo overlay ---
    def set_logo(self, enabled: bool, file: str = "", opacity: int = 255, position: int = 10, x: int = 16, y: int = 16):
        self.logo = {"enabled": enabled, "file": file, "opacity": opacity, "position": position, "x": x, "y": y}
        opt = vlc.VideoLogoOption
        if enabled and file and os.path.exists(file):
            self.player.video_set_logo_string(opt.logo_file, os.path.normpath(file))
            self.player.video_set_logo_int(opt.logo_opacity, int(opacity))
            self.player.video_set_logo_int(opt.logo_position, int(position))
            self.player.video_set_logo_int(opt.logo_x, int(x))
            self.player.video_set_logo_int(opt.logo_y, int(y))
            self.player.video_set_logo_int(opt.logo_enable, 1)
        else:
            self.player.video_set_logo_int(opt.logo_enable, 0)

    # --- Subtitle appearance ---
    def set_subtitle_style(self, style: dict) -> bool:
        """Size and margin change at once; True when the rest needs a restart_media()."""
        needs_restart = False
        for name, value in style.items():
            changed = self.subtitle_style.get(name) != value
            self.subtitle_style[name] = value
            if name in LIVE_SUBTITLE_VARS:
                self._set_video_var(name, int(value))
            else:
                vlc_vars.set_var(self._mp, name, value)
                needs_restart |= changed
        return needs_restart

    def restart_media(self):
        """Re-opens the current media at the same position (new outputs pick up new settings)."""
        if self.player.get_media() is None:
            return
        t = self.player.get_time()
        playing = self.player.is_playing()
        self.player.stop()
        self.recording = False
        self._restart_seek = t if t > 0 else None
        self._restart_paused = not playing
        self.play()

    # --- Recording (VLC's record button: dumps the input stream as-is) ---
    def set_record_dir(self, path: str):
        vlc_vars.set_var(self._mp, "input-record-path", os.path.normpath(path))

    def can_record(self) -> bool:
        with vlc_vars.held_objects(self._mp, vlc_vars.INPUT) as inputs:
            return any(vlc_vars.get_var(i, "can-record", False) for i in inputs)

    def set_recording(self, on: bool) -> bool:
        done = False
        with vlc_vars.held_objects(self._mp, vlc_vars.INPUT) as inputs:
            for i in inputs:
                done |= vlc_vars.set_var(i, "record", on)
        self.recording = on and done
        return done

    # --- Programs (DVB / MPEG-TS services) ---
    def get_programs(self):
        with vlc_vars.held_objects(self._mp, vlc_vars.INPUT) as inputs:
            for i in inputs:
                progs = vlc_vars.choices(i, "program")
                if progs:
                    return progs, vlc_vars.get_var(i, "program")
        return [], None

    def set_program(self, program: int):
        with vlc_vars.held_objects(self._mp, vlc_vars.INPUT) as inputs:
            for i in inputs:
                vlc_vars.set_var(i, "program", int(program))

    # --- Disc menus (DVD / Blu-ray) ---
    def navigate(self, mode: int):
        self.player.navigate(mode)

    def disc_menu(self):
        with vlc_vars.held_objects(self._mp, vlc_vars.INPUT) as inputs:
            for i in inputs:
                vlc_vars.trigger(i, "menu-title")

    # --- Teletext ---
    def get_teletext(self) -> int:
        return self.player.video_get_teletext()

    def set_teletext(self, page: int):
        """0 hides teletext, 100..899 shows that page."""
        self.player.video_set_teletext(int(page))

    # --- Renderers (Chromecast) ---
    def set_renderer(self, item):
        """item: a pointer from renderers.list(), or None for this computer. Takes effect on restart."""
        self.renderer = item
        vlc.dll.libvlc_media_player_set_renderer(self._mp, item)
        self.restart_media()

    def take_snapshot(self, filepath: str) -> bool:
        """Saves current video frame to filepath (PNG)."""
        norm_path = os.path.normpath(filepath)
        os.makedirs(os.path.dirname(norm_path), exist_ok=True)
        return self.player.video_take_snapshot(0, norm_path, 0, 0) == 0

    def get_video_size(self):
        return self.player.video_get_size(0)

    def show_osd(self, text: str, timeout_ms: int = 1600):
        """Draws a short message in the top-right corner of the video."""
        opt = vlc.VideoMarqueeOption
        self.player.video_set_marquee_int(opt.Enable, 1)
        self.player.video_set_marquee_int(opt.Position, 6)  # top | right
        self.player.video_set_marquee_int(opt.Size, 28)
        self.player.video_set_marquee_int(opt.X, 24)
        self.player.video_set_marquee_int(opt.Y, 20)
        self.player.video_set_marquee_int(opt.Timeout, timeout_ms)
        self.player.video_set_marquee_string(opt.Text, text)

    # --- Subtitles ---
    def get_subtitle_tracks(self):
        return _descriptions(self.player.video_get_spu_description())

    def set_subtitle_track(self, spu_id: int):
        self.player.video_set_spu(spu_id)

    def get_current_spu(self) -> int:
        return self.player.video_get_spu()

    def add_subtitle_file(self, srt_path: str):
        if os.path.exists(srt_path):
            uri = "file:///" + os.path.abspath(srt_path).replace("\\", "/")
            self.player.add_slave(vlc.MediaSlaveType.subtitle, uri, True)

    def set_spu_delay(self, delay_ms: int):
        self.player.video_set_spu_delay(delay_ms * 1000)

    def get_spu_delay(self) -> int:
        return self.player.video_get_spu_delay() // 1000

    # --- Titles & chapters (DVD/Blu-ray/MKV) ---
    def get_titles(self):
        return _descriptions(self.player.video_get_title_description())

    def get_current_title(self) -> int:
        return self.player.get_title()

    def set_title(self, title: int):
        self.player.set_title(title)

    def get_chapters(self):
        return _descriptions(self.player.video_get_chapter_description(self.player.get_title()))

    def get_current_chapter(self) -> int:
        return self.player.get_chapter()

    def set_chapter(self, chapter: int):
        self.player.set_chapter(chapter)

    # --- Time ---
    def set_time(self, ms: int):
        self.player.set_time(max(0, ms))

    def get_time(self) -> int:
        return self.player.get_time()

    def get_length(self) -> int:
        return self.player.get_length()

    # --- Media information ---
    def get_media_details(self) -> dict:
        media = self.current_media
        details = {"meta": {}, "tracks": [], "path": self.current_meta.get("path", "")}
        if media is None:
            return details
        meta_keys = [("title", vlc.Meta.Title), ("artist", vlc.Meta.Artist), ("album", vlc.Meta.Album),
                     ("genre", vlc.Meta.Genre), ("date", vlc.Meta.Date), ("track", vlc.Meta.TrackNumber),
                     ("description", vlc.Meta.Description), ("copyright", vlc.Meta.Copyright),
                     ("publisher", vlc.Meta.Publisher), ("encoded_by", vlc.Meta.EncodedBy),
                     ("language", vlc.Meta.Language)]
        for key, meta in meta_keys:
            value = media.get_meta(meta)
            if value:
                details["meta"][key] = value
        details["duration_ms"] = max(0, self.player.get_length())
        details["tracks"] = [t for t in _media_tracks(media) if t["kind"] != "other"]
        return details

    def _poll_status(self):
        state = self.player.get_state()
        if state == vlc.State.Playing and self._last_state != vlc.State.Playing:
            self._reapply_effects()
        if state == vlc.State.Playing and self._restart_seek is not None and self.player.get_time() > 0:
            self.player.set_time(self._restart_seek)
            self._restart_seek = None
            if self._restart_paused:
                self.pause()
        if state == vlc.State.Playing and not self.current_meta.get("is_video") and self.player.has_vout() > 0:
            # Pictures and extensionless streams report no video track up front; the open vout settles it
            self.current_meta["is_video"] = True
            self.media_changed.emit(self.current_meta)
        if state == vlc.State.Playing:
            pos = self.player.get_position()
            cur_ms = self.player.get_time()
            total_ms = self.player.get_length()
            self.position_changed.emit(pos, max(0, cur_ms), max(0, total_ms))
        elif state != self._last_state:
            # Report end/error once on transition, not on every poll
            if state == vlc.State.Ended:
                self.state_changed.emit("stopped")
                self.media_ended.emit()
            elif state == vlc.State.Error:
                self.state_changed.emit("stopped")
        self._last_state = state


class MediaConverter(QObject):
    """Runs a LibVLC stream-output chain (transcode to file or HTTP stream) on its own player."""

    progress = pyqtSignal(float)        # 0..1
    finished = pyqtSignal(bool, str)    # success, message

    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.instance = instance
        self.player = None
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._poll)

    def start(self, source: str, sout: str) -> bool:
        if os.path.exists(source):
            media = self.instance.media_new_path(os.path.normpath(source))
        else:
            media = self.instance.media_new_location(source)
        if media is None:
            return False
        media.add_option(f":sout={sout}")
        media.add_option(":sout-keep")
        self.player = self.instance.media_player_new()
        self.player.set_media(media)
        self.player.play()
        self.timer.start()
        return True

    def cancel(self):
        if self.player:
            self.timer.stop()
            self.player.stop()
            self.player.release()
            self.player = None

    def is_running(self) -> bool:
        return self.player is not None

    def _poll(self):
        if not self.player:
            return
        state = self.player.get_state()
        if state == vlc.State.Ended:
            self.cancel()
            self.finished.emit(True, "")
        elif state == vlc.State.Error:
            self.cancel()
            self.finished.emit(False, "A LibVLC nem tudta feldolgozni a forrást.")
        else:
            self.progress.emit(max(0.0, self.player.get_position()))
