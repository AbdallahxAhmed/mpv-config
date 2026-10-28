import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy.deployer import (
    PREFERRED_FONTS,
    _get_linux_visual_tuning_block,
    _migrate_mpv_conf,
    _pick_preferred_font,
    _resolve_preferred_font,
)
from deploy.detector import Environment


class TestFontPriority(unittest.TestCase):
    def test_pick_preferred_font_respects_rank_order(self):
        # Case 1: Tahoma is present
        self.assertEqual(
            _pick_preferred_font(["Noto Sans", "Segoe UI", "Tahoma"]),
            "Tahoma",
        )
        # Case 2: Tahoma absent, Segoe UI present
        self.assertEqual(
            _pick_preferred_font(["DejaVu Sans", "Noto Sans Arabic", "Segoe UI"]),
            "Segoe UI",
        )
        # Case 3: Tahoma and Segoe UI absent, Noto Sans Arabic present
        self.assertEqual(
            _pick_preferred_font(["DejaVu Sans", "Noto Sans", "Noto Sans Arabic"]),
            "Noto Sans Arabic",
        )
        # Case 4: None of the preferred fonts match
        self.assertEqual(
            _pick_preferred_font(["CustomFont", "Arial"]),
            PREFERRED_FONTS[0],
        )

    def test_resolve_preferred_font_on_windows_returns_tahoma(self):
        env = Environment(os="windows", platform_key="windows")
        self.assertEqual(_resolve_preferred_font(env), "Tahoma")

    def test_resolve_preferred_font_on_linux_queries_fc_list(self):
        env = Environment(os="linux", platform_key="arch", distro="arch")
        with mock.patch(
            "deploy.deployer._probe_fc_list_families",
            return_value={"noto sans arabic", "dejavu sans"},
        ):
            self.assertEqual(_resolve_preferred_font(env), "Noto Sans Arabic")

    def test_get_linux_visual_tuning_block_embeds_font(self):
        block = _get_linux_visual_tuning_block("Noto Sans Arabic")
        self.assertIn('osd-font="Noto Sans Arabic"', block)
        self.assertIn('sub-font="Noto Sans Arabic"', block)

    def test_migrate_mpv_conf_updates_managed_font_on_linux(self):
        env = Environment(os="linux", platform_key="arch", distro="arch")
        sample_conf = """# mpv.conf
osd-font="DejaVu Sans"
sub-font="DejaVu Sans"
sub-font-size=36
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = Path(tmpdir) / "mpv.conf"
            conf_path.write_text(sample_conf, encoding="utf-8")

            with mock.patch("deploy.deployer._resolve_preferred_font", return_value="Tahoma"):
                migrated = _migrate_mpv_conf(str(conf_path), env=env)
                self.assertTrue(migrated)

                content = conf_path.read_text(encoding="utf-8")
                self.assertIn('osd-font="Tahoma"', content)
                self.assertIn('sub-font="Tahoma"', content)

    def test_migrate_mpv_conf_preserves_custom_font(self):
        env = Environment(os="linux", platform_key="arch", distro="arch")
        sample_conf = """# mpv.conf
osd-font="MyCustomFont"
sub-font="Amiri"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = Path(tmpdir) / "mpv.conf"
            conf_path.write_text(sample_conf, encoding="utf-8")

            with mock.patch("deploy.deployer._resolve_preferred_font", return_value="Tahoma"):
                migrated = _migrate_mpv_conf(str(conf_path), env=env)
                self.assertFalse(migrated)

                content = conf_path.read_text(encoding="utf-8")
                self.assertIn('osd-font="MyCustomFont"', content)
                self.assertIn('sub-font="Amiri"', content)


if __name__ == "__main__":
    unittest.main()
