import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestThumbfastRaceProtections(unittest.TestCase):
    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")
        self.thumbfast_conf = (REPO_ROOT / "config" / "script-opts" / "thumbfast.conf").read_text(encoding="utf-8")
        self.timeline_lua = Path(r"C:\Users\Abdallah_Ahmed\AppData\Roaming\mpv\scripts\uosc\elements\Timeline.lua").read_text(encoding="utf-8")

    def test_thumbfast_conf_hwdec_disabled(self):
        """hwdec must be 'no' to prevent GPU decoder contention and initial black frames."""
        self.assertIn("hwdec=no", self.thumbfast_conf)
        self.assertNotIn("hwdec=yes", self.thumbfast_conf)

    def test_thumbfast_lua_overlay_sequence_token(self):
        """overlay_seq generation counter must be present and used in draw and clear."""
        self.assertIn("local overlay_seq = 0", self.thumbfast_lua)
        self.assertIn("overlay_seq = overlay_seq + 1", self.thumbfast_lua)
        self.assertIn("current_seq ~= overlay_seq", self.thumbfast_lua)
        self.assertIn('mp.command_native_async({"overlay-remove", options.overlay_id}', self.thumbfast_lua)

    def test_thumbfast_lua_readiness_gating(self):
        """available must be gated on valid frame readiness, not hardcoded true on file load."""
        self.assertIn("local is_available = not disabled and (has_valid_frame or using_storyboards)", self.thumbfast_lua)
        self.assertIn("available=is_available", self.thumbfast_lua)
        self.assertNotIn("available=true,", self.thumbfast_lua)

    def test_thumbfast_lua_mid_hover_teardown_guard(self):
        """Mid-hover resize must defer teardown while show_thumbnail is true."""
        self.assertIn("if show_thumbnail then", self.thumbfast_lua)
        self.assertIn("pending_respawn = true", self.thumbfast_lua)
        self.assertIn("if pending_respawn and respawn_thumbnailer then", self.thumbfast_lua)

    def test_uosc_timeline_mouse_leave_cleanup(self):
        """Timeline:on_global_mouse_leave must clear thumbnail on window exit."""
        self.assertIn("function Timeline:on_global_mouse_leave()", self.timeline_lua)
        parts = self.timeline_lua.split("function Timeline:on_global_mouse_leave()")
        body = parts[1].split("end")[0]
        self.assertIn("self:clear_thumbnail()", body)


if __name__ == "__main__":
    unittest.main()
