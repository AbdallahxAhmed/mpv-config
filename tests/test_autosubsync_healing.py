import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy.deployer import (
    _find_binary,
    _migrate_autosubsync_conf,
    _migrate_autosubsync_patch,
    _resolve_autosubsync_paths,
)
from deploy.detector import Environment

SAMPLE_AUTOSUBSYNC_CONF = """# Absolute paths to the executables:

# 1. ffmpeg
ffmpeg_path=ffmpeg

# 2. ffsubsync
ffsubsync_path=ffsubsync

# 3. alass
alass_path=alass


# Preferred retiming tool. Allowed options: 'ffsubsync', 'alass', 'ask'.
audio_subsync_tool=alass
altsub_subsync_tool=ffsubsync

# User custom setting
overwrite_old_sub=no
"""


class TestAutosubsyncHealing(unittest.TestCase):
    def test_find_binary_probes_local_bin_on_posix(self):
        env = Environment(os="linux", platform_key="arch", distro="arch")
        with tempfile.TemporaryDirectory() as tmpdir:
            local_bin_file = Path(tmpdir) / "my_mock_tool"
            local_bin_file.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            local_bin_file.chmod(0o755)

            with mock.patch("shutil.which", return_value=None), mock.patch(
                "os.path.expanduser",
                side_effect=lambda p: str(tmpdir) if "~/.local/bin" in p else p,
            ):
                resolved = _find_binary("my_mock_tool", env)
                self.assertEqual(resolved, str(local_bin_file))

    def test_migrate_autosubsync_conf_surgically_updates_binary_paths(self):
        env = Environment(os="linux", platform_key="arch", distro="arch")
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = Path(tmpdir) / "autosubsync.conf"
            conf_path.write_text(SAMPLE_AUTOSUBSYNC_CONF, encoding="utf-8")

            with mock.patch(
                "deploy.deployer._resolve_autosubsync_paths",
                return_value=("/custom/bin/ffmpeg", "/custom/bin/ffsubsync", "/custom/bin/alass"),
            ):
                migrated = _migrate_autosubsync_conf(str(conf_path), env=env)
                self.assertTrue(migrated)

                content = conf_path.read_text(encoding="utf-8")
                self.assertIn("ffmpeg_path=/custom/bin/ffmpeg", content)
                self.assertIn("ffsubsync_path=/custom/bin/ffsubsync", content)
                self.assertIn("alass_path=/custom/bin/alass", content)
                self.assertIn("audio_subsync_tool=alass", content)
                self.assertIn("altsub_subsync_tool=ffsubsync", content)
                self.assertIn("overwrite_old_sub=no", content)

                # Re-running with same resolved paths returns False
                second_run = _migrate_autosubsync_conf(str(conf_path), env=env)
                self.assertFalse(second_run)

    def test_migrate_autosubsync_patch_applies_idempotently(self):
        sample_lua = """local function subprocess(args)
    return mp.command_native {
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        args = args
    }
end
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lua_path = Path(tmpdir) / "autosubsync.lua"
            lua_path.write_text(sample_lua, encoding="utf-8")

            patched = _migrate_autosubsync_patch(str(lua_path))
            self.assertTrue(patched)
            self.assertIn("capture_stderr = true", lua_path.read_text(encoding="utf-8"))

            second_pass = _migrate_autosubsync_patch(str(lua_path))
            self.assertFalse(second_pass)


if __name__ == "__main__":
    unittest.main()
