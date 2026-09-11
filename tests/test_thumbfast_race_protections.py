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

    def test_ready_field_reported_for_placeholder_suppression(self):
        """ready field must be broadcast to allow uosc to suppress empty black placeholders."""
        self.assertIn("ready=is_ready", self.thumbfast_lua)
        self.assertIn("local is_ready = not disabled and (has_valid_frame or (using_storyboards == true))", self.thumbfast_lua)

    def test_network_stream_open_filename_resolution(self):
        """update_property must handle stream-open-filename resolution for network media."""
        self.assertIn('if name == "stream-open-filename"', self.thumbfast_lua)
        self.assertIn("respawn_thumbnailer(last_seek_time or 0)", self.thumbfast_lua)

    def test_network_demuxer_cache_flags(self):
        """Network playback must use seekable cache, readahead for nearby scrubbing, and back-bytes."""
        self.assertIn('local reahead_secs = is_net and "5" or "0"', self.thumbfast_lua)
        self.assertIn('local demux_bytes = is_net and "64MiB" or "32MiB"', self.thumbfast_lua)
        self.assertIn('table.insert(args, "--demuxer-seekable-cache=yes")', self.thumbfast_lua)
        self.assertIn('table.insert(args, "--demuxer-max-back-bytes=32MiB")', self.thumbfast_lua)


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

    SAMPLE_FULL_TIMELINE = (
        "function Timeline:on_global_mouse_leave()\n"
        "\tself.pressed = false\n"
        "end\n\n"
        "\t\t\tlocal ax, ay = (thumb_x - border), (thumb_y - border)\n"
        "\t\t\tlocal bx, by = (thumb_x + thumb_width + border), (thumb_y + thumb_height + border)\n"
        "\t\t\tass:rect(ax, ay, bx, by, {\n"
        "\t\t\t\tcolor = bg,\n"
        "\t\t\t\tborder = 1,\n"
        "\t\t\t\topacity = {main = config.opacity.thumbnail, border = 0.08 * config.opacity.thumbnail},\n"
        "\t\t\t\tborder_color = fg,\n"
        "\t\t\t\tradius = state.radius,\n"
        "\t\t\t})\n"
        "\t\t\tlocal thumb_seconds = 10\n"
    )

    def test_patch_adds_clear_thumbnail(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua
        result = patch_timeline_lua(self.SAMPLE_TIMELINE)
        self.assertIn("self:clear_thumbnail()", result)
        parts = result.split("function Timeline:on_global_mouse_leave()")
        body = parts[1].split("end")[0]
        self.assertIn("self:clear_thumbnail()", body)

    def test_patch_guards_thumbnail_ass_rect(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua
        result = patch_timeline_lua(self.SAMPLE_FULL_TIMELINE)
        self.assertIn("if thumbnail.ready ~= false then", result)
        self.assertIn("UOSC_TIMELINE_THUMB_READY_PATCH", result)

    def test_unpatch_restores_thumbnail_ass_rect(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua, unpatch_timeline_lua
        patched = patch_timeline_lua(self.SAMPLE_FULL_TIMELINE)
        self.assertIn("if thumbnail.ready ~= false then", patched)
        unpatched = unpatch_timeline_lua(patched)
        self.assertNotIn("if thumbnail.ready ~= false then", unpatched)
        self.assertNotIn("UOSC_TIMELINE_THUMB_READY_PATCH", unpatched)
        self.assertIn("ass:rect(ax, ay, bx, by, {", unpatched)

    def test_patch_is_idempotent(self):
        from tools.patch_uosc_timeline_thumb import patch_timeline_lua
        first = patch_timeline_lua(self.SAMPLE_TIMELINE)
        second = patch_timeline_lua(first)
        self.assertEqual(first, second)

        first_full = patch_timeline_lua(self.SAMPLE_FULL_TIMELINE)
        second_full = patch_timeline_lua(first_full)
        self.assertEqual(first_full, second_full)

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


class TestThumbfastSeekWatchdogAndPipeline(unittest.TestCase):
    """Verify the seek queue, timer-driven watchdog, and triple-buffered frame slots."""

    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")

    def test_universal_seek_gating(self):
        """seek() must gate on seek_in_flight universally without an `if is_net` check."""
        seek_match = re.search(
            r"local function seek\(fast\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(seek_match, "seek() function not found")
        seek_body = seek_match.group(1)
        self.assertIn("if seek_in_flight then", seek_body)
        self.assertIn("pending_seek_target = last_seek_time", seek_body)
        self.assertNotIn("if is_net then", seek_body)

    def test_watchdog_lifecycle_functions(self):
        """arm_seek_watchdog and stop_seek_watchdog must exist and use a 2.5s timer."""
        self.assertIn("local function stop_seek_watchdog()", self.thumbfast_lua)
        self.assertIn("local function arm_seek_watchdog()", self.thumbfast_lua)
        self.assertTrue("mp.add_timeout(timeout" in self.thumbfast_lua or "mp.add_timeout(2.5" in self.thumbfast_lua)

    def test_watchdog_disarmed_on_frame_and_lifecycle(self):
        """stop_seek_watchdog must be called in check_new_thumb, clear, file_load, shutdown, and quit."""
        for fn_name in ["check_new_thumb", "clear", "file_load", "shutdown", "quit"]:
            match = re.search(
                rf"local function {fn_name}\([^)]*\)\n(.*?)^end",
                self.thumbfast_lua,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(match, f"{fn_name}() not found")
            self.assertIn("stop_seek_watchdog()", match.group(1), f"stop_seek_watchdog() missing in {fn_name}()")

    def test_triple_buffering_frame_slot_exists(self):
        """check_new_thumb must use rotating frame slots to prevent Windows sharing violations."""
        self.assertIn("local frame_slot = 0", self.thumbfast_lua)
        self.assertIn("local active_bgra_path = nil", self.thumbfast_lua)
        self.assertIn("frame_slot = (frame_slot % 3) + 1", self.thumbfast_lua)
        self.assertIn('thumbnail_path .. "." .. frame_slot .. ".bgra"', self.thumbfast_lua)

    def test_draw_uses_active_bgra_path(self):
        """draw() must target active_bgra_path to match the rotating slots."""
        draw_match = re.search(
            r"local function draw\(w, h, script\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(draw_match)
        self.assertIn("active_bgra_path", draw_match.group(1))

    def test_overlay_add_checks_callback_success(self):
        """mp.command_native_async callback must check success and not blindly assume visibility."""
        self.assertIn("function(success, result, error)", self.thumbfast_lua)
        self.assertIn("if success then", self.thumbfast_lua)
        self.assertIn("overlay_visible = true", self.thumbfast_lua)
        self.assertIn("overlay_visible = false", self.thumbfast_lua)


class TestSeekPipelineStateMachineSimulation(unittest.TestCase):
    """Behavioral simulation of the seek queue, watchdog, and slot rotation state machine."""

    class SimulatedSeekPipeline:
        def __init__(self):
            self.seek_in_flight = False
            self.current_seek_target = None
            self.pending_seek_target = None
            self.seek_watchdog_armed = False
            self.seek_watchdog_timeout = 2.5
            self.seek_retry_count = 0
            self.max_seek_retries = 2
            self.frame_slot = 0
            self.active_bgra = None
            self.dispatched_seeks = []
            self.respawn_called = False

        def arm_watchdog(self):
            self.seek_watchdog_armed = True

        def stop_watchdog(self):
            self.seek_watchdog_armed = False

        def do_raw_seek(self, target_time):
            self.dispatched_seeks.append(target_time)
            self.seek_in_flight = True
            self.current_seek_target = target_time
            self.arm_watchdog()

        def seek(self, target_time):
            if self.seek_in_flight:
                self.pending_seek_target = target_time
                return
            self.do_raw_seek(target_time)

        def fire_watchdog_timeout(self, show_thumbnail=True):
            if not self.seek_watchdog_armed:
                return
            self.seek_watchdog_armed = False
            if not self.seek_in_flight or not show_thumbnail:
                return
            self.seek_in_flight = False
            self.current_seek_target = None
            retry_target = self.pending_seek_target or (self.dispatched_seeks[-1] if self.dispatched_seeks else None)
            self.pending_seek_target = None
            if retry_target and self.seek_retry_count < self.max_seek_retries:
                self.seek_retry_count += 1
                self.do_raw_seek(retry_target)
            elif retry_target:
                self.seek_retry_count = 0
                self.respawn_called = True

        def accept_frame(self, show_thumbnail=True):
            self.stop_watchdog()
            self.seek_retry_count = 0
            self.seek_in_flight = False
            completed = self.current_seek_target
            self.current_seek_target = None

            self.frame_slot = (self.frame_slot % 3) + 1
            self.active_bgra = f"thumb.{self.frame_slot}.bgra"

            next_target = self.pending_seek_target
            self.pending_seek_target = None
            if next_target and show_thumbnail:
                if completed is None or abs(next_target - completed) > 0.05:
                    self.do_raw_seek(next_target)

    def test_deadlock_recovery_when_seek_stalls_and_movement_stops(self):
        """Simulate seek A stalling while user moves to B and stops.

        The watchdog must fire, clear in-flight, and dispatch B automatically.
        """
        pipeline = self.SimulatedSeekPipeline()
        # User starts moving: seek to 10.0
        pipeline.seek(10.0)
        self.assertTrue(pipeline.seek_in_flight)
        self.assertEqual(pipeline.current_seek_target, 10.0)
        self.assertTrue(pipeline.seek_watchdog_armed)

        # User scrubs quickly to 12.0, 15.0, and stops at 20.0
        pipeline.seek(12.0)
        pipeline.seek(15.0)
        pipeline.seek(20.0)
        # Pending should be the latest position 20.0
        self.assertEqual(pipeline.pending_seek_target, 20.0)
        # Only 1 seek dispatched so far
        self.assertEqual(pipeline.dispatched_seeks, [10.0])

        # Seek 10.0 stalls (no frame arrives). Watchdog fires at 2.5s.
        pipeline.fire_watchdog_timeout()

        # Deadlock broken! Seek 20.0 was automatically dispatched.
        self.assertEqual(pipeline.dispatched_seeks, [10.0, 20.0])
        self.assertEqual(pipeline.current_seek_target, 20.0)
        self.assertEqual(pipeline.seek_retry_count, 1)
        self.assertTrue(pipeline.seek_watchdog_armed)

        # Now frame 20.0 arrives
        pipeline.accept_frame()
        self.assertFalse(pipeline.seek_in_flight)
        self.assertFalse(pipeline.seek_watchdog_armed)
        self.assertEqual(pipeline.seek_retry_count, 0)
        self.assertEqual(pipeline.active_bgra, "thumb.1.bgra")

    def test_triple_buffering_slot_rotation(self):
        """Consecutive frames must rotate across slots 1, 2, 3 without colliding."""
        pipeline = self.SimulatedSeekPipeline()
        slots = []
        for _ in range(7):
            pipeline.accept_frame()
            slots.append(pipeline.active_bgra)
        expected = [
            "thumb.1.bgra",
            "thumb.2.bgra",
            "thumb.3.bgra",
            "thumb.1.bgra",
            "thumb.2.bgra",
            "thumb.3.bgra",
            "thumb.1.bgra",
        ]
        self.assertEqual(slots, expected)

    def test_respawn_after_max_retries_exhausted(self):
        """If repeated seeks produce no frames, respawn thumbnailer."""
        pipeline = self.SimulatedSeekPipeline()
        pipeline.seek(5.0)

        # Retry 1
        pipeline.fire_watchdog_timeout()
        self.assertEqual(pipeline.seek_retry_count, 1)
        self.assertFalse(pipeline.respawn_called)

        # Retry 2
        pipeline.fire_watchdog_timeout()
        self.assertEqual(pipeline.seek_retry_count, 2)
        self.assertFalse(pipeline.respawn_called)

        # Retries exhausted -> respawn
        pipeline.fire_watchdog_timeout()
        self.assertTrue(pipeline.respawn_called)


class TestThumbfastPersistentPipeAndDraining(unittest.TestCase):
    """Verify non-blocking persistent named pipe draining and partial write protection."""

    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")

    def test_winapi_functions_defined(self):
        """winapi must implement drain_pipe, get_pipe, close_pipe, and update_socket."""
        self.assertIn("winapi.drain_pipe = function()", self.thumbfast_lua)
        self.assertIn("winapi.get_pipe = function()", self.thumbfast_lua)
        self.assertIn("winapi.close_pipe = function()", self.thumbfast_lua)
        self.assertIn("winapi.update_socket = function(sock_name)", self.thumbfast_lua)

    def test_run_uses_winapi_persistent_pipe_and_drains(self):
        """run() on Windows must use winapi.get_pipe and drain_pipe to prevent buffer stalls."""
        run_match = re.search(
            r"local function run\(command\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(run_match, "run() function not found")
        run_body = run_match.group(1)
        self.assertIn("winapi.get_pipe()", run_body)
        self.assertIn("winapi.drain_pipe()", run_body)
        self.assertIn("winapi.C.WriteFile", run_body)

    def test_check_new_thumb_drains_pipe_and_guards_partial_writes(self):
        """check_new_thumb must drain the pipe and verify minimum expected frame size."""
        check_match = re.search(
            r"local function check_new_thumb\(\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(check_match, "check_new_thumb() function not found")
        check_body = check_match.group(1)
        self.assertIn("if winapi then winapi.drain_pipe() end", check_body)
        self.assertIn("min_expected", check_body)
        self.assertIn("raw_info.size < min_expected", check_body)

    def test_lifecycle_closes_pipe(self):
        """respawn_thumbnailer, quit, shutdown, and remove_thumbnail_files must close pipe."""
        for fn_name in ["respawn_thumbnailer", "quit", "shutdown", "remove_thumbnail_files"]:
            match = re.search(
                rf"local function {fn_name}\([^)]*\)\n(.*?)^end",
                self.thumbfast_lua,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(match, f"{fn_name}() not found")
            self.assertIn("winapi.close_pipe()", match.group(1), f"winapi.close_pipe() missing in {fn_name}()")

    def test_spawn_waiting_prevents_respawn_storm(self):
        """do_raw_seek must not trigger respawn_thumbnailer if still spawn_waiting."""
        seek_match = re.search(
            r"do_raw_seek = function\(target_time, fast\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(seek_match, "do_raw_seek function not found")
        seek_body = seek_match.group(1)
        self.assertIn("if not spawn_waiting then", seek_body)
        self.assertIn("pending_seek_target = target_time", seek_body)


class TestThumbfastNetworkReliability(unittest.TestCase):
    """Verify HTTP headers, User-Agent propagation, and HLS low-bitrate optimization."""

    def setUp(self):
        self.thumbfast_lua = (REPO_ROOT / "scripts" / "thumbfast.lua").read_text(encoding="utf-8")

    def test_user_agent_and_headers_extracted_and_passed(self):
        """User-agent and HTTP headers must be observed, cached, and passed to the thumbnailer."""
        self.assertIn("mp.observe_property(\"user-agent\", \"string\", update_property)", self.thumbfast_lua)
        self.assertIn("mp.observe_property(\"http-header-fields\", \"native\", update_property)", self.thumbfast_lua)
        self.assertIn("cached_user_agent = sb_j.http_headers[\"User-Agent\"]", self.thumbfast_lua)
        self.assertIn("table.insert(args, \"--user-agent=\"..user_agent)", self.thumbfast_lua)
        self.assertIn("table.insert(args, \"--http-header-fields=\"..header_fields)", self.thumbfast_lua)

    def test_hls_min_bitrate_option(self):
        """HLS playback must specify --hls-bitrate=min for fast thumbnail seeking."""
        self.assertIn('table.insert(args, "--hls-bitrate=min")', self.thumbfast_lua)

    def test_storyboard_header_table_safety(self):
        """setup_storyboards must safely parse http-header-fields table without string.match crashing on table."""
        sb_match = re.search(
            r"function setup_storyboards\(\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(sb_match, "setup_storyboards function not found")
        sb_body = sb_match.group(1)
        self.assertIn('if type(headers) == "table"', sb_body)
        self.assertNotIn('string.match(properties["http-header-fields"]', sb_body)

    def test_storyboard_early_exit_preserves_files(self):
        """setup_storyboards must return early before remove_thumbnail_files if not video_url."""
        sb_match = re.search(
            r"function setup_storyboards\(\)\n(.*?)^end",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(sb_match, "setup_storyboards function not found")
        sb_body = sb_match.group(1)
        exit_pos = sb_body.find("if not video_url then return end")
        remove_pos = sb_body.find("remove_thumbnail_files()")
        self.assertNotEqual(exit_pos, -1, "early return guard for non-storyboard url missing")
        self.assertNotEqual(remove_pos, -1, "remove_thumbnail_files missing")
        self.assertLess(exit_pos, remove_pos, "early exit must happen before remove_thumbnail_files")

    def test_network_seek_watchdog_does_not_kill_worker(self):
        """On network streams, seek_watchdog must redispatch rather than killing the worker."""
        watchdog_match = re.search(
            r"seek_watchdog = mp\.add_timeout\(timeout, function\(\)\n(.*?)^    end\)",
            self.thumbfast_lua,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(watchdog_match, "seek_watchdog function not found")
        watchdog_body = watchdog_match.group(1)
        self.assertIn("if is_net then", watchdog_body)
        self.assertIn("do_raw_seek(retry_target, true)", watchdog_body)
        self.assertIn("respawn_thumbnailer(retry_target)", watchdog_body)

    def test_network_reconnect_options_present(self):
        """Network streaming arguments must include stream-lavf reconnect and framedrop options."""
        self.assertIn('table.insert(args, "--stream-lavf-o=reconnect=1,reconnect_streamed=1,reconnect_delay_max=5")', self.thumbfast_lua)
        self.assertIn('table.insert(args, "--hr-seek-framedrop=yes")', self.thumbfast_lua)

    def test_strict_single_flight_seek(self):
        """Seek dispatching must be strictly single-flight; when busy, only update pending_seek_target without overlapping calls."""
        seek_idx = self.thumbfast_lua.find("local function seek(fast)")
        self.assertNotEqual(seek_idx, -1)
        seek_body = self.thumbfast_lua[seek_idx:seek_idx + 300]
        self.assertIn("pending_seek_target = last_seek_time", seek_body)
        self.assertIn("if seek_in_flight then", seek_body)
        self.assertNotIn("math.abs(last_seek_time - current_seek_target)", seek_body)

    def test_extractor_headers_preserved_across_file_loaded(self):
        """yt-dlp extractor headers must not be cleared in file_load, and must reset on start-file."""
        file_load_idx = self.thumbfast_lua.find("local function file_load()")
        self.assertNotEqual(file_load_idx, -1)
        file_load_body = self.thumbfast_lua[file_load_idx:file_load_idx + 1500]
        self.assertNotIn("cached_user_agent = nil", file_load_body)
        self.assertNotIn("cached_referer = nil", file_load_body)
        self.assertNotIn("cached_header_fields = nil", file_load_body)
        self.assertIn('mp.register_event("start-file", reset_network_auth)', self.thumbfast_lua)

    def test_bounded_worker_retries_on_failure(self):
        """Thumbnail worker failures must log error details and only retry within bounded count."""
        self.assertIn("local worker_retry_count = 0", self.thumbfast_lua)
        self.assertIn("local max_worker_retries = 2", self.thumbfast_lua)
        self.assertIn("thumbnail worker failed: status=", self.thumbfast_lua)
        self.assertIn("worker_retry_count < max_worker_retries", self.thumbfast_lua)

    def test_clear_removes_overlay_before_script_name_check(self):
        """clear() must hide and pump overlay before checking script_name to prevent stuck overlays."""
        clear_idx = self.thumbfast_lua.find("local function clear()")
        self.assertNotEqual(clear_idx, -1)
        clear_body = self.thumbfast_lua[clear_idx:clear_idx + 1200]
        desired_idx = clear_body.find("desired_overlay = false")
        script_name_idx = clear_body.find("if script_name then return end")
        self.assertNotEqual(desired_idx, -1)
        self.assertNotEqual(script_name_idx, -1)
        self.assertLess(desired_idx, script_name_idx, "desired_overlay = false must precede if script_name then return end")


if __name__ == "__main__":
    unittest.main()
