"""The plain-text subtitle font is chosen per OS and must have Arabic glyphs.

Windows ships Segoe UI and macOS Geeza Pro (both cover Arabic); Linux probes
fontconfig and only accepts a preferred font that has alef, lam and yeh.
"Noto Sans" was dropped from the candidates: it has no Arabic glyphs.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from deploy import deployer
from deploy.detector import Environment

TEMPLATE = Path(__file__).resolve().parent.parent / "config" / "mpv.conf.template"


def _fc(stdout_for):
    """A fake subprocess.run for fc-list/fc-match: stdout_for(argv) -> str."""

    def run(argv, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout_for(argv))

    return run


class ArabicProbeTests(unittest.TestCase):
    def test_every_probe_codepoint_must_be_covered(self):
        covered = {"0627", "0644"}  # no yeh
        run = _fc(lambda argv: "Font" if argv[1].rsplit("=", 1)[1] in covered else "")
        with mock.patch.object(subprocess, "run", side_effect=run):
            self.assertFalse(deployer._font_has_arabic("Font"))
        with mock.patch.object(subprocess, "run", side_effect=_fc(lambda argv: "Font")):
            self.assertTrue(deployer._font_has_arabic("Font"))

    def test_family_names_are_escaped_for_fontconfig(self):
        seen = []
        run = _fc(lambda argv: seen.append(argv[1]) or "x")
        with mock.patch.object(subprocess, "run", side_effect=run):
            deployer._font_has_arabic("Foo-Bar:Pro")
        self.assertTrue(seen[0].startswith("Foo\\-Bar\\:Pro:charset="))

    def test_noto_sans_is_no_longer_a_candidate(self):
        self.assertNotIn("Noto Sans", deployer.PREFERRED_FONTS)
        self.assertIn("Noto Sans", deployer.LEGACY_SUBTITLE_FONTS)


class LinuxResolutionTests(unittest.TestCase):
    env = Environment(os="linux", platform_key="arch", distro="arch")

    def resolve(self, installed, arabic, fc_match=""):
        with (
            mock.patch.object(deployer, "_probe_fc_list_families", return_value=installed),
            mock.patch.object(deployer, "_probe_font_has_regular_face", return_value=True),
            mock.patch.object(deployer, "_font_has_arabic", side_effect=lambda f: f in arabic),
            mock.patch.object(subprocess, "run", side_effect=_fc(lambda argv: fc_match)),
        ):
            return deployer._resolve_preferred_font(self.env)

    def test_a_preferred_font_without_arabic_is_skipped(self):
        font = self.resolve({"tahoma", "dejavu sans"}, arabic={"DejaVu Sans"})
        self.assertEqual("DejaVu Sans", font)

    def test_without_a_preferred_font_fontconfig_picks_an_arabic_one(self):
        font = self.resolve(
            {"liberation sans"}, arabic={"Noto Naskh Arabic"}, fc_match="Noto Naskh Arabic"
        )
        self.assertEqual("Noto Naskh Arabic", font)


class RenderedSubFontTests(unittest.TestCase):
    def render(self, env):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(deployer, "_resolve_preferred_font", return_value="DejaVu Sans"),
            mock.patch.object(deployer, "_detect_display_fps", return_value=None),
            mock.patch.object(deployer, "ui"),
        ):
            dest = Path(tmp) / "mpv.conf"
            deployer._patch_mpv_conf(str(TEMPLATE), str(dest), env, "native", {"gpu_api": "auto"})
            return dest.read_text(encoding="utf-8")

    def test_each_os_gets_its_arabic_capable_font(self):
        for env, font in (
            (Environment(os="windows", platform_key="windows"), "Segoe UI"),
            (Environment(os="macos", platform_key="macos"), "Geeza Pro"),
            (
                Environment(os="linux", platform_key="arch", distro="arch", display="x11"),
                "DejaVu Sans",
            ),
        ):
            with self.subTest(os=env.os):
                text = self.render(env)
                self.assertIn(f'sub-font                  = "{font}"\n', text)
                self.assertNotIn("{{SUB_FONT}}", text)


@unittest.skipUnless(
    subprocess.run(["which", "fc-list"], capture_output=True).returncode == 0, "no fontconfig"
)
class ThisMachineTests(unittest.TestCase):
    def test_the_font_resolved_here_really_has_arabic_glyphs(self):
        font = deployer._resolve_preferred_font(Environment(os="linux", platform_key="arch"))
        self.assertTrue(deployer._font_has_arabic(font), font)


if __name__ == "__main__":
    unittest.main()
