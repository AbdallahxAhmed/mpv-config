"""Spec 005: the uosc playlist-reorder patch of elements/Menu.lua.

Every test runs against the unmodified upstream uosc 5.13.0 fixture
(tests/fixtures/uosc-5.13.0, research R9).
"""

import contextlib
import difflib
import hashlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import patch_uosc_playlist_reorder as patcher

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "uosc-5.13.0"
FIXTURE_MENU = FIXTURE_DIR / "elements" / "Menu.lua"
UPSTREAM_MENU_SHA256 = "0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49"
UPSTREAM_MENU_LINES = 1831


class FixtureTests(unittest.TestCase):
    """The fixture is the pinned upstream file, byte for byte."""

    def test_menu_is_the_pinned_upstream_file(self):
        data = FIXTURE_MENU.read_bytes()
        self.assertEqual(UPSTREAM_MENU_SHA256, hashlib.sha256(data).hexdigest())
        self.assertEqual(UPSTREAM_MENU_LINES, data.count(b"\n"))
        self.assertNotIn(b"\r", data)

    def test_gitattributes_keeps_the_fixture_byte_exact(self):
        rules = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("tests/fixtures/uosc-5.13.0/** -text", rules)

    def test_license_and_provenance_ship_with_the_fixture(self):
        self.assertIn(
            "GNU LESSER GENERAL PUBLIC LICENSE",
            (FIXTURE_DIR / "LICENSE").read_text(encoding="utf-8"),
        )
        readme = (FIXTURE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(UPSTREAM_MENU_SHA256, readme)
        self.assertIn(str(UPSTREAM_MENU_LINES), readme)


def upstream() -> bytes:
    return FIXTURE_MENU.read_bytes()


def one_byte_changed_outside_anchors(data: bytes) -> bytes:
    """Upstream with a single byte changed in a comment no anchor covers."""
    marker = b"-- Handles all key and mouse button shortcuts"
    assert data.count(marker) == 1
    return data.replace(marker, marker.replace(b"Handles", b"handles"))


class PureFunctionTests(unittest.TestCase):
    """contracts/uosc-reorder-patch.md, guarantees 1-6, on the fixture."""

    def test_every_anchor_matches_exactly_once(self):
        self.assertEqual([], patcher.check_anchors(upstream()))
        self.assertEqual(8, len(patcher.HUNKS))
        self.assertEqual(len(patcher.HUNKS), len({h.id for h in patcher.HUNKS}))

    def test_patch_then_unpatch_is_byte_identical(self):
        original = upstream()
        patched = patcher.patch_bytes(original)
        self.assertNotEqual(original, patched)
        self.assertEqual(original, patcher.unpatch_bytes(patched))

    def test_states_of_upstream_and_patched(self):
        patched = patcher.patch_bytes(upstream())
        self.assertEqual(patcher.PatchState.UPSTREAM, patcher.detect_state(upstream()))
        self.assertEqual(patcher.PatchState.PATCHED, patcher.detect_state(patched))

    def test_hunks_do_not_overlap(self):
        data = upstream()
        spans = sorted(
            (data.index(h.anchor), data.index(h.anchor) + len(h.anchor)) for h in patcher.HUNKS
        )
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)

    def test_lines_are_only_inserted_within_the_budget(self):
        original = upstream().split(b"\n")
        patched = patcher.patch_bytes(upstream()).split(b"\n")
        ops = {
            op
            for op, *_ in difflib.SequenceMatcher(
                None, original, patched, autojunk=False
            ).get_opcodes()
        }
        self.assertEqual({"equal", "insert"}, ops, "an upstream line was replaced or deleted")
        self.assertLessEqual(len(patched) - len(original), 159)
        self.assertLessEqual(patcher.PAYLOAD.count(b"\n"), 149)
        self.assertLessEqual(Path(patcher.__file__).read_bytes().count(b"\n"), 300)
        self.assertEqual(len(patcher.PAYLOAD.split(b"\n")) - 1 + 10, len(patched) - len(original))

    def test_highlight_code_is_untouched(self):  # FR-006
        patched = patcher.patch_bytes(upstream())
        for line in (
            b"\t\t\tlocal highlight_opacity = 0 + (item.active and 0.8 or 0) + (is_selected and 0.15 or 0)\n",
            b"\t\t\tlocal font_color = item.active and fgt or bgt\n",
        ):
            self.assertEqual(upstream().count(line), patched.count(line))
        self.assertNotIn(b"item.active =", patcher.PAYLOAD)

    def test_handle_hook_comes_after_the_last_action_click_zone(self):  # R5
        patched = patcher.patch_bytes(upstream())
        hook = patched.index(b"actions_rect.ax = self:reorder_handle(")
        zone = b"cursor:zone('primary_click'"
        click = patched.rindex(zone, 0, hook)
        self.assertNotIn(b"primary_click", patched[click + len(zone) : hook])
        self.assertLess(hook - click, 1000, "the hook is not right after the action loop")

    def test_key_hook_follows_the_key_up_return(self):  # R5-M1
        patched = patcher.patch_bytes(upstream())
        self.assertIn(
            b"\tif info.event == 'up' then return end\n"
            b"\tif self.reorder then return self:reorder_end() end" + patcher.MARKER + b"\n",
            patched,
        )

    def test_payload_is_pinned_to_the_patch_version(self):
        self.assertEqual(
            hashlib.sha256(patcher.PAYLOAD_PATH.read_bytes()).hexdigest(), patcher.PAYLOAD_SHA256
        )
        self.assertIn(f" v{patcher.PATCH_VERSION}".encode(), patcher.MARKER)
        self.assertNotIn(b"\r", patcher.PAYLOAD)
        self.assertNotIn(b"\r", patcher.patch_bytes(upstream()))

    def test_non_pinned_bytes_are_unexpected_upstream(self):  # R12
        changed = one_byte_changed_outside_anchors(upstream())
        self.assertEqual(patcher.PatchState.UNEXPECTED_UPSTREAM, patcher.detect_state(changed))
        self.assertEqual(
            patcher.PatchState.UPSTREAM, patcher.detect_state(changed, verify_hash=False)
        )
        with self.assertRaises(patcher.PatchError) as raised:
            patcher.patch_bytes(changed)
        self.assertEqual(patcher.PatchState.UNEXPECTED_UPSTREAM, raised.exception.state)

    def test_a_patched_copy_of_non_pinned_bytes_does_not_raise(self):  # guarantee 6
        patched = patcher.patch_bytes(
            one_byte_changed_outside_anchors(upstream()), verify_hash=False
        )
        self.assertEqual(patcher.PatchState.UNEXPECTED_UPSTREAM, patcher.detect_state(patched))

    def test_unknown_or_partial_patches_are_foreign(self):
        patched = patcher.patch_bytes(upstream())
        other_version = patched.replace(b"playlist-reorder v1", b"playlist-reorder v2")
        partial = upstream().replace(
            b"function Menu:on_display() self:update_dimensions() end\n",
            b"-- mpv-config:playlist-reorder v1 begin\nfunction Menu:on_display() self:update_dimensions() end\n",
        )
        for data in (other_version, partial):
            self.assertEqual(patcher.PatchState.FOREIGN, patcher.detect_state(data))

    def test_broken_anchor_is_all_or_nothing(self):  # FR-024
        data = upstream()
        hunk = next(h for h in patcher.HUNKS if h.id == "menu-update")
        broken = data.replace(hunk.anchor, hunk.anchor.replace(b"update", b"updete"))
        before = bytes(broken)
        self.assertEqual([patcher.AnchorFailure("menu-update", 0)], patcher.check_anchors(broken))
        self.assertEqual(
            patcher.PatchState.BROKEN_ANCHOR, patcher.detect_state(broken, verify_hash=False)
        )
        with self.assertRaises(patcher.PatchError) as raised:
            patcher.patch_bytes(broken, verify_hash=False)
        self.assertIn("menu-update", raised.exception.detail)
        self.assertEqual(before, broken)

    def test_unpatch_requires_every_insertion(self):
        patched = patcher.patch_bytes(upstream())
        hunk = next(h for h in patcher.HUNKS if h.id == "menu-draw")
        with self.assertRaises(patcher.PatchError):
            patcher.unpatch_bytes(patched.replace(hunk.insertion, b""))


class ApplyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.uosc = Path(tmp.name) / "uosc"
        (self.uosc / "elements").mkdir(parents=True)
        self.target = self.uosc / "elements" / "Menu.lua"
        shutil.copyfile(FIXTURE_MENU, self.target)

    def test_patch_then_already_patched_writes_nothing(self):
        result = patcher.apply(self.uosc)
        self.assertEqual(("patched", True), (result.status, result.changed))
        stat = self.target.stat()
        again = patcher.apply(self.uosc)
        self.assertEqual(("already-patched", False), (again.status, again.changed))
        self.assertEqual(
            (stat.st_mtime_ns, stat.st_ino),
            (self.target.stat().st_mtime_ns, self.target.stat().st_ino),
        )
        self.assertFalse((self.target.parent / "Menu.lua.mpvcfg-tmp").exists())

    def test_unpatch_restores_upstream(self):
        patcher.apply(self.uosc)
        self.assertEqual("unpatched", patcher.apply(self.uosc, unpatch=True).status)
        self.assertEqual(upstream(), self.target.read_bytes())
        self.assertEqual("already-unpatched", patcher.apply(self.uosc, unpatch=True).status)

    def test_missing_file_is_absent(self):
        self.target.unlink()
        self.assertEqual("absent", patcher.apply(self.uosc).status)

    def test_hash_mismatch_is_skipped_with_the_detail(self):
        self.target.write_bytes(one_byte_changed_outside_anchors(upstream()))
        before = self.target.read_bytes()
        result = patcher.apply(self.uosc)
        self.assertEqual(("skipped", False), (result.status, result.changed))
        digest = hashlib.sha256(before).hexdigest()[:12]
        self.assertEqual(
            "uosc-playlist-reorder skipped: elements/Menu.lua does not match uosc 5.13.0 "
            f"(sha256 of the unpatched form {digest}…); uosc left unchanged",
            result.detail,
        )
        self.assertEqual(before, self.target.read_bytes())

    def test_foreign_is_skipped_with_the_detail(self):
        self.target.write_bytes(patcher.patch_bytes(upstream()).replace(b" v1", b" v2"))
        result = patcher.apply(self.uosc)
        self.assertEqual("skipped", result.status)
        self.assertEqual(
            "uosc-playlist-reorder skipped: elements/Menu.lua carries an unknown or partial "
            "playlist-reorder patch; uosc left unchanged",
            result.detail,
        )

    def test_failed_replace_leaves_the_original(self):
        with mock.patch.object(Path, "replace", side_effect=OSError("disk full")):
            result = patcher.apply(self.uosc)
        self.assertEqual("skipped", result.status)
        self.assertEqual(
            "uosc-playlist-reorder skipped: could not write elements/Menu.lua (disk full); uosc left unchanged",
            result.detail,
        )
        self.assertEqual(upstream(), self.target.read_bytes())
        self.assertFalse((self.target.parent / "Menu.lua.mpvcfg-tmp").exists())

    def test_cli_exit_codes_and_output(self):
        def run(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = patcher.main(["--uosc-dir", str(self.uosc), *argv])
            return code, out.getvalue()

        self.assertEqual((0, "uosc-playlist-reorder: all 8 anchors match\n"), run("--check"))
        self.assertEqual((0, "uosc-playlist-reorder: patched\n"), run())
        self.assertEqual((0, "uosc-playlist-reorder: already-patched\n"), run())
        self.assertEqual((0, "uosc-playlist-reorder: unpatched\n"), run("--unpatch"))
        hunk = next(h for h in patcher.HUNKS if h.id == "menu-draw")
        self.target.write_bytes(upstream().replace(hunk.anchor, b""))
        code, out = run("--check")
        self.assertEqual((1, "anchor menu-draw matched 0x\n"), (code, out))
        code, out = run()
        self.assertEqual(1, code)
        self.assertTrue(out.startswith("uosc-playlist-reorder: skipped -- "), out)
        self.target.unlink()
        self.assertEqual(2, run()[0])


if __name__ == "__main__":
    unittest.main()
