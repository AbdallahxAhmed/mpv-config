import os
import tempfile
import unittest
from unittest import mock

from tools.core.flaresolverr import (
    format_netscape_cookies,
    is_flaresolverr_running,
    save_cookies_to_disk,
)


class TestFlareSolverrIntegration(unittest.TestCase):
    def test_format_netscape_cookies(self):
        cookies = [
            {
                "domain": ".example.com",
                "name": "cf_clearance",
                "value": "test_clearance",
                "secure": True,
                "expiry": 1800000000,
            }
        ]
        text = format_netscape_cookies(cookies)
        self.assertIn("# Netscape HTTP Cookie File", text)
        self.assertIn(".example.com\tTRUE\t/\tTRUE\t1800000000\tcf_clearance\ttest_clearance", text)

    def test_save_cookies_to_disk(self):
        text = "# Netscape HTTP Cookie File\n.test.com\tTRUE\t/\tTRUE\t0\tfoo\tbar\n"
        # Every target hangs off %APPDATA% or ~: point both at a scratch directory so the
        # test can never overwrite a real yt-dlp / mpv-config cookie file.
        with tempfile.TemporaryDirectory() as home:
            fake_env = {"APPDATA": home, "HOME": home, "USERPROFILE": home}
            with mock.patch.dict(os.environ, fake_env):
                saved = save_cookies_to_disk(text, "test.com")
            self.assertGreater(len(saved), 0)
            root = os.path.realpath(home)
            for path in saved:
                self.assertTrue(os.path.realpath(path).startswith(root), path)

    def test_flaresolverr_liveness(self):
        # Checks if FlareSolverr returns boolean without throwing uncaught exceptions
        running = is_flaresolverr_running(timeout=0.5)
        self.assertIsInstance(running, bool)


if __name__ == "__main__":
    unittest.main()
