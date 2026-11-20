"""Runtime values (paths, font names) must reach re.sub as literal text.

A replacement *string* is a template: re parses "\\U", "\\h", "\\g<..>" in it.
A Windows path such as C:\\Users\\Name\\... therefore raised "bad escape \\U" and a
fresh Windows install crashed in deploy() while writing keyboard_layout.conf
(CI: windows-latest, test_smart_motion_vrr). Dynamic values go through a
function replacement instead.
"""

import ast
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import deployer
from deploy.detector import Environment

REPO_ROOT = Path(__file__).resolve().parent.parent
LAYOUT_TEMPLATE = REPO_ROOT / "config" / "script-opts" / "keyboard_layout.conf.template"

# \U, \h, \A and \x are all invalid or meaningful regex escapes in a template.
WINDOWS_PATHS = (
    r"C:\Users\Name\AppData\Local\mpv-config\venv\Scripts\python.exe",
    r"C:\hostedtoolcache\windows\Python\3.12.7\x64\python.exe",
)


class FreshDeployWithWindowsInterpreterTests(unittest.TestCase):
    """Runs the real deploy() into a scratch config directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="mpv-deploy-winpath-")
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.staging = tmp / "staging"
        for folder, name in (("scripts", "x.lua"), ("shaders", "x.glsl"), ("fonts", "x.ttf")):
            (self.staging / folder).mkdir(parents=True)
            (self.staging / folder / name).write_text("x", encoding="utf-8")
        self.config_dir = tmp / "home" / "mpv"
        self.env = Environment(
            os="linux",
            distro="arch",
            platform_key="linux",
            display="wayland",
            gpu_vendor="nvidia",
            config_dir=str(self.config_dir),
        )
        home = tmp / "home"
        patches = (
            mock.patch.dict(
                os.environ,
                {
                    "HOME": str(home),
                    "XDG_DATA_HOME": str(home / "data"),
                    "XDG_CACHE_HOME": str(home / "cache"),
                    "XDG_CONFIG_HOME": str(home / "config"),
                },
            ),
            mock.patch.object(deployer, "_resolve_preferred_font", return_value="Tahoma"),
            mock.patch.object(deployer, "_sync_linux_uosc_fonts"),
            mock.patch.object(deployer, "_deploy_linux_fontconfig_conf"),
            mock.patch.object(deployer, "ui"),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_windows_interpreter_path_does_not_break_a_fresh_install(self):
        for exe in WINDOWS_PATHS:
            with self.subTest(exe=exe):
                shutil.rmtree(self.config_dir, ignore_errors=True)  # each run is a fresh install
                with mock.patch.object(deployer.sys, "executable", exe):
                    results = deployer.deploy(str(self.staging), self.env, str(REPO_ROOT))
                self.assertFalse([r for r in results if r.get("status") == "failed"], results)
                deployed = self.config_dir / "script-opts" / "keyboard_layout.conf"
                self.assertEqual(
                    LAYOUT_TEMPLATE.read_text(encoding="utf-8"),
                    deployed.read_text(encoding="utf-8"),
                )

    def test_no_removed_layout_guard_command_is_written(self):
        deployer.deploy(str(self.staging), self.env, str(REPO_ROOT))
        conf = (self.config_dir / "script-opts" / "keyboard_layout.conf").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("layout_guard", conf)
        self.assertNotIn("command=", conf)


class AutosubsyncHealingWindowsPathTests(unittest.TestCase):
    def test_windows_binary_paths_are_written_verbatim(self):
        paths = (
            r"C:\Users\Name\AppData\Roaming\mpv\tools\ffmpeg\bin\ffmpeg.exe",
            r"C:\Users\Name\.local\bin\ffsubsync.exe",
            r"C:\hostedtoolcache\alass\alass.exe",
        )
        env = Environment(os="windows", platform_key="windows")
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = Path(tmpdir) / "autosubsync.conf"
            conf.write_text(
                "ffmpeg_path=old\nffsubsync_path=old\nalass_path=old\nkeep=me\n", encoding="utf-8"
            )
            with mock.patch.object(deployer, "_resolve_autosubsync_paths", return_value=paths):
                self.assertTrue(deployer._migrate_autosubsync_conf(str(conf), env=env))
            lines = conf.read_text(encoding="utf-8").splitlines()
        self.assertEqual(f"ffmpeg_path={paths[0]}", lines[0])
        self.assertEqual(f"ffsubsync_path={paths[1]}", lines[1])
        self.assertEqual(f"alass_path={paths[2]}", lines[2])
        self.assertIn("keep=me", lines)


class FontMigrationLiteralNameTests(unittest.TestCase):
    def test_a_backslash_in_the_resolved_font_name_is_kept_literally(self):
        font = r"Odd\Unicode\h Font"
        env = Environment(os="linux", platform_key="arch", distro="arch")
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = Path(tmpdir) / "mpv.conf"
            conf.write_text('osd-font = "Segoe UI"\nsub-font = "Tahoma"\n', encoding="utf-8")
            with (
                mock.patch.object(deployer, "_resolve_preferred_font", return_value=font),
                mock.patch.object(deployer, "ui"),
            ):
                deployer._migrate_mpv_conf(str(conf), env=env)
            text = conf.read_text(encoding="utf-8")
        self.assertIn(f'osd-font = "{font}"', text)
        self.assertIn(f'sub-font = "{font}"', text)


class NoInlineFormattedReplacementTests(unittest.TestCase):
    """Guard: an f-string passed straight to re.sub/re.subn is the bug pattern."""

    def test_first_party_code_passes_no_f_string_as_a_replacement(self):
        files = subprocess.run(
            ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        ).stdout.split()
        if not files:
            self.skipTest("not a git checkout")
        offenders = []
        for name in files:
            if name.startswith((".agent/", ".agents/", ".specify/")):
                continue
            tree = ast.parse((REPO_ROOT / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in ("sub", "subn"):
                    continue
                is_re = isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                index = 1 if is_re else 0
                if len(node.args) > index and isinstance(node.args[index], ast.JoinedStr):
                    offenders.append(f"{name}:{node.lineno}")
        self.assertEqual([], offenders, "use a function replacement for runtime values")


if __name__ == "__main__":
    unittest.main()
