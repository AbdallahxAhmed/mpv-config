"""Offline unit tests for the layout twins generator."""
import importlib.util
import os
import re
import sys
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

# Load by file location: an editable install (deploy clone) may be a
# commit behind and already own the cached mpv_config package.
_spec = importlib.util.spec_from_file_location(
    "layout_twins_under_test",
    os.path.join(REPO, "src", "mpv_config", "layout_twins.py"))
layout_twins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout_twins)


class TwinLookupTests(unittest.TestCase):
    def test_known_letter_twins(self):
        """The bindings the shipped config relies on (probed on Arabic 101 & XKB ara)."""
        self.assertEqual(layout_twins._twin_for("c"), ("ؤ", ""))
        self.assertEqual(layout_twins._twin_for("a"), ("ش", ""))
        self.assertEqual(layout_twins._twin_for("n"), ("ى", ""))
        self.assertEqual(layout_twins._twin_for("?"), ("؟", ""))
        # Standard mpv keys
        self.assertEqual(layout_twins._twin_for("f"), ("ب", ""))
        self.assertEqual(layout_twins._twin_for("m"), ("ة", ""))
        self.assertEqual(layout_twins._twin_for("p"), ("ح", ""))
        self.assertEqual(layout_twins._twin_for("i"), ("ه", ""))
        self.assertEqual(layout_twins._twin_for("I"), ("÷", ""))
        self.assertEqual(layout_twins._twin_for("o"), ("خ", ""))
        self.assertEqual(layout_twins._twin_for("O"), ("×", ""))
        self.assertEqual(layout_twins._twin_for("v"), ("ر", ""))
        self.assertEqual(layout_twins._twin_for("j"), ("ت", ""))
        self.assertEqual(layout_twins._twin_for("J"), ("ـ", ""))
        self.assertEqual(layout_twins._twin_for("z"), ("ئ", ""))
        self.assertEqual(layout_twins._twin_for("x"), ("ء", ""))
        self.assertEqual(layout_twins._twin_for("["), ("ج", ""))
        self.assertEqual(layout_twins._twin_for("]"), ("د", ""))
        self.assertEqual(layout_twins._twin_for("s"), ("س", ""))
        self.assertEqual(layout_twins._twin_for("S"), ("ٍ", ""))

    def test_hardware_parity_twins(self):
        """h, g, b, G, B: on Linux XKB (and with AHK on Windows), each has a distinct
        single-character twin (h->ا, g->ل, b->ﻻ, B->ﻵ, G->ﻷ)."""
        self.assertEqual(layout_twins._twin_for("h"), ("ا", ""))
        self.assertEqual(layout_twins._twin_for("g"), ("ل", ""))
        self.assertEqual(layout_twins._twin_for("b"), ("ﻻ", ""))
        self.assertEqual(layout_twins._twin_for("B"), ("ﻵ", ""))
        self.assertEqual(layout_twins._twin_for("G"), ("ﻷ", ""))

    def test_modified_combo_twins(self):
        """Ctrl+Shift+<letter> under Arabic arrives as Ctrl+<the shift-layer
        Arabic char> - NOT a control code (user's capture shows 'Ctrl+أ'
        for Ctrl+Shift+H). The generator binds those events directly."""
        self.assertEqual(layout_twins._twin_for("Ctrl+Shift+h"), ("Ctrl+أ", ""))
        self.assertEqual(layout_twins._twin_for("Ctrl+Shift+H"), ("Ctrl+أ", ""))
        self.assertEqual(layout_twins._twin_for("Ctrl+Shift+m"), ("Ctrl+’", ""))
        self.assertEqual(layout_twins._twin_for("Ctrl+Shift+s"), ("Ctrl+ٍ", ""))
        # Ctrl+Shift+b emits both Windows (Ctrl+آ) and Linux XKB (Ctrl+ﻵ)
        twins, _ = layout_twins._twins_for("Ctrl+Shift+b")
        self.assertIn("Ctrl+آ", twins)
        self.assertIn("Ctrl+ﻵ", twins)
        self.assertEqual(layout_twins._twin_for("Ctrl+Shift+u"), ("Ctrl+‘", ""))

    def test_modified_twins_refuse_ascii(self):
        """Ctrl+Shift+l's Arabic half is plain '/' - binding Ctrl+/ could
        fire on US keystrokes, so it is refused."""
        twin, reason = layout_twins._twin_for("Ctrl+Shift+l")
        self.assertIsNone(twin)
        self.assertIn("US", reason)

    def test_plain_ctrl_gets_no_twin(self):
        """Plain Ctrl+<letter> arrives as a layout-independent control code
        on every layout - it needs no twin (and Alt delivery is
        unverified)."""
        for key in ("Ctrl+v", "Ctrl+c", "Alt+t"):
            self.assertIn(layout_twins._twin_for(key)[1],
                          ("control-code or unverified combo",))
            self.assertFalse(layout_twins._is_twinable(key), key)

    def test_ascii_twins_are_refused(self):
        """>/< shift to plain ASCII under Arabic - binding those would
        change US-layout behaviour (measured: Shift+. and . collide in
        mpv's binder)."""
        for key in (">", "<", "L", "D", "F"):
            twin, reason = layout_twins._twin_for(key)
            self.assertIsNone(twin, key)
            self.assertIn("US", reason)

    def test_modified_and_named_keys_have_no_twin(self):
        for key in ("Ctrl+v", "Alt+t", "F1", "RIGHT", "MBTN_RIGHT",
                    "Shift+RIGHT", "CLOSE_WIN"):
            self.assertFalse(layout_twins._is_twinable(key), key)

    def test_no_twin_is_typeable_on_the_us_layout(self):
        """A single-character twin reachable from the US layout must never
        be emitted: _validate has to refuse it (the shift table carries
        such entries on purpose, as documentation of the real layout)."""
        for table in (layout_twins.ARABIC_PLAIN, layout_twins.ARABIC_SHIFT):
            for key, twin in table.items():
                if len(twin) == 1 and twin in layout_twins.US_REACHABLE:
                    emitted, reason = layout_twins._twin_for(key)
                    self.assertIsNone(emitted, key)
                    self.assertIn("US", reason)

class GenerateTests(unittest.TestCase):
    MINI = """# comment line
c    script-binding uosc/subtitles
h    script-binding memo-history
g    script-binding sponsorblock_set_segment
b    script-binding sub_backdrop/toggle
Ctrl+c   ignored
F9   ignored
"""

    def test_emits_twins_and_report(self):
        text, report = layout_twins.generate(self.MINI)
        self.assertIn("ؤ script-binding uosc/subtitles", text)
        self.assertIn("# twin of c", text)
        self.assertIn("c    script-binding uosc/subtitles", text)
        # On Linux XKB (and with AHK on Windows), h/g/b have direct twins:
        self.assertIn("ا script-binding memo-history", text)
        self.assertIn("ل script-binding sponsorblock_set_segment", text)
        self.assertIn("ﻻ script-binding sub_backdrop/toggle", text)
        self.assertEqual(report, [])
        self.assertTrue(text.endswith("\n"))

    def test_idempotent(self):
        once, _ = layout_twins.generate(self.MINI)
        twice, _ = layout_twins.generate(once)
        self.assertEqual(once, twice)

    def test_replaces_previous_block(self):
        once, _ = layout_twins.generate(self.MINI)
        mutated = once.replace(
            "ؤ script-binding uosc/subtitles",
            "ؤ script-binding something-else")
        self.assertIn("something-else", mutated)
        refreshed, _ = layout_twins.generate(mutated)
        self.assertIn("ؤ script-binding uosc/subtitles", refreshed)
        self.assertNotIn("something-else", refreshed)

    def test_twin_colliding_with_user_binding_is_skipped(self):
        conf = self.MINI + "\nؤ script-binding user/own\n"
        text, report = layout_twins.generate(conf)
        self.assertIn(("c", "twin 'ؤ' already bound - skipped"), report)
        self.assertNotIn("ؤ script-binding uosc/subtitles", text)
        self.assertIn("ؤ script-binding user/own", text)

    def test_shipped_template_gets_the_expected_twins(self):
        """Pin the actual deployed bindings: standard mpv keys, scripts,
        and modified-combo twins across Windows 101 and Linux XKB ara."""
        path = os.path.join(REPO, "config", "input.conf.template")
        with open(path, "r", encoding="utf-8") as handle:
            base_text = handle.read()
        text, report = layout_twins.generate(base_text)
        for twin, command in [
            ("ؤ", "script-binding uosc/subtitles"),
            ("ش", "script-binding uosc/audio"),
            ("ى", "script-binding autosubsync-menu"),
            ("؟", "no-osd script-message-to help_overlay help"),
            ("Ctrl+أ", "script-binding memo-history"),
            ("Ctrl+’", "script-binding sponsorblock_set_segment"),
            ("Ctrl+ٍ", "script-binding sponsorblock_submit_segment"),
            ("Ctrl+آ", "script-binding sub_backdrop/toggle"),
            ("Ctrl+ﻵ", "script-binding sub_backdrop/toggle"),
            ("Ctrl+‘", "script-binding sponsorblock_upvote"),
            ("ا", "script-binding memo-history"),
            ("ل", "script-binding sponsorblock_set_segment"),
            ("ﻷ", "script-binding sponsorblock_submit_segment"),
            ("ﻻ", "script-binding sub_backdrop/toggle"),
            ("ﻵ", "script-binding sponsorblock_upvote"),
            ("ب", "cycle fullscreen"),
            ("ة", "cycle mute"),
            ("ح", "cycle pause"),
            ("ه", "script-binding stats/display-stats"),
            ("÷", "script-binding stats/display-stats-toggle"),
            ("خ", "show-progress"),
            ("×", "no-osd cycle-values osd-level 3 1"),
            ("ر", "cycle sub-visibility"),
            ("ت", "cycle sub"),
            ("ـ", "cycle sub down"),
            ("ئ", "add sub-delay -0.1"),
            ("ء", "add sub-delay +0.1"),
            ("ج", "multiply speed 1/1.1"),
            ("د", "multiply speed 1.1"),
            ("س", "screenshot"),
            ("ٍ", "screenshot video"),
        ]:
            self.assertIn("%s %s" % (twin, command), text)
        # the template's own bare shift-layer route is present and survives
        # generation untouched
        for glyph, command in [
            ("أ", "script-binding memo-history"),
            ("’", "script-binding sponsorblock_set_segment"),
            ("آ", "script-binding sub_backdrop/toggle"),
            ("‘", "script-binding sponsorblock_upvote"),
        ]:
            self.assertRegex(base_text,
                             r"(?m)^%s\s+%s$" % (glyph, re.escape(command)))
            self.assertEqual(
                len(re.findall(r"^%s[ \t]+%s$" % (glyph, re.escape(command)),
                               text, re.MULTILINE)), 1)
        reported = {key for key, _ in report}
        self.assertEqual(
            reported,
            {"Ctrl+Shift+v", "Ctrl+Shift+V"})

    def test_block_is_utf8_round_trip(self):
        text, _ = layout_twins.generate(self.MINI)
        text.encode("utf-8")


# A faithful miniature of the user's deployed input.conf: the legacy
# mnemonic twin block as shipped by the previous migration.
LEGACY_DEPLOYED = """# Subtitle background box toggle (Netflix / YouTube translucent box <-> transparent Cinema)
b    script-binding sub_backdrop/toggle

# ─── Arabic Bilingual Twin Bindings (Arabic 102 AZERTY layout) ────
# Ground truth, probed from the deployed keyboard layout (00000C01):
#   b → لا (lam+alef, TWO codepoints), f → ب, j → ت, l → م, p → ح.
# Subtitles menu (uosc) — ؤ = c
ؤ        script-binding uosc/subtitles

# History (memo) — ح = h (physical P in Arabic layout)
ح        script-binding memo-history

# Subtitle background box toggle — ب = b (physical F in Arabic layout)
ب       script-binding sub_backdrop/toggle

# SponsorBlock segment marking / submission — ت = g (physical J), م = G (physical L)
ت        script-binding sponsorblock_set_segment
م        script-binding sponsorblock_submit_segment

# Explicit Latin bindings for SponsorBlock segment marking
g        script-binding sponsorblock_set_segment
G        script-binding sponsorblock_submit_segment

c        script-binding uosc/subtitles
a        script-binding uosc/audio
h        script-binding memo-history
n        script-binding autosubsync-menu
? no-osd script-message-to help_overlay help
"""


class MigrationTests(unittest.TestCase):
    """_migrate_input_conf moves a legacy deployment onto the twins."""

    def _migrate(self, content):
        from deploy.deployer import _migrate_input_conf

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".conf", delete=False, encoding="utf-8")
        try:
            handle.write(content)
            handle.close()
            changed = _migrate_input_conf(handle.name)
            with open(handle.name, "r", encoding="utf-8") as stream:
                return changed, stream.read()
        finally:
            os.unlink(handle.name)

    def test_legacy_block_is_replaced_by_same_key_twins(self):
        changed, text = self._migrate(LEGACY_DEPLOYED)
        self.assertTrue(changed)
        # the mnemonic twins (other physical keys) are gone
        for glyph, command in [
            ("ح", "memo-history"), ("ت", "sponsorblock_set_segment"),
            ("م", "sponsorblock_submit_segment"), ("ب", "sub_backdrop"),
        ]:
            self.assertNotRegex(
                text, r"^%s[ \t]+.*%s" % (glyph, command))
        self.assertNotIn("Arabic Bilingual Twin Bindings", text)
        # the same-key twins are present, exactly once each, plus the
        # modified-combo twins; the template's bare shift-layer lines
        # (أ آ ’ ‘ ٍ) would be in deployed files too and survive
        for glyph, command in [
            ("ؤ", "script-binding uosc/subtitles"),
            ("ش", "script-binding uosc/audio"),
            ("ى", "script-binding autosubsync-menu"),
            ("؟", "no-osd script-message-to help_overlay help"),
            ("Ctrl+أ", "script-binding memo-history"),
            ("Ctrl+’", "script-binding sponsorblock_set_segment"),
            ("Ctrl+ٍ", "script-binding sponsorblock_submit_segment"),
            ("Ctrl+آ", "script-binding sub_backdrop/toggle"),
            ("Ctrl+‘", "script-binding sponsorblock_upvote"),
        ]:
            self.assertEqual(
                len(re.findall(r"^%s[ \t]+%s$" % (re.escape(glyph), re.escape(command)),
                               text, re.MULTILINE)), 1)
        # the hardware parity twins for h/g/b are generated
        self.assertIn("ا script-binding memo-history", text)
        self.assertIn("ل script-binding sponsorblock_set_segment", text)
        self.assertIn("ﻻ script-binding sub_backdrop/toggle", text)
        # the Latin bindings survive untouched
        for latin in ("c", "a", "h", "n", "g", "G", "b"):
            self.assertTrue(
                re.search(r"^%s[ \t]" % latin, text, re.MULTILINE),
                "Latin binding lost: %s" % latin)

    def test_layout_independent_backups_are_added(self):
        _, text = self._migrate(LEGACY_DEPLOYED)
        for combo, command in [
            ("Ctrl+Shift+h", "script-binding memo-history"),
            ("Ctrl+Shift+m", "script-binding sponsorblock_set_segment"),
            ("Ctrl+Shift+s", "script-binding sponsorblock_submit_segment"),
            ("Ctrl+Shift+b", "script-binding sub_backdrop/toggle"),
            ("Ctrl+Shift+u", "script-binding sponsorblock_upvote"),
        ]:
            self.assertTrue(
                re.search(r"^%s[ \t]+%s$" % (re.escape(combo), re.escape(command)),
                          text, re.MULTILINE),
                "backup binding missing: %s" % combo)

    def test_migration_is_idempotent(self):
        changed_once, text_once = self._migrate(LEGACY_DEPLOYED)
        changed_twice, text_twice = self._migrate(text_once)
        self.assertFalse(changed_twice)
        self.assertEqual(text_once, text_twice)

    def test_guard_conf_migration_disables_the_hook(self):
        from deploy.deployer import _migrate_keyboard_layout_conf

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".conf", delete=False, encoding="utf-8")
        try:
            handle.write('enabled=yes\ncommand="py" -m mpv_config.layout_guard\n')
            handle.close()
            self.assertTrue(_migrate_keyboard_layout_conf(handle.name))
            with open(handle.name, "r", encoding="utf-8") as stream:
                content = stream.read()
            self.assertIn("enabled=no", content)
            self.assertIn("layout_guard", content)  # command preserved
            self.assertFalse(_migrate_keyboard_layout_conf(handle.name))
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
