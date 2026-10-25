import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestSubBackdropToggle(unittest.TestCase):
    """The b/ب subtitle backdrop toggle: script-driven OSD with readable state.

    The old binding (`b cycle-values sub-back-color ...`) shows mpv's raw
    property feedback ("sub-back-color = #B3080808"). The toggle now lives in
    scripts/sub_backdrop.lua and shows "Subtitle backdrop: on/off". These
    tests pin the binding parity (en/ar), the script wiring, and the sync of
    the ON fallback color with the mpv.conf template styling.
    """

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "config" / "input.conf.template").read_text(encoding="utf-8")
        cls.script = (ROOT / "scripts" / "sub_backdrop.lua").read_text(encoding="utf-8")
        cls.mpv_conf = (ROOT / "config" / "mpv.conf.template").read_text(encoding="utf-8")
        cls.verifier = (ROOT / "deploy" / "verifier.py").read_text(encoding="utf-8")

    def test_en_binding_is_present_and_no_twin_remains(self):
        """The Latin binding stays; the only Arabic key is the documented
        bare shift-layer one (آ - Shift+B under Arabic).

        mpv matches the CHARACTER a key produces, so a twin only works
        while that layout is active. The bare shift-layer lines give the
        lam-alef actions a no-Ctrl route under Arabic (measured:
        Shift+B delivers آ); anything else Arabic-script is a regression.
        """
        template = self.template
        self.assertRegex(template, r"(?m)^b\s+script-binding sub_backdrop/toggle\s*$")
        self.assertRegex(template, r"(?m)^آ\s+script-binding sub_backdrop/toggle\s*$")
        active = [
            line.split(None, 1)[0]
            for line in template.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(
            sorted(k for k in active if any(ord(c) > 0x590 for c in k)),
            sorted(["أ", "’", "ٍ", "آ", "‘"]))

    def test_uppercase_sponsorblock_B_binding_untouched(self):
        self.assertIn("B        script-binding sponsorblock_upvote", self.template)
        self.assertIn("Ctrl+b   script-binding sponsorblock_downvote", self.template)

    def test_script_binds_keyless_toggle_without_cycle_values(self):
        self.assertIn('mp.add_key_binding(nil, "toggle"', self.script)
        self.assertNotIn("cycle-values sub-back-color", self.script)

    def test_script_uses_exact_round_trip_colors(self):
        self.assertIn('local OFF = "#00000000"', self.script)
        # print_color() in mpv emits #AARRGGBB, so #B3080808 == alpha 0xB3.
        self.assertIn('local ON_FALLBACK = "#B3080808"', self.script)

    def test_on_fallback_matches_mpv_conf_template(self):
        conf = re.search(r'^sub-back-color\s*=\s*"([^"]+)"', self.mpv_conf, re.MULTILINE)
        self.assertIsNotNone(conf)
        fallback = re.search(r'^local ON_FALLBACK = "([^"]+)"', self.script, re.MULTILINE)
        self.assertIsNotNone(fallback)
        self.assertEqual(conf.group(1), fallback.group(1))

    def test_verifier_checks_the_script(self):
        self.assertIn('"sub_backdrop",', self.verifier)

    def test_lua_suite_registered(self):
        harness = (ROOT / "tests" / "run_lua_tests.py").read_text(encoding="utf-8")
        self.assertIn('"test_sub_backdrop.lua"', harness)

    def test_quick_reference_documented_b(self):
        self.assertIn(
            "# │ b           │  Subtitle backdrop box on/off (Netflix look)     │",
            self.template,
        )

    def test_quick_reference_table_rows_align(self):
        # Every single-key row (F1..F8, letters, arrows, and the b row) must
        # keep the same box alignment. Rows containing astral-plane emoji are
        # excluded: those two SponsorBlock rows compensate for terminal emoji
        # width, so their codepoint length legitimately sits one char short.
        rows = [
            line
            for line in self.template.splitlines()
            if line.startswith("# │")
            and re.match(r"^# │ \S", line)
            and not re.search(r"[\U0001F000-\U0010FFFF]", line)
        ]
        self.assertGreater(len(rows), 10)
        widths = {len(line) for line in rows}
        self.assertEqual(
            1,
            len(widths),
            f"quick-reference box rows lost alignment: {sorted(widths)}",
        )


class TestMigrateInputConfSubBackdrop(unittest.TestCase):
    """Already-deployed machines must be repaired by migrate-input-conf."""

    def setUp(self):
        from deploy.deployer import _migrate_input_conf

        self._migrate_input_conf = _migrate_input_conf

    def test_rewrites_b_and_la_twin_cycle_values_to_script_binding(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            Path(conf_path).write_text(
                "# SponsorBlock voting — B = Block (Upvote), Ctrl+B = Downvote\n"
                "B        script-binding sponsorblock_upvote\n"
                "b    cycle-values sub-back-color \"#B3080808\" \"#00000000\"\n"
                "\n"
                "# Subtitle background box toggle — ب = b\n"
                "ب       cycle-values sub-back-color \"#B3080808\" \"#00000000\"\n",
                encoding="utf-8",
            )

            self.assertTrue(self._migrate_input_conf(conf_path))
            content = Path(conf_path).read_text(encoding="utf-8")

            self.assertNotIn("cycle-values sub-back-color", content)
            self.assertIn("b    script-binding sub_backdrop/toggle", content)
            self.assertIn("ب       script-binding sub_backdrop/toggle", content)
            self.assertIn("B        script-binding sponsorblock_upvote", content)
            # The deployer-owned comment gains the friendly-OSD note.
            self.assertIn('OSD shows "Subtitle backdrop: on/off"', content)

            # Idempotent: a second pass must not touch a repaired config.
            self.assertFalse(self._migrate_input_conf(conf_path))

    def test_rewrites_legacy_multi_codepoint_la_twin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            Path(conf_path).write_text(
                "# Subtitle background box toggle — لا = b\n"
                "لا       cycle-values sub-back-color \"#B3080808\" \"#00000000\"\n",
                encoding="utf-8",
            )

            self.assertTrue(self._migrate_input_conf(conf_path))
            content = Path(conf_path).read_text(encoding="utf-8")

            self.assertNotIn("لا", content)
            self.assertNotIn("cycle-values sub-back-color", content)
            self.assertIn("ب       script-binding sub_backdrop/toggle", content)
            # Rule 5 keeps the historical comment honest about the rebind.
            self.assertIn("# Subtitle background box toggle — ب = b", content)

    def test_unrelated_cycle_values_are_not_touched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            Path(conf_path).write_text(
                "F8 cycle-values af \"lavfi=[dynaudnorm=f=500:g=15:p=0.95:m=10],"
                "lavfi=[alimiter=limit=0.9:level=false]\" \"\"\n",
                encoding="utf-8",
            )

            self.assertTrue(self._migrate_input_conf(conf_path))
            content = Path(conf_path).read_text(encoding="utf-8")

            # F8 night mode stays byte-identical; only the backdrop toggle is
            # allowed to be rewritten to script-binding form.
            self.assertIn(
                'F8 cycle-values af "lavfi=[dynaudnorm=f=500:g=15:p=0.95:m=10],'
                'lavfi=[alimiter=limit=0.9:level=false]" ""',
                content,
            )
            # Rule 6 must never invent a script binding for other keys/CIFs:
            # no sub-back-color cycle-values line may appear; the sub_backdrop
            # lines here are the backup combo and its generated Arabic twin
            # Ctrl+آ (Ctrl+Shift+b under Arabic arrives as Ctrl+آ).
            self.assertNotIn("cycle-values sub-back-color", content)
            backdrops = [
                line
                for line in content.splitlines()
                if "sub_backdrop" in line
            ]
            self.assertTrue(backdrops)
            for line in backdrops:
                self.assertIn(
                    line.split(None, 2)[:2],
                    (["Ctrl+Shift+b", "script-binding"],
                     ["Ctrl+آ", "script-binding"],
                     ["آ", "script-binding"]),
                    "unexpected rewrite of unrelated binding: %r" % line,
                )


if __name__ == "__main__":
    unittest.main()
