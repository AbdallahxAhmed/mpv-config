"""install.sh output goes through Gum wrappers with a fallback (constitution Principle V).

The wrapper block is extracted from the real install.sh (between its
``# >>> output wrappers`` / ``# <<< output wrappers`` markers) and run in a
bare bash with a controlled PATH, so no clone, venv or download happens.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"
BASH = shutil.which("bash")

try:
    import pty

    _HAS_PTY = True
except ImportError:  # Windows
    _HAS_PTY = False


def _wrapper_block():
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(r"^# >>> output wrappers.*?^# <<< output wrappers[^\n]*$", text, re.S | re.M)
    if not match:
        raise AssertionError("install.sh output wrapper markers not found")
    return match.group(0)


@unittest.skipUnless(os.name == "posix" and BASH, "POSIX bash bootstrap script")
class InstallShOutputTests(unittest.TestCase):
    def setUp(self):
        self._bin = tempfile.TemporaryDirectory(prefix="mpv-install-bin-")
        self.addCleanup(self._bin.cleanup)
        self.bin_dir = Path(self._bin.name)

    def _fake_gum(self, body):
        gum = self.bin_dir / "gum"
        gum.write_text("#!" + BASH + "\n" + body, encoding="utf-8")
        gum.chmod(0o755)

    def _run(self, snippet, stdin=b"", extra_env=None):
        """Run the wrapper block + snippet with only self.bin_dir on PATH."""
        env = {"PATH": str(self.bin_dir)}
        env.update(extra_env or {})
        return subprocess.run(
            [BASH, "-c", _wrapper_block() + "\n" + snippet],
            input=stdin,
            capture_output=True,
            env=env,
            timeout=30,
        )

    def test_no_bare_echo_outside_the_wrappers(self):
        offenders = []
        for number, line in enumerate(INSTALL_SH.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
            if re.search(r"(?<![\w-])echo\b", code):
                offenders.append(f"{number}: {line.strip()}")
        self.assertEqual(offenders, [], "raw echo in install.sh")

    def test_without_gum_falls_back_to_plain_text_when_not_a_terminal(self):
        result = self._run('_styled_echo info "Cloning repository..."')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"Cloning repository...\n")
        self.assertNotIn(b"\x1b", result.stdout)

    def test_die_writes_the_error_to_stderr_and_exits_1(self):
        result = self._run('die "git is required"')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"error: git is required\n")

    def test_notes_keep_going_to_stderr(self):
        result = self._run('_styled_echo dim "note: left unchanged." >&2')
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"note: left unchanged.\n")

    def test_gum_renders_when_installed_and_never_reads_stdin(self):
        record = self.bin_dir / "gum-calls.txt"
        self._fake_gum(
            f'printf "%s|" "$@" >> "{record}"\n'
            f'printf "\\nSTDIN=" >> "{record}"\n'
            f'cat >> "{record}"\n'  # whatever gum could read from stdin
            'printf "GUM:%s\\n" "${!#}"\n'
        )
        result = self._run('_styled_echo warn "falling back to uv..."', stdin=b"REST OF SCRIPT\n")
        self.assertEqual(result.stdout, b"GUM:falling back to uv...\n")
        calls = record.read_text(encoding="utf-8")
        self.assertTrue(calls.startswith("style|"), calls)
        self.assertIn("falling back to uv...", calls)
        self.assertIn("STDIN=", calls)
        self.assertNotIn("REST OF SCRIPT", calls)  # curl | bash: script stays unread

    def test_a_failing_gum_falls_back_to_plain_text(self):
        self._fake_gum("exit 1\n")
        result = self._run('_styled_echo info "Bootstrapping mpv-config..."')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"Bootstrapping mpv-config...\n")

    @unittest.skipUnless(_HAS_PTY, "needs a pty")
    def test_without_gum_uses_ansi_colour_on_a_terminal_unless_no_color(self):
        for extra_env, want_ansi in (({}, True), ({"NO_COLOR": "1"}, False)):
            with self.subTest(no_color=bool(extra_env)):
                master, slave = pty.openpty()
                try:
                    env = {"PATH": str(self.bin_dir), **extra_env}
                    proc = subprocess.run(
                        [BASH, "-c", _wrapper_block() + '\n_styled_echo info "hello"'],
                        stdin=subprocess.DEVNULL,
                        stdout=slave,
                        stderr=subprocess.DEVNULL,
                        env=env,
                        timeout=30,
                    )
                    os.close(slave)
                    slave = None
                    output = b""
                    while True:
                        try:
                            chunk = os.read(master, 1024)
                        except OSError:  # EIO once the pty is drained
                            break
                        if not chunk:
                            break
                        output += chunk
                finally:
                    if slave is not None:
                        os.close(slave)
                    os.close(master)
                self.assertEqual(proc.returncode, 0)
                self.assertIn(b"hello", output)
                self.assertEqual(b"\x1b[36m" in output, want_ansi, output)


if __name__ == "__main__":
    unittest.main()
