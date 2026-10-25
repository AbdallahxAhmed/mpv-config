"""
Unit tests for tools/core architecture (SiteRegistry, SiteKit, SessionManager, EngineOrchestrator, ClipboardService).
"""

import os
import sys
import unittest

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from yt_dlp.extractor.common import InfoExtractor

from tools.core.clipboard import ClipboardService
from tools.core.engine import EngineOrchestrator
from tools.core.registry import SiteRegistry
from tools.core.session import SessionManager
from tools.yt_dlp_plugins.extractor._sitekit import SiteKit


class ExampleComIE(SiteKit, InfoExtractor):
    IE_NAME = "example"
    SITE_NAME = "example.com"
    _VALID_URL = r"https?://(?:www\.)?example\.com/watch/(?P<id>[a-zA-Z0-9_-]+)"
    ENGINE = "native"
    REQUIRES_COOKIES = True

    def _real_extract(self, url):
        return {"id": "123", "title": "Example Video"}


class TestCoreArchitecture(unittest.TestCase):
    def setUp(self):
        self.registry = SiteRegistry()
        self.dummy_ie = ExampleComIE()
        self.registry._custom_ies["example"] = self.dummy_ie
        self.session = SessionManager()
        self.engine = EngineOrchestrator()

    def test_sitekit_mixin_defaults(self):
        opts = ExampleComIE.ytdl_opts()
        self.assertIn("1080", opts["format"])
        self.assertEqual(opts["concurrent_fragment_downloads"], 16)

    def test_registry_discovery(self):
        url = "https://example.com/watch/sample-video"
        ie = self.registry.find(url)
        self.assertIsNotNone(ie)
        self.assertEqual(ie.IE_NAME, "example")
        self.assertTrue(self.registry.is_custom(ie))

    def test_session_manager(self):
        browsers = self.session.get_preferred_browsers(ExampleComIE)
        self.assertIn("brave", browsers)
        self.assertIn("chrome", browsers)

        health = self.session.check_health()
        self.assertIn("installed_browsers", health)
        self.assertIn("curl_cffi_available", health)

    def test_engine_orchestrator_routing(self):
        opts = {}
        routed = self.engine.apply_engine_opts(opts, "https://example.com/watch/test", ExampleComIE)
        self.assertEqual(routed["concurrent_fragment_downloads"], 16)
        self.assertNotIn("external_downloader", routed)

    def test_clipboard_service_url_validation(self):
        self.assertTrue(ClipboardService.is_url("https://example.com/watch/sample"))
        self.assertTrue(ClipboardService.is_url("http://example.org/test-slug/"))
        self.assertFalse(ClipboardService.is_url("just plain text"))
        self.assertFalse(ClipboardService.is_url(""))
        self.assertFalse(ClipboardService.is_url("ftp://unsupported"))


if __name__ == "__main__":
    unittest.main()
