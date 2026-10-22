\"\"\"Make mpv's letter keys work under ANY keyboard layout.

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

How the decision is made:
  - the virtual key code of a key event is PHYSICAL (VK_A is the key
    labelled A on a US keyboard), so the table below maps it to the US
    character of that key;
  - the layout handle of mpv's own thread tells whether mpv is already on
    a US layout - if it is, nothing is translated at all;
  - Ctrl/Alt/Win combinations are never translated: Windows turns
    Ctrl+letter into a control code, which is layout independent already.

Windows only. Elsewhere this exits with a clear message and no effect.
\"\"\"
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import sys

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
LLKHF_INJECTED = 0x00000010
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

US_LAYOUT = "00000409"       # en-US
US_LAYOUT_ID = 0x0409        # the low word of the US layout handle
ARABIC_LAYOUT = "00010401"   # ar-SA with the Arabic 101 layout

# The US layout: what each physical key produces there. The VK codes of
# the letters and digits are their ASCII codes.
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


class MSG(ctypes.Structure):
    \"\"\"The Win32 message struct - GetMessage needs a real pointer.\"\"\"
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", ctypes.c_byte * 8)]


def _windows_only() -> bool:
    global _user32, _kernel32, _EnumWindowsProc, _HOOKPROC
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
    # Handles are pointer sized: without the restype ctypes truncates them
    # to 32 bit, which breaks the module lookup (ERROR_MOD_NOT_FOUND) and
    # every window comparison.
    _kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    _kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.GetClassNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = ctypes.c_uint
    _user32.GetKeyboardLayout.argtypes = [ctypes.c_uint]
    _user32.GetKeyboardLayout.restype = ctypes.c_void_p
    _user32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    _user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
    _user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
    _user32.SendInput.restype = ctypes.c_uint
    return True


def _find_mpv_windows():
    \"\"\"Every visible mpv window (class \"mpv\") with its owning thread.\"\"\"
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
    \"\"\"mpv's window handle and its thread, if it is up.\"\"\"
    for hwnd, thread in _find_mpv_windows():
        return hwnd, thread
    return None, None


def _mpv_is_foreground() -> bool:
    foreground = _user32.GetForegroundWindow()
    if not foreground:
        return False
    hwnd, _thread = _mpv_window()
    return hwnd is not None and hwnd == foreground


def _mpv_layout():
    \"\"\"The keyboard layout handle mpv's own thread is using.\"\"\"
    _hwnd, thread = _mpv_window()
    if not thread:
        return None
    return _user32.GetKeyboardLayout(thread)


def _is_us_layout(hkl) -> bool:
    \"\"\"Is this layout handle a US one? The low word is the layout id.\"\"\"
    if not hkl:
        return False
    return (int(hkl) & 0xFFFF) == US_LAYOUT_ID


def _us_char(vk: int, scan: int, shift: bool) -> str:
    \"\"\"The character the US layout produces for this physical key.\"\"\"
    table = US_SHIFT if shift else US_CHARS
    return table.get(vk, "")


def should_translate(layout_hkl, target: str) -> bool:
    \"\"\"Does this key need the US character instead of the layout's one?

    Pure so it can be tested without a keyboard:
      - nothing to translate without a US character for the key;
      - nothing to translate when mpv already is on a US layout - the key
        produces exactly the character the bindings expect;
      - otherwise mpv is on a layout that produces something else, so the
        US character of the same physical key is the useful one.
    \"\"\"
    if not target:
        return False
    return not _is_us_layout(layout_hkl)


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


def _make_hook(log, foreground_check=None, inject=None, layout_of=None):
    \"\"\"Build the low level keyboard hook.

    foreground_check, inject and layout_of can be replaced so the whole key
    path can be tested without a real window and without sending real keys.
    \"\"\"
    check_foreground = foreground_check or _mpv_is_foreground
    inject_char = inject or _inject_char
    get_layout = layout_of or _mpv_layout
    state = {"swallow_keyup": None}

    def hook(code, wparam, lparam):
        vk = wparam & 0xFF
        if code == WM_KEYUP:
            # the key we swallowed must not report a release of its own:
            # the injected US character brings its own key up.
            if state["swallow_keyup"] == vk:
                state["swallow_keyup"] = None
                return 1
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        if code != WM_KEYDOWN:
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        if (lparam >> 24) & LLKHF_INJECTED:
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        if not check_foreground():
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        scan = (lparam >> 16) & 0xFF
        # Ctrl/Alt/Win combinations are already layout independent (Windows
        # turns Ctrl+letter into a control code), so they must never be
        # translated.
        for modifier in (0x11, 0x12, 0x5B, 0x5C):
            if _user32.GetKeyState(modifier) & 0x8000:
                return _user32.CallNextHookEx(None, code, wparam, lparam)
        shift = bool(_user32.GetKeyState(0x10) & 0x8000)
        target = _us_char(vk, scan, shift)
        if not should_translate(get_layout(), target):
            return _user32.CallNextHookEx(None, code, wparam, lparam)
        # mpv is on another layout: give it the US character of this key
        if log:
            log("translate vk=%d -> %r" % (vk, target))
        state["swallow_keyup"] = vk
        inject_char(target)
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
        message = "layout_guard: could not install the keyboard hook (%s)" % (
            _kernel32.GetLastError(),)
        print(message, file=sys.stderr)
        if log:
            log(message)
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
