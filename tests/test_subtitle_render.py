"""Headless render check: our config leaves ASS styles and positions alone.

A sample ASS track (a typeset sign and Arabic dialogue with entities) is
rendered by real mpv with --vo=image (no window) using the mpv.conf a fresh
install writes. The frame must be pixel-identical to the same render with
sub-ass-override=no, i.e. libass drawing exactly what the author wrote.
sub-ass-override=force must differ, which proves the comparison is sensitive.
Skipped where mpv is not installed (CI only installs it for the Lua job).
"""

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import deployer
from deploy.detector import Environment

MPV = shutil.which("mpv")

SAMPLE_ASS = r"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans,44,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,40,1
Style: Sign,DejaVu Serif,60,&H0000FFFF,&H000000FF,&H00400000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 1,0:00:00.00,0:00:05.00,Sign,,0,0,0,,{\pos(200,130)\frz12}OPEN 24H
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,&rlm;مرحباً&nbsp;بك يا صديقي{\i1}!{\i0}\h&#x200F;
"""


def render_config_dir(root, env=None):
    """The mpv.conf a fresh install writes, in its own config dir."""
    env = env or Environment(
        os="linux", distro="arch", platform_key="arch", display="x11", gpu_vendor="nvidia"
    )
    with (
        mock.patch.object(deployer, "_resolve_preferred_font", return_value="DejaVu Sans"),
        mock.patch.object(deployer, "ui"),
    ):
        text = deployer._render_mpv_conf_text(
            env, deployer.MPV_PROFILE_DEFAULT, deployer._infer_mpv_conf_choices("", env)
        )
    config = Path(root) / "cfg"
    config.mkdir()
    (config / "mpv.conf").write_text(text, encoding="utf-8")
    return config


def render_frame(config_dir, sub_file, out_dir, *extra):
    """Render one frame with subtitles to a PNG; return the sha256 of its pixels."""
    out_dir = Path(out_dir)
    subprocess.run(
        [
            MPV,
            f"--config-dir={config_dir}",
            "--load-scripts=no",
            "--no-audio",
            "--ao=null",
            "--no-terminal",
            "--idle=no",
            "--keep-open=no",
            "--force-window=no",
            "--vo=image",
            "--vo-image-format=png",
            f"--vo-image-outdir={out_dir}",
            "--frames=1",
            f"--sub-file={sub_file}",
            *extra,
            "av://lavfi:color=c=0x505060:s=1280x720:d=2",
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    frames = sorted(out_dir.glob("*.png"))
    if not frames:
        raise AssertionError(f"mpv rendered no frame into {out_dir}")
    return hashlib.sha256(frames[0].read_bytes()).hexdigest()


@unittest.skipUnless(MPV, "mpv is not installed")
class AssRenderUnchangedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mpv-sub-render-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = render_config_dir(self.root)
        self.sub = self.root / "sample.ass"
        self.sub.write_text(SAMPLE_ASS, encoding="utf-8")

    def frame(self, name, *extra):
        return render_frame(self.config, self.sub, self.root / name, *extra)

    def test_our_config_draws_ass_exactly_as_authored(self):
        ours = self.frame("ours")
        authored = self.frame("authored", "--sub-ass-override=no")
        self.assertEqual(authored, ours, "the deployed config changed ASS styles or positions")

    def test_the_comparison_notices_a_style_override(self):
        authored = self.frame("authored", "--sub-ass-override=no")
        forced = self.frame("forced", "--sub-ass-override=force")
        self.assertNotEqual(authored, forced)


ARABIC_SRT = "1\n00:00:00,000 --> 00:00:02,000\nمرحباً بك يا صديقي، كيف حالك؟\n"


@unittest.skipUnless(MPV and shutil.which("fc-list"), "needs mpv and fontconfig")
class DeployedSubFontHasArabicTests(unittest.TestCase):
    """libass logs "Glyph 0x... not found" when the font lacks a character."""

    def test_the_deployed_sub_font_draws_arabic_without_fallback(self):
        with tempfile.TemporaryDirectory(prefix="mpv-sub-font-") as tmp:
            root = Path(tmp)
            env = Environment(os="linux", distro="arch", platform_key="arch", display="x11")
            with mock.patch.object(deployer, "ui"):
                text = deployer._render_mpv_conf_text(
                    env, deployer.MPV_PROFILE_DEFAULT, deployer._infer_mpv_conf_choices("", env)
                )
            (root / "cfg").mkdir()
            (root / "cfg" / "mpv.conf").write_text(text, encoding="utf-8")
            (root / "plain.srt").write_text(ARABIC_SRT, encoding="utf-8")
            log = root / "mpv.log"
            render_frame(
                root / "cfg",
                root / "plain.srt",
                root / "out",
                "--msg-level=all=no,sub/ass=v",
                f"--log-file={log}",
            )
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        font_lines = [line for line in lines if "fontselect" in line]
        self.assertTrue(font_lines, "libass did not report a font")
        self.assertEqual([], [line for line in lines if "not found" in line and "Glyph" in line])


class SubAssOverrideMigrationTests(unittest.TestCase):
    """A kept mpv.conf (--keep-conf) with the old template value is switched."""

    def migrate(self, line):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "mpv.conf"
            conf.write_text(f"volume = 100\n{line}\nsub-fix-timing = yes\n", encoding="utf-8")
            with mock.patch.object(deployer, "ui"):
                deployer._migrate_mpv_conf(str(conf))
            return conf.read_text(encoding="utf-8").splitlines()[1]

    def test_the_old_template_force_becomes_scale(self):
        for line in (
            "sub-ass-override = force",
            "sub-ass-override=force",
            "  sub-ass-override  =  force",
        ):
            with self.subTest(line=line):
                self.assertEqual("sub-ass-override          = scale", self.migrate(line).strip())

    def test_a_deliberate_choice_is_kept(self):
        for line in (
            "sub-ass-override           = no",
            "sub-ass-override = yes",
            "sub-ass-override=strip",
        ):
            with self.subTest(line=line):
                self.assertEqual(line, self.migrate(line))


if __name__ == "__main__":
    unittest.main()
