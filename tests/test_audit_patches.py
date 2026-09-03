import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
