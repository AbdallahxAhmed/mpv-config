"""install.sh must reattach piped stdin to /dev/tty so the CLI stays interactive.

``curl -fsSL .../install.sh | bash`` feeds the script through a pipe: the
bootstrapped Python inherits that pipe as stdin, ``sys.stdin.isatty()`` is
False, and the Anime4K menu plus the plan confirmation silently take their
defaults (``ui.confirm`` treats EOF as "no"). Reported from a real CachyOS
install on 2026-10-27.

The tests run the real install.sh against a stub ``python3`` on PATH, so no
venv, clone, or download happens; the pty case gives the child session a
controlling terminal (setsid + TIOCSCTTY) the way a real terminal would.
"""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"

try:
    import fcntl
    import pty
    import select
    import termios

    _POSIX_TTY_TOOLS = True
except ImportError:  # Windows: no pty module — the suite is skipped there
    _POSIX_TTY_TOOLS = False

_STUB = """\
#!/usr/bin/env bash
# Stands in for python3: answers install.sh's probes (version check,
# ensurepip, venv creation, editable pip install) and reports the stdin
# tty-ness of the final `python -m mpv_config install` exec.
case " $* " in
  *" -m mpv_config "*)
      if [ -t 0 ]; then echo "MPVCONFIG_STDIN=tty"; else echo "MPVCONFIG_STDIN=pipe"; fi
      ;;
  *" -m venv "*)
      vdir="${*: -1}"
      mkdir -p "${vdir}/bin"
      cp "$0" "${vdir}/bin/python"
      chmod +x "${vdir}/bin/python"
      ;;
esac
exit 0
"""


@unittest.skipUnless(os.name == "posix", "POSIX-only bootstrap script")
class InstallShStdinTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.TemporaryDirectory(prefix="mpv-install-home-")
        self.addCleanup(self._home.cleanup)
        self._stub = tempfile.TemporaryDirectory(prefix="mpv-install-stub-")
        self.addCleanup(self._stub.cleanup)
        stub_path = Path(self._stub.name) / "python3"
        stub_path.write_text(_STUB, encoding="utf-8")
        stub_path.chmod(0o755)
        self.env = dict(os.environ)
        self.env["HOME"] = self._home.name
        self.env["XDG_DATA_HOME"] = os.path.join(self._home.name, "xdg-data")
        self.env["PATH"] = self._stub.name + os.pathsep + self.env["PATH"]

    def test_piped_stdin_with_tty_stdout_reattaches_dev_tty(self):
        """The curl | bash shape: stdin pipe, stdout terminal, /dev/tty there."""
        output = self._run_with_pty_stdout()
        self.assertIn("MPVCONFIG_STDIN=tty", output)

    def test_non_tty_stdout_stays_non_interactive(self):
        """No terminal on stdout (CI, logs): no reattach, stdin stays the pipe."""
        result = subprocess.run(
            ["bash", str(INSTALL_SH)],
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self.env,
            cwd=REPO_ROOT,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))
        self.assertIn("MPVCONFIG_STDIN=pipe", result.stdout.decode(errors="replace"))

    def _run_with_pty_stdout(self):
        """Run install.sh with piped stdin and a pty on stdout; return output.

        The forked child makes the pty its controlling terminal so /dev/tty
        resolves for it; the parent drains the master side until the child
        exits (EIO marks the drained pty). The stub env is passed explicitly:
        the forked child would otherwise inherit this test process's PATH and
        run the real python3.
        """
        master, slave = pty.openpty()
        stdin_read, stdin_write = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(stdin_write)
                os.close(master)
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
                os.dup2(stdin_read, 0)
                os.dup2(slave, 1)
                os.dup2(slave, 2)
                os.close(stdin_read)
                os.close(slave)
                os.chdir(REPO_ROOT)
                os.execvpe("bash", ["bash", str(INSTALL_SH)], self.env)
            except Exception:
                os._exit(127)
        os.close(stdin_read)
        os.close(stdin_write)
        os.close(slave)
        try:
            output = self._drain_pty(master, pid)
            _, status = os.waitpid(pid, 0)
        finally:
            os.close(master)
        self.assertEqual(status, 0)
        return output.decode(errors="replace")

    def _drain_pty(self, master, pid, timeout_seconds=60):
        """Read the pty master until EOF/EIO or the deadline; fail on hang."""
        chunks = []
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 1.0)
            if not ready:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break  # EIO: the child exited and the pty is drained
            if not chunk:
                break
            chunks.append(chunk)
        else:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            self.fail(f"install.sh did not exit within {timeout_seconds}s")
        return b"".join(chunks)


if __name__ == "__main__":
    unittest.main()
