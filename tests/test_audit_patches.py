import json
import os
import re
import shutil
import sys
import tempfile
import time
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

    def test_d3d11_gated_to_windows_only(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with tempfile.TemporaryDirectory() as tmpdir:
            win_dest = os.path.join(tmpdir, "win_mpv.conf")
            linux_dest = os.path.join(tmpdir, "linux_mpv.conf")

            win_env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
            _patch_mpv_conf(
                template_file,
                win_dest,
                win_env,
                selected_profile="native",
                resolved_defaults={"gpu_api": "d3d11"},
            )
            with open(win_dest, "r", encoding="utf-8") as f:
                win_out = f.read()
            self.assertIn("d3d11-flip", win_out)
            self.assertIn("d3d11-output-format", win_out)

            linux_env = Environment(
                os="linux", platform_key="arch", distro="arch", gpu_vendor="nvidia"
            )
            _patch_mpv_conf(
                template_file,
                linux_dest,
                linux_env,
                selected_profile="native",
                resolved_defaults={"gpu_api": "vulkan"},
            )
            with open(linux_dest, "r", encoding="utf-8") as f:
                linux_out = f.read()
            self.assertNotIn("d3d11-flip", linux_out)
            self.assertNotIn("d3d11-output-format", linux_out)

    def test_template_profile_cond_nil_safe(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            "profile-cond              = (p.path or \"\"):lower():match('anime') ~= nil or (p.path or \"\"):lower():match('cartoon') ~= nil",
            content,
        )
        self.assertIn(
            'profile-cond              = (p["display-fps"] or 0) > 140 and (p["display-fps"] or 0) < 148',
            content,
        )

    def test_template_streaming_inherits_sync(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        https_section = content.split("\n[protocol.https]\n")[1].split("[protocol.http]")[0]
        self.assertNotIn("video-sync                = audio", https_section)
        self.assertNotIn("interpolation             = no", https_section)
        self.assertIn("demuxer-max-bytes         = 800MiB", https_section)

    def test_spec_004_playback_performance_profiles(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        live_action = content.split("\n[live-action]\n")[1].split("\n[anime]\n")[0]
        self.assertIn("tscale                    = linear", live_action)
        self.assertIn("video-timing-offset       = 0.01", live_action)

        anime = content.split("\n[anime]\n")[1].split("\n[wayland-144hz-fix]\n")[0]
        self.assertIn("tscale                    = linear", anime)
        self.assertIn("video-timing-offset       = 0.01", anime)

        wayland = content.split("\n[wayland-144hz-fix]\n")[1].split("\n[protocol.file]\n")[0]
        self.assertIn('(p["display-fps"] or 0) > 140', wayland)
        # --override-display-fps was renamed to --display-fps-override in
        # mpv 0.37; the old name only emits a deprecation warning now.
        self.assertIn("display-fps-override      = 143.981", wayland)
        self.assertIn("profile-restore           = copy", wayland)

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
        self.assertIn("hwdec=no", content)
        self.assertIn("tone_mapping=auto", content)
        self.assertIn("max_height=200", content)
        self.assertIn("max_width=200", content)
        self.assertIn("spawn_first=yes", content)

    def test_migrate_input_conf_updates_f8_and_preserves_custom(self):
        from deploy.deployer import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = (
                "# User custom keys\n"
                "ctrl+x quit\n"
                "# F8: (جديد) تفعيل/تعطيل توحيد مستوى الصوت (Stable Volume / Night Mode)\n"
                "# مفيد جداً في الأنمي والأفلام التي يكون فيها صوت الحوار منخفضاً والمؤثرات عالية\n"
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

    def test_migrate_input_conf_fixes_shader_clear_and_ligature_key(self):
        """CTRL+0 'clr' and the two-codepoint 'لا' key are rejected by every mpv."""
        from deploy.deployer import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = (
                'CTRL+0 no-osd change-list glsl-shaders clr; show-text "Shaders Cleared"\n'
                "# Subtitle background box toggle — لا = b\n"
                'لا       cycle-values sub-back-color "#B3080808" "#00000000"\n'
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            # change-list needs the empty-string value ('clr ""'); a bare
            # 'clr' fails with "required argument value not set".
            self.assertIn(
                'change-list glsl-shaders clr ""; show-text "Shaders Cleared"',
                new_content,
            )
            # 'لا' is two codepoints (U+0644 U+0627); mpv rejects
            # multi-codepoint key names with "Unknown key 'لا'".
            self.assertIn(
                'ب       cycle-values sub-back-color "#B3080808" "#00000000"',
                new_content,
            )
            self.assertNotIn("لا", new_content)

            # Idempotent for these two fixes specifically.
            self.assertNotIn("clr;", new_content)

    def test_migrate_mpv_conf_renames_override_display_fps(self):
        from deploy.deployer import _migrate_mpv_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "mpv.conf")
            old_content = (
                "[wayland-144hz-fix]\n"
                'profile-desc              = "Fix unstable display-resample on KDE Wayland 144Hz"\n'
                "override-display-fps      = 143.981\n"
                "profile-restore           = copy\n"
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_mpv_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("display-fps-override      = 143.981", new_content)
            self.assertNotIn("override-display-fps", new_content)

            # Second run is a no-op.
            self.assertFalse(_migrate_mpv_conf(conf_path))

        # Missing file is a no-op.
        self.assertFalse(_migrate_mpv_conf(os.path.join(tmpdir, "never-written.conf")))

    def test_migrate_mpv_conf_forces_opengl_on_legacy_intel(self):
        """Haswell-era Intel: patched gpu-api=vulkan renders magenta → opengl."""
        from deploy.detector import Environment
        from deploy.deployer import _migrate_mpv_conf

        env = Environment(
            os="linux", platform_key="ubuntu", gpu_vendor="intel", legacy_vulkan_gpu=True
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "mpv.conf")
            old_content = (
                "gpu-api                  = vulkan\n"
                "vo                        = gpu-next\n"
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_mpv_conf(conf_path, env=env)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("= opengl", new_content)
            self.assertNotIn("vulkan", new_content)
            self.assertIn("vo                        = gpu-next", new_content)

            # Second run is a no-op.
            self.assertFalse(_migrate_mpv_conf(conf_path, env=env))

        # Healthy GPUs are untouched.
        healthy = Environment(os="linux", platform_key="arch", gpu_vendor="nvidia")
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "mpv.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write("gpu-api                  = vulkan\n")
            self.assertFalse(_migrate_mpv_conf(conf_path, env=healthy))

    def test_patched_mpv_conf_forces_opengl_on_legacy_intel(self):
        from deploy.detector import Environment
        from deploy.deployer import _patch_mpv_conf

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template = os.path.join(repo_root, "config", "mpv.conf.template")
        env = Environment(
            os="linux", platform_key="ubuntu", gpu_vendor="intel", legacy_vulkan_gpu=True
        )
        defaults = {"gpu_api": "vulkan", "hwdec": "auto-safe", "gpu_context": "", "vo": "gpu-next"}

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "mpv.conf")
            _patch_mpv_conf(template, dest, env, "linux-like", defaults)
            with open(dest, "r", encoding="utf-8") as f:
                content = f.read()

            # "gpu-api".ljust(26) is the template's alignment for this key.
            self.assertIn("gpu-api".ljust(26) + "= opengl", content)
            self.assertNotIn("{{GPU_API}}", content)

    def test_migrate_mpv_conf_comments_removed_sub_ass_option(self):
        from deploy.deployer import _migrate_mpv_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "mpv.conf")
            old_content = (
                "sub-ass-vsfilter-aspect-compat = 'no'\n"
                "sub-ass-use-video-data = aspect-ratio\n"
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_mpv_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertEqual(
                re.search(
                    r"^[ \t]*sub-ass-vsfilter-aspect-compat[ \t]*=", new_content, re.MULTILINE
                ),
                None,
                "active removed-option line still present",
            )
            self.assertIn(
                "# removed in newer mpv — was: sub-ass-vsfilter-aspect-compat = 'no'",
                new_content,
            )
            self.assertIn("sub-ass-use-video-data = aspect-ratio", new_content)

            # Second run is a no-op.
            self.assertFalse(_migrate_mpv_conf(conf_path))

        # Without the replacement option present, the canonical one is
        # inserted right above the commented-out line (global section).
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "mpv.conf")
            old_content = "sub-ass-vsfilter-aspect-compat = 'no'\nosd-font = \"Segoe UI\"\n"
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            self.assertTrue(_migrate_mpv_conf(conf_path))
            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn(
                "sub-ass-use-video-data = aspect-ratio\n"
                "# removed in newer mpv — was: sub-ass-vsfilter-aspect-compat = 'no'",
                new_content,
            )
            self.assertIn('osd-font = "Segoe UI"', new_content)

    def test_gpu_vendor_scan_optimus_laptop(self):
        """iGPU + old Quadro (Optimus): hybrid detected, legacy iGPU detected."""
        from deploy import detector
        from deploy.detector import _detect_gpus, _gpu_vendor_from_device, _is_display_device

        self.assertFalse(
            _is_display_device(
                "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection I219-V"
            )
        )
        self.assertTrue(
            _is_display_device(
                "01:00.0 3D controller: NVIDIA Corporation GK107GLM [Quadro K1100M]"
            )
        )
        self.assertEqual(
            _gpu_vendor_from_device(
                "01:00.0 3D controller: NVIDIA Corporation GK107GLM [Quadro K1100M]"
            ),
            "nvidia",
        )

        optimus_lines = [
            "00:02.0 VGA compatible controller: Intel Corporation 4th Gen Core "
            "Processor Integrated Graphics Controller (rev 06)",
            "01:00.0 3D controller: NVIDIA Corporation GK107GLM [Quadro K1100M] (rev a1)",
            "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection I219-V",
        ]
        with mock.patch.object(detector, "_display_device_lines", return_value=optimus_lines):
            primary, vendors, lines = _detect_gpus()

        self.assertEqual(primary, "nvidia")  # historical priority preserved
        self.assertEqual(sorted(vendors), ["intel", "nvidia"])
        # (The Ethernet line is excluded by _is_display_device inside the
        # real _display_device_lines; the mock above replaces it wholesale,
        # so _detect_gpus simply classifies the lines it is handed.)

        with mock.patch.object(detector, "_display_device_lines", return_value=optimus_lines):
            # _legacy_vulkan_intel_gpu only runs on Linux — patch its os gate.
            with mock.patch("platform.system", return_value="Linux"):
                self.assertTrue(detector._legacy_vulkan_intel_gpu())

    def test_gpu_vendor_scan_legacy_intel_false_positive_free(self):
        """An NVIDIA desktop with an Intel NIC must not read as legacy Intel."""
        from deploy import detector
        from deploy.detector import _detect_gpus

        desktop_lines = [
            "01:00.0 VGA compatible controller: NVIDIA Corporation GP104 [GeForce GTX 1070]",
            "00:1f.6 Ethernet controller: Intel Corporation I219-V (Ethernet Only)",
        ]
        with mock.patch.object(
            detector, "_display_device_lines", return_value=[desktop_lines[0]]
        ):
            primary, vendors, _ = _detect_gpus()
        self.assertEqual(vendors, ["nvidia"])
        self.assertFalse(detector._legacy_vulkan_intel_gpu())

    def test_patched_native_nvdec_requires_libcuda_and_pure_nvidia(self):
        """nvdec forcing only on pure-NVIDIA Linux with a CUDA runtime present."""
        from deploy.detector import Environment
        from deploy.deployer import _patch_mpv_conf

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template = os.path.join(repo_root, "config", "mpv.conf.template")
        defaults = {
            "gpu_api": "vulkan",
            "hwdec": "auto-safe",
            "gpu_context": "",
            "vo": "gpu-next",
        }

        def hwdec_for(env, profile):
            with tempfile.TemporaryDirectory() as tmpdir:
                dest = os.path.join(tmpdir, "mpv.conf")
                _patch_mpv_conf(template, dest, env, profile, defaults)
                with open(dest, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("hwdec"):
                            return line.split("=", 1)[1].strip()
            return None

        optimus = Environment(
            os="linux",
            platform_key="ubuntu",
            distro="ubuntu",
            gpu_vendor="nvidia",
            gpu_hybrid=True,
            has_libcuda=True,
        )
        pure = Environment(
            os="linux", platform_key="arch", gpu_vendor="nvidia", has_libcuda=True
        )
        pure_nocuda = Environment(
            os="linux", platform_key="arch", gpu_vendor="nvidia", has_libcuda=False
        )

        # Pure NVIDIA + CUDA → nvidia-grade in-VRAM decode on both profiles.
        self.assertEqual(hwdec_for(pure, "native"), "nvdec")
        self.assertEqual(hwdec_for(pure, "windows-like"), "nvdec")

        # Optimus laptop → decode on the iGPU it renders on (no cross-PCIe copy).
        self.assertEqual(hwdec_for(optimus, "native"), "auto-safe")
        self.assertEqual(hwdec_for(optimus, "windows-like"), "auto-safe")

        # CUDA runtime missing → never write a decoder that cannot initialize.
        self.assertEqual(hwdec_for(pure_nocuda, "native"), "auto-safe")
        self.assertEqual(hwdec_for(pure_nocuda, "windows-like"), "auto-safe")

    def test_parse_mpv_version(self):
        """Distro and dev-build version strings both parse."""
        from deploy.detector import _parse_mpv_version

        self.assertEqual(_parse_mpv_version("mpv 0.37.0-1ubuntu4"), (0, 37, 0))
        self.assertEqual(_parse_mpv_version("mpv v0.41.0-934-g9f9f8c4dd"), (0, 41, 0))
        self.assertEqual(_parse_mpv_version("mpv 0.40.0"), (0, 40, 0))
        self.assertEqual(_parse_mpv_version("mpv 0.39.0 (C) 2000-2025"), (0, 39, 0))
    def test_ffsubsync_module_import_diagnostics_use_real_error_line(self):
        """Import failure diagnostics surface the error, not 'Traceback (...': head noise."""
        from deploy import detector

        def fake_subprocess_run(cmd, **kwargs):
            return mock.Mock(
                returncode=1,
                stderr=(
                    "Traceback (most recent call last):\n"
                    '  File "<string>", line 2, in <module>\n'
                    "ModuleNotFoundError: No module named 'pkg_resources'\n"
                ),
                stdout="",
            )

        with mock.patch.object(detector.subprocess, "run", side_effect=fake_subprocess_run):
            ok, diagnostic = detector._check_python_module_import(
                "python3", "pkg_resources", {"capture_output": True, "text": True}
            )
        self.assertFalse(ok)
        self.assertEqual(diagnostic, "ModuleNotFoundError: No module named 'pkg_resources'")

        with mock.patch.object(detector.subprocess, "run", return_value=mock.Mock(returncode=0)):
            ok, diagnostic = detector._check_python_module_import(
                "python3", "webrtcvad", {"capture_output": True, "text": True}
            )
        self.assertTrue(ok)
        self.assertEqual(diagnostic, "")

    def test_ffsubsync_health_pkg_resources_soft_webrtcvad_required(self):
        """Missing pkg_resources no longer queues a reinstall; webrtcvad failure does."""
        from deploy import detector

        launcher_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, launcher_dir, ignore_errors=True)
        launcher = os.path.join(launcher_dir, "ffsubsync")
        with open(launcher, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/python3\n")

        def fake_subprocess_run(cmd, **kwargs):
            module = cmd[-1] if cmd[-1] else ""
            returncode = 0
            stderr = ""
            if module == "pkg_resources":
                returncode = 1
                stderr = (
                    "Traceback (most recent call last):\n"
                    "ModuleNotFoundError: No module named 'pkg_resources'\n"
                )
            return mock.Mock(returncode=returncode, stderr=stderr, stdout="")

        with mock.patch.object(detector, "_run_silent", return_value=(True, "ffsubsync 0.4.26")), \
                mock.patch.object(detector.shutil, "which", return_value=launcher), \
                mock.patch.object(detector.sys, "platform", "linux"), \
                mock.patch.object(detector.subprocess, "run", side_effect=fake_subprocess_run):
            with mock.patch.object(detector.ui, "info") as ui_info:
                with mock.patch.object(detector.ui, "warn") as ui_warn:
                    ok = detector._check_ffsubsync_installed(launcher)
            # pkg_resources absence alone keeps ffsubsync "installed".
            self.assertTrue(ok)
            ui_info.assert_called_once()
            self.assertIn("--with setuptools", ui_info.call_args.args[0])
            ui_warn.assert_not_called()

            def fake_webrtcvad_broken(cmd, **kwargs):
                returncode = 0 if cmd[-1] != "webrtcvad" else 1
                stderr = "" if returncode == 0 else (
                    "Traceback (most recent call last):\n"
                    "ModuleNotFoundError: No module named 'webrtcvad'\n"
                )
                return mock.Mock(returncode=returncode, stderr=stderr, stdout="")

            with mock.patch.object(detector.subprocess, "run", side_effect=fake_webrtcvad_broken):
                with mock.patch.object(detector.ui, "warn") as ui_warn:
                    broken = detector._check_ffsubsync_installed(launcher)
            # webrtcvad still marks ffsubsync broken (planner reinstalls it).
            self.assertFalse(broken)
            self.assertTrue(ui_warn.called)
            self.assertIn("webrtcvad", ui_warn.call_args.args[0])


    def test_sanitize_mpv_conf_for_mpv_version(self):
        """Too-new options are commented; known/unknown-version callers keep control."""
        from deploy.deployer import _sanitize_mpv_conf_for_mpv_version

        content = (
            "clipboard-monitor = yes\n"
            "sub-ass-use-video-data = aspect-ratio\n"
            "hwdec = auto-safe\n"
            "# clipboard-monitor = no (pre-existing comment — untouched)\n"
            "sub-ass-vsfilter-blur-compat = yes\n"
        )

        old, removed = _sanitize_mpv_conf_for_mpv_version(content, (0, 37, 0))
        self.assertEqual(removed, 2)
        self.assertNotRegex(old, r"(?m)^clipboard-monitor[ \t]*=")
        self.assertNotRegex(old, r"(?m)^sub-ass-use-video-data[ \t]*=")
        self.assertIn("was: clipboard-monitor = yes", old)
        self.assertIn("was: sub-ass-use-video-data = aspect-ratio", old)
        self.assertIn("hwdec = auto-safe", old)  # existing option untouched
        self.assertIn("# clipboard-monitor = no (pre-existing comment — untouched)", old)
        self.assertIn("sub-ass-vsfilter-blur-compat = yes", old)  # not in the table
        # idempotent
        again, removed_again = _sanitize_mpv_conf_for_mpv_version(old, (0, 37, 0))
        self.assertEqual(removed_again, 0)
        self.assertEqual(again, old)

        current, removed_current = _sanitize_mpv_conf_for_mpv_version(content, (0, 41, 0))
        self.assertEqual(removed_current, 0)
        self.assertEqual(current, content)

        unknown, removed_unknown = _sanitize_mpv_conf_for_mpv_version(content, None)
        self.assertEqual(removed_unknown, 0)
        self.assertEqual(unknown, content)

    def test_patched_mpv_conf_adapts_to_old_mpv(self):
        """Fresh deploys render loadable configs on sub-minimum mpv (e.g. 0.37)."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template = os.path.join(repo_root, "config", "mpv.conf.template")
        defaults = {"gpu_api": "vulkan", "hwdec": "auto-safe", "gpu_context": "", "vo": "gpu-next"}

        old_env = Environment(
            os="linux",
            platform_key="ubuntu",
            gpu_vendor="intel",
            mpv_version=(0, 37, 0),
        )
        new_env = Environment(
            os="linux",
            platform_key="ubuntu",
            gpu_vendor="intel",
            mpv_version=(0, 41, 0),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            old_dest = os.path.join(tmpdir, "mpv-old.conf")
            _patch_mpv_conf(template, old_dest, old_env, "linux-like", defaults)
            with open(old_dest, "r", encoding="utf-8") as f:
                old_content = f.read()

            self.assertNotRegex(old_content, r"(?m)^clipboard-monitor[ \t]*=")
            self.assertNotRegex(old_content, r"(?m)^sub-ass-use-video-data[ \t]*=")
            self.assertIn("beyond installed mpv", old_content)

            new_dest = os.path.join(tmpdir, "mpv-new.conf")
            _patch_mpv_conf(template, new_dest, new_env, "linux-like", defaults)
            with open(new_dest, "r", encoding="utf-8") as f:
                new_content = f.read()
            self.assertRegex(new_content, r"(?m)^clipboard-monitor[ \t]*=")
            self.assertRegex(new_content, r"(?m)^sub-ass-use-video-data[ \t]*=")
            self.assertNotIn("beyond installed mpv", new_content)

    def test_migrate_mpv_conf_is_version_aware(self):
        """Old mpv keeps its valid options; upgraded mpv strips and restores."""
        from deploy.deployer import _migrate_mpv_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "mpv.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(
                    "sub-ass-vsfilter-blur-compat = yes\n"
                    "clipboard-monitor = yes\n"
                    "gpu-api = vulkan\n"
                )

            # Older-than-replacement mpv (e.g. 0.37): vsfilter options are
            # still VALID there — nothing about sub-ass gets touched.
            env_old = Environment(os="linux", distro="ubuntu", mpv_version=(0, 37, 0))
            self.assertTrue(_migrate_mpv_conf(conf_path, env_old))
            with open(conf_path, "r", encoding="utf-8") as f:
                old_state = f.read()
            self.assertRegex(old_state, r"(?m)^sub-ass-vsfilter-blur-compat[ \t]*=")
            self.assertIsNone(
                re.search(r"(?m)^sub-ass-use-video-data[ \t]*=", old_state)
            )
            # clipboard-monitor cannot exist on 0.37 → sanitizer comments it.
            self.assertIn("was: clipboard-monitor = yes", old_state)
            # idempotent
            self.assertFalse(_migrate_mpv_conf(conf_path, env_old))

            # Upgraded mpv: restore the commented option, retire vsfilter,
            # insert the canonical replacement.
            env_new = Environment(os="linux", distro="ubuntu", mpv_version=(0, 41, 0))
            self.assertTrue(_migrate_mpv_conf(conf_path, env_new))
            with open(conf_path, "r", encoding="utf-8") as f:
                new_state = f.read()
            self.assertRegex(new_state, r"(?m)^clipboard-monitor[ \t]*=")
            self.assertIn(
                "# removed in newer mpv — was: sub-ass-vsfilter-blur-compat = yes",
                new_state,
            )
            self.assertRegex(new_state, r"(?m)^sub-ass-use-video-data[ \t]*= aspect-ratio")
            self.assertFalse(_migrate_mpv_conf(conf_path, env_new))

    def test_install_mpv_latest_single_fast_ppa_flow(self):
        """PPA setup must not refresh the whole apt cache and must use the long budget."""
        from deploy import installer

        calls = []

        def fake_run(cmd, check=True, env=None, timeout=300):
            calls.append((tuple(cmd), timeout))
            return True

        env = Environment(os="linux", distro="ubuntu")
        with mock.patch.object(installer.shutil, "which", return_value="/usr/bin/add-apt-repository"), \
                mock.patch.object(installer, "_os_release_id", return_value="ubuntu"), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "probe_mpv_version", return_value=(0, 41, 0)), \
                mock.patch.object(installer.ui, "step"):
            installer._install_mpv_latest(env)

        commands = [c[0] for c in calls]
        # Nothing double-updates: add-apt-repository runs with -n (no internal
        # refresh), followed by exactly ONE apt-get update.
        add_calls = [c for c in commands if "add-apt-repository" in c]
        self.assertEqual(len(add_calls), 1)
        self.assertIn("-n", add_calls[0])
        update_calls = [c for c in commands if c[:2] == ("sudo", "apt-get") and "update" in c]
        self.assertEqual(len(update_calls), 1)
        self.assertIn("Acquire::Retries=3", update_calls[0])
        self.assertIn("Acquire::ForceIPv4=true", update_calls[0])
        install_calls = [c for c in commands if c[:2] == ("sudo", "apt-get") and "install" in c]
        self.assertEqual(len(install_calls), 1)
        self.assertIn("mpv", install_calls[0])
        self.assertIn("Acquire::Retries=3", install_calls[0])
        self.assertIn("Acquire::ForceIPv4=true", install_calls[0])
        # The registration attempt is deliberately SHORT: healthy machines
        # register in seconds and wedging attempts must fail fast into the
        # HTTPS-only fallback instead of burning the half-hour budget.
        for cmd, timeout in calls:
            if "add-apt-repository" in cmd:
                self.assertEqual(timeout, 300)
            elif any(marker in cmd for marker in ("apt-get", "apt")):
                self.assertEqual(timeout, installer.PKG_TIMEOUT)

    def test_install_mpv_latest_reports_below_minimum_as_failed(self):
        """Distro-0.37 'success' must not masquerade as a completed upgrade."""
        from deploy import installer

        def fake_run(cmd, check=True, env=None, timeout=300):
            return True  # every apt step "succeeds", but apt only has 0.37

        env = Environment(os="linux", distro="ubuntu")
        with mock.patch.object(installer.shutil, "which", return_value="/usr/bin/add-apt-repository"), \
                mock.patch.object(installer, "_os_release_id", return_value="ubuntu"), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "probe_mpv_version", return_value=(0, 37, 0)):
            with mock.patch.object(installer.ui, "warn") as warn, \
                    mock.patch.object(installer.ui, "step"):
                ok = installer._install_mpv_latest(env)

        self.assertFalse(ok)  # routes into the tolerate-mpv + sanitizer flow
        warn.assert_called_once()  # exactly one explanation, not red herrings

        # Nothing installed at all is also honest failure.
        with mock.patch.object(installer.shutil, "which", return_value="/usr/bin/add-apt-repository"), \
                mock.patch.object(installer, "_os_release_id", return_value="ubuntu"), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "probe_mpv_version", return_value=None):
            with mock.patch.object(installer.ui, "warn") as warn, \
                    mock.patch.object(installer.ui, "error") as error, \
                    mock.patch.object(installer.ui, "step"):
                ok = installer._install_mpv_latest(env)
        self.assertFalse(ok)
        self.assertTrue(warn.called)
        self.assertTrue(error.called)

    def test_ubuntu_series_prefers_debian_family_codename(self):
        """Mint renames VERSION_CODENAME; the PPA URL needs the Ubuntu base series."""
        from deploy import installer

        mint = 'ID=linuxmint\nVERSION_CODENAME="xia"\nUBUNTU_CODENAME=noble\n'
        with mock.patch("builtins.open", mock.mock_open(read_data=mint)):
            self.assertEqual(installer._ubuntu_series(), "noble")

        plain = "ID=ubuntu\nVERSION_CODENAME=noble\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=plain)):
            self.assertEqual(installer._ubuntu_series(), "noble")

        with mock.patch("builtins.open", side_effect=OSError("no os-release")):
            self.assertEqual(installer._ubuntu_series(), "")

    def test_direct_ppa_registers_via_https_only(self):
        """Direct registration touches ONLY curl -4 HTTPS + gpg + a sources file."""
        from deploy import installer

        run_calls = []
        net_calls = []

        def fake_run(cmd, check=True, env=None, timeout=300):
            run_calls.append(tuple(cmd))
            return True

        def fake_capture(cmd, timeout=60):
            net_calls.append(tuple(cmd))
            joined = " ".join(cmd)
            if "api.launchpad.net" in joined:
                return True, '{"signing_key_fingerprint": "5E52F0DFE436AFEC51F07B8D3ABE0C0EB9EC1B6C"}'
            if "keyserver.ubuntu.com/pks" in joined and "op=get" in joined:
                return True, (
                    "-----BEGIN PGP PUBLIC KEY BLOCK-----\narmor\n"
                    "-----END PGP PUBLIC KEY BLOCK-----\n"
                )
            return False, ""

        with mock.patch.object(installer, "_capture", side_effect=fake_capture), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "_ubuntu_series", return_value="noble"), \
                mock.patch.object(installer.ui, "step"), \
                mock.patch.object(installer.ui, "success"):
            self.assertTrue(installer._direct_ppa_register())

        # Every network fetch is IPv4-forced curl over 443 — no HKP, no tool,
        # and the keyserver search used the fingerprint the API returned.
        self.assertEqual(
            [c[:4] for c in net_calls],
            [("curl", "-m", "30", "-4"), ("curl", "-m", "30", "-4")],
        )
        self.assertIn(
            "op=get&search=0x5E52F0DFE436AFEC51F07B8D3ABE0C0EB9EC1B6C",
            " ".join(net_calls[1]),
        )
        none_network = run_calls + net_calls
        self.assertFalse(
            any("add-apt-repository" in " ".join(c) for c in none_network)
        )
        dearmor = [c for c in run_calls if "--dearmor" in c]
        self.assertEqual(len(dearmor), 1)
        self.assertIn(
            "/usr/share/keyrings/ubuntuhandbook1-mpv-archive-keyring.gpg", dearmor[0]
        )
        joined = [" ".join(c) for c in run_calls]
        sources = [c for c in joined if "sources.list.d" in c]
        self.assertEqual(len(sources), 1)
        self.assertIn("/etc/apt/sources.list.d/ubuntuhandbook1-ubuntu-mpv-noble.list", sources[0])
        self.assertIn("signed-by=/usr/share/keyrings/ubuntuhandbook1-mpv-archive-keyring.gpg", sources[0])
        self.assertIn("noble main", sources[0])

    def test_direct_ppa_register_failure_contract(self):
        """Unparseable/missing metadata fails closed with an explanation."""
        from deploy import installer

        with mock.patch.object(installer, "_ubuntu_series", return_value=""), \
                mock.patch.object(installer.ui, "warn") as warn:
            self.assertFalse(installer._direct_ppa_register())
        self.assertTrue(warn.called)

        with mock.patch.object(installer, "_ubuntu_series", return_value="noble"), \
                mock.patch.object(installer, "_capture", return_value=(True, "{}")), \
                mock.patch.object(installer.ui, "warn") as warn, \
                mock.patch.object(installer.ui, "step"):
            self.assertFalse(installer._direct_ppa_register())
        self.assertTrue(warn.called)

        with mock.patch.object(installer, "_ubuntu_series", return_value="noble"), \
                mock.patch.object(
                    installer, "_capture", side_effect=[(False, ""), (False, "")]
                ), \
                mock.patch.object(installer.ui, "warn") as warn, \
                mock.patch.object(installer.ui, "step"):
            self.assertFalse(installer._direct_ppa_register())
        self.assertEqual(warn.call_count, 1)

    def test_install_mpv_latest_falls_back_to_direct_https(self):
        """A broken add-apt-repository must never block the PPA — direct wins."""
        from deploy import installer

        calls = []

        def fake_run(cmd, check=True, env=None, timeout=300):
            calls.append(tuple(cmd))
            if "add-apt-repository" in cmd:
                return False  # the tool path is wedged/failed on this box
            return True

        env = Environment(os="linux", distro="ubuntu")
        with mock.patch.object(installer.shutil, "which", return_value="/usr/bin/add-apt-repository"), \
                mock.patch.object(installer, "_os_release_id", return_value="ubuntu"), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "_direct_ppa_register", return_value=True), \
                mock.patch.object(installer, "probe_mpv_version", return_value=(0, 41, 0)), \
                mock.patch.object(installer.ui, "step"):
            self.assertTrue(installer._install_mpv_latest(env))

        commands = [list(c) for c in calls]
        # One short tool attempt, one successful direct registration,
        # then the usual single refresh + install.
        self.assertEqual(len([c for c in commands if "add-apt-repository" in c]), 1)
        update_calls = [c for c in commands if c[:2] == ["sudo", "apt-get"] and "update" in c]
        self.assertEqual(len(update_calls), 1)
        install_calls = [c for c in commands if c[:2] == ["sudo", "apt-get"] and "install" in c]
        self.assertEqual(len(install_calls), 1)
        self.assertIn("mpv", install_calls[0])

    def test_install_mpv_latest_minimal_install_skips_tool_bootstrap(self):
        """No add-apt-repository at all → direct HTTPS first, no big bootstrap."""
        from deploy import installer

        calls = []

        def fake_run(cmd, check=True, env=None, timeout=300):
            calls.append(tuple(cmd))
            return True

        env = Environment(os="linux", distro="ubuntu")
        with mock.patch.object(installer.shutil, "which", return_value=None), \
                mock.patch.object(installer, "_os_release_id", return_value="ubuntu"), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "_direct_ppa_register", return_value=True), \
                mock.patch.object(installer, "probe_mpv_version", return_value=(0, 41, 0)), \
                mock.patch.object(installer.ui, "step"), \
                mock.patch.object(installer.ui, "success"):
            self.assertTrue(installer._install_mpv_latest(env))

        joined = [" ".join(c) for c in calls]
        self.assertFalse(any("add-apt-repository" in c for c in joined))
        self.assertFalse(any("software-properties-common" in c for c in joined))
        self.assertTrue(any("apt-get" in c and "update" in c for c in joined))
        self.assertTrue(any("apt-get" in c and "install" in c and " mpv" in c for c in joined))

    def test_install_mpv_latest_direct_failure_uses_tool_last_resort(self):
        """If direct registration fails, bootstrap the standard tool and retry."""
        from deploy import installer

        calls = []
        add_attempts = []

        def fake_run(cmd, check=True, env=None, timeout=300):
            calls.append(tuple(cmd))
            if "add-apt-repository" in cmd:
                add_attempts.append(tuple(cmd))
                return True  # the freshly bootstrapped tool works
            return True

        env = Environment(os="linux", distro="ubuntu")
        with mock.patch.object(
                installer.shutil, "which",
                side_effect=[None, None, "/usr/bin/add-apt-repository"]), \
                mock.patch.object(installer, "_os_release_id", return_value="ubuntu"), \
                mock.patch.object(installer, "_run", side_effect=fake_run), \
                mock.patch.object(installer, "_direct_ppa_register", return_value=False), \
                mock.patch.object(installer, "probe_mpv_version", return_value=(0, 41, 0)), \
                mock.patch.object(installer.ui, "step"), \
                mock.patch.object(installer.ui, "warn"):
            self.assertTrue(installer._install_mpv_latest(env))

        joined = [" ".join(c) for c in calls]
        self.assertEqual(len(add_attempts), 1)
        self.assertTrue(any("software-properties-common" in c for c in joined))
        self.assertFalse(any("add-apt-repository" in c and "-y -n" not in c for c in joined))

    def test_run_check_false_yields_child_exit_code(self):
        """(regression) check=False must not lie about a child's failure.

        The streaming rewrite returned True for every check=False call,
        which made a failed `add-apt-repository -n` (Mint's fork has no
        such option) read as SUCCESS — the HTTPS/IPv4 fallback never ran
        and the PPA silently stayed unregistered on the friend's machine.
        """
        from deploy import installer

        ok = installer._run(
            [sys.executable, "-c", "import sys; sys.exit(3)"], check=False, timeout=60
        )
        self.assertFalse(ok)

        ok = installer._run([sys.executable, "-c", "pass"], check=False, timeout=60)
        self.assertTrue(ok)

    def test_run_quiet_mode_echoes_command_but_captures_output(self):
        """Quiet mode: the command echoes once; output lines do not flood."""
        from deploy import installer

        buf = []
        with tempfile.TemporaryDirectory() as td:
            payload = os.path.join(td, "payload.txt")
            with open(payload, "w", encoding="utf-8") as fh:
                fh.write("streamed-line-1\nstreamed-line-2\n")
            child = f"import sys\n[print(l) for l in open({payload!r})]"
            with mock.patch("builtins.print", side_effect=lambda *a, **k: buf.append(" ".join(str(x) for x in a))):
                ok = installer._run([sys.executable, "-c", child], check=False, timeout=60)
        joined = "\n".join(buf)
        self.assertTrue(ok)
        self.assertIn("  $ ", joined)
        # Captured, not printed: the feed stays readable even when the child
        # (apt/pacman) produces walls of text.
        self.assertNotIn("streamed-line-1", joined)
        self.assertNotIn("streamed-line-2", joined)
        # A fast command must NOT ooze heartbeat noise, and the old
        # per-command "(finished in …)" trailer is gone from quiet mode.
        self.assertNotIn("... running ", joined)
        self.assertNotIn("(finished in", joined)

    def test_run_failure_shows_short_tail_only(self):
        """A failed command reveals a bounded tail — diagnosis without a flood."""
        from deploy import installer

        child = (
            "for i in range(10): print(f'noise-{i}')\n"
            "print('important-1')\n"
            "print('important-2')\n"
            "print('important-3')\n"
            "import sys; sys.exit(3)"
        )
        buf = []
        with mock.patch("builtins.print", side_effect=lambda *a, **k: buf.append(" ".join(str(x) for x in a))):
            ok = installer._run([sys.executable, "-c", child], check=False, timeout=60)
        joined = "\n".join(buf)
        self.assertFalse(ok)
        # 16 lines captured, only the last _TAIL_SHOW surface (bounded).
        self.assertIn("⌄ last 6 of 13 output lines:", joined)
        self.assertIn("│ important-3", joined)
        self.assertIn("│ important-1", joined)
        self.assertNotIn("noise-0", joined)

    def test_run_verbose_streams_everything(self):
        """MPV_VERBOSE=1 restores full live streaming (diagnosis mode)."""
        from deploy import installer

        child = "print('streamed-line-1'); print('streamed-line-2')"
        buf = []
        with mock.patch.dict(os.environ, {"MPV_VERBOSE": "1"}), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: buf.append(" ".join(str(x) for x in a))):
            ok = installer._run([sys.executable, "-c", child], check=False, timeout=60)
        joined = "\n".join(buf)
        self.assertTrue(ok)
        # The lines stream as they appear (twice: echo + live lines are hard
        # to distinguish in a join, so assert the per-line prefix exists).
        streamed = [l for l in joined.splitlines() if l.startswith("      streamed-line-")]
        self.assertEqual(len(streamed), 2)
        self.assertIn("  $ ", joined)
        self.assertIn("(finished in", joined)

    def test_run_heartbeat_reports_silence(self):
        """A silent-but-working step prints elapsed ticks instead of dead air."""
        from deploy import installer

        child = "import time; time.sleep(0.6)"
        buf = []
        with mock.patch.object(installer, "_HEARTBEAT_INTERVAL", 0.05), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: buf.append(" ".join(str(x) for x in a))):
            ok = installer._run([sys.executable, "-c", child], check=False, timeout=60)
        joined = "\n".join(buf)
        ticks = [l for l in joined.splitlines() if "... running " in l and "/ limit 60s" in l]
        self.assertTrue(ok)
        self.assertGreaterEqual(len(ticks), 2)

    def test_run_heartbeat_respects_interval_spacing(self):
        """Heartbeats fire per interval, NOT per poll slice (no 5x/second spam)."""
        from deploy import installer

        child = "import time; time.sleep(1.0)"
        buf = []
        with mock.patch.object(installer, "_HEARTBEAT_INTERVAL", 0.5), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: buf.append(" ".join(str(x) for x in a))):
            ok = installer._run([sys.executable, "-c", child], check=False, timeout=60)
        joined = "\n".join(buf)
        ticks = [l for l in joined.splitlines() if "... running " in l and "/ limit 60s" in l]
        self.assertTrue(ok)
        # Slices fire at 0.2s granularity (~5 over one second): interval
        # gating keeps ticks roughly at interval cadence, never per-slice.
        self.assertGreaterEqual(len(ticks), 1)
        self.assertLessEqual(len(ticks), 4)

    def test_run_timeout_kills_process_and_reports(self):
        """Stuck children are killed at budget; the failure says why."""
        from deploy import installer

        with mock.patch.object(installer, "_HEARTBEAT_INTERVAL", 0.2), \
                mock.patch.object(installer.ui, "error") as err:
            ok = installer._run(
                [sys.executable, "-c", "import time; time.sleep(30)"], check=False, timeout=1
            )
        self.assertFalse(ok)
        self.assertTrue(err.called)
        err_text = " ".join(str(c) for c in err.call_args.args)
        self.assertIn("timed out after 1s", err_text)

    def test_run_file_not_found_contract(self):
        """A missing binary stays a clean False with an explanation."""
        from deploy import installer

        with mock.patch.object(installer.ui, "error") as err:
            ok = installer._run(["definitely_not_a_real_cmd_XYZ"], check=True)
        self.assertFalse(ok)
        err_text = " ".join(str(c) for c in err.call_args.args)
        self.assertIn("Command not found", err_text)

    def test_install_loops_announce_with_steps_not_spinner(self):
        """Install loops stream output; no spinner may redraw over it."""
        import inspect

        from deploy import installer

        src = inspect.getsource(installer.install_deps)
        self.assertIn('ui.step(f"Installing {name}...")', src)
        self.assertIn('ui.step(f"Installing {name} (optional)...")', src)
        self.assertNotIn("ui.spinner", src)

    def test_mpv_flow_breadcrumbs_exist(self):
        """Every mpv stage prints what it is doing before doing it."""
        import inspect

        from deploy import installer

        src = inspect.getsource(installer._install_mpv_latest)
        for marker in (
            "Registering ppa:ubuntuhandbook1/mpv",
            "HTTPS/IPv4-only path",
            "Refreshing apt cache",
            "Installing mpv from the PPA",
        ):
            self.assertIn(marker, src)
        direct = inspect.getsource(installer._direct_ppa_register)
        self.assertIn("signing-key fingerprint", direct)
        self.assertIn("signing key", direct)

    def test_install_deps_warms_up_sudo_before_installs(self):
        """One password prompt up-front; package steps never stop mid-flow."""
        import inspect

        from deploy import installer

        src = inspect.getsource(installer.install_deps)
        self.assertIn("Preauthenticating sudo", src)
        warm_up_at = src.index('["sudo", "-v"]')
        loop_at = src.index("for name in to_install:")
        self.assertLess(warm_up_at, loop_at)

    def test_mpv_repo_source_parses_pacman_output(self):
        """pacman -Qi 'Repository:' is extracted; missing pacman yields ''."""
        from deploy import verifier

        def fake_run(cmd, **kwargs):
            return mock.Mock(
                returncode=0,
                stdout=(
                    "Name            : mpv\n"
                    "Repository      : cachyos-extra-v3\n"
                    "Version         : 1:0.41.0-6.1\n"
                ),
                stderr="",
            )

        with mock.patch.object(verifier.subprocess, "run", side_effect=fake_run):
            self.assertEqual(verifier._mpv_repo_source(), "cachyos-extra-v3")

        with mock.patch.object(
            verifier.subprocess, "run", side_effect=OSError("no pacman")
        ):
            self.assertEqual(verifier._mpv_repo_source(), "")

    def test_mpv_optimization_row_variants(self):
        """CachyOS machines get the v3 verdict; pure Arch is silently skipped."""
        from deploy import verifier

        arch_env = Environment(os="linux", distro="arch")
        windows_env = Environment(os="windows", distro="arch")

        # Not a Linux/Arch context → no row at all.
        self.assertIsNone(verifier._mpv_optimization_row(windows_env))

        # CachyOS + mpv from the v3 repo → positive, explicit confirmation.
        with mock.patch.object(verifier.shutil, "which", return_value="/bin/x"), \
                mock.patch.object(verifier, "_read_os_release_text", return_value='ID=cachyos\nID_LIKE="arch"\n'), \
                mock.patch.object(verifier, "_mpv_repo_source", return_value="cachyos-extra-v3"):
            row = verifier._mpv_optimization_row(arch_env)
        self.assertEqual(row, {"name": "mpv optimized build (x86-64-v3/v4)", "status": "ok", "detail": "installed from cachyos-extra-v3"})

        # mpv previously installed from plain `extra` → skipped + repair command.
        with mock.patch.object(verifier.shutil, "which", return_value="/bin/x"), \
                mock.patch.object(verifier, "_read_os_release_text", return_value="ID=cachyos\n"), \
                mock.patch.object(verifier, "_mpv_repo_source", return_value="extra"):
            row = verifier._mpv_optimization_row(arch_env)
        self.assertEqual(row and row["status"], "skipped")
        self.assertIn("pacman -Syyu mpv", (row or {}).get("detail", ""))

        # Pure Arch (no cachyos in os-release) → no opinion.
        with mock.patch.object(verifier.shutil, "which", return_value="/bin/x"), \
                mock.patch.object(verifier, "_read_os_release_text", return_value="ID=arch\n"), \
                mock.patch.object(verifier, "_mpv_repo_source", return_value="extra"):
            self.assertIsNone(verifier._mpv_optimization_row(arch_env))

    def test_migrate_uosc_conf_removes_volume_max(self):
        from deploy.deployer import _migrate_uosc_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "uosc.conf")
            old_content = (
                "volume=right\n"
                "volume_size=40\n"
                "volume_border=1\n"
                "volume_step=1\n"
                "volume_max=200\n"
                "volume_persistency=\n"
            )
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_uosc_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            # volume_max was removed in uosc 5.13 (widget follows mpv's
            # volume-max); stale copies log "[uosc] unknown key 'volume_max'".
            self.assertNotIn("volume_max", new_content)
            self.assertIn("volume_step=1", new_content)
            self.assertIn("volume_persistency=", new_content)

            # Second run is a no-op.
            self.assertFalse(_migrate_uosc_conf(conf_path))

        self.assertFalse(_migrate_uosc_conf(os.path.join(tmpdir, "never-written.conf")))

    def test_input_conf_mouse_right_click_bindings(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        input_template = os.path.join(repo_root, "config", "input.conf.template")

        with open(input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("MBTN_RIGHT       cycle pause", content)
        self.assertIn("MBTN_RIGHT_DBL   ignore", content)

    def test_migrate_input_conf_updates_mbtn_right_from_context_menu(self):
        from deploy.deployer import _migrate_input_conf

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
        from deploy.deployer import _migrate_input_conf

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
        from deploy.installer import _get_target_tools_dir, sync_dependencies

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        # The tools directory probe creates %ProgramFiles%\\mpv (falling back to %APPDATA%)
        # and writes a test file in it; keep both in a scratch directory.
        with (
            tempfile.TemporaryDirectory() as scratch,
            mock.patch.dict(os.environ, {"ProgramFiles": scratch, "APPDATA": scratch}),
        ):
            target = _get_target_tools_dir(env)
            self.assertTrue(target)
            results = sync_dependencies(env=env, dry_run=True)
        self.assertTrue(any(r["name"] == "yt-dlp" and r["status"] == "skipped" for r in results))
        self.assertTrue(
            any(r["name"] == "ffmpeg-full" and r["status"] == "skipped" for r in results)
        )
        self.assertTrue(any(r["name"] == "alass" and r["status"] == "skipped" for r in results))

    def test_input_conf_clipboard_binding(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        input_template = os.path.join(repo_root, "config", "input.conf.template")

        with open(input_template, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Ctrl+v           script-binding smart_paste/paste-to-open", content)

    def test_migrate_input_conf_appends_clipboard_when_absent(self):
        from deploy.deployer import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = "SPACE cycle pause\nMBTN_RIGHT cycle pause\nMBTN_RIGHT_DBL ignore\n"
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("Ctrl+v           script-binding smart_paste/paste-to-open", new_content)

    def test_migrate_input_conf_upgrades_raw_clipboard(self):
        from deploy.deployer import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = (
                "SPACE cycle pause\n"
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

            self.assertIn("Ctrl+v           script-binding smart_paste/paste-to-open", new_content)
            self.assertIn("Ctrl+V           script-binding smart_paste/paste-to-open", new_content)
            self.assertIn("Ctrl+ر           script-binding smart_paste/paste-to-open", new_content)
            self.assertNotIn('loadfile "${clipboard/text:${clipboard}}"', new_content)
            self.assertNotIn('loadfile "${clipboard}"', new_content)

    def test_template_1080p_high_bitrate_stream_selection(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_file = os.path.join(repo_root, "config", "mpv.conf.template")

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check ytdl-format ceiling and removal of obsolete vp09 filter
        self.assertIn(
            'ytdl-format = "bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best"', content
        )
        self.assertNotIn("vp0?9", content)

        # Check bitrate sorting
        self.assertIn("ytdl-raw-options-append = format-sort=res:1080,vbr,abr", content)

    def test_uosc_controls_toolbar_configured(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        uosc_conf = os.path.join(repo_root, "config", "script-opts", "uosc.conf")

        with open(uosc_conf, "r", encoding="utf-8") as f:
            content = f.read()

        controls = [
            line.split("=", 1)[1] for line in content.splitlines() if line.startswith("controls=")
        ]
        self.assertEqual(len(controls), 1)
        items = controls[0].split(",")
        self.assertEqual(items[0], "menu")
        self.assertEqual(items[-2:], ["gap", "fullscreen"])
        self.assertIn(
            "command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions", items
        )
        self.assertTrue(
            "button:audio-tracks" in items
            or "command:headphones:script-binding uosc/audio?Audio tracks and dubs" in items
        )
        self.assertIn("button:stable-volume", items)
        self.assertNotIn("keypress", controls[0])

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
        self.assertIn("Ctrl+ر           script-binding smart_paste/paste-to-open", content)

    def test_migrate_input_conf_appends_arabic_twins(self):
        from deploy.deployer import _migrate_input_conf

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "input.conf")
            old_content = "SPACE cycle pause\nCtrl+v script-binding smart_paste/paste-to-open\n"
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(old_content)

            migrated = _migrate_input_conf(conf_path)
            self.assertTrue(migrated)

            with open(conf_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            self.assertIn("ا        script-binding memo-history", new_content)
            self.assertIn("ى        script-binding autosubsync-menu", new_content)
            self.assertIn("ﻻ        script-binding sponsorblock_upvote", new_content)
            self.assertIn("Ctrl+ر           script-binding smart_paste/paste-to-open", new_content)

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
        # URL normalization must run before the vendored extractor at priority 10.
        self.assertIn('mp.add_hook("on_load", 5', sp_content)
        self.assertIn("watch%?v=", sp_content)
        self.assertIn("start_loading_indicator", sp_content)

        with open(yh, "r", encoding="utf-8") as f:
            yh_content = f.read()
        self.assertIn("tostring(data):gsub", yh_content)
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

        from deploy.detector import Environment
        from deploy.installer import _install_uv_tool

        env = Environment(os="windows", platform_key="windows", gpu_vendor="nvidia")
        captured_kwargs = {}

        def fake_run(cmd, check=True, env=None):
            captured_kwargs["cmd"] = cmd
            captured_kwargs["env"] = env
            return True

        with (
            patch("deploy.installer._run", side_effect=fake_run),
            patch("shutil.which", return_value="C:\\dummy\\uv.exe"),
            patch("deploy.installer._add_to_path"),
            patch("deploy.installer.os.makedirs"),  # bin_dir is a Windows path: never create it
        ):
            ok = _install_uv_tool({"pkg": "testpkg", "bin_dir": "C:\\custom\\bin"}, env)
            self.assertTrue(ok)
            self.assertIn("testpkg", captured_kwargs["cmd"])
            self.assertNotIn("--bin-dir", captured_kwargs["cmd"])
            self.assertIsNotNone(captured_kwargs.get("env"))
            self.assertEqual(captured_kwargs["env"].get("UV_TOOL_BIN_DIR"), "C:\\custom\\bin")

    def test_verifier_mpv_launch_includes_idle_no(self):
        from unittest.mock import patch

        from deploy.detector import Environment
        from deploy.verifier import verify

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

        from deploy.detector import Environment
        from deploy.verifier import verify

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
        from unittest.mock import MagicMock, patch

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

        with (
            patch("subprocess.run", side_effect=fake_subprocess_run),
            patch("shutil.which", return_value=r"C:\Program Files\mpv\mpv.exe"),
            patch("os.path.isfile", return_value=True),
        ):
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
        from deploy.deployer import _extract_overrides

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

        # include must be placed under [default] at EOF so user globals override profile defaults
        ytdl_idx = content.find("[protocol.ytdl]")
        default_idx = content.rfind("[default]")
        include_idx = content.find('include                   = "~~/mpv.conf.user"')

        self.assertNotEqual(ytdl_idx, -1)
        self.assertNotEqual(default_idx, -1)
        self.assertNotEqual(include_idx, -1)
        self.assertTrue(ytdl_idx < default_idx < include_idx)
        self.assertTrue(content.strip().endswith('include                   = "~~/mpv.conf.user"'))

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
        with (
            mock.patch("deploy.installer.os.makedirs") as m_makedirs,
            mock.patch("deploy.installer._add_to_path") as m_add_path,
        ):
            results = sync_dependencies(env=env, dry_run=True)

            self.assertTrue(all(r["status"] == "skipped" for r in results))
            m_makedirs.assert_not_called()
            m_add_path.assert_not_called()

    def test_detect_maps_fedora_platform_key(self):
        from deploy import detector

        with (
            mock.patch("deploy.detector._detect_os", return_value="linux"),
            mock.patch("deploy.detector._detect_distro", return_value="fedora"),
            mock.patch("deploy.detector._detect_display", return_value="wayland"),
            mock.patch("deploy.detector._detect_gpu", return_value="nvidia"),
            mock.patch("deploy.detector._detect_avx2", return_value=False),
            mock.patch("deploy.detector._detect_pkg_manager", return_value="dnf"),
            mock.patch("deploy.detector._detect_python", return_value=("python3", "pip3")),
            mock.patch("deploy.detector._which", return_value=True),
            mock.patch("deploy.detector._resolve_config_dir", return_value="/tmp/mpv"),
            mock.patch("deploy.detector._check_installed", return_value=False),
        ):
            env = detector.detect()

        self.assertEqual(env.platform_key, "fedora")


class AlassInstallerTests(unittest.TestCase):
    """alass: prebuilt GitHub release on Ubuntu/Fedora; AUR + binary fallback on Arch."""

    def test_ubuntu_fedora_use_github_release_file(self):
        from deploy.registry import SYSTEM_DEPS

        entry = SYSTEM_DEPS["alass"]
        for key in ("ubuntu", "fedora"):
            self.assertEqual(entry[key]["method"], "github_release_file")
            self.assertEqual(entry[key]["dest_name"], "alass")
            self.assertNotIn("~", entry[key]["install_dir"])

    def test_asset_pattern_matches_upstream_name(self):
        from deploy.registry import SYSTEM_DEPS

        self.assertTrue(
            any(
                re.match(pattern, "alass-linux64")
                for pattern in SYSTEM_DEPS["alass"]["ubuntu"]["asset_patterns"]
            )
        )

    def test_arch_has_prebuilt_fallback(self):
        from deploy.registry import SYSTEM_DEPS

        fallback = SYSTEM_DEPS["alass"]["arch"]["fallback"]
        self.assertEqual(fallback["method"], "github_release_file")
        self.assertEqual(fallback["dest_name"], "alass")

    def test_no_aur_helper_falls_back_to_prebuilt(self):
        from deploy import installer
        from deploy.registry import SYSTEM_DEPS

        env = Environment(os="linux", platform_key="arch", aur_helper="")
        with mock.patch.object(
            installer, "_install_github_release_file", return_value=True
        ) as m_github:
            ok = installer._install_one("alass", SYSTEM_DEPS["alass"], env)

        self.assertTrue(ok)
        m_github.assert_called_once()
        self.assertEqual(m_github.call_args[0][0], "alass")

    def test_aur_build_failure_falls_back_to_prebuilt(self):
        from deploy import installer
        from deploy.registry import SYSTEM_DEPS

        env = Environment(os="linux", platform_key="arch", aur_helper="paru")
        with (
            mock.patch.object(installer, "_run", return_value=False) as m_run,
            mock.patch.object(
                installer, "_install_github_release_file", return_value=True
            ) as m_github,
        ):
            ok = installer._install_one("alass", SYSTEM_DEPS["alass"], env)

        self.assertTrue(ok)
        self.assertEqual(m_run.call_count, 2)  # pkg + fallback_pkg attempts
        m_github.assert_called_once()

    def test_aur_success_never_falls_back(self):
        from deploy import installer
        from deploy.registry import SYSTEM_DEPS

        env = Environment(os="linux", platform_key="arch", aur_helper="paru")
        with (
            mock.patch.object(installer, "_run", return_value=True),
            mock.patch.object(
                installer, "_install_github_release_file", return_value=True
            ) as m_github,
        ):
            ok = installer._install_one("alass", SYSTEM_DEPS["alass"], env)

        self.assertTrue(ok)
        m_github.assert_not_called()

    def test_release_file_installs_executable_binary(self):
        from deploy import installer

        release = {
            "assets": [
                {
                    "name": "alass-linux64",
                    "browser_download_url": "https://example.com/alass-linux64",
                }
            ]
        }

        def fake_download(url, dest):
            with open(dest, "wb") as fh:
                fh.write(b"ELF-binary-payload")

        with tempfile.TemporaryDirectory() as install_dir:
            info = {
                "method": "github_release_file",
                "repo": "kaegi/alass",
                "asset_patterns": [r"^alass-linux64$"],
                "install_dir": install_dir,
                "dest_name": "alass",
            }
            env = Environment(os="linux", platform_key="ubuntu")
            with (
                mock.patch.object(installer, "_fetch_latest_release", return_value=release),
                mock.patch.object(installer, "_download_asset", side_effect=fake_download),
                mock.patch.object(installer.shutil, "which", return_value=None),
                mock.patch.object(installer, "_run", return_value=True) as m_run,
            ):
                ok = installer._install_github_release_file("alass", info, env)

            self.assertTrue(ok)
            dest = os.path.join(install_dir, "alass")
            self.assertTrue(os.path.isfile(dest))
            with open(dest, "rb") as fh:
                self.assertEqual(fh.read(), b"ELF-binary-payload")
            # PATH-unreachable install dirs get a /usr/local/bin symlink
            m_run.assert_called_once()
            self.assertIn("ln", m_run.call_args[0][0])

    def test_release_file_missing_asset_fails(self):
        from deploy import installer

        release = {"assets": [{"name": "unrelated.tar.gz", "browser_download_url": "u"}]}

        with tempfile.TemporaryDirectory() as install_dir:
            info = {
                "method": "github_release_file",
                "repo": "kaegi/alass",
                "asset_patterns": [r"^alass-linux64$"],
                "install_dir": install_dir,
                "dest_name": "alass",
            }
            env = Environment(os="linux", platform_key="ubuntu")
            with (
                mock.patch.object(installer, "_fetch_latest_release", return_value=release),
                mock.patch.object(installer, "_download_asset") as m_dl,
                mock.patch.object(installer, "_run", return_value=True),
            ):
                ok = installer._install_github_release_file("alass", info, env)

            self.assertFalse(ok)
            m_dl.assert_not_called()


class YtDlpFreshnessTests(unittest.TestCase):
    """yt-dlp: standalone GitHub binary on Ubuntu/Fedora + 7-day self-refresh."""

    def test_ubuntu_fedora_use_standalone_binary(self):
        from deploy.registry import SYSTEM_DEPS

        for key in ("ubuntu", "fedora"):
            info = SYSTEM_DEPS["yt-dlp"][key]
            self.assertEqual(info["method"], "github_release_file")
            self.assertEqual(info["dest_name"], "yt-dlp")
            self.assertEqual(info["refresh_days"], 7)
            self.assertNotIn("~", info["install_dir"])

    def test_asset_pattern_matches_x86_and_not_arm(self):
        from deploy.registry import SYSTEM_DEPS

        patterns = SYSTEM_DEPS["yt-dlp"]["ubuntu"]["asset_patterns"]
        self.assertTrue(any(re.match(p, "yt-dlp_linux") for p in patterns))
        self.assertFalse(any(re.match(p, "yt-dlp_linux_aarch64") for p in patterns))

    def test_windows_entry_carries_refresh_days(self):
        from deploy.registry import SYSTEM_DEPS

        self.assertEqual(SYSTEM_DEPS["yt-dlp"]["windows"]["refresh_days"], 7)

    def test_freshness_stamp_matrix(self):
        from deploy import installer

        with tempfile.TemporaryDirectory() as tmpdir:
            info = {"install_dir": tmpdir, "dest_name": "yt-dlp"}
            dest = os.path.join(tmpdir, "yt-dlp")

            # No binary at all.
            self.assertFalse(installer._dep_is_fresh(info, 7))

            # Binary exists but no stamp (apt-installed class) → stale.
            with open(dest, "wb") as fh:
                fh.write(b"ELF")
            self.assertFalse(installer._dep_is_fresh(info, 7))

            # A refresh install stamps it → fresh within the window.
            installer._write_refresh_stamp(info)
            self.assertTrue(os.path.isfile(dest + ".stamp"))
            self.assertTrue(installer._dep_is_fresh(info, 7))

            # Stamp older than the window → stale again.
            old = time.time() - 8 * 86400
            os.utime(dest + ".stamp", (old, old))
            self.assertFalse(installer._dep_is_fresh(info, 7))

    def test_install_deps_refresh_gate_requeues_stale_launcher(self):
        from deploy import installer

        env = Environment(
            os="linux",
            platform_key="ubuntu",
            installed={
                "mpv": True,
                "yt-dlp": True,
                "ffmpeg": True,
                "python": True,
                "uv": True,
            },
            mpv_version=(0, 41, 0),
        )
        with mock.patch.object(installer, "_dep_is_fresh", return_value=False):
            results = installer.install_deps(env, dry_run=True)

        by_name = {r["name"]: r for r in results}
        # Everything already present stays "already installed"…
        self.assertEqual(by_name["mpv"]["status"], "ok")
        self.assertEqual(by_name["ffmpeg"]["status"], "ok")
        # …but the stale yt-dlp is requeued (dry run → planned, not run).
        self.assertEqual(by_name["yt-dlp"]["status"], "skipped")
        self.assertEqual(by_name["yt-dlp"]["detail"], "dry run")

    def test_install_deps_refresh_gate_respects_fresh_stamp(self):
        from deploy import installer

        env = Environment(
            os="linux",
            platform_key="ubuntu",
            installed={
                "mpv": True,
                "yt-dlp": True,
                "ffmpeg": True,
                "python": True,
                "uv": True,
            },
            mpv_version=(0, 41, 0),
        )
        with mock.patch.object(installer, "_dep_is_fresh", return_value=True):
            results = installer.install_deps(env, dry_run=True)

        by_name = {r["name"]: r for r in results}
        self.assertEqual(by_name["yt-dlp"]["status"], "ok")
        self.assertEqual(by_name["yt-dlp"]["detail"], "already installed")


    def test_deployer_refreshes_its_own_generated_stub(self):
        """A generated ytdl_path stub gets re-resolved; personal files never do."""
        import tempfile as tf_mod

        from deploy import deployer

        env = Environment(os="linux", platform_key="ubuntu")
        races = deployer._ytdl_path_candidates(env)
        self.assertIn(os.path.expanduser("~/.local/bin/yt-dlp"), races)
        self.assertIn("/usr/bin/yt-dlp", races)

        with tf_mod.TemporaryDirectory() as tmpdir:
            stub = os.path.join(tmpdir, "ytdl_hook.conf")

            # A stub the deployer itself generated (older standard path).
            with open(stub, "w", encoding="utf-8") as fh:
                fh.write("ytdl_path=/usr/bin/yt-dlp\n")
            self.assertTrue(deployer._ytdl_conf_is_refreshable(stub, env))

            # User customization (comments / extra options) is personal.
            with open(stub, "w", encoding="utf-8") as fh:
                fh.write("ytdl_path=/usr/bin/yt-dlp\n# keep my custom flags\n")
            self.assertFalse(deployer._ytdl_conf_is_refreshable(stub, env))

            # A non-standard single value (hand-rolled tooling) is personal.
            with open(stub, "w", encoding="utf-8") as fh:
                fh.write("ytdl_path=/opt/private/yt-dlp\n")
            self.assertFalse(deployer._ytdl_conf_is_refreshable(stub, env))

            # Missing file is reported as never for a refresh.
            self.assertFalse(
                deployer._ytdl_conf_is_refreshable(
                    os.path.join(tmpdir, "absent.conf"), env
                )
            )

    def test_resolver_prefers_local_bin_over_distro_package(self):
        from deploy import deployer

        with tempfile.TemporaryDirectory() as home:

            def fake_expanduser(path):
                # Windows Python prefers USERPROFILE over HOME, so patch the
                # expansion itself to keep the test host-independent.
                if path.startswith("~"):
                    return os.path.join(home, *path[2:].replace("\\", "/").split("/"))
                return path

            with mock.patch.object(
                deployer.os.path, "expanduser", side_effect=fake_expanduser
            ):
                env = Environment(os="linux", platform_key="ubuntu")
                fresh = os.path.join(home, ".local", "bin", "yt-dlp")
                os.makedirs(os.path.dirname(fresh), exist_ok=True)
                with open(fresh, "wb") as fh:
                    fh.write(b"#!/bin/sh\n")
                self.assertEqual(deployer._resolve_ytdl_path(env), fresh)

                # When the home binary is gone, resolution falls back to the
                # distro package (verified entry stays meaningful).
                os.remove(fresh)
                self.assertNotIn(home, deployer._resolve_ytdl_path(env))


class CachyOSOptimizedReposTests(unittest.TestCase):
    """pacman deps prefer the CachyOS x86-64-v3/v4 optimized builds."""

    CONF_TEMPLATE = """[options]
HoldPkg     = pacman glibc man
Architecture = auto

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist

[cachyos]
Include = /etc/pacman.d/cachyos-mirrorlist
"""

    def _ensure(
        self,
        tmpdir,
        tier="v3",
        conf_text=None,
        os_release_text='ID=cachyos\nPRETTY_NAME="CachyOS Linux"\n',
    ):
        from deploy import installer

        conf_path = os.path.join(tmpdir, "pacman.conf")
        with open(conf_path, "w", encoding="utf-8") as fh:
            fh.write(conf_text or self.CONF_TEMPLATE)
        pacman_d = os.path.join(tmpdir, "pacman.d")
        os.makedirs(pacman_d, exist_ok=True)
        for name in ("cachyos-mirrorlist", "cachyos-v3-mirrorlist", "cachyos-v4-mirrorlist"):
            with open(os.path.join(pacman_d, name), "w", encoding="utf-8") as fh:
                fh.write("Server = https://mirror.cachyos.org/repo/x86_64/$repo/os/$arch\n")

        env = Environment(os="linux", platform_key="arch")
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[:2] == ["sudo", "cp"]:
                shutil.copyfile(cmd[2], cmd[3])
            return True

        with (
            mock.patch.object(installer, "_x86_64_isa_level", return_value=tier),
            mock.patch.object(installer, "_run", side_effect=fake_run),
        ):
            ok = installer._ensure_cachyos_optimized_repos(
                env,
                conf_path=conf_path,
                os_release_text=os_release_text,
                pacman_d_dir=pacman_d,
            )
        return ok, calls, conf_path

    def test_isa_level_probe(self):
        import subprocess

        from deploy import installer

        def completed(stdout):
            return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=None)

        with mock.patch.object(
            installer.subprocess, "run", return_value=completed("  x86-64-v3 (supported, searched)\n  x86-64-v4 (supported, searched)\n")
        ):
            self.assertEqual(installer._x86_64_isa_level(), "v4")

        with mock.patch.object(
            installer.subprocess, "run", return_value=completed("  x86-64-v3 (supported, searched)\n")
        ):
            self.assertEqual(installer._x86_64_isa_level(), "v3")

        with mock.patch.object(installer.subprocess, "run", return_value=completed("")):
            self.assertEqual(installer._x86_64_isa_level(), "")

        with mock.patch.object(installer.subprocess, "run", side_effect=OSError("gone")):
            self.assertEqual(installer._x86_64_isa_level(), "")

    def test_v3_repos_enabled_on_cachyos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ok, calls, conf_path = self._ensure(tmpdir, tier="v3")

            self.assertTrue(ok)
            with open(conf_path, encoding="utf-8") as fh:
                text = fh.read()
            for section in ("[cachyos-v3]", "[cachyos-core-v3]", "[cachyos-extra-v3]"):
                self.assertIn(section, text)
            # tier repos go ahead of existing repos: first match wins in pacman
            self.assertLess(text.index("[cachyos-v3]"), text.index("[core]"))

            flat = [" ".join(c) for c in calls]
            self.assertTrue(any("cachyos-keyring" in s and "-S" in s for s in flat))
            self.assertTrue(any(c[-1] == "-Sy" for c in calls))
            self.assertTrue(any("cp" in s and ".mpv-config.bak" in s for s in flat))

    def test_idempotent_when_already_enabled(self):
        conf = self.CONF_TEMPLATE.replace(
            "[core]",
            "[cachyos-extra-v3]\nInclude = /etc/pacman.d/cachyos-v3-mirrorlist\n\n[core]",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ok, calls, _ = self._ensure(tmpdir, tier="v3", conf_text=conf)

            self.assertTrue(ok)
            self.assertEqual(calls, [])

    def test_skips_non_cachyos_hosts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ok, calls, conf_path = self._ensure(
                tmpdir, os_release_text='ID=arch\nPRETTY_NAME="Arch Linux"\n'
            )

            self.assertFalse(ok)
            self.assertEqual(calls, [])
            with open(conf_path, encoding="utf-8") as fh:
                self.assertNotIn("[cachyos-v3]", fh.read())

    def test_missing_include_file_aborts_cleanly(self):
        from deploy import installer

        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "pacman.conf")
            with open(conf_path, "w", encoding="utf-8") as fh:
                fh.write(self.CONF_TEMPLATE)
            env = Environment(os="linux", platform_key="arch")
            with (
                mock.patch.object(installer, "_x86_64_isa_level", return_value="v3"),
                mock.patch.object(installer, "_run", return_value=False),
            ):
                ok = installer._ensure_cachyos_optimized_repos(
                    env,
                    conf_path=conf_path,
                    os_release_text="ID=cachyos\n",
                    pacman_d_dir=os.path.join(tmpdir, "pacman.d"),
                )

            self.assertFalse(ok)
            with open(conf_path, encoding="utf-8") as fh:
                self.assertNotIn("[cachyos-v3]", fh.read())

    def test_non_arch_env_skipped(self):
        from deploy import installer

        env = Environment(os="linux", platform_key="ubuntu")
        with mock.patch.object(installer, "_x86_64_isa_level") as m_level:
            ok = installer._ensure_cachyos_optimized_repos(
                env, conf_path="irrelevant", os_release_text="ID=cachyos\n"
            )

        self.assertFalse(ok)
        m_level.assert_not_called()

    def test_pacman_hook_invoked_for_optimized_deps(self):
        from deploy import installer
        from deploy.registry import SYSTEM_DEPS

        env = Environment(os="linux", platform_key="arch")
        with (
            mock.patch.object(installer, "_ensure_cachyos_optimized_repos") as m_ensure,
            mock.patch.object(installer, "_run", return_value=True) as m_run,
        ):
            ok = installer._install_one("mpv", SYSTEM_DEPS["mpv"], env)

        self.assertTrue(ok)
        m_ensure.assert_called_once()
        self.assertIn("mpv", m_run.call_args[0][0])

    def test_all_pacman_deps_prefer_optimized_repo(self):
        from deploy.registry import SYSTEM_DEPS

        for name in ("mpv", "yt-dlp", "ffmpeg", "python", "aria2"):
            self.assertTrue(SYSTEM_DEPS[name]["arch"].get("prefer_optimized_repo"))


if __name__ == "__main__":
    unittest.main()
