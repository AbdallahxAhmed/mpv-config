"""The Wayland refresh-rate pin follows the detected mode (audit 2026-11-20, 1.3).

The deployer detects the active display mode and hands it to
scripts/display_fps_guard.lua, which pins display-fps-override only while the
compositor reports that same rate. Its runtime behaviour is covered by
tests/lua/test_display_fps_guard.lua; these tests cover rendering and detection.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from deploy import deployer
from deploy.detector import Environment

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "config" / "mpv.conf.template"
PIN_LINE = "script-opts-append        = display_fps_guard-detected_fps="


def _render(env, detected):
    with (
        tempfile.TemporaryDirectory() as tmp,
        mock.patch.object(deployer, "_resolve_preferred_font", return_value="Tahoma"),
        mock.patch.object(deployer, "_detect_display_fps", return_value=detected) as detect,
        mock.patch.object(deployer, "ui"),
    ):
        dest = Path(tmp) / "mpv.conf"
        deployer._patch_mpv_conf(
            str(TEMPLATE), str(dest), env, "linux-like", {"gpu_api": "vulkan", "vo": "gpu-next"}
        )
        return dest.read_text(encoding="utf-8"), detect


def _env(**fields):
    base = dict(
        os="linux", distro="arch", platform_key="arch", display="wayland", gpu_vendor="nvidia"
    )
    base.update(fields)
    return Environment(**base)


class RenderTests(unittest.TestCase):
    def test_wayland_gets_the_detected_mode(self):
        for detected, expected in (("143.98", "143.98"), ("144.00", "144"), ("59.94", "59.94")):
            with self.subTest(detected=detected):
                text, _ = _render(_env(), detected)
                self.assertIn(PIN_LINE + expected + "\n", text)
                self.assertNotIn("{{", text)

    def test_no_pin_without_a_detected_mode(self):
        for detected in (None, "", "garbage"):
            with self.subTest(detected=detected):
                text, _ = _render(_env(), detected)
                self.assertNotIn("display_fps_guard", text)
                self.assertNotIn("{{", text)

    def test_no_pin_on_x11_windows_or_macos(self):
        for env in (
            _env(display="x11"),
            Environment(os="windows", platform_key="windows", gpu_vendor="nvidia"),
            Environment(os="macos", platform_key="macos"),
        ):
            with self.subTest(env=env.os, display=env.display):
                text, detect = _render(env, "143.98")
                self.assertNotIn("display_fps_guard", text)
                detect.assert_not_called()  # no probing where it cannot be used

    def test_the_verifier_checks_the_script_is_deployed(self):
        verifier = (REPO_ROOT / "deploy" / "verifier.py").read_text(encoding="utf-8")
        self.assertIn('"display_fps_guard",', verifier)
        self.assertTrue((REPO_ROOT / "scripts" / "display_fps_guard.lua").is_file())

    def test_nothing_forces_143_981_any_more(self):
        text, _ = _render(_env(), "120.00")
        self.assertNotIn("143.981", text)
        self.assertNotIn("[wayland-144hz-fix]", text)


class UpdateKeepsDetectedRateTests(unittest.TestCase):
    """mpv-config update with the monitor off keeps the previous refresh rate."""

    def regenerate(self, old_pin, detected, env=None):
        env = env or _env()
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "mpv"
            config.mkdir()
            with (
                mock.patch.object(deployer, "_resolve_preferred_font", return_value="Tahoma"),
                mock.patch.object(deployer, "_detect_display_fps") as detect,
                mock.patch.object(deployer, "ui") as ui,
            ):
                # the previous update ran with the monitor on and found old_pin
                detect.return_value = old_pin
                old = deployer._render_mpv_conf_text(
                    env, deployer.MPV_PROFILE_DEFAULT, deployer._infer_mpv_conf_choices("", env)
                )
                (config / "mpv.conf").write_text(old, encoding="utf-8")
                detect.reset_mock()
                detect.return_value = detected
                deployer._regenerate_mpv_conf(config, env, Path(tmp))
                new = (config / "mpv.conf").read_text(encoding="utf-8")
            return new, ui.warn.call_args_list, detect.call_count

    def test_monitor_off_keeps_the_previous_rate_and_warns_once(self):
        new, warnings, probes = self.regenerate("143.98", None)
        self.assertIn(PIN_LINE + "143.98\n", new)
        self.assertEqual(1, len(warnings))
        self.assertIn("143.98 Hz", warnings[0].args[0])
        self.assertEqual(1, probes)  # detected once, not once per trial render

    def test_a_detected_rate_replaces_the_old_one_silently(self):
        new, warnings, _ = self.regenerate("143.98", "119.88")
        self.assertIn(PIN_LINE + "119.88\n", new)
        self.assertNotIn(PIN_LINE + "143.98", new)
        self.assertEqual([], warnings)

    def test_nothing_to_keep_means_no_pin_and_no_warning(self):
        new, warnings, _ = self.regenerate(None, None)
        self.assertNotIn("display_fps_guard", new)
        self.assertEqual([], warnings)

    def test_x11_never_gets_a_pin(self):
        new, warnings, probes = self.regenerate("143.98", None, env=_env(display="x11"))
        self.assertNotIn("display_fps_guard", new)
        self.assertEqual(0, probes)


KSCREEN = (
    "\x1b[01;32mOutput: \x1b[0;0m1 DP-2 enabled connected\n"
    "\tModes:  1:1920x1080@60.00  2:1920x1080@143.98*!  3:1920x1080@119.88\n"
)
XRANDR_XWAYLAND = "DP-2 connected 1920x1080+0+0\n   1920x1080     59.96*+\n"


class DetectionTests(unittest.TestCase):
    def detect(self, display, outputs):
        def run(cmd, **_kwargs):
            if cmd[0] not in outputs:
                raise FileNotFoundError(cmd[0])
            return SimpleNamespace(returncode=0, stdout=outputs[cmd[0]])

        with mock.patch.object(subprocess, "run", side_effect=run):
            return deployer._detect_display_fps(SimpleNamespace(os="linux", display=display))

    def test_kscreen_doctor_reports_the_active_mode_not_the_first(self):
        self.assertEqual("143.98", self.detect("wayland", {"kscreen-doctor": KSCREEN}))

    def test_on_wayland_the_compositor_tool_beats_xwayland_xrandr(self):
        both = {"kscreen-doctor": KSCREEN, "xrandr": XRANDR_XWAYLAND}
        self.assertEqual("143.98", self.detect("wayland", both))

    def test_on_x11_xrandr_answers(self):
        both = {"kscreen-doctor": KSCREEN, "xrandr": XRANDR_XWAYLAND}
        self.assertEqual("59.96", self.detect("x11", both))

    def test_no_tool_means_unknown(self):
        self.assertIsNone(self.detect("wayland", {}))


if __name__ == "__main__":
    unittest.main()
