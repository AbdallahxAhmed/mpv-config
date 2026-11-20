"""VRR display mode seeds smart_motion disabled so it cannot undo video-sync=audio.

scripts/smart_motion.lua sets video-sync=display-resample and interpolation at
runtime on local files. With --display-mode vrr the deployer writes
video-sync=audio / interpolation=no into a fresh mpv.conf, so a fresh
smart_motion.conf must say enabled=no. Existing script-opts are personal and
are only warned about.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import deployer
from deploy.detector import Environment

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_CONF = REPO_ROOT / "config" / "script-opts" / "smart_motion.conf"


def _enabled_lines(text):
    return [line for line in text.splitlines() if line.strip().startswith("enabled")]


class SeedSmartMotionConfTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="mpv-smart-motion-")
        self.addCleanup(self._tmp.cleanup)
        self.conf = Path(self._tmp.name) / "smart_motion.conf"
        shutil.copyfile(SHIPPED_CONF, self.conf)

    def test_shipped_conf_enables_smart_motion(self):
        self.assertEqual(_enabled_lines(SHIPPED_CONF.read_text(encoding="utf-8")), ["enabled=yes"])

    def test_vrr_fresh_conf_is_disabled_and_keeps_everything_else(self):
        before = self.conf.read_text(encoding="utf-8").splitlines()
        self.assertTrue(deployer._seed_smart_motion_conf(str(self.conf), "vrr", fresh=True))
        after = self.conf.read_text(encoding="utf-8").splitlines()
        self.assertEqual(_enabled_lines("\n".join(after)), ["enabled=no"])
        self.assertEqual(len(before), len(after))
        changed = [(b, a) for b, a in zip(before, after) if b != a]
        self.assertEqual(changed, [("enabled=yes", "enabled=no")])

    def test_vrr_fresh_conf_without_an_enabled_line_gets_one(self):
        self.conf.write_text("# comments only\n", encoding="utf-8")
        self.assertTrue(deployer._seed_smart_motion_conf(str(self.conf), "vrr", fresh=True))
        self.assertEqual(self.conf.read_text(encoding="utf-8"), "# comments only\nenabled=no\n")

    def test_other_display_modes_leave_the_conf_alone(self):
        original = self.conf.read_text(encoding="utf-8")
        for mode in ("fixed", "auto"):
            with self.subTest(mode=mode):
                self.assertFalse(deployer._seed_smart_motion_conf(str(self.conf), mode, fresh=True))
                self.assertEqual(self.conf.read_text(encoding="utf-8"), original)

    def test_vrr_existing_enabled_conf_is_preserved_and_warned_about(self):
        original = self.conf.read_text(encoding="utf-8")
        with mock.patch.object(deployer, "ui") as fake_ui:
            self.assertFalse(deployer._seed_smart_motion_conf(str(self.conf), "vrr", fresh=False))
        self.assertEqual(self.conf.read_text(encoding="utf-8"), original)
        fake_ui.warn.assert_called_once()
        self.assertIn("enabled=no", fake_ui.warn.call_args.args[0])

    def test_vrr_existing_disabled_conf_is_silent(self):
        self.conf.write_text("enabled=no\n", encoding="utf-8")
        with mock.patch.object(deployer, "ui") as fake_ui:
            self.assertFalse(deployer._seed_smart_motion_conf(str(self.conf), "vrr", fresh=False))
        fake_ui.warn.assert_not_called()


class DeploySmartMotionVrrTests(unittest.TestCase):
    """Runs the real deploy() into a scratch config directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="mpv-deploy-vrr-")
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
        home = str(tmp / "home")
        patches = (
            mock.patch.dict(
                os.environ,
                {
                    "HOME": home,
                    "XDG_DATA_HOME": os.path.join(home, "data"),
                    "XDG_CACHE_HOME": os.path.join(home, "cache"),
                    "XDG_CONFIG_HOME": os.path.join(home, "config"),
                },
            ),
            mock.patch.object(deployer, "_resolve_preferred_font", return_value="Tahoma"),
            # Font sync copies into the user font dir and runs fc-cache:
            # unrelated to smart_motion, slow, and never wanted from a test.
            mock.patch.object(deployer, "_sync_linux_uosc_fonts"),
            mock.patch.object(deployer, "_deploy_linux_fontconfig_conf"),
            mock.patch.object(deployer, "ui"),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _deploy(self, display_mode):
        results = deployer.deploy(
            str(self.staging), self.env, str(REPO_ROOT), display_mode=display_mode
        )
        self.assertFalse([r for r in results if r.get("status") == "failed"], results)
        return (self.config_dir / "script-opts" / "smart_motion.conf").read_text(encoding="utf-8")

    def _mpv_conf_video_sync(self):
        lines = (self.config_dir / "mpv.conf").read_text(encoding="utf-8").splitlines()
        return [line.split("=", 1)[1].strip() for line in lines if line.startswith("video-sync")]

    def test_fresh_vrr_install_disables_smart_motion(self):
        conf = self._deploy("vrr")
        self.assertEqual(_enabled_lines(conf), ["enabled=no"])
        self.assertEqual(self._mpv_conf_video_sync(), ["audio"])

    def test_fresh_fixed_install_keeps_smart_motion_enabled(self):
        conf = self._deploy("fixed")
        self.assertEqual(_enabled_lines(conf), ["enabled=yes"])
        self.assertEqual(self._mpv_conf_video_sync(), ["display-resample"])

    def test_vrr_keeps_an_existing_personal_smart_motion_conf(self):
        existing = self.config_dir / "script-opts" / "smart_motion.conf"
        existing.parent.mkdir(parents=True)
        existing.write_text("# mine\nenabled=yes\n", encoding="utf-8")
        conf = self._deploy("vrr")
        self.assertEqual(conf, "# mine\nenabled=yes\n")


if __name__ == "__main__":
    unittest.main()
