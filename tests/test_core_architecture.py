"""
Unit tests for tools/core architecture (SiteRegistry, SiteKit, SessionManager, EngineOrchestrator, ClipboardService).
"""

import unittest
import os
import sys

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.core.registry import SiteRegistry
from tools.core.session import SessionManager
from tools.core.engine import EngineOrchestrator
from tools.core.clipboard import ClipboardService
from tools.yt_dlp_plugins.extractor._sitekit import SiteKit
from tools.yt_dlp_plugins.extractor.htv import HanimeTVIE
from tools.yt_dlp_plugins.extractor.perverzija import TubePerverzijaIE


class TestCoreArchitecture(unittest.TestCase):

    def setUp(self):
        self.registry = SiteRegistry()
        self.session = SessionManager()
        self.engine = EngineOrchestrator()

    def test_sitekit_mixin_defaults(self):
        opts = HanimeTVIE.ytdl_opts()
        self.assertIn("1080", opts["format"])
        self.assertEqual(opts["concurrent_fragment_downloads"], 16)
        self.assertEqual(HanimeTVIE.ENGINE, "native")
        self.assertTrue(HanimeTVIE.REQUIRES_COOKIES)

    def test_registry_discovery(self):
        # Hanime URL should match HanimeTVIE
        hanime_url = "https://hanime.tv/videos/hentai/sample-video"
        ie = self.registry.find(hanime_url)
        self.assertIsNotNone(ie)
        self.assertEqual(ie.IE_NAME, "hanime")

        # Perverzija URL should match TubePerverzijaIE
        perverzija_url = "https://tube.perverzija.com/sample-video/"
        ie_pv = self.registry.find(perverzija_url)
        self.assertIsNotNone(ie_pv)
        self.assertEqual(ie_pv.IE_NAME, "perverzija")

    def test_session_manager(self):
        browsers = self.session.get_preferred_browsers(HanimeTVIE)
        self.assertIn("brave", browsers)
        self.assertIn("chrome", browsers)

        health = self.session.check_health()
        self.assertIn("installed_browsers", health)
        self.assertIn("curl_cffi_available", health)

    def test_engine_orchestrator_routing(self):
        opts = {}
        # Hanime stream should route to native fragment downloader (NOT aria2c)
        routed = self.engine.apply_engine_opts(opts, "https://hanime.tv/videos/hentai/test", HanimeTVIE)
        self.assertEqual(routed["concurrent_fragment_downloads"], 16)
        self.assertNotIn("external_downloader", routed)

    def test_clipboard_service_url_validation(self):
        self.assertTrue(ClipboardService.is_url("https://hanime.tv/videos/hentai/sample"))
        self.assertTrue(ClipboardService.is_url("http://tube.perverzija.com/test-slug/"))
        self.assertFalse(ClipboardService.is_url("just plain text"))
        self.assertFalse(ClipboardService.is_url(""))
        self.assertFalse(ClipboardService.is_url("ftp://unsupported"))


if __name__ == "__main__":
    unittest.main()
