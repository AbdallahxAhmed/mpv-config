"""Tests for spec 006 P1 and P2: player UI appearance configuration, deployment, and guard."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from deploy import deployer
from tests.test_deploy_uosc_reorder_patch import DeployerTestCase, REPO_ROOT
from tools import check_uosc_release


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


class UIAppearanceGuardTests(unittest.TestCase):
    def test_read_looks_keys_returns_four_tables(self):
        looks_lua = REPO_ROOT / "scripts" / "modules" / "looks.lua"
        owned, color, opacity, bindings = check_uosc_release.read_looks_keys(looks_lua)
        self.assertEqual(11, len(owned))
        self.assertIn("controls", owned)
        self.assertIn("progress_size", owned)
        self.assertEqual(10, len(color))
        self.assertIn("foreground", color)
        self.assertIn("heatmap", color)
        self.assertEqual(19, len(opacity))
        self.assertIn("timeline", opacity)
        self.assertIn("heatmap", opacity)
        self.assertEqual(5, len(bindings))
        self.assertIn("shuffle", bindings)
        self.assertIn("menu-blurred", bindings)

    def test_check_options_on_committed_fixture(self):
        fixture_path = REPO_ROOT / "tests" / "fixtures" / "uosc-5.13.0" / "uosc-options.json"
        self.assertTrue(fixture_path.is_file(), f"{fixture_path} missing")
        facts = json.loads(fixture_path.read_text(encoding="utf-8"))
        owned, color, opacity, bindings = check_uosc_release.read_looks_keys()
        problems = check_uosc_release.check_options(facts, owned, color, opacity, bindings)
        self.assertEqual([], problems)

    def test_check_options_missing_keys_and_handler(self):
        facts = {
            "uosc_version": "5.13.0",
            "options": {"progress_size": "2"},
            "color": {"heatmap": "00adee"},
            "opacity": {},
            "runtime_handler": True,
            "bindings": ["menu-blurred"],
        }
        # progress_size removed
        facts_no_opt = copy.deepcopy(facts)
        facts_no_opt["options"].pop("progress_size")
        problems = check_uosc_release.check_options(facts_no_opt, ["progress_size"], [], [], [])
        self.assertEqual(["uosc 5.13.0: option progress_size missing"], problems)

        # color.heatmap removed
        facts_no_color = copy.deepcopy(facts)
        facts_no_color["color"].pop("heatmap")
        problems = check_uosc_release.check_options(facts_no_color, [], ["heatmap"], [], [])
        self.assertEqual(["uosc 5.13.0: color heatmap missing"], problems)

        # binding menu-blurred removed
        facts_no_binding = copy.deepcopy(facts)
        facts_no_binding["bindings"].remove("menu-blurred")
        problems = check_uosc_release.check_options(facts_no_binding, [], [], [], ["menu-blurred"])
        self.assertEqual(["uosc 5.13.0: binding menu-blurred missing"], problems)

        # runtime_handler: false
        facts_no_handler = copy.deepcopy(facts)
        facts_no_handler["runtime_handler"] = False
        problems = check_uosc_release.check_options(facts_no_handler, [], [], [], [])
        self.assertEqual(["uosc 5.13.0: runtime option handler missing"], problems)

    def test_check_menu_constants(self):
        menu_path = REPO_ROOT / "tests" / "fixtures" / "uosc-5.13.0" / "elements" / "Menu.lua"
        menu_lua = menu_path.read_bytes()
        problems = check_uosc_release.check_menu_constants(menu_lua)
        self.assertEqual([], problems)

        const = "(item.active and 0.8 or 0) + (is_selected and 0.15 or 0)"
        broken = menu_lua.replace(const.encode("utf-8"), b"")
        problems = check_uosc_release.check_menu_constants(broken)
        self.assertEqual([f'uosc 5.13.0: menu constant "{const}" missing'], problems)

    def test_extract_uosc_facts_on_synthetic_snippet(self):
        snippet = b"""
defaults = {
    timeline_size = 40,
    controls = 'menu',
}

local config_defaults = {
    color = {
        foreground = serialize_rgba('ffffff').color,
    },
    opacity = {
        timeline = 0.9,
    },
}

opt.read_options(options, 'uosc', handle_options)

bind_command('menu-blurred', function() end)
bind_command('shuffle', function() end)
"""
        facts = check_uosc_release.extract_uosc_facts(snippet, "5.13.0")
        self.assertEqual("5.13.0", facts["uosc_version"])
        self.assertEqual(hashlib.sha256(snippet).hexdigest(), facts["main_lua_sha256"])
        self.assertTrue(facts["runtime_handler"])
        self.assertEqual({"timeline_size": "40", "controls": "'menu'"}, facts["options"])
        self.assertEqual({"foreground": "ffffff"}, facts["color"])
        self.assertEqual({"timeline": "0.9"}, facts["opacity"])
        self.assertEqual(["menu-blurred", "shuffle"], facts["bindings"])

    def test_extract_uosc_facts_missing_defaults_raises_check_error(self):
        snippet = b"local x = 1\n"
        with self.assertRaises(check_uosc_release.CheckError) as ctx:
            check_uosc_release.extract_uosc_facts(snippet, "5.13.0")
        self.assertIn("defaults block not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
