import os
import unittest
from tools.core.flaresolverr import (
    is_flaresolverr_running,
    format_netscape_cookies,
    save_cookies_to_disk,
)
from tools.yt_dlp_plugins.extractor.htv import _get_default_user_agent, _solve_via_flaresolverr


class TestFlareSolverrIntegration(unittest.TestCase):
    def test_format_netscape_cookies(self):
        cookies = [
            {"domain": ".hanime.tv", "name": "cf_clearance", "value": "test_clearance", "secure": True, "expiry": 1800000000}
        ]
        text = format_netscape_cookies(cookies)
        self.assertIn("# Netscape HTTP Cookie File", text)
        self.assertIn(".hanime.tv\tTRUE\t/\tTRUE\t1800000000\tcf_clearance\ttest_clearance", text)

    def test_save_cookies_to_disk(self):
        text = "# Netscape HTTP Cookie File\n.test.com\tTRUE\t/\tTRUE\t0\tfoo\tbar\n"
        saved = save_cookies_to_disk(text, "test.com")
        self.assertGreater(len(saved), 0)

    def test_default_user_agent(self):
        ua = _get_default_user_agent()
        self.assertTrue(isinstance(ua, str))
        self.assertIn("Mozilla/5.0", ua)

    def test_flaresolverr_liveness(self):
        # Checks if FlareSolverr returns boolean without throwing uncaught exceptions
        running = is_flaresolverr_running(timeout=0.5)
        self.assertIsInstance(running, bool)


if __name__ == "__main__":
    unittest.main()
