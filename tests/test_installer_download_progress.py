"""Live download progress: the installer previously sat silent through
`Downloading yt-dlp.exe...` on slow links and read as frozen. The inline
progress renderer must show real byte counts, a bar, and stay silent
exactly like before when output is piped."""

import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from deploy.installer import _download_asset, _InlineDownloadProgress


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class _TtySink(io.StringIO):
    """StringIO that reports isatty() True to exercise the rendering path."""

    def isatty(self):
        return True


def _progress(total=None, **kwargs):
    out = _TtySink()
    clock = _FakeClock()
    progress = _InlineDownloadProgress(
        "yt-dlp.exe", total=total, stdout=out, clock=clock, **kwargs
    )
    return progress, out, clock


class InlineProgressTests(unittest.TestCase):
    def test_known_total_first_update_renders_bar_and_pct(self):
        progress, out, clock = _progress(total=1000)
        clock.advance(0.5)
        progress.update(500)
        text = out.getvalue()
        self.assertIn("yt-dlp.exe", text)
        self.assertIn("50%", text)
        self.assertIn("#" * 12, text)
        self.assertIn("500.0 B/1000.0 B", text)

    def test_bytes_only_when_total_unknown(self):
        progress, out, clock = _progress(total=None)
        progress.start()
        clock.advance(1.0)
        progress.update(2048)
        text = out.getvalue()
        self.assertIn("2.0 KB", text)
        self.assertNotIn("%", text)
        self.assertIn("KB/s", text)

    def test_throttled_updates_do_not_flood_the_console(self):
        progress, out, clock = _progress(total=1000, update_interval=0.1)
        clock.advance(0.5)
        progress.update(500)  # first update: always renders
        clock.advance(0.01)
        progress.update(10)  # inside the throttle window: skipped
        self.assertEqual(out.getvalue().count("\r"), 1)
        clock.advance(0.2)
        progress.update(10)  # throttle elapsed: renders again
        self.assertEqual(out.getvalue().count("\r"), 2)
        self.assertIn("52%", out.getvalue())

    def test_finish_renders_final_state_and_closes_the_line(self):
        progress, out, clock = _progress(total=1000)
        clock.advance(0.25)
        progress.update(999)  # initial render (99%)
        clock.advance(1.0)
        progress.finish()  # final render + newline
        text = out.getvalue()
        self.assertEqual(text.count("\n"), 1)
        self.assertIn("99%", text)

    def test_finish_without_any_render_writes_nothing(self):
        # Sandboxed sink without a TTY: silent mode, matching piped installs.
        out = io.StringIO()
        clock = _FakeClock()
        progress = _InlineDownloadProgress(
            "yt-dlp.exe", total=1000, stdout=out, clock=clock
        )
        progress.update(1000)
        progress.finish()
        self.assertEqual(out.getvalue(), "")

    def test_abort_closes_a_started_line(self):
        progress, out, clock = _progress(total=1000)
        clock.advance(0.2)
        progress.update(300)
        progress.abort()
        self.assertEqual(out.getvalue().count("\n"), 1)


_BODY = b"x" * 262144  # one full 256 KiB chunk


class _ChunkedHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/missing"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, *args):  # silence the test run
        pass


class DownloadAssetTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ChunkedHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _url(self, suffix=""):
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}/asset{suffix}"

    def test_download_writes_exact_bytes_atomically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "yt-dlp.exe")
            _download_asset(self._url(), dest, "yt-dlp.exe", io.StringIO())
            with open(dest, "rb") as fh:
                self.assertEqual(fh.read(), _BODY)
            # no half-written .mpvdl- leftovers
            self.assertEqual(os.listdir(tmpdir), ["yt-dlp.exe"])

    def test_download_failure_removes_tmp_and_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "yt-dlp.exe")
            with self.assertRaises(Exception):
                _download_asset(
                    self._url("/missing"), dest, "yt-dlp.exe", io.StringIO()
                )
            self.assertFalse(os.path.exists(dest))
            self.assertEqual(os.listdir(tmpdir), [])

    def test_progress_sink_receives_render_when_tty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "yt-dlp.exe")
            sink = _TtySink()
            _download_asset(self._url(), dest, "yt-dlp.exe", sink)
            text = sink.getvalue()
            self.assertIn("yt-dlp.exe", text)
            self.assertIn("100%", text)
            self.assertIn("\n", text)  # line closed after completion

    def test_non_tty_output_stays_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "yt-dlp.exe")
            sink = io.StringIO()
            _download_asset(self._url(), dest, "yt-dlp.exe", sink)
            self.assertEqual(sink.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
