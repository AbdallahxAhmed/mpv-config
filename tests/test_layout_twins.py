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
        """The bindings the shipped config relies on (probed on the target
        machine's Arabic 101 layout)."""
        self.assertEqual(layout_twins._twin_for("c"), ("ؤ", ""))
        self.assertEqual(layout_twins._twin_for("a"), ("ش", ""))
        self.assertEqual(layout_twins._twin_for("n"), ("ى", ""))
        self.assertEqual(layout_twins._twin_for("h"), ("ا", ""))
        self.assertEqual(layout_twins._twin_for("?"), ("؟", ""))

    def test_lam_alef_keys_get_sequence_twins(self):
        """b/G/B emit lam-alef as TWO key events; mpv's dash-joined key
        sequences consume both (measured: the twin fires once, the
        completing key's single binding does not)."""
        self.assertEqual(layout_twins._twin_for("b"), ("ل-ا", ""))
        self.assertEqual(layout_twins._twin_for("G"), ("ل-أ", ""))
        self.assertEqual(layout_twins._twin_for("B"), ("ل-آ", ""))

    def test_lam_is_refused_as_a_single(self):
        """Binding ل would defeat every lam-alef sequence (mpv: a
        single-key binding on a sequence's first element wins) - g keeps
        only its Ctrl+Shift+ backup."""
        twin, reason = layout_twins._twin_for("g")
        self.assertIsNone(twin)
        self.assertIn("sequence", reason)

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

    def test_refused_singles_are_never_emitted(self):
        """ل أ إ آ must never appear as a single-key twin: ل defeats the
        lam-alef sequences, the others are only sequence components."""
        for table in (layout_twins.ARABIC_PLAIN, layout_twins.ARABIC_SHIFT):
            for key, twin in table.items():
                if len(twin) == 1 and twin in layout_twins.LAM_ALEF_REFUSED_SINGLES:
                    emitted, reason = layout_twins._twin_for(key)
                    if twin == "ا":
                        continue  # allowed: h's twin, consumed by sequences
                    self.assertIsNone(emitted, key)


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
        # h's twin is the single ا; b's twin is the ل-ا sequence
        self.assertIn("ا script-binding memo-history", text)
        self.assertIn("ل-ا script-binding sub_backdrop/toggle", text)
        # g (ل) is the one key that cannot be twinned
        reported = dict(report)
        self.assertIn("sequence", reported["g"])
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
        """Pin the actual deployed bindings: the safe single-key twins, the
        Arabic question mark, and the lam-alef sequence twins; only g is
        reported as needing the Ctrl+Shift+ backup."""
        path = os.path.join(REPO, "config", "input.conf.template")
        with open(path, "r", encoding="utf-8") as handle:
            text, report = layout_twins.generate(handle.read())
        for twin, command in [
            ("ؤ", "script-binding uosc/subtitles"),
            ("ش", "script-binding uosc/audio"),
            ("ا", "script-binding memo-history"),
            ("ى", "script-binding autosubsync-menu"),
            ("ل-ا", "script-binding sub_backdrop/toggle"),
            ("ل-أ", "script-binding sponsorblock_submit_segment"),
            ("ل-آ", "script-binding sponsorblock_upvote"),
            ("؟", "no-osd script-message-to help_overlay help"),
        ]:
            self.assertIn("%s %s" % (twin, command), text)
        # the refused singles never appear as active keys (exact match:
        # the sequence twins legitimately START with ل)
        for line in text.splitlines():
            if line and not line.startswith("#"):
                self.assertNotIn(line.split(None, 1)[0],
                                 layout_twins.LAM_ALEF_REFUSED_SINGLES,
                                 "bound a refused lam-alef single: %r" % line)
        reported = {key for key, _ in report}
        self.assertEqual(reported, {"g"})

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
        # the same-key twins are present, exactly once each: the singles,
        # and h via ا and b/G/B via the lam-alef sequences
        for glyph, command in [
            ("ؤ", "script-binding uosc/subtitles"),
            ("ش", "script-binding uosc/audio"),
            ("ا", "script-binding memo-history"),
            ("ى", "script-binding autosubsync-menu"),
            ("ل-ا", "script-binding sub_backdrop/toggle"),
            ("؟", "no-osd script-message-to help_overlay help"),
        ]:
            self.assertEqual(
                len(re.findall(r"^%s[ \t]+%s$" % (glyph, re.escape(command)),
                               text, re.MULTILINE)), 1)
        # the refused singles stay unbound (exact match: the sequence
        # twins legitimately START with ل)
        for line in text.splitlines():
            if line and not line.startswith("#"):
                self.assertNotIn(line.split(None, 1)[0],
                                 layout_twins.LAM_ALEF_REFUSED_SINGLES,
                                 repr(line))
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
