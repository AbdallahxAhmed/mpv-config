"""The keyboard-layout guard: mpv's keys must work under any layout."""
import ctypes
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from mpv_config import layout_guard as lg
except Exception:  # pragma: no cover
    lg = None

MPV = None
for candidate in ("mpv.exe", "mpv.com", "mpv"):
    for folder in (Path(r"C:\Program Files\mpv"), Path("/usr/bin"), Path("/usr/local/bin")):
        probe = folder / candidate
        if probe.is_file():
            MPV = str(probe)
            break
    if MPV:
        break

VK_H = ord("H")
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
US_HKL = 0x04090409          # en-US
ARABIC_HKL = 0x04010C01      # ar-SA, Arabic 101 layout


def key_event(vk, scan=0x23, injected=False):
    """Build an lParam for a WM_KEYDOWN/WM_KEYUP like Windows does."""
    lparam = (scan & 0xFF) << 16
    if injected:
        lparam |= 0x10 << 24        # LLKHF_INJECTED
    return lparam


@unittest.skipUnless(lg is not None, "mpv_config is not importable")
@unittest.skipUnless(sys.platform == "win32", "the layout guard is Windows only")
class LayoutGuardTests(unittest.TestCase):
    def setUp(self):
        lg._windows_only()

    # ── the tables ────────────────────────────────────────────────────────
    def test_the_us_character_of_a_key_is_the_english_one(self):
        for vk, expected in ((ord("A"), "a"), (ord("H"), "h"), (ord("K"), "k"),
                             (ord("1"), "1"), (0x20, " ")):
            self.assertEqual(lg._us_char(vk, 0, False), expected)
        self.assertEqual(lg._us_char(ord("1"), 0, True), "!")
        self.assertEqual(lg._us_char(ord("H"), 0, True), "H")

    # ── the layout decision ───────────────────────────────────────────────
    def test_a_us_layout_needs_no_translation(self):
        self.assertTrue(lg._is_us_layout(US_HKL))
        self.assertFalse(lg.should_translate(US_HKL, "h"))

    def test_another_layout_needs_the_us_character(self):
        """The arabic layout is not a US one, so the key must be translated."""
        self.assertFalse(lg._is_us_layout(ARABIC_HKL))
        self.assertTrue(lg.should_translate(ARABIC_HKL, "h"))

    def test_without_a_layout_nothing_is_translated(self):
        self.assertFalse(lg.should_translate(None, "h"))

    def test_a_key_without_a_us_equivalent_is_untouched(self):
        self.assertFalse(lg.should_translate(ARABIC_HKL, ""))

    def test_the_installed_arabic_layout_is_recognised(self):
        """The machine really has the arabic layout - and it is not US."""
        user32 = lg._user32
        user32.GetKeyboardLayoutList.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        buf = (ctypes.c_void_p * 32)()
        user32.GetKeyboardLayoutList(32, buf)
        layouts = [buf[i] for i in range(32) if buf[i]]
        self.assertTrue(layouts, "no keyboard layout at all")
        arabic = [hkl for hkl in layouts if (int(hkl) & 0xFFFF) == 0x0C01]
        if not arabic:
            self.skipTest("the arabic layout is not installed")
        self.assertFalse(lg._is_us_layout(arabic[0]))
        self.assertTrue(lg.should_translate(arabic[0], "h"))

    # ── the hook ──────────────────────────────────────────────────────────
    def _hook(self, foreground=True, layout=ARABIC_HKL):
        """Build the hook with a fake foreground check, layout and injector."""
        sent = []
        hook = lg._make_hook(
            None,
            foreground_check=lambda: foreground,
            inject=lambda char: sent.append(char),
            layout_of=lambda: layout,
        )
        return hook, sent

    def test_the_hook_translates_and_swallows_the_key(self):
        hook, sent = self._hook()
        result = hook(WM_KEYDOWN, VK_H, key_event(VK_H))
        self.assertEqual(result, 1, "the original key was not swallowed")
        self.assertEqual(sent, ["h"])

    def test_the_hook_also_swallows_the_matching_key_up(self):
        """mpv must not see a key up for a key down it never got."""
        hook, sent = self._hook()
        hook(WM_KEYDOWN, VK_H, key_event(VK_H))
        result = hook(WM_KEYUP, VK_H, key_event(VK_H))
        self.assertEqual(result, 1, "the original key up was not swallowed")

    def test_the_hook_passes_the_key_through_when_mpv_is_not_focused(self):
        hook, sent = self._hook(foreground=False)
        result = hook(WM_KEYDOWN, VK_H, key_event(VK_H))
        self.assertNotEqual(result, 1)
        self.assertEqual(sent, [])

    def test_the_hook_does_nothing_on_a_us_layout(self):
        hook, sent = self._hook(layout=US_HKL)
        result = hook(WM_KEYDOWN, VK_H, key_event(VK_H))
        self.assertNotEqual(result, 1)
        self.assertEqual(sent, [])

    def test_the_hook_ignores_its_own_injected_keys(self):
        hook, sent = self._hook()
        result = hook(WM_KEYDOWN, VK_H, key_event(VK_H, injected=True))
        self.assertNotEqual(result, 1)
        self.assertEqual(sent, [])

    # ── the process ───────────────────────────────────────────────────────
    @unittest.skipUnless(MPV, "mpv is not installed")
    def test_the_guard_starts_and_installs_its_hook(self):
        guard = subprocess.Popen(
            [sys.executable, "-m", "mpv_config.layout_guard", "--duration", "3"],
            cwd=str(REPO_ROOT / "src"), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
            creationflags=0x08000000)
        time.sleep(1.5)
        alive = guard.poll() is None
        guard.terminate()
        output = guard.stdout.read() if guard.stdout else ""
        self.assertTrue(alive, "the guard exited: %s" % output[:300])
        self.assertNotIn("could not install", output)

    def test_the_guard_writes_a_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "guard.log"
            guard = subprocess.Popen(
                [sys.executable, "-m", "mpv_config.layout_guard",
                 "--log", str(log_path)],
                cwd=str(REPO_ROOT / "src"), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=0x08000000)
            time.sleep(1.5)
            guard.terminate()
            try:
                guard.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                guard.kill()
                guard.wait(timeout=5)
            self.assertTrue(log_path.exists(), "the guard wrote no log")
            self.assertIn("guard started", log_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
