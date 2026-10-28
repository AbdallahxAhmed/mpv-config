"""Auto-answered confirm prompts must not reach the screen.

`sudo pacman -S --noconfirm --needed yt-dlp` prints ':: Proceed with
installation? [Y/n]' even though --noconfirm answers it; the quiet-mode
runner forwarded that line because it matched the shared prompt regex,
and the operator's reflexive 'y' landed in the shell after the installer
exited (real CachyOS run, 2026-10-28). Password prompts (sudo) stay
forwarded; confirm-class prompts forward only when the command carries
no auto-answer flag, and suppressed lines still reach the failure tail.
"""

import io
import os
import unittest
from contextlib import redirect_stdout

from deploy.installer import _run


@unittest.skipUnless(os.name == "posix", "POSIX-only child shell")
class PromptForwardingTests(unittest.TestCase):
    def _capture(self, script, *extra_flags):
        out = io.StringIO()
        with redirect_stdout(out):
            ok = _run(["/bin/sh", "-c", script, *extra_flags], timeout=30)
        return ok, out.getvalue()

    @staticmethod
    def _live_lines(out):
        """Output lines minus the command echo (which embeds the script)."""
        return [ln for ln in out.splitlines() if not ln.lstrip().startswith("$ ")]

    def test_noconfirm_suppresses_the_pacman_confirm_prompt(self):
        ok, out = self._capture(
            "printf ':: Proceed with installation? [Y/n]\\n'", "--noconfirm"
        )
        self.assertTrue(ok)
        self.assertNotIn("[Y/n]", "\n".join(self._live_lines(out)))

    def test_without_auto_answer_the_confirm_prompt_stays_forwarded(self):
        ok, out = self._capture("printf ':: Proceed with installation? [Y/n]\\n'")
        self.assertTrue(ok)
        self.assertIn("      :: Proceed with installation? [Y/n]", out)

    def test_sudo_password_prompt_stays_forwarded_despite_flags(self):
        ok, out = self._capture(
            "printf '[sudo] password for user: \\n'", "--noconfirm"
        )
        self.assertTrue(ok)
        self.assertIn("      [sudo] password for user", out)

    def test_apt_dash_y_suppresses_its_confirm_prompt(self):
        ok, out = self._capture(
            "printf 'Do you want to continue? [Y/n]\\n'", "-y"
        )
        self.assertTrue(ok)
        self.assertNotIn("[Y/n]", "\n".join(self._live_lines(out)))

    def test_suppressed_lines_still_reach_the_failure_tail(self):
        ok, out = self._capture(
            "echo 'resolving dependencies...'; "
            "echo ':: Proceed with installation? [Y/n]'; exit 3",
            "--noconfirm",
        )
        self.assertFalse(ok)
        self.assertIn("│ :: Proceed with installation? [Y/n]", out)


if __name__ == "__main__":
    unittest.main()
