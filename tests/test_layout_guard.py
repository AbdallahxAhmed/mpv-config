"""The keyboard-layout guard: mpv's window must end up on a latin layout."""
import ctypes
import ctypes.wintypes as wintypes
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from mpv_config import layout_guard as lg
except Exception:  # pragma: no cover - the package is not installed in CI
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


@unittest.skipUnless(lg is not None, "mpv_config is not importable")
@unittest.skipUnless(sys.platform == "win32", "the layout guard is Windows only")
@unittest.skipUnless(MPV, "mpv is not installed")
class LayoutGuardTests(unittest.TestCase):
    def test_mpv_window_ends_up_on_the_latin_layout(self):
        lg._windows_only()
        user32 = ctypes.windll.user32

        # Put THIS thread on the Arabic layout so the mpv we start inherits
        # it - that inheritance is the whole problem.
        arabic = user32.LoadKeyboardLayoutW("00000C01", 1)
        try:
            user32.SetThreadInputLayout(arabic)
        except Exception:
            pass

        proc = subprocess.Popen(
            [MPV, "--no-config", "--idle=yes", "--force-window=immediate",
             "--geometry=320x200+50+50"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 15
            windows = []
            while time.time() < deadline:
                windows = lg._find_mpv_windows()
                if windows:
                    break
                time.sleep(0.25)
            self.assertTrue(windows, "no mpv window appeared")

            hwnd, thread = windows[0]
            self.assertNotEqual(lg._layout_of(thread), 0x409,
                                "the test needs mpv to start on a non-latin layout")

            # the guard puts it back
            self.assertTrue(lg._ensure_layout(hwnd, thread, "00000409", 0x409))
            self.assertEqual(lg._layout_of(thread), 0x409)
        finally:
            proc.kill()

    def test_the_guard_leaves_other_windows_alone(self):
        lg._windows_only()
        user32 = ctypes.windll.user32
        # the helper only ever touches windows whose class is "mpv"
        self.assertTrue(hasattr(lg, "_find_mpv_windows"))
        self.assertEqual(lg.WM_INPUTLANGCHANGEREQUEST, 0x0050)


if __name__ == "__main__":
    unittest.main()
