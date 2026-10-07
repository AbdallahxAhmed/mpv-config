import tempfile
import unittest
from pathlib import Path

from tools import patch_uosc_timeline_thumb as patcher

SAMPLE_TIMELINE_LUA = """
function Timeline:on_global_mouse_leave()
\tself.pressed = false
end

function Timeline:on_global_mouse_move()
\tself.pressed = false
end
"""


class TestPatchUoscTimelineThumb(unittest.TestCase):
    def test_patch_and_unpatch(self):
        patched = patcher.patch_timeline_lua(SAMPLE_TIMELINE_LUA)
        self.assertIn("self:clear_thumbnail()", patched)
        self.assertIn(patcher.PATCH_MARKER, patched)

        # Idempotent
        patched_again = patcher.patch_timeline_lua(patched)
        self.assertEqual(patched, patched_again)

        # Unpatch
        unpatched = patcher.unpatch_timeline_lua(patched)
        self.assertNotIn("self:clear_thumbnail()", unpatched)
        self.assertNotIn(patcher.PATCH_MARKER, unpatched)
        self.assertEqual(unpatched.strip(), SAMPLE_TIMELINE_LUA.strip())

    def test_full_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            elements_dir = base / "elements"
            elements_dir.mkdir()
            timeline_file = elements_dir / "Timeline.lua"
            timeline_file.write_text(SAMPLE_TIMELINE_LUA, encoding="utf-8")

            # Patch
            patcher.run_patcher(base, unpatch=False)
            self.assertIn("self:clear_thumbnail()", timeline_file.read_text(encoding="utf-8"))

            # Unpatch
            patcher.run_patcher(base, unpatch=True)
            self.assertNotIn("self:clear_thumbnail()", timeline_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
