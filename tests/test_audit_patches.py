import json
import os
import tempfile
import unittest
from unittest import mock

from deploy.deployer import _patch_mpv_conf, ensure_mpv_conf_user
from deploy.detector import Environment


class TestAuditPatches(unittest.TestCase):
    def test_ensure_mpv_conf_user_creates_when_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_path = os.path.join(tmpdir, "mpv.conf.user")
            self.assertFalse(os.path.exists(user_path))

            ensure_mpv_conf_user(tmpdir)

            self.assertTrue(os.path.exists(user_path))
            with open(user_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("# mpv.conf.user — personal overrides.", content)
            self.assertIn("Loaded LAST by mpv.conf", content)

    def test_ensure_mpv_conf_user_never_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_path = os.path.join(tmpdir, "mpv.conf.user")
            custom_content = "# User custom config\nvolume=80\n"
            with open(user_path, "w", encoding="utf-8") as f:
                f.write(custom_content)

            ensure_mpv_conf_user(tmpdir)

            with open(user_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, custom_content)

    def test_windows_native_hwdec_pinned_to_d3d11va(self):
        env = Environment(
            os="windows",
            platform_key="windows",
            gpu_vendor="nvidia",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, "mpv.conf.template")
            dest_path = os.path.join(tmpdir, "mpv.conf")

            with open(template_path, "w", encoding="utf-8") as f:
                f.write("hwdec = {{HWDEC}}\ngpu-api = {{GPU_API}}\n")

            # Native profile with empty or auto hwdec on Windows must resolve to d3d11va
            _patch_mpv_conf(
                template_path,
                dest_path,
                env,
                selected_profile="native",
                resolved_defaults={"hwdec": "auto", "gpu_api": "d3d11"},
            )

            with open(dest_path, "r", encoding="utf-8") as f:
                output = f.read()

            self.assertIn("hwdec = d3d11va", output)

    def test_template_profile_cond_nil_safe(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            "profile-cond              = (p.path or \"\"):lower():match('anime') ~= nil or (p.path or \"\"):lower():match('cartoon') ~= nil",
            content,
        )

    def test_template_streaming_inherits_sync(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        https_section = content.split("[protocol.https]")[1].split("[protocol.http]")[0]
        self.assertNotIn("video-sync                = audio", https_section)
        self.assertNotIn("interpolation             = no", https_section)
        self.assertIn("demuxer-max-bytes         = 800MiB", https_section)

    def test_input_conf_dynaudnorm_and_limiter(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        input_template = os.path.join(repo_root, "config", "input.conf.template")

        with open(input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            'F8 cycle-values af "lavfi=[dynaudnorm=f=500:g=15:p=0.95:m=10],lavfi=[alimiter=limit=0.9:level=false]" ""',
            content,
        )

    def test_template_volume_max_200(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("volume-max                = 200", content)

    def test_thumbfast_config_exists_and_valid(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        thumbfast_conf = os.path.join(repo_root, "config", "script-opts", "thumbfast.conf")

        self.assertTrue(os.path.isfile(thumbfast_conf))
        with open(thumbfast_conf, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("network=yes", content)
        self.assertIn("hwdec=yes", content)
        self.assertIn("max_height=200", content)
        self.assertIn("max_width=200", content)
        self.assertIn("spawn_first=no", content)

    def test_migrate_input_conf_updates_f8_and_preserves_custom(self):
        from setup import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = (
                "# User custom keys\n"
                "ctrl+x quit\n"
                "# F8: (جديد) تفعيل/تعطيل توحيد مستوى الصوت (Stable Volume / Night Mode)\n"
                '# مفيد جداً في الأنمي والأفلام التي يكون فيها صوت الحوار منخفضاً والمؤثرات عالية\n'
                'F8 cycle-values af "lavfi=[dynaudnorm=f=250:g=31:p=0.5]" ""\n'
                "SPACE cycle pause\n"
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("ctrl+x quit", new_content)
            self.assertIn("SPACE cycle pause", new_content)
            self.assertIn(
                'F8 cycle-values af "lavfi=[dynaudnorm=f=500:g=15:p=0.95:m=10],lavfi=[alimiter=limit=0.9:level=false]" ""',
                new_content,
            )
            self.assertNotIn("dynaudnorm=f=250:g=31:p=0.5", new_content)

    def test_input_conf_mouse_right_click_bindings(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        input_template = os.path.join(repo_root, "config", "input.conf.template")

        with open(input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("MBTN_RIGHT       cycle pause", content)
        self.assertIn("MBTN_RIGHT_DBL   ignore", content)

    def test_migrate_input_conf_updates_mbtn_right_from_context_menu(self):
        from setup import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = (
                "# User keys\n"
                "MBTN_RIGHT context-menu\n"
                "MBTN_RIGHT_DBL context-menu\n"
                "w cycle sub\n"
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("MBTN_RIGHT       cycle pause", new_content)
            self.assertIn("MBTN_RIGHT_DBL   ignore", new_content)
            self.assertIn("w cycle sub", new_content)
            self.assertNotIn("context-menu", new_content)

    def test_migrate_input_conf_appends_mbtn_right_when_absent(self):
        from setup import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = "SPACE cycle pause\n"
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("SPACE cycle pause", new_content)
            self.assertIn("MBTN_RIGHT       cycle pause", new_content)
            self.assertIn("MBTN_RIGHT_DBL   ignore", new_content)

    def test_template_watch_later_options_persists_volume_mute(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("watch-later-options       = start,vid,aid,sid,volume,mute", content)

    def test_template_youtube_startup_latency_options(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("ytdl                      = no", content)
        self.assertIn("ytdl-raw-options-append = no-playlist=", content)
        self.assertNotIn("player_client=android,web", content)
        self.assertNotIn("write-auto-subs=", content)
        self.assertNotIn("sub-langs=", content)
        self.assertIn("ytdl-raw-options-append = socket-timeout=15", content)
        self.assertIn("ytdl-raw-options-append = format-sort=res:1080,vbr,abr", content)
        self.assertNotIn("ytdl_hook-ytdl_path", content)
        self.assertNotIn("C:/", content)
        self.assertNotIn("C:\\", content)

    def test_ytdl_hook_conf_and_pinned_binary(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        hook_conf = os.path.join(repo_root, "config", "script-opts", "ytdl_hook.conf")
        self.assertTrue(os.path.isfile(hook_conf), "config/script-opts/ytdl_hook.conf must exist")

        with open(hook_conf, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("ytdl_path=yt-dlp", content)
        self.assertNotIn("C:/", content)

        # Verify dynamic resolution logic
        from deploy.deployer import _resolve_ytdl_path
        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        resolved = _resolve_ytdl_path(env)
        self.assertTrue(resolved)

    def test_sync_dependencies_dry_run(self):
        from deploy.installer import sync_dependencies, _get_target_tools_dir
        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        target = _get_target_tools_dir(env)
        self.assertTrue(target)
        results = sync_dependencies(env=env, dry_run=True)
        self.assertTrue(any(r["name"] == "yt-dlp" and r["status"] == "skipped" for r in results))
        self.assertTrue(any(r["name"] == "ffmpeg-full" and r["status"] == "skipped" for r in results))
        self.assertTrue(any(r["name"] == "alass" and r["status"] == "skipped" for r in results))

    def test_input_conf_clipboard_binding(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        input_template = os.path.join(repo_root, "config", "input.conf.template")

        with open(input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('Ctrl+v           script-binding smart_paste/paste-to-open', content)

    def test_migrate_input_conf_appends_clipboard_when_absent(self):
        from setup import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = "SPACE cycle pause\nMBTN_RIGHT cycle pause\nMBTN_RIGHT_DBL ignore\n"
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn('Ctrl+v           script-binding smart_paste/paste-to-open', new_content)

    def test_migrate_input_conf_upgrades_raw_clipboard(self):
        from setup import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = (
                'SPACE cycle pause\n'
                'Ctrl+v loadfile "${clipboard/text:${clipboard}}"\n'
                'Ctrl+V loadfile "${clipboard/text:${clipboard}}"\n'
                'Ctrl+ر loadfile "${clipboard/text:${clipboard}}"\n'
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn('Ctrl+v           script-binding smart_paste/paste-to-open', new_content)
            self.assertIn('Ctrl+V           script-binding smart_paste/paste-to-open', new_content)
            self.assertIn('Ctrl+ر           script-binding smart_paste/paste-to-open', new_content)
            self.assertNotIn('loadfile "${clipboard/text:${clipboard}}"', new_content)
            self.assertNotIn('loadfile "${clipboard}"', new_content)

    def test_template_1080p_high_bitrate_stream_selection(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check ytdl-format ceiling and removal of obsolete vp09 filter
        self.assertIn('ytdl-format = "bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best"', content)
        self.assertNotIn("vp0?9", content)

        # Check bitrate sorting
        self.assertIn("ytdl-raw-options-append = format-sort=res:1080,vbr,abr", content)

    def test_uosc_controls_toolbar_configured(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        uosc_conf = os.path.join(repo_root, "config", "script-opts", "uosc.conf")

        with open(uosc_conf, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            "controls=menu,gap,subtitles,audio,<stream>stream-quality,command:graphic_eq:keypress F8?Stable Volume,gap,fullscreen",
            content,
        )

    def test_input_conf_arabic_twin_bindings(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        input_template = os.path.join(repo_root, "config", "input.conf.template")

        with open(input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("ا        script-binding memo-history", content)
        self.assertIn("ى        script-binding autosubsync-menu", content)
        self.assertIn("ﻻ        script-binding sponsorblock_upvote", content)
        self.assertIn("ﻵ        script-binding sponsorblock_downvote", content)
        self.assertIn("ل        script-binding sponsorblock_set_segment", content)
        self.assertIn('Ctrl+ر           script-binding smart_paste/paste-to-open', content)

    def test_migrate_input_conf_appends_arabic_twins(self):
        from setup import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = 'SPACE cycle pause\nCtrl+v script-binding smart_paste/paste-to-open\n'
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("ا        script-binding memo-history", new_content)
            self.assertIn("ى        script-binding autosubsync-menu", new_content)
            self.assertIn("ﻻ        script-binding sponsorblock_upvote", new_content)
            self.assertIn('Ctrl+ر           script-binding smart_paste/paste-to-open', new_content)

    def test_vendored_scripts_exist_and_patched(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        tf = os.path.join(repo_root, "scripts", "thumbfast.lua")
        sp = os.path.join(repo_root, "scripts", "smart-paste.lua")
        ss = os.path.join(repo_root, "scripts", "SmartSkip.lua")
        yh = os.path.join(repo_root, "scripts", "ytdl_hook.lua")

        self.assertTrue(os.path.isfile(tf), "scripts/thumbfast.lua must exist in repo")
        self.assertTrue(os.path.isfile(sp), "scripts/smart-paste.lua must exist in repo")
        self.assertTrue(os.path.isfile(ss), "scripts/SmartSkip.lua must exist in repo")
        self.assertTrue(os.path.isfile(yh), "scripts/ytdl_hook.lua must exist in repo")

        with open(tf, "r", encoding="utf-8") as f:
            tf_content = f.read()
        self.assertIn("user-data/mpv/ytdl/json-subprocess-result", tf_content)
        self.assertIn("resized_storyboard or not using_storyboards", tf_content)

        with open(sp, "r", encoding="utf-8") as f:
            sp_content = f.read()
        self.assertIn('mp.add_hook("on_load", 10', sp_content)
        self.assertIn("watch%?v=", sp_content)
        self.assertIn("start_loading_indicator", sp_content)

        with open(yh, "r", encoding="utf-8") as f:
            yh_content = f.read()
        self.assertIn('tostring(data):gsub', yh_content)
        self.assertIn('json_name ~= "ytdl_description" and json_name ~= "description"', yh_content)
        self.assertIn("user-data/mpv/ytdl/json-subprocess-result", yh_content)
        self.assertNotIn('if not mp.get_property_bool("ytdl", true) then return end', yh_content)
        self.assertNotIn('mp.get_property_bool("ytdl"', yh_content)
        self.assertIn("known_paths", yh_content)
        self.assertIn("C:/Program Files/mpv/yt-dlp/yt-dlp.exe", yh_content)
        self.assertIn("utils.file_info", yh_content)

    def test_mpv_conf_template_idle_mode(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")
        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("idle                      = yes", content)

    def test_installer_uv_tool_uses_env_bin_dir(self):
        from unittest.mock import patch
        from deploy.installer import _install_uv_tool
        from deploy.detector import Environment

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        captured_kwargs = {}

        def fake_run(cmd, check=True, env=None):
            captured_kwargs["cmd"] = cmd
            captured_kwargs["env"] = env
            return True

        with patch("deploy.installer._run", side_effect=fake_run), \
             patch("shutil.which", return_value="C:\\dummy\\uv.exe"), \
             patch("deploy.installer._add_to_path"):
            ok = _install_uv_tool({"pkg": "testpkg", "bin_dir": "C:\\custom\\bin"}, env)
            self.assertTrue(ok)
            self.assertIn("testpkg", captured_kwargs["cmd"])
            self.assertNotIn("--bin-dir", captured_kwargs["cmd"])
            self.assertIsNotNone(captured_kwargs.get("env"))
            self.assertEqual(captured_kwargs["env"].get("UV_TOOL_BIN_DIR"), "C:\\custom\\bin")

    def test_verifier_mpv_launch_includes_idle_no(self):
        from unittest.mock import patch
        from deploy.verifier import verify
        from deploy.detector import Environment

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        captured_cmds = []

        def fake_run_check(cmd):
            captured_cmds.append(cmd)
            return True

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("deploy.verifier._run_check", side_effect=fake_run_check):
                verify(tmpdir, env)
                mpv_cmds = [c for c in captured_cmds if "mpv" in c[0]]
                self.assertTrue(any("--idle=no" in c for c in mpv_cmds))

    def test_verifier_startup_check_disables_scripts(self):
        """The startup probe must not execute the config's Lua scripts."""
        from unittest.mock import patch
        from deploy.verifier import verify
        from deploy.detector import Environment

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        captured_cmds = []

        def fake_run_check(cmd):
            captured_cmds.append(cmd)
            return True

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("deploy.verifier._run_check", side_effect=fake_run_check):
                verify(tmpdir, env)

        startup_cmds = [c for c in captured_cmds if any("--config-dir=" in a for a in c)]
        self.assertTrue(startup_cmds, "expected an mpv startup probe command")
        for cmd in startup_cmds:
            self.assertIn("--load-scripts=no", cmd)

    def test_ensure_windows_shortcuts_enforces_userprofile_working_directory(self):
        from unittest.mock import patch, MagicMock
        from deploy.deployer import ensure_windows_shortcuts
        from deploy.detector import Environment

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        captured_powershell_cmds = []
        captured_stdin = []

        # The hardened implementation passes a constant script and sends the
        # variable data as JSON on stdin, so the fake must accept `input=` and
        # report a successful exit status.
        def fake_subprocess_run(cmd, input=None, capture_output=True, text=True, timeout=15):
            captured_powershell_cmds.append(cmd)
            captured_stdin.append(input)
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "SHORTCUT_OK: C:\\dummy\\mpv.lnk\n"
            return mock_res

        with patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("shutil.which", return_value=r"C:\Program Files\mpv\mpv.exe"), \
             patch("os.path.isfile", return_value=True):
            updated = ensure_windows_shortcuts(env)
            self.assertEqual(len(updated), 1)
            self.assertIn("C:\\dummy\\mpv.lnk", updated)

            self.assertEqual(len(captured_powershell_cmds), 1)
            cmd_args = captured_powershell_cmds[0]
            self.assertIn("powershell", cmd_args[0].lower())
            script_text = cmd_args[cmd_args.index("-Command") + 1]

            # Enforce WorkingDirectory is set to $userProfile
            self.assertIn("$sc.WorkingDirectory = $userProfile", script_text)
            self.assertNotIn("$sc.WorkingDirectory = ''", script_text)
            self.assertNotIn("$sc.WorkingDirectory = 'C:\\Windows\\System32'", script_text)

            # Command-injection guard: the executable path must travel as JSON
            # data on stdin and must never be interpolated into the script text.
            payload = json.loads(captured_stdin[0])
            self.assertEqual(payload["exe"], r"C:\Program Files\mpv\mpv.exe")
            self.assertNotIn(r"C:\Program Files\mpv\mpv.exe", script_text)

    def test_ensure_mpv_conf_user_strips_self_include(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_path = os.path.join(tmpdir, "mpv.conf.user")
            corrupt_content = (
                "# Preserved user overrides\n"
                "volume = 90\n"
                "\n"
                "[protocol.http]\n"
                'include = "~~/mpv.conf.user"\n'
            )
            with open(user_path, "w", encoding="utf-8") as f:
                f.write(corrupt_content)

            ensure_mpv_conf_user(tmpdir)

            with open(user_path, "r", encoding="utf-8") as f:
                cleaned = f.read()

            self.assertNotIn('include = "~~/mpv.conf.user"', cleaned)
            self.assertNotIn("[protocol.http]", cleaned)
            self.assertIn("volume = 90", cleaned)

    def test_extract_overrides_ignores_include_directive(self):
        from setup import _extract_overrides

        conf_content = (
            "volume = 80\n"
            'include = "~~/mpv.conf.user"\n'
            "[protocol.http]\n"
            'include = "~~/mpv.conf.user"\n'
        )
        defaults = {}
        order, overrides = _extract_overrides(conf_content, defaults)

        for section, pairs in overrides.items():
            for key, val in pairs:
                self.assertNotEqual(key.lower(), "include")

    def test_mpv_conf_template_clipboard_monitor_and_default_include(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("clipboard-monitor         = yes", content)

        # [default] must precede the user overrides include so it is not grouped into [protocol.http]
        http_idx = content.find("[protocol.http]")
        default_idx = content.find("[default]\n#######################################################################################\n# User overrides")
        include_idx = content.find('include                   = "~~/mpv.conf.user"')

        self.assertNotEqual(http_idx, -1)
        self.assertNotEqual(default_idx, -1)
        self.assertNotEqual(include_idx, -1)
        self.assertTrue(http_idx < default_idx < include_idx)

    def test_smart_paste_type_safe_clipboard(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sp_file = os.path.join(repo_root, "scripts", "smart-paste.lua")

        with open(sp_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('if not s or type(s) ~= "string" then return nil end', content)
        self.assertIn('mp.commandv("update-clipboard", "text")', content)
        self.assertIn('type(val) == "string"', content)
        self.assertIn('type(val) == "table"', content)

    def test_sync_dependencies_dry_run_is_read_only(self):
        from deploy.installer import sync_dependencies

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        with mock.patch("deploy.installer.os.makedirs") as m_makedirs, \
                mock.patch("deploy.installer._add_to_path") as m_add_path:
            results = sync_dependencies(env=env, dry_run=True)

            self.assertTrue(all(r["status"] == "skipped" for r in results))
            m_makedirs.assert_not_called()
            m_add_path.assert_not_called()

    def test_detect_maps_fedora_platform_key(self):
        from deploy import detector

        with mock.patch("deploy.detector._detect_os", return_value="linux"), \
                mock.patch("deploy.detector._detect_distro", return_value="fedora"), \
                mock.patch("deploy.detector._detect_display", return_value="wayland"), \
                mock.patch("deploy.detector._detect_gpu", return_value="nvidia"), \
                mock.patch("deploy.detector._detect_avx2", return_value=False), \
                mock.patch("deploy.detector._detect_pkg_manager", return_value="dnf"), \
                mock.patch("deploy.detector._detect_python", return_value=("python3", "pip3")), \
                mock.patch("deploy.detector._which", return_value=True), \
                mock.patch("deploy.detector._resolve_config_dir", return_value="/tmp/mpv"), \
                mock.patch("deploy.detector._check_installed", return_value=False):
            env = detector.detect()

        self.assertEqual(env.platform_key, "fedora")


if __name__ == "__main__":
    unittest.main()
