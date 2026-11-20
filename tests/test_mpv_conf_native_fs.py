"""mpv.conf never carries native-fs: mpv documents --native-fs as macOS-only.

It used to be written as `native-fs = no` on Linux (spec 003, User Story 4),
where it has no effect; KDE/Wayland fullscreen state is kept in sync by mpv's
own Wayland backend. These tests render the real template per platform.
"""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy.deployer import _patch_mpv_conf
from deploy.detector import Environment

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "config" / "mpv.conf.template"

PLATFORMS = (
    ("linux wayland", dict(os="linux", distro="arch", platform_key="linux", display="wayland")),
    ("linux x11", dict(os="linux", distro="arch", platform_key="linux", display="x11")),
    ("windows", dict(os="windows", platform_key="windows")),
    ("macos", dict(os="macos", platform_key="macos")),
)


class MpvConfNativeFsTests(unittest.TestCase):
    def test_template_has_no_native_fs_option_or_placeholder(self):
        content = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("NATIVE_FS", content)
        self.assertIsNone(re.search(r"^\s*native-fs\s*=", content, re.M))

    def test_rendered_mpv_conf_has_no_native_fs_on_any_platform(self):
        for label, fields in PLATFORMS:
            with self.subTest(platform=label):
                env = Environment(gpu_vendor="nvidia", **fields)
                with (
                    tempfile.TemporaryDirectory() as tmpdir,
                    mock.patch("deploy.deployer._resolve_preferred_font", return_value="Tahoma"),
                ):
                    dest = os.path.join(tmpdir, "mpv.conf")
                    _patch_mpv_conf(
                        str(TEMPLATE),
                        dest,
                        env,
                        selected_profile="native",
                        resolved_defaults={"hwdec": "auto", "gpu_api": "vulkan"},
                    )
                    rendered = Path(dest).read_text(encoding="utf-8")
                self.assertNotIn("native-fs", rendered)
                self.assertNotIn("{{", rendered, "unfilled template placeholder")


if __name__ == "__main__":
    unittest.main()
