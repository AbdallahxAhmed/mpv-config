"""ui.summary closes a batch with counts plus failing rows only.

The full row dump used to duplicate the 45-row verification table under
itself on every deploy (user report 2026-10-27). These tests pin the new
contract: failing rows stay visible, ok/skipped rows are only counted, and
both the rich path and the ANSI fallback agree.
"""

import contextlib
import io
import re
import unittest

from deploy import ui


@contextlib.contextmanager
def _capture_console():
    """Route rich console output through a buffer for assertion."""
    out = io.StringIO()
    original_file = ui._console.file
    ui._console.file = out
    try:
        yield out
    finally:
        ui._console.file = original_file


class SummaryRichPathTests(unittest.TestCase):
    def test_only_failures_are_listed_counts_cover_every_row(self):
        results = [
            {"name": "uosc", "status": "ok", "detail": "v1"},
            {"name": "anime4k", "status": "skipped", "detail": "up to date"},
            {"name": "mpv launch test", "status": "failed", "detail": "exit 3"},
        ]
        with _capture_console() as out:
            ui.summary(results)
        text = out.getvalue()
        self.assertIn("mpv launch test", text)
        self.assertIn("exit 3", text)
        self.assertNotIn("uosc", text)
        self.assertNotIn("anime4k", text)
        self.assertIn("1 succeeded", text)
        self.assertIn("1 skipped", text)
        self.assertIn("1 failed", text)

    def test_all_ok_prints_a_single_count_line_without_rows(self):
        results = [{"name": "check-%d" % n, "status": "ok"} for n in range(3)]
        with _capture_console() as out:
            ui.summary(results)
        text = out.getvalue()
        self.assertIn("3 succeeded", text)
        self.assertNotIn("check-", text)
        self.assertNotIn("Table", text)

    def test_empty_batch_says_nothing_to_report(self):
        with _capture_console() as out:
            ui.summary([])
        self.assertIn("nothing to report", out.getvalue())


class SummaryAnsiFallbackTests(unittest.TestCase):
    def test_failures_listed_and_counts_printed_without_rich(self):
        results = [
            {"name": "staging", "status": "ok"},
            {"name": "verify config", "status": "failed", "detail": "bad shader path"},
        ]
        original_rich = ui._RICH_AVAILABLE
        ui._RICH_AVAILABLE = False
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                ui.summary(results)
        finally:
            ui._RICH_AVAILABLE = original_rich
        text = buffer.getvalue()
        self.assertIn("Failed:", text)
        self.assertIn("verify config", text)
        self.assertIn("bad shader path", text)
        self.assertNotIn("staging", text)
        self.assertIn("1 succeeded", text)
        self.assertIn("1 failed", text)


# Spec 005: rows with status "warn" get their own Warnings list (plan "Summary warnings").
LONG_DETAIL = (
    "uosc-playlist-reorder skipped: elements/Menu.lua does not match uosc 5.13.0 "
    "(sha256 of the unpatched form 0123456789ab…); uosc left unchanged"
)
WARN_ROWS = [
    {"name": "staging", "status": "ok"},
    {"name": "fonts", "status": "skipped"},
    {"name": "uosc-playlist-reorder-patch", "status": "warn", "detail": LONG_DETAIL},
    {"name": "migration", "status": "warn", "detail": "[Errno 2] No such file"},
    {"name": "bare", "status": "warn"},
    {"name": "verify config", "status": "failed", "detail": "bad shader path"},
]


def _plain_lines(text):
    return [re.sub(r"\x1b\[[0-9;]*m", "", line).rstrip() for line in text.splitlines()]


class SummaryWarningsTests(unittest.TestCase):
    def test_rich_lists_warnings_unwrapped_before_failures(self):
        with _capture_console() as out:
            ui.summary(WARN_ROWS)
        lines = _plain_lines(out.getvalue())
        start = lines.index("Warnings")
        self.assertEqual(
            [
                f"! uosc-playlist-reorder-patch -- {LONG_DETAIL}",
                "! migration -- [Errno 2] No such file",
                "! bare",
            ],
            lines[start + 1 : start + 4],
        )
        failed_at = next(i for i, line in enumerate(lines) if "verify config" in line)
        self.assertLess(start, failed_at)
        self.assertFalse(
            any("uosc-playlist-reorder-patch" in line and "✗" in line for line in lines)
        )
        self.assertIn("1 succeeded  1 skipped  3 warnings  1 failed", lines)

    def test_ansi_lists_warnings_before_the_failed_block(self):
        original_rich = ui._RICH_AVAILABLE
        ui._RICH_AVAILABLE = False
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                ui.summary(WARN_ROWS)
        finally:
            ui._RICH_AVAILABLE = original_rich
        lines = _plain_lines(buffer.getvalue())
        start = lines.index("Warnings:")
        self.assertEqual(
            [
                f"  {ui.S.WARN} uosc-playlist-reorder-patch -- {LONG_DETAIL}",
                f"  {ui.S.WARN} migration -- [Errno 2] No such file",
                f"  {ui.S.WARN} bare",
            ],
            lines[start + 1 : start + 4],
        )
        self.assertLess(start, lines.index("Failed:"))
        failed_block = lines[lines.index("Failed:") + 1 :]
        self.assertFalse(any("uosc-playlist-reorder-patch" in line for line in failed_block))
        self.assertIn("  1 succeeded  1 skipped  3 warnings  1 failed", lines)

    def test_one_warning_is_singular_and_not_counted_as_failed(self):
        with _capture_console() as out:
            ui.summary([{"name": "a", "status": "warn", "detail": "d"}])
        lines = _plain_lines(out.getvalue())
        self.assertIn("1 warning", lines)
        self.assertFalse(any("failed" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
