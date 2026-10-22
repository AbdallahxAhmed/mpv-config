"""Make mpv's letter keys work under ANY keyboard layout.

mpv matches a key binding against the CHARACTER a key produces. With an
Arabic (or any non-latin) layout active the letter bindings never fire,
because the key produces an Arabic character.

The obvious fix - switching mpv's window to another layout - does not work:
Windows' WM_INPUTLANGCHANGEREQUEST TOGGLES between the active layout and
the last active one of the FOREGROUND thread, so a helper that toggles mpv
ends up putting it back on whatever the focused application last used
(measured here: US -> Arabic -> US). It also fights the taskbar indicator.

So the layout is left alone entirely. A low level keyboard hook translates
the printable keys while mpv is the focused window: the key is swallowed
and the character of the SAME physical key on a US layout is injected
instead. The system layout, the taskbar indicator and every other
application keep working exactly as they did.

Both characters come from Windows itself:
  produced = MapVirtualKeyW(vk, MAPVK_VK_TO_CHAR)      (the current layout)
  target   = ToUnicodeEx(vk, scan, state, ..., us_hkl)  (the US layout)
so no key table has to be maintained here.

Ctrl+<letter> already works in any layout (Windows turns it into a
control code), so only the plain printable keys are translated.

Windows only. Elsewhere this exits with a clear message and no effect.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import sys
import time

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
LLKHF_INJECTED = 0x00000010
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_CHAR = 0
US_LAYOUT = "00000409"

# The US layout: what each physical key produces there. The VK codes of the
# letters and digits are their ASCII codes.
US_CHARS = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    US_CHARS[ord(_c.upper())] = _c
for _c in "0123456789":
    US_CHARS[ord(_c)] = _c
US_CHARS.update({
    0x20: " ", 0xBA: ";", 0xBB: "=", 0xC0: "`", 0xDB: "[", 0xDC: "]",
    0xDD: "\\", 0xA2: "\\", 0xA3: "]", 0xA4: "[", 0xA5: "'", 0xA6: ";",
    0xA7: "/", 0xA8: "`", 0x2C: ",", 0x2E: ".", 0x2F: "/", 0x3A: ";",
    0x3B: "+", 0x2D: "-", 0x3D: "=", 0x27: "'",
})
US_SHIFT = {
    0x31: "!", 0x32: "@", 0x33: "#", 0x34: "$", 0x35: "%", 0x36: "^",
    0x37: "&", 0x38: "*", 0x39: "(", 0x30: ")", 0xBA: ":", 0xBB: "+",
    0xDB: "{", 0xDC: "}", 0xDD: "|", 0xA2: "|", 0xA3: "}", 0xA4: "{",
    0xA5: '"', 0xA6: ":", 0xA7: "?", 0xA8: "~", 0x2C: "<", 0x2E: ">",
    0x2F: "?", 0x3A: ":", 0x3B: "+", 0x2D: "_", 0x3D: "+", 0x27: '"',
}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    US_SHIFT[ord(_c)] = _c

_user32 = None
_kernel32 = None
_EnumWindowsProc = None
_HOOKPROC = None
_us_hkl = None


class MSG(ctypes.Structure):
    """The Win32 message struct - GetMessage needs a real pointer."""
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", ctypes.c_byte * 8)]


def _windows_only() -> bool:
    global _user32, _kernel32, _EnumWindowsProc, _HOOKPROC, _us_hkl
    if sys.platform != "win32":
        print(
            "layout_guard: the key translation is Windows only; nothing to do here.",
            file=sys.stderr,
        )
        return False
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )
    # The hook callback returns a LRESULT (pointer sized) and the module
    # handle is a pointer: without the right argtypes ctypes truncates them
    # to 32 bit and SetWindowsHookEx fails (ERROR_MOD_NOT_FOUND / 126).
    _HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    )
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, _HOOKPROC, ctypes.c_void_p, ctypes.c_uint]
    _user32.SetWindowsHookExW.restype = ctypes.c_void_p
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    _user32.CallNextHookEx.argtypes = [
        ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.GetClassNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = ctypes.c_uint
    _user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
    _user32.MapVirtualKeyW.restype = ctypes.c_int
    _user32.MapVirtualKeyExW.argtypes = [
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    _user32.MapVirtualKeyExW.restype = ctypes.c_int
    _user32.GetKeyboardLayout.argtypes = [ctypes.c_uint]
    _user32.GetKeyboardLayout.restype = ctypes.c_void_p
    _user32.ToUnicodeEx.argtypes = [
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    _user32.ToUnicodeEx.restype = ctypes.c_int
    _user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
    _user32.SendInput.restype = ctypes.c_uint
    _kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    _kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    # the US layout, loaded (not activated) - ToUnicodeEx uses it as the
    # reference without touching the layout the user is typing in.
    _us_hkl = _user32.LoadKeyboardLayoutW(US_LAYOUT, 1)
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
            found.append((hwnd, _user32.GetWindowThreadProcessId(hwnd, None)))
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found


def _mpv_window():
    """mpv's window handle and its thread, if it is up."""
    for hwnd, thread in _find_mpv_windows():
        return hwnd, thread
    return None, None


def _mpv_is_foreground() -> bool:
    foreground = _user32.GetForegroundWindow()
    if not foreground:
        return False
    hwnd, _thread = _mpv_window()
    return hwnd is not None and hwnd == foreground


def _produced_char(vk: int, hkl=None) -> str:
    """The character the layout of the GIVEN thread produces for this key.

    MapVirtualKeyW would use THIS process' own thread layout, which is not
    the layout the user types in - MapVirtualKeyExW with the target
    thread's layout handle is the only correct way to ask.
    """
    if hkl is None:
        hkl = _user32.GetKeyboardLayout(0)
    code = _user32.MapVirtualKeyExW(vk, MAPVK_VK_TO_CHAR, hkl, 0)
    return chr(code) if code else ""


def _us_char(vk: int, scan: int, shift: bool) -> str:
    """The character the US layout produces for the same physical key.

    The table is the US layout itself (letters, digits and the punctuation
    block). It is checked against Windows at runtime: with a US layout
    active, MapVirtualKeyW must report the same characters.
    """
    table = US_SHIFT if shift else US_CHARS
    return table.get(vk, "")


def _inject_char(char: str) -> None:
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]

        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
        item = INPUT(type=1, ki=KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=flags,
                                            time=0, dwExtraInfo=None))
        _user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))


def should_translate(produced: str, target: str) -> bool:
    """Does this key need the US character instead of the layout's one?

    Pure so it can be tested without a keyboard:
      - nothing to translate when the layout already produces the US one;
      - a control code means a modifier is involved (Windows turns Ctrl+letter
        into a control code, and those combos are layout independent) - never
        touch them;
      - otherwise the layout produced something else, so mpv gets the US
        character of the same physical key.
    """
    if not target:
        return False
    if produced and (ord(produced) < 32 or ord(produced) == 127):
        # a control code: a modifier is involved (Windows turns Ctrl+letter
        # into one) and those combos are layout independent
        return False
    return produced != target


def _make_hook(log):
    def hook(code, wparam, lparam):
        if code != WM_KEYDOWN:
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        flags = lparam >> 24
        if flags & LLKHF_INJECTED:
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        if not _mpv_is_foreground():
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        vk = wparam & 0xFF
        scan = (lparam >> 16) & 0xFF
        # Ctrl/Alt/Win combos are already layout independent (Windows turns
        # Ctrl+letter into a control code), so they must never be
        # translated.
        for modifier in (0x11, 0x12, 0x5B, 0x5C):
            if _user32.GetKeyState(modifier) & 0x8000:
                return _user32.CallNextHookEx(None, code, wparam, lparam)
        shift = bool(_user32.GetKeyState(0x10) & 0x8000)
        target = _us_char(vk, scan, shift)
        _hwnd, thread = _mpv_window()
        produced = _produced_char(vk, _user32.GetKeyboardLayout(thread) if thread else None)
        if log and produced != target:
            log("key vk=%d produced=%r target=%r fg=%s"
                % (vk, produced, target, _mpv_is_foreground()))
        if not should_translate(produced, target):
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        # the layout produced something else: give mpv the US character
        if log:
            log("translate %r -> %r" % (produced, target))
        _inject_char(target)
        return 1  # swallow the original

    return _HOOKPROC(hook)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mpv_config.layout_guard",
        description="Make mpv's letter keys work under any keyboard layout.",
    )
    parser.add_argument("--log", default="",
                        help="write what was translated to this file")
    parser.add_argument("--duration", type=float, default=0,
                        help="stop after this many seconds (0 = until stopped)")
    args = parser.parse_args(argv)

    if not _windows_only():
        return 0

    log_file = None
    log = None
    if args.log:
        try:
            log_file = open(args.log, "a", encoding="utf-8")
            log = lambda line: (log_file.write(line + "\n"), log_file.flush())
        except OSError:
            log = None

    hook = _make_hook(log)
    module = _kernel32.GetModuleHandleW(None)
    handle = _user32.SetWindowsHookExW(
        WH_KEYBOARD_LL, hook, ctypes.c_void_p(module), 0)
    if not handle:
        print("layout_guard: could not install the keyboard hook (%s)"
              % (_kernel32.GetLastError(),), file=sys.stderr)
        return 1
    if log:
        log("guard started")

    msg = MSG()
    _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
    _user32.UnhookWindowsHookEx(handle)
    if log_file:
        log_file.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
