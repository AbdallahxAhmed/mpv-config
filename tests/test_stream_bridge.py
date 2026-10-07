import json
import time
import unittest
import urllib.request

from tools.native_host.cookie_sync_host import (
    get_cached_stream,
    save_cookies,
    save_stream,
    start_http_server,
)


class TestStreamBridge(unittest.TestCase):
    def test_save_cookies_netscape(self):
        sample = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t9999999999\tcf_clearance\ttestval\n"
        targets = save_cookies(sample, "example.com")
        self.assertGreater(len(targets), 0)

    def test_save_cookies_header_format(self):
        sample = "cf_clearance=test12345; in_d4=1"
        targets = save_cookies(sample, "example.com")
        self.assertGreater(len(targets), 0)

    def test_stream_cache(self):
        slug = "test-video-unit"
        m3u8 = "https://example.com/stream/index.m3u8"
        save_stream(slug, m3u8, title="Unit Video")

        cached = get_cached_stream(slug)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["url"], m3u8)
        self.assertEqual(cached["title"], "Unit Video")

    def test_clipboard_stream_extractor(self):
        # Verify get_cached_stream gracefully returns None for unknown slug
        res = get_cached_stream("non-existent-slug-xyz")
        self.assertIsNone(res)

    def test_http_daemon_endpoints(self):
        server = start_http_server(8765)
        time.sleep(0.3)

        try:
            # 1. Health
            with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as r:
                data = json.loads(r.read().decode())
                self.assertEqual(data.get("status"), "ok")

            # 2. Sync
            req = urllib.request.Request(
                "http://127.0.0.1:8765/sync",
                data=json.dumps(
                    {"cookies": "cf_clearance=unit_test_cookie", "domain": "example.com"}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read().decode())
                self.assertEqual(data.get("status"), "ok")

            # 3. Stream
            req = urllib.request.Request(
                "http://127.0.0.1:8765/stream",
                data=json.dumps(
                    {"slug": "daemon-test", "url": "https://cdn.example.com/live.m3u8"}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read().decode())
                self.assertEqual(data.get("status"), "ok")

            # 4. Stream GET
            with urllib.request.urlopen(
                "http://127.0.0.1:8765/stream?slug=daemon-test", timeout=2
            ) as r:
                data = json.loads(r.read().decode())
                self.assertEqual(data.get("status"), "ok")
                self.assertEqual(data["stream"]["url"], "https://cdn.example.com/live.m3u8")

        finally:
            if server:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()
