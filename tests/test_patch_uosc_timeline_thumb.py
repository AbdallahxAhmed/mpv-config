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

    def test_missing_target_raises_instead_of_exiting(self):
        # deploy() runs the patcher in-process after the transaction has
        # committed; SystemExit would escape its `except Exception` guard.
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                patcher.run_patcher(Path(tmp_dir))

    def test_update_migration_reapplies_patch_to_fresh_upstream_uosc(self):
        from deploy.deployer import _migrate_deployed_configs
        from deploy.detector import Environment

        with tempfile.TemporaryDirectory() as tmp_dir:
            timeline = Path(tmp_dir) / "scripts" / "uosc" / "elements" / "Timeline.lua"
            timeline.parent.mkdir(parents=True)
            timeline.write_text(SAMPLE_TIMELINE_LUA, encoding="utf-8")
            env = Environment(os="windows", platform_key="windows")

            rows = _migrate_deployed_configs(tmp_dir, env)

            self.assertIn(patcher.PATCH_MARKER, timeline.read_text(encoding="utf-8"))
            self.assertIn("migrate-uosc-timeline-patch", [row["name"] for row in rows])
            again = _migrate_deployed_configs(tmp_dir, env)
            self.assertNotIn("migrate-uosc-timeline-patch", [row["name"] for row in again])


if __name__ == "__main__":
    unittest.main()
