import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from deploy.deployer import (
    PREFERRED_FONTS,
    REPO_ROOT,
    _deploy_linux_fontconfig_conf,
    _migrate_input_conf,
    _migrate_mpv_conf,
    _migrate_uosc_topbar_patch,
    _pick_preferred_font,
    _probe_font_has_regular_face,
    _resolve_preferred_font,
    _sync_linux_uosc_fonts,
)
from mpv_config.layout_twins import generate as generate_twins


class TestLinuxUiUxFixes(unittest.TestCase):
    def test_mpv_conf_template_fonts_dir(self):
        template_file = os.path.join(REPO_ROOT, "config", "mpv.conf.template")
        self.assertTrue(os.path.isfile(template_file))
        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("osd-fonts-dir             = ~~/fonts", content)
        self.assertIn("sub-fonts-dir             = ~~/fonts", content)

    def test_input_conf_template_fast_close(self):
        template_file = os.path.join(REPO_ROOT, "config", "input.conf.template")
        self.assertTrue(os.path.isfile(template_file))
        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("CLOSE_WIN set window-minimized yes ; quit", content)
        self.assertIn("q         set window-minimized yes ; quit", content)
        self.assertIn("Q         set window-minimized yes ; quit-watch-later", content)

    def test_migrate_mpv_conf_adds_fonts_dir(self):
        sample_conf = (
            "# mpv.conf\n"
            "osc = no\n"
            "osd-border-color = #000000\n"
            "idle = yes\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = Path(tmpdir) / "mpv.conf"
            conf_path.write_text(sample_conf, encoding="utf-8")

            migrated = _migrate_mpv_conf(str(conf_path))
            self.assertTrue(migrated)

            updated = conf_path.read_text(encoding="utf-8")
            self.assertIn("osd-fonts-dir             = ~~/fonts", updated)
            self.assertIn("sub-fonts-dir             = ~~/fonts", updated)

            # Idempotent
            migrated_again = _migrate_mpv_conf(str(conf_path))
            self.assertFalse(migrated_again)

    def test_migrate_input_conf_updates_fast_close(self):
        sample_input = (
            "# input.conf\n"
            "CLOSE_WIN quit\n"
            "SPACE cycle pause\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.conf"
            input_path.write_text(sample_input, encoding="utf-8")

            migrated = _migrate_input_conf(str(input_path))
            self.assertTrue(migrated)

            updated = input_path.read_text(encoding="utf-8")
            self.assertIn("CLOSE_WIN        set window-minimized yes ; quit", updated)
            self.assertIn("q                set window-minimized yes ; quit", updated)
            self.assertIn("Q                set window-minimized yes ; quit-watch-later", updated)
            # Twin of q should be generated
            self.assertIn("ض set window-minimized yes ; quit", updated)

    def test_layout_twins_includes_arabic_q_twin(self):
        sample = "q   set window-minimized yes ; quit\n"
        twinned, _ = generate_twins(sample)
        self.assertIn("ض set window-minimized yes ; quit", twinned)

    def test_sync_linux_uosc_fonts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            fonts_dir = config_dir / "fonts"
            fonts_dir.mkdir(parents=True)
            (fonts_dir / "uosc_icons.otf").write_bytes(b"dummy font otf")
            (fonts_dir / "uosc_textures.ttf").write_bytes(b"dummy font ttf")

            fake_xdg_data = Path(tmpdir) / "local_share"
            fake_xdg_config = Path(tmpdir) / "config_home"

            with patch.dict(os.environ, {
                "XDG_DATA_HOME": str(fake_xdg_data),
                "XDG_CONFIG_HOME": str(fake_xdg_config),
            }), \
                 patch("shutil.which", return_value="/usr/bin/fc-cache"), \
                 patch("subprocess.run") as mock_run:
                env = MagicMock()
                env.os = "linux"
                result = _sync_linux_uosc_fonts(str(config_dir), env=env)
                self.assertTrue(result)

                dest_dir = fake_xdg_data / "fonts" / "mpv-uosc"
                self.assertTrue((dest_dir / "uosc_icons.otf").is_file())
                self.assertTrue((dest_dir / "uosc_textures.ttf").is_file())
                self.assertTrue(mock_run.called)

    def test_deploy_linux_fontconfig_conf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_config = Path(tmpdir) / "config_home"
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(fake_config)}), \
                 patch("shutil.which", return_value="/usr/bin/fc-cache"), \
                 patch("subprocess.run") as mock_run:
                env = MagicMock()
                env.os = "linux"
                deployed = _deploy_linux_fontconfig_conf(env=env)
                self.assertTrue(deployed)

                conf_file = fake_config / "fontconfig" / "conf.d" / "99-mpv-uosc.conf"
                self.assertTrue(conf_file.is_file())
                content = conf_file.read_text(encoding="utf-8")
                self.assertIn("<string>uosc_icons</string>", content)
                self.assertIn("<string>Material Icons Round</string>", content)
                self.assertIn("<string>uosc_textures</string>", content)
                self.assertIn("<string>Tahoma</string>", content)
                mock_run.assert_called_once()

                # Idempotent
                deployed_again = _deploy_linux_fontconfig_conf(env=env)
                self.assertFalse(deployed_again)

    def test_probe_font_has_regular_face_valid(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Tahoma|Regular,Normal|0|/path/to/tahoma.ttf",
            )
            self.assertTrue(_probe_font_has_regular_face("Tahoma"))

    def test_probe_font_has_regular_face_rejects_italic(self):
        with patch("subprocess.run") as mock_run:
            # Slant = 100
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Segoe UI|Italic|100|/path/to/segoeuii.ttf",
            )
            self.assertFalse(_probe_font_has_regular_face("Segoe UI"))

            # Style = Italic with slant 0
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Segoe UI|Italic|0|/path/to/segoeuii.ttf",
            )
            self.assertFalse(_probe_font_has_regular_face("Segoe UI"))

    def test_probe_font_has_regular_face_rejects_black(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Segoe UI,Segoe UI Black|Black,Regular|0|/path/to/seguibl.ttf",
            )
            self.assertFalse(_probe_font_has_regular_face("Segoe UI"))

    def test_probe_font_has_regular_face_rejects_family_mismatch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="DejaVu Sans|Regular|0|/path/to/dejavu.ttf",
            )
            self.assertFalse(_probe_font_has_regular_face("NonExistentFont"))

    def test_pick_preferred_font_with_validator(self):
        installed = {"Segoe UI", "Noto Sans Arabic"}
        # Segoe UI fails validator (e.g. only has italic)
        validator = lambda f: f != "Segoe UI"
        chosen = _pick_preferred_font(installed, validator=validator)
        self.assertEqual(chosen, "Noto Sans Arabic")

    def test_resolve_preferred_font_linux(self):
        env = MagicMock()
        env.os = "linux"
        with patch("deploy.deployer._probe_fc_list_families", return_value={"Segoe UI", "Tahoma"}), \
             patch("deploy.deployer._probe_font_has_regular_face") as mock_probe:
            # Both Tahoma and Segoe UI are probed; Tahoma has regular face
            mock_probe.side_effect = lambda f: f == "Tahoma"
            font = _resolve_preferred_font(env=env)
            self.assertEqual(font, "Tahoma")

        with patch("deploy.deployer._probe_fc_list_families", return_value={"Segoe UI", "Noto Sans"}), \
             patch("deploy.deployer._probe_font_has_regular_face") as mock_probe:
            # Tahoma not installed, Segoe UI lacks regular face, Noto Sans has regular
            mock_probe.side_effect = lambda f: f == "Noto Sans"
            font = _resolve_preferred_font(env=env)
            self.assertEqual(font, "Noto Sans")

    def test_migrate_uosc_topbar_patch(self):
        sample_topbar = (
            "function TopBar:new()\n"
            "\tlocal close = {icon = 'close', hover_bg = '2311e8', hover_fg = 'ffffff', command = function() mp.command('quit') end}\n"
            "\tlocal max = {icon = 'crop_square', command = maximized_command}\n"
            "\tlocal min = {icon = 'minimize', command = function() mp.command('cycle window-minimized') end}\n"
            "end\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            topbar_path = Path(tmpdir) / "TopBar.lua"
            topbar_path.write_text(sample_topbar, encoding="utf-8")

            migrated = _migrate_uosc_topbar_patch(str(topbar_path))
            self.assertTrue(migrated)

            updated = topbar_path.read_text(encoding="utf-8")
            self.assertIn("pcall(mp.set_property, 'window-minimized', 'yes')", updated)

            # Idempotent
            migrated_again = _migrate_uosc_topbar_patch(str(topbar_path))
            self.assertFalse(migrated_again)


if __name__ == "__main__":
    unittest.main()
