import os
import shutil
import subprocess
import unittest

from deploy.deployer import _patch_mpv_conf
from deploy.detector import Environment


def _parse_conf(filepath):
    """Parse global key-value settings from an mpv-style configuration file."""
    settings = {}
    if not os.path.isfile(filepath):
        return settings
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                break
            if "=" in line:
                k, v = line.split("=", 1)
                settings[k.strip()] = v.strip()
            else:
                settings[line.strip()] = "yes"
    return settings


class TestConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.template_file = os.path.join(cls.repo_root, "config", "mpv.conf.template")
        cls.uosc_template = os.path.join(cls.repo_root, "config", "script-opts", "uosc.conf")
        cls.input_template = os.path.join(cls.repo_root, "config", "input.conf.template")
        cls.ytdl_sub_menu = os.path.join(cls.repo_root, "scripts", "ytdl-sub-menu.lua")

        cls.appdata = os.environ.get("APPDATA")
        cls.active_mpv_conf = (
            os.path.join(cls.appdata, "mpv", "mpv.conf") if cls.appdata else None
        )
        cls.active_uosc_conf = (
            os.path.join(cls.appdata, "mpv", "script-opts", "uosc.conf") if cls.appdata else None
        )
        cls.active_user_conf = (
            os.path.join(cls.appdata, "mpv", "mpv.conf.user") if cls.appdata else None
        )
        cls.active_input_conf = (
            os.path.join(cls.appdata, "mpv", "input.conf") if cls.appdata else None
        )

        cls.expected_sub_rules = {
            "sub-fix-timing": "yes",
            "sub-ass-override": "force",
            "sub-ass-force-margins": "yes",
            "sub-ass-vsfilter-aspect-compat": "no",
            "sub-ass-vsfilter-blur-compat": "no",
            "demuxer-mkv-subtitle-preroll": "yes",
        }

    def test_template_volume_max_is_200(self):
        settings = _parse_conf(self.template_file)
        self.assertIn("volume-max", settings)
        self.assertEqual(settings["volume-max"], "200")

    def test_template_subtitle_timing_and_sanitation(self):
        settings = _parse_conf(self.template_file)
        for param, expected in self.expected_sub_rules.items():
            self.assertIn(param, settings, f"Missing subtitle timing param: {param}")
            self.assertEqual(
                settings[param],
                expected,
                f"Subtitle parameter {param} expected {expected}, got {settings[param]}",
            )

    def test_uosc_template_volume_max_is_200(self):
        settings = _parse_conf(self.uosc_template)
        self.assertIn("volume_max", settings)
        self.assertEqual(settings["volume_max"], "200")

    def test_uosc_controls_has_subtitles_and_audio(self):
        settings = _parse_conf(self.uosc_template)
        self.assertIn("controls", settings)
        controls_str = settings["controls"]
        controls_items = [item.strip() for item in controls_str.split(",")]
        self.assertIn("subtitles", controls_items, "controls must contain dedicated subtitles button")
        self.assertIn("audio", controls_items, "controls must contain dedicated audio button")

    def test_active_uosc_controls_has_subtitles_and_audio(self):
        if not self.active_uosc_conf or not os.path.isfile(self.active_uosc_conf):
            self.skipTest("Active %APPDATA%\\mpv\\script-opts\\uosc.conf not found")
        settings = _parse_conf(self.active_uosc_conf)
        self.assertIn("controls", settings)
        controls_str = settings["controls"]
        controls_items = [item.strip() for item in controls_str.split(",")]
        self.assertIn("subtitles", controls_items)
        self.assertIn("audio", controls_items)

    def test_ytdl_sub_menu_exists_and_syntax_valid(self):
        self.assertTrue(os.path.isfile(self.ytdl_sub_menu), "scripts/ytdl-sub-menu.lua does not exist")

        with open(self.ytdl_sub_menu, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("open-menu", content)
        self.assertIn("uosc", content)
        self.assertIn("fetch-sub", content)

        luac_bin = shutil.which("luac")
        mpv_bin = shutil.which("mpv")
        if luac_bin:
            res = subprocess.run([luac_bin, "-p", self.ytdl_sub_menu], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Lua syntax error: {res.stderr}")
        elif mpv_bin:
            try:
                res = subprocess.run(
                    [mpv_bin, "--no-config", "--idle=no", f"--scripts={self.ytdl_sub_menu}", "null://"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                combined = (res.stdout or "") + (res.stderr or "")
                self.assertNotIn("syntax error", combined.lower())
                self.assertNotIn("lua: error", combined.lower())
            except subprocess.TimeoutExpired:
                pass

    def test_input_conf_keybindings(self):
        with open(self.input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("script-binding uosc/subtitles", content)
        self.assertIn("script-binding ytdl_sub_menu/open", content)
        self.assertIn("script-binding uosc/audio", content)

        # Check Latin and Arabic twin bindings
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
        bindings = {}
        for line in lines:
            parts = line.split(None, 1)
            if len(parts) == 2:
                bindings[parts[0]] = parts[1]

        self.assertEqual(bindings.get("c"), "script-binding uosc/subtitles")
        self.assertEqual(bindings.get("ؤ"), "script-binding uosc/subtitles")
        self.assertEqual(bindings.get("Ctrl+c"), "script-binding ytdl_sub_menu/open")
        self.assertEqual(bindings.get("Ctrl+ؤ"), "script-binding ytdl_sub_menu/open")
        self.assertEqual(bindings.get("a"), "script-binding uosc/audio")
        self.assertEqual(bindings.get("ش"), "script-binding uosc/audio")

    def test_active_mpv_conf_volume_max_and_subtitles(self):
        if not self.active_mpv_conf or not os.path.isfile(self.active_mpv_conf):
            self.skipTest("Active %APPDATA%\\mpv\\mpv.conf not found")

        settings = _parse_conf(self.active_mpv_conf)
        self.assertIn("volume-max", settings)
        self.assertEqual(settings["volume-max"], "200")

        for param, expected in self.expected_sub_rules.items():
            self.assertIn(param, settings, f"Active config missing subtitle param: {param}")
            self.assertEqual(
                settings[param],
                expected,
                f"Active config param {param} expected {expected}, got {settings[param]}",
            )

    def test_active_uosc_conf_volume_max(self):
        if not self.active_uosc_conf or not os.path.isfile(self.active_uosc_conf):
            self.skipTest("Active %APPDATA%\\mpv\\script-opts\\uosc.conf not found")

        settings = _parse_conf(self.active_uosc_conf)
        self.assertIn("volume_max", settings)
        self.assertEqual(settings["volume_max"], "200")

    def test_active_mpv_conf_user_volume_max(self):
        if not self.active_user_conf or not os.path.isfile(self.active_user_conf):
            self.skipTest("Active %APPDATA%\\mpv\\mpv.conf.user not found")

        settings = _parse_conf(self.active_user_conf)
        if "volume-max" in settings:
            self.assertEqual(
                settings["volume-max"],
                "200",
                "mpv.conf.user has conflicting volume-max override",
            )

    def test_patched_deployment_preserves_volume_and_subtitles(self):
        import tempfile

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "mpv.conf")
            _patch_mpv_conf(
                self.template_file,
                dest,
                env,
                selected_profile="native",
                resolved_defaults={"hwdec": "d3d11va", "gpu_api": "d3d11"},
            )
            settings = _parse_conf(dest)
            self.assertEqual(settings.get("volume-max"), "200")
            for param, expected in self.expected_sub_rules.items():
                self.assertEqual(settings.get(param), expected)


if __name__ == "__main__":
    unittest.main()
