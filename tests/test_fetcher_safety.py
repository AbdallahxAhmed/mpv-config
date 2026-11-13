import io
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from deploy import fetcher
from deploy.fetcher import fetch_release


def _zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _latest_release_payload():
    """Unpinned entries resolve the newest release, so the API returns a list."""
    return json.dumps(
        [
            {
                "tag_name": "v1",
                "assets": [{"name": "uosc.zip", "browser_download_url": "https://x/uosc.zip"}],
            }
        ]
    )


def _pinned_release_payload():
    """A pinned entry hits /tags/<pin>, which returns a single release object."""
    return json.dumps(
        {
            "tag_name": "v1",
            "assets": [{"name": "uosc.zip", "browser_download_url": "https://x/uosc.zip"}],
        }
    )


UOSC_ENTRY = {
    "name": "uosc",
    "source": {"repo": "tomasklaen/uosc", "asset_pattern": "uosc.zip"},
    "install": {"map": {"scripts/uosc/": "scripts/uosc/", "fonts/": "fonts/"}},
}


class TestFetcherSafety(unittest.TestCase):
    def test_fetch_release_rejects_path_traversal_member(self):
        release_payload = _latest_release_payload()
        zip_payload = _zip_bytes({"scripts/uosc/../../../outside.lua": "x"})
        entry = json.loads(json.dumps(UOSC_ENTRY))
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("deploy.fetcher._request", side_effect=[release_payload, zip_payload]):
                with self.assertRaises(ValueError):
                    fetch_release(entry, tmpdir)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "outside.lua")))

    def test_fetch_release_accepts_release_root_prefix(self):
        release_payload = _latest_release_payload()
        zip_payload = _zip_bytes(
            {
                "uosc-v1/scripts/uosc/main.lua": "print('ok')",
                "uosc-v1/fonts/uosc-icons.ttf": "font",
            }
        )
        entry = json.loads(json.dumps(UOSC_ENTRY))
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("deploy.fetcher._request", side_effect=[release_payload, zip_payload]):
                meta = fetch_release(entry, tmpdir)
            self.assertGreater(meta["files_count"], 0)
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "scripts", "uosc", "main.lua")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "fonts", "uosc-icons.ttf")))

    def test_fetch_release_pinned_tag_reads_single_release_object(self):
        release_payload = _pinned_release_payload()
        zip_payload = _zip_bytes({"uosc-v1/scripts/uosc/main.lua": "print('ok')"})
        entry = json.loads(json.dumps(UOSC_ENTRY))
        entry["source"]["pin"] = "v1"
        entry["install"]["map"] = {"scripts/uosc/": "scripts/uosc/"}
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("deploy.fetcher._request", side_effect=[release_payload, zip_payload]):
                meta = fetch_release(entry, tmpdir)
            self.assertGreater(meta["files_count"], 0)
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "scripts", "uosc", "main.lua")))


class _TtySink(io.StringIO):
    """StringIO reporting isatty() True to exercise the rendering path."""

    def isatty(self):
        return True


_BODY = (b"u" * 1024) * 300  # 300 KiB: more than one STREAM_CHUNK_BYTES block


class _ChunkedBodyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, *args):  # silence the test run
        pass


class RequestStreamingProgressTests(unittest.TestCase):
    """_request streams the body in 256 KiB chunks into the inline readout
    instead of the one-shot read that left the scripts/shaders phase frozen
    at 0% until component jumps (user report 2026-10-27)."""

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ChunkedBodyHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/asset.bin"

    def test_binary_body_streams_with_total_and_counted_chunks(self):
        from deploy.fetcher import _request
        from deploy.ui import InlineDownloadProgress

        sink = _TtySink()
        progress = InlineDownloadProgress("uosc.zip", stdout=sink, update_interval=0.0)
        data = _request(self._url(), binary=True, progress=progress)
        self.assertEqual(data, _BODY)
        self.assertEqual(progress.total, len(_BODY))
        self.assertEqual(progress._done, len(_BODY))
        # More than one streamed block: the one-shot read is gone.
        self.assertGreater(progress.total, fetcher.STREAM_CHUNK_BYTES)
        rendered = sink.getvalue()
        self.assertIn("100%", rendered)
        self.assertIn(f"{len(_BODY) / 1024:.1f} KB", rendered)

    def test_non_tty_output_stays_silent(self):
        from deploy.fetcher import _request
        from deploy.ui import InlineDownloadProgress

        sink = io.StringIO()
        progress = InlineDownloadProgress("uosc.zip", stdout=sink, update_interval=0.0)
        data = _request(self._url(), binary=True, progress=progress)
        self.assertEqual(data, _BODY)
        self.assertEqual(sink.getvalue(), "")


class ReleaseResolutionAndRetryTests(unittest.TestCase):
    def test_unpinned_release_uses_latest_endpoint_and_skips_prereleases(self):
        payload = json.dumps(
            [
                {"tag_name": "v2-rc1", "prerelease": True, "assets": []},
                {
                    "tag_name": "v1",
                    "assets": [{"name": "uosc.zip", "browser_download_url": "https://x/uosc.zip"}],
                },
            ]
        )
        zip_payload = _zip_bytes({"scripts/uosc/main.lua": "x", "fonts/a.ttf": "f"})
        entry = json.loads(json.dumps(UOSC_ENTRY))
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch(
                "deploy.fetcher._request", side_effect=[payload, zip_payload]
            ) as request:
                result = fetch_release(entry, tmpdir)
        self.assertTrue(request.call_args_list[0].args[0].endswith("/releases/latest"))
        self.assertEqual(result["version"], "v1")

    def _response(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"ok"
        return response

    def test_connection_reset_mid_body_is_retried(self):
        with (
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[ConnectionResetError("reset"), self._response()],
            ),
            mock.patch("deploy.fetcher.time.sleep"),
        ):
            self.assertEqual(fetcher._request("https://example.invalid/a", binary=True), b"ok")

    def test_exhausted_rate_limit_fails_fast_with_token_hint(self):
        import urllib.error
        from email.message import Message

        headers = Message()
        headers["X-RateLimit-Remaining"] = "0"
        error = urllib.error.HTTPError("https://api.github.com/x", 403, "rate", headers, None)
        with (
            mock.patch("urllib.request.urlopen", side_effect=error) as urlopen,
            mock.patch("deploy.fetcher.time.sleep") as sleep,
            self.assertRaisesRegex(ConnectionError, "GITHUB_TOKEN"),
        ):
            fetcher._request("https://api.github.com/x")
        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_github_token_is_sent_only_to_the_api_host(self):
        seen = []

        def fake_urlopen(request, timeout):
            seen.append((request.full_url, request.get_header("Authorization")))
            return self._response()

        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t0k"}),
            mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            fetcher._request("https://api.github.com/repos/a/b/releases/latest")
            fetcher._request("https://raw.githubusercontent.com/a/b/main/x.lua")
        self.assertEqual(seen[0][1], "Bearer t0k")
        self.assertIsNone(seen[1][1])


if __name__ == "__main__":
    unittest.main()
