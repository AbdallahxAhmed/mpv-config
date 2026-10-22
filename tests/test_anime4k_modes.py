"""The Anime4K chains live in two places: deploy/registry.py (the installer)
and scripts/profile_picker.lua (the runtime). They must agree, otherwise the
mode you pick at install time is not the mode the player uses."""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "deploy" / "registry.py"
LUA = REPO_ROOT / "scripts" / "profile_picker.lua"


def python_chains():
    source = REGISTRY.read_text(encoding="utf-8")
    block = source.split("ANIME4K_CHAINS = {", 1)[1].split("\n}", 1)[0]
    chains = {}
    for name, value in re.findall(r'"([^"]+)":\s*"([^"]*)"', block):
        chains[name] = value
    return chains


def lua_chains():
    source = LUA.read_text(encoding="utf-8")
    block = source.split("local CHAINS = {", 1)[1].split("\n}", 1)[0]
    chains = {}
    # the Lua table entries are ["name"] = "shader;shader" (possibly split
    # over several lines with .. concatenation)
    for name, value in re.findall(
        r'\["([^"]+)"\]\s*=\s*((?:"[^"]*"\s*\n?\s*\.\.\s*)*"[^"]*")', block
    ):
        parts = re.findall(r'"([^"]*)"', value)
        chains[name] = "".join(parts)
    return chains


class Anime4kModeTests(unittest.TestCase):
    def test_lua_and_python_chains_match(self):
        py = python_chains()
        lua = lua_chains()
        self.assertTrue(py, "no chains parsed from registry.py")
        self.assertTrue(lua, "no chains parsed from profile_picker.lua")
        self.assertEqual(set(py), set(lua), "the two chain tables list different modes")
        for mode in py:
            self.assertEqual(
                py[mode], lua[mode], f"chain for mode {mode} differs between the two tables"
            )

    def test_every_mode_is_offered_by_the_installer(self):
        py = python_chains()
        for mode in ("A", "A+A", "B", "B+B", "C", "C+A", "fast", "off"):
            self.assertIn(mode, py)

    def test_the_shipped_default_exists(self):
        py = python_chains()
        self.assertIn("A", py)


if __name__ == "__main__":
    unittest.main()
