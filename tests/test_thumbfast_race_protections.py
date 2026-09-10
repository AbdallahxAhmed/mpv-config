import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestThumbfastOverlayDispatcher(unittest.TestCase):
    """Verify the single-flight coalescing overlay dispatcher in thumbfast.lua."""

    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")

    def test_dispatcher_state_variables_exist(self):
        """The dispatcher must declare overlay_busy, desired_overlay, overlay_visible."""
        self.assertIn("local overlay_busy = false", self.thumbfast_lua)
        self.assertIn("local desired_overlay = nil", self.thumbfast_lua)
        self.assertIn("local overlay_visible = false", self.thumbfast_lua)

    def test_pump_overlay_function_exists(self):
        """pump_overlay must be defined as the sole entry point for overlay mutations."""
        self.assertIn("local function pump_overlay()", self.thumbfast_lua)

    def test_draw_uses_dispatcher_not_direct_commands(self):
        """draw() must set desired_overlay and call pump_overlay, not dispatch overlay-add directly."""
        # Extract draw() body
        draw_match = re.search(
            r"local function draw\(w, h, script\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(draw_match, "draw() function not found")
        draw_body = draw_match.group(1)

        self.assertIn("desired_overlay =", draw_body)
        self.assertIn("pump_overlay()", draw_body)
        # Must NOT contain direct overlay-add calls
        self.assertNotIn('mp.command_native_async({"overlay-add"', draw_body)
        self.assertNotIn('mp.command_native({"overlay-add"', draw_body)

    def test_clear_uses_dispatcher_not_direct_remove(self):
        """clear() must set desired_overlay = false and pump, not issue overlay-remove directly."""
        # Extract clear() body
        clear_match = re.search(
            r"local function clear\(\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(clear_match, "clear() function not found")
        clear_body = clear_match.group(1)

        self.assertIn("desired_overlay = false", clear_body)
        self.assertIn("pump_overlay()", clear_body)
        # Must NOT contain direct overlay-remove calls
        self.assertNotIn('mp.command_native({"overlay-remove"', clear_body)
        self.assertNotIn('mp.command_native_async({"overlay-remove"', clear_body)
        # Must NOT contain the old safety timer hack
        self.assertNotIn("mp.add_timeout(0.03", clear_body)

    def test_no_stale_callback_removal(self):
        """No async callback should independently call overlay-remove.

        The old bug: a stale overlay-add callback would check current_seq != overlay_seq
        and fire overlay-remove, which removes the *current* overlay (shared ID 42),
        not the stale one. The dispatcher model eliminates this entirely.
        """
        self.assertNotIn("current_seq ~= overlay_seq", self.thumbfast_lua)
        # Verify overlay-remove only appears inside pump_overlay, not in any callback
        # Extract all command_native_async callback bodies
        callbacks = re.findall(
            r"mp\.command_native_async\([^,]+,\s*function\([^)]*\)(.*?)end\)",
            self.thumbfast_lua,
            re.DOTALL,
        )
        for cb_body in callbacks:
            self.assertNotIn(
                '"overlay-remove"',
                cb_body,
                "Found overlay-remove inside an async callback — stale removal bug",
            )

    def test_overlay_seq_removed(self):
        """overlay_seq is dead code and must not exist."""
        self.assertNotIn("local overlay_seq", self.thumbfast_lua)
        self.assertNotIn("overlay_seq = overlay_seq + 1", self.thumbfast_lua)

    def test_pump_only_dispatches_when_not_busy(self):
        """pump_overlay must guard with overlay_busy to ensure single-flight."""
        pump_match = re.search(
            r"local function pump_overlay\(\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(pump_match, "pump_overlay() function not found")
        pump_body = pump_match.group(1)
        self.assertIn("if overlay_busy then return end", pump_body)

    def test_pump_redrives_on_callback(self):
        """After each async callback completes, pump must check for pending work."""
        pump_match = re.search(
            r"local function pump_overlay\(\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(pump_match)
        pump_body = pump_match.group(1)
        # Each callback path must re-check desired_overlay and re-pump
        self.assertIn("if desired_overlay ~= nil then pump_overlay() end", pump_body)


class TestThumbfastAvailability(unittest.TestCase):
    """Verify the is_available handshake prevents chicken-and-egg deadlock."""

    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")

    def test_availability_not_gated_on_valid_frame(self):
        """available must report readiness when not disabled, without requiring has_valid_frame."""
        self.assertIn("local is_available = not disabled\n", self.thumbfast_lua)
        self.assertIn("available=is_available", self.thumbfast_lua)
        self.assertNotIn("has_valid_frame or using_storyboards", self.thumbfast_lua)


class TestThumbfastMidHoverTeardownGuard(unittest.TestCase):
    """Verify mid-hover resize defers teardown."""

    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")

    def test_pending_respawn_guard(self):
        self.assertIn("pending_respawn = true", self.thumbfast_lua)
        self.assertIn("if pending_respawn and respawn_thumbnailer then", self.thumbfast_lua)


class TestThumbfastConfig(unittest.TestCase):
    """Verify thumbfast.conf settings."""

    def setUp(self):
        self.thumbfast_conf = (REPO_ROOT / "config" / "script-opts" / "thumbfast.conf").read_text(encoding="utf-8")

    def test_hwdec_disabled(self):
        self.assertIn("hwdec=no", self.thumbfast_conf)
        self.assertNotIn("hwdec=yes", self.thumbfast_conf)

    def test_tone_mapping_auto(self):
        """tone_mapping must be auto to prevent black frames on HDR/DV content."""
        self.assertIn("tone_mapping=auto", self.thumbfast_conf)
        self.assertNotIn("tone_mapping=no", self.thumbfast_conf)


class TestUoscTimelinePatcher(unittest.TestCase):
    """Test the uosc timeline patcher input/output directly, not from a machine-local file."""

    SAMPLE_TIMELINE = (
        "function Timeline:on_global_mouse_leave()\n"
        "\tself.pressed = false\n"
        "end\n"
    )

    SAMPLE_TIMELINE_PATCHED = (
        "function Timeline:on_global_mouse_leave()\n"
        "\tself.pressed = false\n"
        "\t-- UOSC_TIMELINE_THUMB_CLEANUP_PATCH\n"
        "\tself:clear_thumbnail()\n"
        "end\n"
    )

    def test_patch_adds_clear_thumbnail(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua
        result = patch_timeline_lua(self.SAMPLE_TIMELINE)
        self.assertIn("self:clear_thumbnail()", result)
        parts = result.split("function Timeline:on_global_mouse_leave()")
        body = parts[1].split("end")[0]
        self.assertIn("self:clear_thumbnail()", body)

    def test_patch_is_idempotent(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua
        first = patch_timeline_lua(self.SAMPLE_TIMELINE)
        second = patch_timeline_lua(first)
        self.assertEqual(first, second)

    def test_unpatch_removes_clear_thumbnail(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua, unpatch_timeline_lua
        patched = patch_timeline_lua(self.SAMPLE_TIMELINE)
        self.assertIn("self:clear_thumbnail()", patched)
        unpatched = unpatch_timeline_lua(patched)
        parts = unpatched.split("function Timeline:on_global_mouse_leave()")
        body = parts[1].split("end")[0]
        self.assertNotIn("self:clear_thumbnail()", body)

    def test_patcher_referenced_in_deployer(self):
        """The timeline patcher must be wired into the deployment flow."""
        deployer_src = (REPO_ROOT / "deploy" / "deployer.py").read_text(encoding="utf-8")
        self.assertIn("patch_uosc_timeline_thumb", deployer_src)


if __name__ == "__main__":
    unittest.main()
