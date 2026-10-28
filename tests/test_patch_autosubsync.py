import tempfile
import unittest
from pathlib import Path

from tools.patch_autosubsync import (
    AUTOSUBSYNC_STDERR_MARKER,
    find_and_patch_autosubsync,
    patch_autosubsync_file,
    patch_autosubsync_lua,
)

SAMPLE_AUTOSUBSYNC_LUA = """-- autosubsync.lua
local function subprocess(args)
    return mp.command_native {
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        args = args
    }
end

local function sync_subtitles(ref_sub_path)
    if ret.status == 0 then
        notify("Subtitle synchronized.", nil, 2)
    else
        notify("Subtitle synchronization failed.", "error", 3)
    end
end
"""


class TestPatchAutosubsync(unittest.TestCase):
    def test_unpatched_script_adds_capture_stderr_and_diagnostics(self):
        patched = patch_autosubsync_lua(SAMPLE_AUTOSUBSYNC_LUA)
        self.assertIn("capture_stderr = true", patched)
        self.assertIn(AUTOSUBSYNC_STDERR_MARKER, patched)
        self.assertIn("ret.stderr", patched)
        self.assertIn('notify(err_msg, "error", 5)', patched)

    def test_patcher_is_idempotent(self):
        patched_once = patch_autosubsync_lua(SAMPLE_AUTOSUBSYNC_LUA)
        patched_twice = patch_autosubsync_lua(patched_once)
        self.assertEqual(patched_once, patched_twice)

    def test_patch_autosubsync_file_modifies_on_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "autosubsync.lua"
            script_path.write_text(SAMPLE_AUTOSUBSYNC_LUA, encoding="utf-8")

            modified = patch_autosubsync_file(script_path)
            self.assertTrue(modified)

            content = script_path.read_text(encoding="utf-8")
            self.assertIn("capture_stderr = true", content)

            # Second pass should return False (no modification)
            modified_again = patch_autosubsync_file(script_path)
            self.assertFalse(modified_again)

    def test_find_and_patch_autosubsync_in_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "scripts" / "autosubsync"
            nested.mkdir(parents=True)
            script_path = nested / "autosubsync.lua"
            script_path.write_text(SAMPLE_AUTOSUBSYNC_LUA, encoding="utf-8")

            found_and_patched = find_and_patch_autosubsync(tmpdir)
            self.assertTrue(found_and_patched)
            self.assertIn("capture_stderr = true", script_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
