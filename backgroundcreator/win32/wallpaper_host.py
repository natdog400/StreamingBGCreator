from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_IS_WINDOWS = sys.platform == "win32"

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
LRESULT = ctypes.c_ssize_t


GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002

SMTO_NORMAL = 0x0000


# The Win32 entry points only exist on Windows. Importing this module on any other
# platform must stay harmless so the rest of the application can still start.
user32 = None
EnumWindowsProc = None

if _IS_WINDOWS:
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND

        user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowExW.restype = wintypes.HWND

        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ULONG_PTR),
        ]
        user32.SendMessageTimeoutW.restype = LRESULT

        user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL

        user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        user32.SetParent.restype = wintypes.HWND

        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long

        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long

        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
    except Exception:
        user32 = None
        EnumWindowsProc = None


def wallpaper_supported() -> bool:
    """True when this platform can host a window behind the desktop icons."""
    return bool(user32 is not None)


def _spawn_workerw() -> None:
    if not wallpaper_supported():
        return
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return

    result = ULONG_PTR()
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, SMTO_NORMAL, 1000, ctypes.byref(result))


def _find_workerw() -> int | None:
    if not wallpaper_supported():
        return None

    target: int | None = None

    def enum_proc(hwnd: int, _lparam: int) -> bool:
        nonlocal target
        shell_view = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if shell_view:
            worker = user32.FindWindowExW(0, hwnd, "WorkerW", None)
            if worker:
                target = int(worker)
                return False
        return True

    user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
    return target


def attach_window_to_desktop(hwnd: int, x: int = 0, y: int = 0, width: int | None = None, height: int | None = None) -> bool:
    if not wallpaper_supported():
        return False

    _spawn_workerw()
    workerw = _find_workerw()
    if not workerw:
        return False

    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    style = (style | WS_CHILD | WS_VISIBLE) & ~WS_POPUP
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)

    user32.SetParent(hwnd, workerw)
    flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW
    if width is None or height is None:
        flags |= SWP_NOSIZE
        width = 0
        height = 0
    user32.SetWindowPos(hwnd, 0, int(x), int(y), int(width), int(height), flags)
    return True
