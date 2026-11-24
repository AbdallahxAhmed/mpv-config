"""Tests for spec 006 P1: player UI appearance configuration and deployment."""

import unittest
from pathlib import Path

from deploy import deployer
from tests.test_deploy_uosc_reorder_patch import DeployerTestCase, REPO_ROOT


class UIAppearanceDeployerTests(DeployerTestCase):
    def deploy(self, **kwargs):
        return deployer.deploy(str(self.staging), self.env, str(REPO_ROOT), **kwargs)

    def test_fresh_install_has_shipped_ui_appearance_conf(self):
        self.stage(menu=None)
        self.deploy()
        target = self.config_dir / "script-opts" / "ui_appearance.conf"
        shipped = REPO_ROOT / "config" / "script-opts" / "ui_appearance.conf"
        self.assertTrue(target.is_file(), "script-opts/ui_appearance.conf was not created on fresh deploy")
        self.assertEqual(
            shipped.read_text(encoding="utf-8"),
            target.read_text(encoding="utf-8"),
        )

    def test_migrate_deployed_configs_seeds_missing_conf(self):
        conf_path = self.config_dir / "script-opts" / "ui_appearance.conf"
        self.assertFalse(conf_path.exists())
        results = deployer._migrate_deployed_configs(str(self.config_dir), self.env)
        self.assertTrue(conf_path.is_file(), "migration did not seed missing ui_appearance.conf")
        shipped = REPO_ROOT / "config" / "script-opts" / "ui_appearance.conf"
        self.assertEqual(
            shipped.read_text(encoding="utf-8"),
            conf_path.read_text(encoding="utf-8"),
        )
        rows = [r for r in results if r["name"] == "seed-ui-appearance-conf"]
        self.assertEqual(1, len(rows), "seed-ui-appearance-conf migration row not found")
        self.assertEqual("ok", rows[0]["status"])

    def test_migrate_deployed_configs_leaves_changed_conf_byte_identical(self):
        conf_path = self.config_dir / "script-opts" / "ui_appearance.conf"
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        custom_content = (
            "# Player look, chosen in More > Appearance. Values:\n"
            "# style=calm|bar|focus background=dark|black|slate accent=amber|teal|violet|rose|white size=comfortable|compact\n"
            "style=bar\n"
            "background=black\n"
            "accent=teal\n"
            "size=compact\n"
        )
        conf_path.write_text(custom_content, encoding="utf-8")
        results = deployer._migrate_deployed_configs(str(self.config_dir), self.env)
        self.assertEqual(
            custom_content,
            conf_path.read_text(encoding="utf-8"),
            "migration overwrote existing customized ui_appearance.conf",
        )
        rows = [r for r in results if r["name"] == "seed-ui-appearance-conf"]
        self.assertEqual(0, len(rows), "seed-ui-appearance-conf should not append a result when conf already exists")


class UIAppearanceTemplateTests(unittest.TestCase):
    def test_mpv_conf_template_has_startup_only_keys_after_osd_fonts_dir(self):
        template_path = REPO_ROOT / "config" / "mpv.conf.template"
        lines = template_path.read_text(encoding="utf-8").splitlines()
        osd_fonts_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("osd-fonts-dir"):
                osd_fonts_idx = i
                break
        self.assertNotEqual(-1, osd_fonts_idx, "osd-fonts-dir line not found in mpv.conf.template")
        self.assertEqual(
            "script-opts-append        = uosc-border_radius=10",
            lines[osd_fonts_idx + 1],
        )
        self.assertEqual(
            "script-opts-append        = uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80",
            lines[osd_fonts_idx + 2],
        )


if __name__ == "__main__":
    unittest.main()
