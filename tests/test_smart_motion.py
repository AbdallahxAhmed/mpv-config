import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestSmartMotion(unittest.TestCase):
    """Unit tests for the Intelligent Algorithmic Motion Controller (smart_motion.lua)."""

    @classmethod
    def setUpClass(cls):
        cls.script_path = ROOT / "scripts" / "smart_motion.lua"
        cls.conf_path = ROOT / "config" / "script-opts" / "smart_motion.conf"
        cls.input_template = ROOT / "config" / "input.conf.template"
        cls.verifier_path = ROOT / "deploy" / "verifier.py"

        cls.script_content = cls.script_path.read_text(encoding="utf-8")
        cls.conf_content = cls.conf_path.read_text(encoding="utf-8")
        cls.input_content = cls.input_template.read_text(encoding="utf-8")
        cls.verifier_content = cls.verifier_path.read_text(encoding="utf-8")

    def test_script_exists_and_declares_core_functions(self):
        self.assertTrue(self.script_path.is_file())
        self.assertIn("evaluate_motion_profile", self.script_content)
        self.assertIn("is_network_stream", self.script_content)
        self.assertIn("apply_profile", self.script_content)
        self.assertIn("smart_motion/toggle", self.input_content)

    def test_script_opts_config_defaults(self):
        self.assertTrue(self.conf_path.is_file())
        self.assertIn("enabled=yes", self.conf_content)
        self.assertIn("stream_web_parity=no", self.conf_content)
        self.assertIn("high_fps_threshold=50.0", self.conf_content)

    def test_input_conf_keybinding_registered(self):
        self.assertIn("Ctrl+Alt+m script-binding smart_motion/toggle", self.input_content)
        # Manual override hotkeys preserved
        self.assertIn("F4 cycle interpolation", self.input_content)
        self.assertIn("Shift+F4 cycle-values tscale", self.input_content)
        self.assertIn("Alt+t cycle-values tscale", self.input_content)

    def test_verifier_checks_smart_motion(self):
        self.assertIn('"smart_motion"', self.verifier_content)
        self.assertIn('"smart_motion.conf"', self.verifier_content)

    def test_lua_test_suite_registered(self):
        harness = (ROOT / "tests" / "run_lua_tests.py").read_text(encoding="utf-8")
        self.assertIn('"test_smart_motion.lua"', harness)


if __name__ == "__main__":
    unittest.main()
