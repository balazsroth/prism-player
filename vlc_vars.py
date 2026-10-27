"""
Live access to LibVLC 3 object variables through libvlccore.

LibVLC 3 exposes no API for user audio/video filters, recording, programs or
subtitle styling, but the media player is itself a VLC object: its audio output,
video outputs and input thread are child objects whose variables drive those
features (this is what VLC's own Qt interface sets). Every helper degrades to a
no-op when libvlccore cannot be reached.
"""

import ctypes

import vlc

VAR_BOOL, VAR_INTEGER, VAR_STRING, VAR_FLOAT = 0x20, 0x30, 0x40, 0x50
VAR_TYPE_MASK = 0xF0
_GETCHOICES = 0x24

AUDIO_OUTPUT = b"audio output"
VIDEO_OUTPUT = b"video output"
INPUT = b"input"


class _Value(ctypes.Union):
    _fields_ = [("i_int", ctypes.c_int64), ("b_bool", ctypes.c_bool), ("f_float", ctypes.c_float),
                ("psz_string", ctypes.c_void_p), ("p_address", ctypes.c_void_p)]


class _List(ctypes.Structure):
    _fields_ = [("i_type", ctypes.c_int), ("i_count", ctypes.c_int), ("p_values", ctypes.POINTER(_Value))]


def _load_core():
    # libvlc.dll has already loaded its libvlccore; bind to that very module
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        handle = kernel32.GetModuleHandleW("libvlccore.dll")
        if not handle:
            return None
        core = ctypes.CDLL("libvlccore.dll", handle=handle)
        core.vlc_list_children.restype = ctypes.POINTER(_List)
        core.vlc_list_children.argtypes = [ctypes.c_void_p]
        core.vlc_list_release.argtypes = [ctypes.POINTER(_List)]
        core.vlc_object_hold.argtypes = [ctypes.c_void_p]
        core.vlc_object_hold.restype = ctypes.c_void_p
        core.vlc_object_release.argtypes = [ctypes.c_void_p]
        core.var_Create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        core.var_Type.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        core.var_SetChecked.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, _Value]
        core.var_GetChecked.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(_Value)]
        core.var_TriggerCallback.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        core.var_Change.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                    ctypes.POINTER(_Value), ctypes.POINTER(_Value)]
        core.var_FreeList.argtypes = [ctypes.POINTER(_Value), ctypes.POINTER(_Value)]
        return core
    except (AttributeError, OSError):
        return None


_core = None
_free = None


def _ensure():
    global _core, _free
    if _core is None:
        _core = _load_core() or False
        try:
            _free = vlc.dll.libvlc_free
            _free.argtypes = [ctypes.c_void_p]
        except AttributeError:
            _free = None
    return _core or None


def available() -> bool:
    return _ensure() is not None


def object_of(libvlc_obj) -> int:
    """Address of a python-vlc wrapper's underlying C object."""
    return ctypes.cast(libvlc_obj._as_parameter_, ctypes.c_void_p).value or 0


def _object_type(obj: int) -> bytes:
    # Every VLC 3 object starts with VLC_COMMON_MEMBERS, whose first field is object_type
    return ctypes.cast(ctypes.c_void_p.from_address(obj).value, ctypes.c_char_p).value or b""


class held_objects:
    """Context manager: the descendants of `root` of the given object type, held while in use."""

    def __init__(self, root: int, object_type: bytes):
        self.root, self.object_type, self.objects = root, object_type, []

    def __enter__(self):
        core = _ensure()
        if core and self.root:
            self._collect(core, self.root)
        return self.objects

    def _collect(self, core, parent):
        children = core.vlc_list_children(parent)
        if not children:
            return
        for i in range(children.contents.i_count):
            child = children.contents.p_values[i].p_address
            if _object_type(child) == self.object_type:
                self.objects.append(core.vlc_object_hold(child))
            self._collect(core, child)
        core.vlc_list_release(children)

    def __exit__(self, *exc):
        core = _ensure()
        for obj in self.objects:
            core.vlc_object_release(obj)
        self.objects = []


def _var_type(core, obj, name: bytes) -> int:
    return core.var_Type(obj, name) & VAR_TYPE_MASK


def set_var(obj: int, name: str, value) -> bool:
    """Sets (creating if needed) an object variable; the Python type picks the VLC type."""
    core = _ensure()
    if not core or not obj:
        return False
    key = name.encode()
    vtype = _var_type(core, obj, key)
    if not vtype:
        vtype = (VAR_BOOL if isinstance(value, bool) else VAR_INTEGER if isinstance(value, int)
                 else VAR_FLOAT if isinstance(value, float) else VAR_STRING)
        core.var_Create(obj, key, vtype)
    val = _Value()
    if vtype == VAR_BOOL:
        val.b_bool = bool(value)
    elif vtype == VAR_INTEGER:
        val.i_int = int(value)
    elif vtype == VAR_FLOAT:
        val.f_float = float(value)
    elif vtype == VAR_STRING:
        buf = ctypes.create_string_buffer(str(value).encode("utf-8"))
        val.psz_string = ctypes.cast(buf, ctypes.c_void_p)
    else:
        return False
    return core.var_SetChecked(obj, key, vtype, val) == 0


def get_var(obj: int, name: str, default=None):
    core = _ensure()
    if not core or not obj:
        return default
    key = name.encode()
    vtype = _var_type(core, obj, key)
    if not vtype:
        return default
    val = _Value()
    if core.var_GetChecked(obj, key, vtype, ctypes.byref(val)) != 0:
        return default
    if vtype == VAR_BOOL:
        return bool(val.b_bool)
    if vtype == VAR_INTEGER:
        return int(val.i_int)
    if vtype == VAR_FLOAT:
        return float(val.f_float)
    if vtype == VAR_STRING:
        text = ctypes.cast(val.psz_string, ctypes.c_char_p).value if val.psz_string else b""
        if val.psz_string and _free:
            _free(val.psz_string)
        return (text or b"").decode("utf-8", errors="ignore")
    return default


def trigger(obj: int, name: str) -> bool:
    core = _ensure()
    return bool(core and obj) and core.var_TriggerCallback(obj, name.encode()) == 0


def choices(obj: int, name: str) -> list:
    """[(value, label)] of a choice variable such as an input's "program"."""
    core = _ensure()
    if not core or not obj:
        return []
    key = name.encode()
    vtype = _var_type(core, obj, key)
    if vtype not in (VAR_INTEGER, VAR_STRING):
        return []
    values, texts = _Value(), _Value()
    if core.var_Change(obj, key, _GETCHOICES, ctypes.byref(values), ctypes.byref(texts)) != 0:
        return []
    result = []
    vlist = ctypes.cast(values.p_address, ctypes.POINTER(_List))
    tlist = ctypes.cast(texts.p_address, ctypes.POINTER(_List))
    if vlist:
        for i in range(vlist.contents.i_count):
            v = vlist.contents.p_values[i]
            value = int(v.i_int) if vtype == VAR_INTEGER else \
                (ctypes.cast(v.psz_string, ctypes.c_char_p).value or b"").decode("utf-8", errors="ignore")
            label = ""
            if tlist and i < tlist.contents.i_count and tlist.contents.p_values[i].psz_string:
                label = (ctypes.cast(tlist.contents.p_values[i].psz_string, ctypes.c_char_p).value or b"") \
                    .decode("utf-8", errors="ignore")
            result.append((value, label or str(value)))
    core.var_FreeList(ctypes.byref(values), ctypes.byref(texts))
    return result
