"""Spec 005: the uosc playlist-reorder patch of elements/Menu.lua.

Every test runs against the unmodified upstream uosc 5.13.0 fixture
(tests/fixtures/uosc-5.13.0, research R9).
"""

import hashlib
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
