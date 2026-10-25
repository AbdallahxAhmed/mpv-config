# -*- coding: utf-8 -*-
"""Full keybinding conflict audit.

Ground truth comes from probing the deployed Windows keyboard layouts
(TMP/opencode/probe_layouts.py, July 2026):

* Layout 00000C01 (Arabic 102 AZERTY) maps the physical b key to the
  two-codepoint lam-alef sequence U+0644 U+0627 ("لا").  mpv binds single
  codepoints only, so 'لا' can never bind; worse, mpv receives the
  sequence as TWO unicode events, so any binding on ل or ا fires while
  the user types lam-alef — this is the bug where the physical b key
  popped SponsorBlock marking.
* The ligature composites this layout can emit are لا لآ لأ لإ, so the
  glyph set {ل, ا, آ, أ, إ} must never be bound.
* Windows converts every ctrl+letter into a control code (0x02 for B in
  both layouts); mpv names those events "ctrl+b" instead, therefore
  modified Arabic-char combos (Ctrl+ؤ, Ctrl+ر, ctrl+ز, alt+ى, shift+ى…)
  can never fire and must not be declared.
* Presentation forms (U+FExx such as ﻻ) are never emitted by any layout,
  so bindings on them were dead code.

These tests lock the whole binding inventory against every failure class
found during that audit.
"""

import os
import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INPUT_TEMPLATE = os.path.join(REPO_ROOT, "config", "input.conf.template")
SMARTSKIP_CONF = os.path.join(REPO_ROOT, "config", "script-opts", "SmartSkip.conf")

# Glyphs that appear inside the lam-alef composites emitable on the
# deployed Arabic layout; binding any of them breaks/mis-triggers
# while the user is typing Arabic text in other apps… and worse, the
# FIRST glyph is delivered to mpv even mid-composite, so a binding on ل
# pops on every press of the physical b key.
LAM_ALEF_COMPOSITE_GLYPHS = ("لا", "لآ", "لأ", "لإ")

SPECIAL_KEY_RE = re.compile(r"^(?:F[1-9]|MBTN\S*|WHEEL\S*|CLOSE_WIN|CTRL\+\d|SPC|TAB|ENTER)$", re.IGNORECASE)


def _active_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line and not line.startswith("#"):
                yield line


def _parse_input_bindings(path=INPUT_TEMPLATE):
    """key -> command for every active input.conf line; also returns duplicates."""
    bindings = {}
    duplicates = {}
    for line in _active_lines(path):
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        key, command = parts
        if key in bindings and bindings[key] != command:
            duplicates[key] = (bindings[key], command)
        bindings[key] = command
    return bindings, duplicates


def _parse_smartskip_keys(path=SMARTSKIP_CONF):
    conf = {}
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for match in re.finditer(r"^(\w+_keybind)=(\[[^\n]*\])\s*$", content, re.MULTILINE):
        name, value = match.group(1), match.group(2)
        keys = [k for k in re.findall(r'"([^"]*)"', value) if k]
        conf[name] = keys
    return conf


class TestInputConfConflictAudit(unittest.TestCase):
    """Every failure class observed in the real-world keybinding audit."""

    def setUp(self):
        self.bindings, self.duplicates = _parse_input_bindings()

    def test_every_plain_key_is_single_codepoint(self):
        """mpv rejects multi-codepoint key names (the old 'لا' bug)."""
        for key in self.bindings:
            if "+" in key or SPECIAL_KEY_RE.match(key):
                continue
            self.assertEqual(
                len(key),
                1,
                "plain key %r must be a single codepoint (mpv rejects multi-codepoint names)" % key,
            )

    def test_no_presentation_form_keys(self):
        """Presentation forms (U+FExx) are never emitted by any real layout."""
        for key in self.bindings:
            for ch in key:
                self.assertFalse(
                    0xFE70 <= ord(ch) <= 0xFEFF,
                    "presentation form U+%04X in key %r is unreachable (old dead upvote/downvote twins)"
                    % (ord(ch), key),
                )

    def test_lam_alef_composite_glyphs_are_never_bound(self):
        """Physical b emits ل+ا as two events; exactly the old SponsorBlock bug."""
        for key in self.bindings:
            for glyph in LAM_ALEF_COMPOSITE_GLYPHS:
                self.assertNotIn(
                    glyph,
                    key,
                    "key %r contains lam-alef composite glyph %r — binding it makes the physical b key fire mid-sequence"
                    % (key, glyph),
                )

    def test_no_duplicate_keys_with_conflicting_commands(self):
        self.assertEqual(
            self.duplicates,
            {},
            "keys bound twice with different commands: %r" % self.duplicates,
        )

    def test_no_bilingual_twins_remain(self):
        """No Arabic twin bindings: the layout guard replaces them.

        A twin only works while its layout is active, and the lam-alef
        composites can never be bound safely. The guard puts mpv's window
        on a latin layout instead, so the Latin keys cover everything.
        """
        template = Path(__file__).resolve().parent.parent / "config" / "input.conf.template"
        content = template.read_text(encoding="utf-8")
        active = [
            line.split(None, 1)[0]
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        twins = [k for k in active if any(ord(c) > 0x590 for c in k)]
        self.assertEqual(twins, [], "the Arabic twins were replaced by the layout guard")

    def test_modified_arabic_combos_are_not_declared(self):
        """Windows control codes make ctrl/alt/shift+Arabic-char unreachable."""
        for banned in ("Ctrl+ؤ", "Ctrl+ر", "Ctrl+Shift+ر", "Shift+ل", "Ctrl+ﻻ"):
            self.assertNotIn(banned, self.bindings, "%s can never fire (control codes)" % banned)


class TestSmartSkipConflictAudit(unittest.TestCase):
    def setUp(self):
        self.conf = _parse_smartskip_keys()

    def test_expected_keybind_sections_present(self):
        for name in (
            "toggle_autoskip_keybind",
            "toggle_category_autoskip_keybind",
            "proceed_autoskip_countdown_keybind",
            "add_chapter_keybind",
            "remove_chapter_keybind",
            "write_chapters_keybind",
            "silence_skip_keybind",
        ):
            self.assertIn(name, self.conf, "%s missing from SmartSkip.conf" % name)

    def test_no_modified_arabic_combos(self):
        for keys in self.conf.values():
            for key in keys:
                if "+" in key:
                    self.assertFalse(
                        bool(re.search(r"[\u0600-\u06FF]", key)),
                        "SmartSkip key %r is a modified Arabic-char combo (unreachable)" % key,
                    )

    def test_plain_char_keys_are_safe_single_codepoints(self):
        hazards = LAM_ALEF_COMPOSITE_GLYPHS
        for keys in self.conf.values():
            for key in keys:
                if "+" in key or not re.search(r"[\u0600-\u06FF]", key):
                    continue
                self.assertEqual(len(key), 1, "SmartSkip key %r must be single codepoint" % key)
                for glyph in hazards:
                    self.assertNotIn(glyph, key, "SmartSkip key %r hits a lam-alef composite" % key)

    def test_no_plain_char_overlap_with_input_conf(self):
        """A script default loses to an input.conf line for the same key."""
        bindings, _ = _parse_input_bindings()
        input_plain = {k for k in bindings if "+" not in k and not SPECIAL_KEY_RE.match(k)}
        smart_plain = {
            key for keys in self.conf.values() for key in keys if "+" not in key
            and re.search(r"[\u0600-\u06FF]", key)
        }
        overlap = input_plain & smart_plain
        self.assertEqual(
            overlap,
            set(),
            "plain Arabic keys bound in both input.conf and SmartSkip: %r (input.conf wins and kills the script twin)"
            % overlap,
        )

    def test_smartskip_arabic_twins_are_the_documented_safe_set(self):
        expected_subset = {
            "toggle_autoskip_keybind": "ز",
            "toggle_category_autoskip_keybind": "د",
            "proceed_autoskip_countdown_keybind": "غ",
            "add_chapter_keybind": "ء",
            "remove_chapter_keybind": "ق",
            "write_chapters_keybind": "ك",
            "silence_skip_keybind": "؟",
        }
        for name, arabic in expected_subset.items():
            self.assertIn(arabic, self.conf.get(name, []), "SmartSkip %s lost its %r twin" % (name, arabic))


class TestArabicKeyMigrations(unittest.TestCase):
    """deployer must repair machines that still carry the hazard bindings."""

    LEGACY_ARABIC_BLOCK = (
        "SPACE cycle pause\n"
        "b    script-binding sub_backdrop/toggle\n"
        "ؤ        script-binding uosc/subtitles\n"
        "ش        script-binding uosc/audio\n"
        "ب       script-binding sub_backdrop/toggle\n"
        "ا        script-binding memo-history\n"
        "ﻻ        script-binding sponsorblock_upvote\n"
        "Ctrl+ﻻ   script-binding sponsorblock_downvote\n"
        "Shift+ﻻ  script-binding sponsorblock_downvote\n"
        "ﻵ        script-binding sponsorblock_downvote\n"
        "ل        script-binding sponsorblock_set_segment\n"
        "Shift+ل  script-binding sponsorblock_submit_segment\n"
        "إ        script-binding sponsorblock_submit_segment\n"
        "Ctrl+ؤ   script-binding ytdl_sub_menu/open\n"
        "Ctrl+ر           script-binding smart_paste/paste-to-open\n"
        "Ctrl+Shift+ر     script-binding smart_paste/paste-to-playlist\n"
    )

    def test_migrate_input_conf_retires_hazard_bindings(self):
        from deploy.deployer import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(self.LEGACY_ARABIC_BLOCK)

            self.assertTrue(_migrate_input_conf(conf_path))
            bindings, duplicates = _parse_input_bindings(conf_path)
            self.assertEqual(duplicates, {})

            # No hazard glyph remains bound, in any form.
            for key in bindings:
                for glyph in LAM_ALEF_COMPOSITE_GLYPHS:
                    self.assertNotIn(glyph, key, "hazard key %r survived migration" % key)
            for banned in ("Ctrl+ؤ", "Ctrl+ر", "Ctrl+Shift+ر", "Shift+ل", "Ctrl+ﻻ"):
                self.assertNotIn(banned, bindings, "%s survived migration" % banned)

            # The mnemonic twins (actions on OTHER physical keys) are NOT
            # force-appended anymore: the same-physical-key twins are
            # generated from the file's own Latin bindings, and this legacy
            # fixture carries none (b/ؤ/ش/ب survive as pre-existing lines).
            self.assertIsNone(bindings.get("ح"), "mnemonic twin ح must not be appended")
            self.assertIsNone(bindings.get("ت"), "mnemonic twin ت must not be appended")
            self.assertIsNone(bindings.get("م"), "mnemonic twin م must not be appended")
            self.assertEqual(bindings.get("ؤ"), "script-binding uosc/subtitles")
            self.assertEqual(bindings.get("ش"), "script-binding uosc/audio")
            # b's untwinnable action gets the layout-independent backup
            self.assertEqual(
                bindings.get("Ctrl+Shift+b"), "script-binding sub_backdrop/toggle")

            # Each safe twin appears at most once — pre-existing twins must
            # not be duplicated by the ensure-twins append.
            with open(conf_path, "r", encoding="utf-8") as f:
                for twin in ("ؤ", "ش", "ح", "ى", "ت", "م", "ب"):
                    count = sum(
                        1
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                        and line.split(None, 1)[0].strip() == twin
                    )
                    f.seek(0)
                    self.assertLessEqual(
                        count,
                        1,
                        "twin %r bound %d times after migration" % (twin, count),
                    )

            # Idempotent.
            with open(conf_path, "r", encoding="utf-8") as f:
                settled = f.read()
            self.assertFalse(_migrate_input_conf(conf_path))
            with open(conf_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), settled)

    def test_migrate_smartskip_conf_rekeys_arabic_lists(self):
        from deploy.deployer import _migrate_smartskip_conf

        OLD = (
            'toggle_autoskip_keybind=["ctrl+.", "ctrl+ز"]\n'
            'toggle_category_autoskip_keybind=["alt+.", "alt+ز"]\n'
            'proceed_autoskip_countdown_keybind=["enter", "y", "إ", "غ"]\n'
            'add_chapter_keybind=["shift+n", "shift+ى", "آ"]\n'
            'remove_chapter_keybind=["alt+n", "alt+ى"]\n'
            'write_chapters_keybind=["ctrl+n", "ctrl+ى"]\n'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "SmartSkip.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(OLD)

            self.assertTrue(_migrate_smartskip_conf(conf_path))
            conf = _parse_smartskip_keys(conf_path)
            self.assertEqual(conf["toggle_autoskip_keybind"], ["ctrl+.", "ز"])
            self.assertEqual(conf["toggle_category_autoskip_keybind"], ["alt+.", "د"])
            self.assertEqual(conf["proceed_autoskip_countdown_keybind"], ["enter", "y", "غ"])
            self.assertEqual(conf["add_chapter_keybind"], ["shift+n", "ء"])
            self.assertEqual(conf["remove_chapter_keybind"], ["alt+n", "ق"])
            self.assertEqual(conf["write_chapters_keybind"], ["ctrl+n", "ك"])

            # Idempotent.
            self.assertFalse(_migrate_smartskip_conf(conf_path))


if __name__ == "__main__":
    unittest.main()
