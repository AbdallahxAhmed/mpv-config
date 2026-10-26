# -*- coding: utf-8 -*-
"""Unit tests for AutoHotkey dependency and Arabic scan-code layout helper."""

import os
import re
import tempfile
import unittest

from deploy.registry import SYSTEM_DEPS


class TestAutoHotkeyIntegration(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.ahk_script_path = os.path.join(self.repo_root, "tools", "mpv_arabic_layout.ahk")
        self.input_conf_path = os.path.join(self.repo_root, "config", "input.conf.template")
        self.smartskip_conf_path = os.path.join(
            self.repo_root, "config", "script-opts", "SmartSkip.conf"
        )

    def test_autohotkey_registered_in_system_deps(self):
        self.assertIn("autohotkey", SYSTEM_DEPS)
        win_info = SYSTEM_DEPS["autohotkey"].get("windows")
        self.assertIsNotNone(win_info)
        self.assertEqual(win_info.get("method"), "github_release_zip")
        self.assertEqual(win_info.get("repo"), "AutoHotkey/AutoHotkey")
        self.assertIn("AutoHotkey64.exe", win_info.get("bin_names", []))

    def test_ahk_script_exists_and_contains_scan_codes(self):
        self.assertTrue(os.path.isfile(self.ahk_script_path))
        with open(self.ahk_script_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check header requirements
        self.assertIn("#Requires AutoHotkey v2.0", content)
        self.assertIn("#SingleInstance Force", content)
        self.assertIn("WatchMpv", content)
        self.assertIn("IsArabic()", content)

        # Critical scan codes must be mapped with {Blind}
        # H (SC023), B (SC030), G (SC022), / (SC035)
        self.assertIn('SC023::Send("{Blind}h")', content)
        self.assertIn('SC030::Send("{Blind}b")', content)
        self.assertIn('SC022::Send("{Blind}g")', content)
        self.assertIn('SC035::Send("{Blind}/")', content)

    def test_smartskip_silence_skip_does_not_hijack_question_mark(self):
        with open(self.smartskip_conf_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"^silence_skip_keybind=(.+)$", content, re.MULTILINE)
        self.assertIsNotNone(match)
        value = match.group(1).strip()
        self.assertNotIn('"?"', value, "SmartSkip silence_skip must not hijack '?' from Help")
        self.assertNotIn('"؟"', value, "SmartSkip silence_skip must not hijack '؟' from Help")
        self.assertIn("ctrl+?", value)

    def test_input_conf_has_slash_ignore(self):
        with open(self.input_conf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(
            bool(re.search(r"^[ \t]*/[ \t]+ignore", content, re.MULTILINE)),
            "input.conf must contain '/ ignore' to prevent accidental volume drop",
        )

    def test_migrate_smartskip_conf_updates_silence_skip(self):
        from deploy.deployer import _migrate_smartskip_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "SmartSkip.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write('silence_skip_keybind=["?", "؟"]\n')
            migrated = _migrate_smartskip_conf(conf_path)
            self.assertTrue(migrated)
            with open(conf_path, "r", encoding="utf-8") as f:
                updated = f.read()
            self.assertIn('silence_skip_keybind=["ctrl+?"]', updated)

    def test_migrate_arabic_layout_ahk(self):
        from deploy.deployer import _migrate_arabic_layout_ahk

        with tempfile.TemporaryDirectory() as tmpdir:
            migrated = _migrate_arabic_layout_ahk(tmpdir)
            self.assertTrue(migrated)
            target = os.path.join(tmpdir, "tools", "mpv_arabic_layout.ahk")
            self.assertTrue(os.path.isfile(target))
            # Second call should be a no-op (idempotent)
            self.assertFalse(_migrate_arabic_layout_ahk(tmpdir))


if __name__ == "__main__":
    unittest.main()
