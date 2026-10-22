"""Keep mpv's window on a Latin keyboard layout while it is focused.

mpv matches a key binding against the CHARACTER the key produces, so with
an Arabic (or any non-latin) layout active the letter bindings never fire.
Windows keeps the input layout per input context, and mpv's window inherits
the layout of whoever started mpv - so the fix is to put mpv's own window
back on a latin layout and leave every other window alone.

Windows has no "set the layout of another window" call: the
WM_INPUTLANGCHANGEREQUEST message TOGGLES between the active layout and the
previously active one. So the layout is read back after every toggle and the
toggle is repeated until the wanted layout is the active one.

Nothing here touches the system input list, the taskbar indicator or any
other application: only mpv's own input context is changed.

Windows only. Elsewhere this exits with a clear message and no effect.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import sys
import time

WM_INPUTLANGCHANGEREQUEST = 0x0050
SW_SHOWMINIMIZED = 2
ENGLISH_US = "00000409"

_user32 = None
_EnumWindowsProc = None


def _windows_only() -> bool:
    global _user32, _EnumWindowsProc
    if sys.platform != "win32":
        print(
            "layout_guard: only Windows can set another window's input layout; "
            "nothing to do here.",
            file=sys.stderr,
        )
        return False
    _user32 = ctypes.windll.user32
    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )
    return True


def _find_mpv_windows():
    """Every visible mpv window (class "mpv") with its owning thread."""
    found = []

    def callback(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        if buf.value == "mpv":
            thread = _user32.GetWindowThreadProcessId(hwnd, None)
            found.append((hwnd, thread))
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found


def _layout_of(thread_id: int) -> int:
    """The active layout id of a thread (low word = locale id)."""
    return _user32.GetKeyboardLayout(thread_id) & 0xFFFF


def _toggle(hwnd: int, layout_id: str) -> None:
    """Ask the window's thread to switch layout (it toggles, hence the loop)."""
    hkl = _user32.LoadKeyboardLayoutW(layout_id, 1)
    _user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, hkl, 0)


def _ensure_layout(hwnd: int, thread_id: int, layout_id: str, target: int,
                   attempts: int = 4) -> bool:
    """Toggle until the wanted layout is active; return whether it worked."""
    for _ in range(attempts):
        if _layout_of(thread_id) == target:
            return True
        _toggle(hwnd, layout_id)
        time.sleep(0.25)
    return _layout_of(thread_id) == target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mpv_config.layout_guard",
        description="Keep mpv's window on a latin keyboard layout.",
    )
    parser.add_argument("--layout", default=ENGLISH_US,
                        help="layout id to use (default: %(default)s = English US)")
    parser.add_argument("--interval", type=float, default=0.4,
                        help="seconds between checks (default: %(default)s)")
    parser.add_argument("--duration", type=float, default=0,
                        help="stop after this many seconds (0 = until mpv exits)")
    args = parser.parse_args(argv)

    if not _windows_only():
        return 0

    target = int(args.layout, 16)
    started = time.time()

    while True:
        windows = _find_mpv_windows()
        if not windows:
            # mpv is gone (or has no window yet): wait a moment and retry,
            # then give up - the script that started us exits with mpv.
            if time.time() - started > 30:
                return 0
            time.sleep(args.interval)
            continue

        foreground = _user32.GetForegroundWindow()
        for hwnd, thread in windows:
            if hwnd != foreground:
                continue
            if _layout_of(thread) != target:
                _ensure_layout(hwnd, thread, args.layout, target)
            break
        else:
            # another window is in front: leave its layout alone, but make
            # sure mpv is ready for the next switch.
            for hwnd, thread in windows:
                if _layout_of(thread) != target:
                    _ensure_layout(hwnd, thread, args.layout, target)
                break

        if args.duration and (time.time() - started) > args.duration:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
