import tempfile
import unittest
from pathlib import Path

from tools import patch_uosc_topbar as patcher

SAMPLE_TOPBAR_LUA = """
function TopBar:new()
\tlocal close = {icon = 'close', hover_bg = '2311e8', hover_fg = 'ffffff', command = function() mp.command('quit') end}
\tlocal max = {icon = 'crop_square', command = maximized_command}
\tlocal min = {icon = 'minimize', command = function() mp.command('cycle window-minimized') end}
\tself.buttons = options.top_bar_controls == 'left' and {close, max, min} or {min, max, close}
end
"""


class TestPatchUoscTopbar(unittest.TestCase):
    def test_patch_and_unpatch(self):
        patched = patcher.patch_topbar_lua(SAMPLE_TOPBAR_LUA)
        self.assertIn("pcall(mp.set_property, 'window-minimized', 'yes')", patched)
        self.assertIn(patcher.PATCH_MARKER, patched)

        # Idempotent
        patched_again = patcher.patch_topbar_lua(patched)
        self.assertEqual(patched, patched_again)

        # Unpatch
        unpatched = patcher.unpatch_topbar_lua(patched)
        self.assertNotIn(patcher.PATCH_MARKER, unpatched)
        self.assertNotIn("window-minimized", unpatched.split("local close")[1].split("local max")[0])
        self.assertEqual(unpatched.strip(), SAMPLE_TOPBAR_LUA.strip())

    def test_full_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            elements_dir = base / "elements"
            elements_dir.mkdir()
            topbar_file = elements_dir / "TopBar.lua"
            topbar_file.write_text(SAMPLE_TOPBAR_LUA, encoding="utf-8")

            # Patch
            patcher.run_patcher(base, unpatch=False)
            self.assertIn("window-minimized", topbar_file.read_text(encoding="utf-8"))

            # Unpatch
            patcher.run_patcher(base, unpatch=True)
            self.assertNotIn("window-minimized", topbar_file.read_text(encoding="utf-8").split("local close")[1].split("local max")[0])


if __name__ == "__main__":
    unittest.main()
