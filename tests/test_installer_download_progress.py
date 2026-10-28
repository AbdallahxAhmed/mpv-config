"""Live download progress: the installer previously sat silent through
`Downloading yt-dlp.exe...` on slow links and read as frozen. The inline
progress renderer must show real byte counts, a bar, and stay silent
exactly like before when output is piped."""

import io
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from deploy.installer import _create_tmp_file, _download_asset
from deploy.ui import InlineDownloadProgress as _InlineDownloadProgress


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


def _progress(total=None, label="yt-dlp.exe", **kwargs):
    out = _TtySink()
    clock = _FakeClock()
    # ASCII glyphs by default so assertions are hermetic across terminals;
    # individual tests may override with theme="unicode".
    kwargs.setdefault("theme", "ascii")
    progress = _InlineDownloadProgress(
        label, total=total, stdout=out, clock=clock, **kwargs
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

    def test_unicode_theme_uses_heavy_bar_glyphs(self):
        # The default theme mirrors the rich Progress bars used elsewhere in
        # the output; force it explicitly here so the test is hermetic.
        progress, out, clock = _progress(total=1000, theme="unicode")
        clock.advance(0.5)
        progress.update(500)
        text = out.getvalue()
        self.assertIn("━" * 12, text)
        self.assertIn("─" * 12, text)
        self.assertIn("50%", text)

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

    def test_connect_ticks_show_liveness_before_first_byte(self):
        progress, out, clock = _progress(total=1000, tick_interval=0.1)
        progress.start_connect_ticks()
        time.sleep(0.3)  # connect phase: only tick frames exist so far
        self.assertIn("connecting", out.getvalue())
        self.assertNotIn("%", out.getvalue())  # no fake progress while dialing

        clock.advance(0.5)
        progress.update(500)  # first byte: ticks stop, bar takes over
        text = out.getvalue()
        self.assertIn("50%", text)
        self.assertIsNone(progress._tick_thread)  # tick thread joined

    def test_connect_ticks_aborted_mid_connect_close_the_line(self):
        progress, out, clock = _progress(total=1000, tick_interval=0.1)
        progress.start_connect_ticks()
        time.sleep(0.25)
        progress.abort()
        self.assertEqual(out.getvalue().count("\n"), 1)
        self.assertIsNone(progress._tick_thread)

    def test_connect_ticks_stay_silent_when_not_a_tty(self):
        out = io.StringIO()
        clock = _FakeClock()
        progress = _InlineDownloadProgress(
            "yt-dlp.exe", total=1000, stdout=out, clock=clock, tick_interval=0.1
        )
        progress.start_connect_ticks()
        time.sleep(0.2)
        progress.update(500)
        progress.finish()
        self.assertEqual(out.getvalue(), "")


class InlineProgressWidthClampTests(unittest.TestCase):
    """The rendered line must never exceed the terminal width.

    Reported from a real CachyOS install: on an 80-column terminal the full
    readout exceeded the row, auto-wrapped, and the carriage-return overwrite
    left a trail of wrapped lines down the screen. The no-wrap contract:
    budget = columns - 1, shrunk bar-first (bar to zero, then ETA, then
    speed, then the label) while pct and byte counts always stay.
    """

    def setUp(self):
        super().setUp()
        from unittest import mock
        import deploy.ui as ui
        patcher = mock.patch.object(ui, "USE_COLOR", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _render_at(self, budget, total=1000, done=500, label="yt-dlp.exe"):
        """Render the frame under test at a fixed terminal width.

        A throwaway first update anchors the elapsed clock (speed would
        otherwise read 0.0 and omit the ETA); the returned text is the
        last frame only, so ladder assertions see exactly one render.
        """
        progress, out, clock = _progress(
            total=total, label=label, width_fn=lambda: budget
        )
        clock.advance(0.5)
        progress.update(0)
        clock.advance(1.0)
        progress.update(done)
        return out.getvalue().split("\r")[-1]

    @staticmethod
    def _frames(out):
        return [frame.rstrip("\n") for frame in out.getvalue().split("\r") if frame.strip()]

    def test_full_readout_fits_the_linux_80_column_default(self):
        self.assertLessEqual(len(self._render_at(80)), 79)

    def test_bar_shrinks_before_eta_is_dropped(self):
        # full readout at bar 24 is 80 chars; budget 69 shrinks the bar to 13
        frame = self._render_at(70)
        self.assertLessEqual(len(frame), 69)
        self.assertIn("ETA", frame)
        self.assertLess(frame.count("#"), 12)

    def test_eta_dropped_when_the_bar_is_exhausted(self):
        # bar-0 skeleton with ETA is 56 chars — still over budget 51, so
        # ETA goes; the speed readout (48 chars with it) stays.
        frame = self._render_at(52)
        self.assertLessEqual(len(frame), 51)
        self.assertNotIn("ETA", frame)
        self.assertIn("B/s", frame)

    def test_label_truncated_last_pct_and_bytes_kept(self):
        frame = self._render_at(40, label="uosc-stable-volume-menu.zip")
        self.assertLessEqual(len(frame), 39)
        self.assertNotIn("uosc-stable-volume-menu.zip", frame)
        self.assertIn("uosc", frame)  # truncated, not vanished
        self.assertIn("50%", frame)
        self.assertIn("500.0 B/1000.0 B", frame)

    def test_unknown_total_line_clamped_too(self):
        frame = self._render_at(50, total=None)
        self.assertLessEqual(len(frame), 49)
        self.assertIn("500.0 B", frame)

    def test_ansi_output_is_erased_and_clamped_by_visible_length(self):
        import re
        from unittest import mock

        import deploy.ui as ui

        ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
        with mock.patch.object(ui, "USE_COLOR", True):
            frame = self._render_at(60)
        visible = len(ansi.sub("", frame))
        self.assertLessEqual(visible, 59)
        self.assertIn("\x1b[2K", frame)  # whole-row erase, no pad

    def test_connect_line_never_exceeds_the_budget(self):
        import time as _time

        progress, out, clock = _progress(
            total=1000,
            label="a-quite-long-download-label-exceeding-rows.zip",
            width_fn=lambda: 30,
            tick_interval=0.1,
        )
        progress.start_connect_ticks()
        _time.sleep(0.25)
        self.assertTrue(self._frames(out))
        self.assertTrue(all(len(frame) <= 29 for frame in self._frames(out)))
        progress.abort()


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

    def test_create_tmp_file_creates_a_dot_mpvdl_file_in_dest_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fd, tmp_path = _create_tmp_file(os.path.join(tmpdir, "bin.exe"))
            try:
                self.assertTrue(os.path.isfile(tmp_path))
                self.assertIn(".mpvdl-", os.path.basename(tmp_path))
                self.assertEqual(os.path.dirname(tmp_path), tmpdir)
                os.write(fd, b"probe")
            finally:
                os.close(fd)
                os.remove(tmp_path)

    def test_create_tmp_file_denied_raises_clear_actionable_error(self):
        from unittest import mock

        with mock.patch(
            "deploy.installer.os.open",
            side_effect=PermissionError(13, "Access is denied"),
        ):
            with self.assertRaises(PermissionError) as ctx:
                _create_tmp_file(r"C:\Program Files\mpv\yt-dlp\yt-dlp.exe")
            self.assertIn("not writable", str(ctx.exception))
            self.assertIn("elevated", str(ctx.exception))

    def test_unwritable_dest_fails_fast_instead_of_freezing(self):
        # Regression: tempfile.mkstemp retried PermissionError for eons on a
        # non-elevated C:\Program Files\mpv target, freezing the installer
        # inside 'Downloading yt-dlp.exe...' with no output at all.
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "yt-dlp.exe")
            with mock.patch(
                "deploy.installer.os.open",
                side_effect=PermissionError(13, "Access is denied"),
            ):
                start = time.time()
                with self.assertRaises(PermissionError) as ctx:
                    _download_asset(self._url(), dest, "yt-dlp.exe", io.StringIO())
                elapsed = time.time() - start
            self.assertIn("not writable", str(ctx.exception))
            # fail-fast: well under any human-visible hang
            self.assertLess(elapsed, 5.0)

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
