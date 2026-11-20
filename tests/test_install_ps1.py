"""install.ps1 installs the CLI into a private venv, never the system Python.

Constitution Principle III allows pip only inside the isolated venv. The
script used to run `pip install --user` against the system interpreter; it now
mirrors install.sh. These checks are static (this suite also runs on Linux);
when pwsh is on PATH the script is additionally parsed for syntax errors.
"""

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_PS1 = REPO_ROOT / "install.ps1"
LAUNCHERS = (REPO_ROOT / "Download-Video.cmd", REPO_ROOT / "Watch-Clipboard.cmd")


def _code_lines(path):
    """Non-comment lines of a PowerShell script (# comments only)."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


class InstallPs1VenvTests(unittest.TestCase):
    def setUp(self):
        self.code = _code_lines(INSTALL_PS1)
        self.text = "\n".join(self.code)

    def test_never_installs_into_the_user_site(self):
        self.assertNotIn("--user", self.text)

    def test_system_python_is_only_used_to_create_the_venv(self):
        uses = [line for line in self.code if "& $PyExe @PyArgs" in line]
        for line in uses:
            with self.subTest(line=line):
                self.assertTrue(
                    "-m venv" in line or "import sys" in line,
                    "the system Python may only probe its version or create the venv",
                )
        self.assertTrue(any("-m venv $VenvDir" in line for line in uses))

    def test_venv_lives_under_localappdata_mpv_config(self):
        self.assertIn('$DataDir = Join-Path $DataRoot "mpv-config"', self.text)
        self.assertIn('$VenvDir = Join-Path $DataDir "venv"', self.text)
        self.assertIn('$VenvPython = Join-Path $VenvDir "Scripts\\python.exe"', self.text)
        self.assertRegex(self.text, r"\$env:LOCALAPPDATA")

    def test_pip_and_the_installer_run_with_the_venv_python(self):
        self.assertRegex(self.text, r"& \$VenvPython -m pip install --quiet --editable \.")
        self.assertRegex(self.text, r"& \$VenvPython -m mpv_config install @ForwardedArgs")
        self.assertNotRegex(self.text, r"\$PyExe @PyArgs -m (pip|mpv_config)")

    def test_cli_shim_points_into_the_venv_without_an_absolute_path(self):
        self.assertIn('"%~dp0..\\venv\\Scripts\\mpv-config.exe" %*', self.text)

    @unittest.skipUnless(shutil.which("pwsh"), "pwsh not installed")
    def test_script_parses(self):
        command = (
            "$errors = $null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            "$env:MPV_PS1_UNDER_TEST, [ref]$null, [ref]$errors) | Out-Null; "
            "if ($errors) { $errors | ForEach-Object { $_.ToString() }; exit 1 }"
        )
        result = subprocess.run(
            [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command", command],
            env={**os.environ, "MPV_PS1_UNDER_TEST": str(INSTALL_PS1)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class WindowsLaunchersTests(unittest.TestCase):
    def test_launchers_prefer_the_venv_python(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                text = launcher.read_text(encoding="utf-8")
                self.assertIn(
                    r'set "MPV_CONFIG_PY=%LOCALAPPDATA%\mpv-config\venv\Scripts\python.exe"', text
                )
                self.assertIn('if not exist "%MPV_CONFIG_PY%" set "MPV_CONFIG_PY=python"', text)
                self.assertRegex(text, r'(?m)^"%MPV_CONFIG_PY%" -m mpv_config\.cli\.main download')
                self.assertIsNone(re.search(r"(?m)^python -m mpv_config", text))


if __name__ == "__main__":
    unittest.main()
