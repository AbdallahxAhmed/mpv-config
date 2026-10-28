import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from deploy.deployer import (
    REPO_ROOT,
    _migrate_input_conf,
    _migrate_mpv_conf,
    _migrate_uosc_topbar_patch,
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

            fake_xdg = Path(tmpdir) / "local_share"

            with patch.dict(os.environ, {"XDG_DATA_HOME": str(fake_xdg)}), \
                 patch("shutil.which", return_value="/usr/bin/fc-cache"), \
                 patch("subprocess.run") as mock_run:
                env = MagicMock()
                env.os = "linux"
                result = _sync_linux_uosc_fonts(str(config_dir), env=env)
                self.assertTrue(result)

                dest_dir = fake_xdg / "fonts" / "mpv-uosc"
                self.assertTrue((dest_dir / "uosc_icons.otf").is_file())
                self.assertTrue((dest_dir / "uosc_textures.ttf").is_file())
                mock_run.assert_called_once()
                self.assertIn(str(dest_dir), mock_run.call_args[0][0])

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
