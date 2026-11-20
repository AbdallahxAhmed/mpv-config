"""Headless render check: our config leaves ASS styles and positions alone.

A sample ASS track (a typeset sign and Arabic dialogue with entities) is
rendered by real mpv with --vo=image (no window) using the mpv.conf a fresh
install writes. The frame must be pixel-identical to the same render with
sub-ass-override=no, i.e. libass drawing exactly what the author wrote.
sub-ass-override=force must differ, which proves the comparison is sensitive.
Skipped where mpv is not installed (CI only installs it for the Lua job).
"""

import hashlib
import os
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


def render_frame(config_dir, sub_file, out_dir, *extra, frames=1, env=None):
    """Render frames with subtitles to PNGs; return the sha256 of the last one."""
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
            f"--frames={frames}",
            f"--sub-file={sub_file}",
            *extra,
            "av://lavfi:color=c=0x505060:s=1280x720:d=2",
        ],
        capture_output=True,
        timeout=60,
        check=False,
        env=env,
    )
    rendered = sorted(out_dir.glob("*.png"))
    if not rendered:
        raise AssertionError(f"mpv rendered no frame into {out_dir}")
    return hashlib.sha256(rendered[-1].read_bytes()).hexdigest()


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


SANITIZER = Path(__file__).resolve().parent.parent / "scripts" / "sub_sanitizer.lua"
CLEANED_ASS = (
    SAMPLE_ASS.replace("&rlm;", "\u200f").replace("&nbsp;", "\u00a0").replace("&#x200F;", "\u200f")
)


@unittest.skipUnless(MPV, "mpv is not installed")
class SanitizedAssRenderTests(unittest.TestCase):
    """After the sanitizer swaps in its cleaned track, only the entities differ."""

    def test_the_cleaned_track_renders_like_a_hand_cleaned_file(self):
        with tempfile.TemporaryDirectory(prefix="mpv-sanitized-render-") as tmp:
            root = Path(tmp)
            config = render_config_dir(root)
            (root / "sample.ass").write_text(SAMPLE_ASS, encoding="utf-8")
            (root / "expected.ass").write_text(CLEANED_ASS, encoding="utf-8")
            (root / "tmp").mkdir()
            env = dict(os.environ, TMPDIR=str(root / "tmp"), TEMP=str(root / "tmp"))
            sanitized = render_frame(
                config,
                root / "sample.ass",
                root / "sanitized",
                f"--script={SANITIZER}",
                frames=20,
                env=env,
            )
            expected = render_frame(config, root / "expected.ass", root / "expected", frames=20)
            leftovers = [p.name for p in (root / "tmp").iterdir()]
        # identical pixels also prove the swap happened: unswapped, the
        # entities would be visible
        self.assertEqual(expected, sanitized)
        self.assertEqual([], leftovers, "temp files survived mpv quitting")


PROBE_LUA = """
mp.add_timeout(1.0, function()
  local text = mp.get_property("sub-text") or ""
  io.stderr:write("SUBTEXT|" .. (mp.get_property("current-tracks/sub/title") or "-") .. "|"
    .. text:gsub(".", function(c) return string.format("%02x", c:byte()) end) .. "\\n")
  mp.command("quit")
end)
"""
LINE = "&rlm;مرحباً بك&nbsp;يا صديقي"
SHOWN = "\u200fمرحباً بك\u00a0يا صديقي"


@unittest.skipUnless(MPV, "mpv is not installed")
class SanitizerEncodingTests(unittest.TestCase):
    """What mpv actually shows after the sanitizer cleaned a legacy-encoded file."""

    def shown(self, encoded):
        with tempfile.TemporaryDirectory(prefix="mpv-sanitizer-enc-") as tmp:
            root = Path(tmp)
            (root / "tmp").mkdir()
            sub = root / "arabic.srt"
            sub.write_bytes(encoded)
            probe = root / "probe.lua"
            probe.write_text(PROBE_LUA, encoding="utf-8")
            proc = subprocess.run(
                [
                    MPV,
                    "--no-config",
                    "--load-scripts=no",
                    f"--script={SANITIZER}",
                    f"--script={probe}",
                    "--no-audio",
                    "--ao=null",
                    "--vo=null",
                    "--no-terminal",
                    "--idle=no",
                    f"--sub-file={sub}",
                    "av://lavfi:color=s=320x240:d=3",
                ],
                capture_output=True,
                timeout=60,
                check=False,
                env=dict(os.environ, TMPDIR=str(root / "tmp"), TEMP=str(root / "tmp")),
            )
        line = next(out for out in proc.stderr.splitlines() if out.startswith(b"SUBTEXT|"))
        _, title, hexed = line.split(b"|", 2)
        return title.decode(), bytes.fromhex(hexed.decode()).decode("utf-8", "replace")

    def cue(self, text):
        return f"1\n00:00:00,000 --> 00:00:05,000\n{text}\n"

    def test_windows_1256_is_shown_correctly_after_cleaning(self):
        title, text = self.shown(self.cue(LINE).encode("cp1256"))
        self.assertTrue(title.endswith("[cleaned]"), title)
        self.assertEqual(SHOWN, text)

    def test_utf16_is_shown_correctly_after_cleaning(self):
        title, text = self.shown(self.cue(LINE).encode("utf-16"))
        self.assertTrue(title.endswith("[cleaned]"), title)
        self.assertEqual(SHOWN, text)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
    def test_an_embedded_track_is_extracted_in_the_background_and_shown_clean(self):
        with tempfile.TemporaryDirectory(prefix="mpv-sanitizer-mkv-") as tmp:
            root = Path(tmp)
            (root / "tmp").mkdir()
            srt = root / "embedded.srt"
            srt.write_text(self.cue(LINE), encoding="utf-8")
            mkv = root / "episode.mkv"
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=s=320x240:d=3",
                    "-i",
                    str(srt),
                    "-map",
                    "0:v",
                    "-map",
                    "1",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:s",
                    "srt",
                    str(mkv),
                ],
                check=True,
                timeout=60,
            )
            probe = root / "probe.lua"
            probe.write_text(PROBE_LUA, encoding="utf-8")
            proc = subprocess.run(
                [
                    MPV,
                    "--no-config",
                    "--load-scripts=no",
                    f"--script={SANITIZER}",
                    f"--script={probe}",
                    "--no-audio",
                    "--ao=null",
                    "--vo=null",
                    "--no-terminal",
                    "--idle=no",
                    "--sid=1",
                    str(mkv),
                ],
                capture_output=True,
                timeout=60,
                check=False,
                env=dict(os.environ, TMPDIR=str(root / "tmp"), TEMP=str(root / "tmp")),
            )
            leftovers = [p.name for p in (root / "tmp").iterdir()]
        line = next(out for out in proc.stderr.splitlines() if out.startswith(b"SUBTEXT|"))
        _, title, hexed = line.split(b"|", 2)
        self.assertTrue(title.decode().endswith("[cleaned]"), title)
        self.assertEqual(SHOWN, bytes.fromhex(hexed.decode()).decode("utf-8"))
        self.assertEqual([], leftovers)


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


def band_brightness(png):
    """Mean luma (0-255) inside the subtitle line of a 1280x720 frame (rows 647-683)."""
    raw = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            str(png),
            "-vf",
            "crop=400:36:440:647,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    return sum(raw) / len(raw)


BACKDROP = Path(__file__).resolve().parent.parent / "scripts" / "sub_backdrop.lua"


@unittest.skipUnless(MPV and shutil.which("ffmpeg"), "needs mpv and ffmpeg")
class BackdropToggleTests(unittest.TestCase):
    """The real b toggle (sub_backdrop.lua), pressed 0, 1 or 2 times at file load."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mpv-backdrop-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = render_config_dir(self.root)
        self.srt = self.root / "plain.srt"
        self.srt.write_text(ARABIC_SRT, encoding="utf-8")

    def press(self, times):
        """Render with the toggle pressed `times` times; return (hash, brightness)."""
        driver = self.root / f"press{times}.lua"
        driver.write_text(
            'mp.register_event("file-loaded", function()\n'
            f"  for _ = 1, {times} do mp.commandv('script-binding', 'sub_backdrop/toggle') end\n"
            "end)\n",
            encoding="utf-8",
        )
        out = self.root / f"pressed{times}"
        digest = render_frame(
            self.config, self.srt, out, f"--script={BACKDROP}", f"--script={driver}", frames=10
        )
        return digest, band_brightness(sorted(out.glob("*.png"))[-1])

    def test_off_is_pixel_identical_to_the_default_look(self):
        default = render_frame(self.config, self.srt, self.root / "plain", frames=10)
        explicit = render_frame(
            self.config,
            self.srt,
            self.root / "explicit",
            "--sub-border-style=outline-and-shadow",
            "--sub-back-color=#B3080808",
            frames=10,
        )
        off, _ = self.press(0)
        self.assertEqual(default, off)
        self.assertEqual(explicit, off)

    def test_on_draws_the_box_and_off_again_restores_the_default(self):
        off, off_brightness = self.press(0)
        on, on_brightness = self.press(1)
        back, _ = self.press(2)
        self.assertNotEqual(off, on)
        self.assertGreater(off_brightness - on_brightness, 15.0, "no visible box when on")
        self.assertEqual(off, back)


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
