"""The keyboard-layout guard: mpv's keys must work under any layout."""
import ctypes
import subprocess
import sys
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


@unittest.skipUnless(lg is not None, "mpv_config is not importable")
@unittest.skipUnless(sys.platform == "win32", "the layout guard is Windows only")
class LayoutGuardTests(unittest.TestCase):
    def test_the_us_character_of_a_key_is_the_english_one(self):
        """The US table gives the English character for the key."""
        lg._windows_only()
        for vk, expected in ((ord("A"), "a"), (ord("H"), "h"), (ord("K"), "k"),
                             (ord("1"), "1"), (0x20, " ")):
            self.assertEqual(lg._us_char(vk, 0, False), expected)
        self.assertEqual(lg._us_char(ord("1"), 0, True), "!")
        self.assertEqual(lg._us_char(ord("H"), 0, True), "H")

    def test_a_key_that_already_produces_the_us_character_is_untouched(self):
        self.assertFalse(lg.should_translate("a", "a"))

    def test_a_dead_key_is_translated(self):
        # the layout produced nothing (a dead key): the US character is
        # the useful one
        self.assertTrue(lg.should_translate("", "a"))

    def test_a_different_character_is_translated(self):
        # the Arabic 102 AZERTY layout puts 'ا' on the physical H key
        self.assertTrue(lg.should_translate("ا", "h"))

    def test_control_codes_are_never_translated(self):
        # Ctrl+letter is a control code and already layout independent
        self.assertFalse(lg.should_translate("\x1e", "a"))
        self.assertFalse(lg.should_translate("\x02", "1"))

    def test_a_key_without_a_us_equivalent_is_untouched(self):
        self.assertFalse(lg.should_translate("ش", ""))

    @unittest.skipUnless(MPV, "mpv is not installed")
    def test_the_guard_starts_and_installs_its_hook(self):
        lg._windows_only()
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


if __name__ == "__main__":
    unittest.main()
