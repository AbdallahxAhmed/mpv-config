import os
import shutil
import tempfile
import unittest
from unittest import mock

from deploy.deployer import rollback_config


class TestRollback(unittest.TestCase):
    def test_same_drive_uses_move(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = os.path.join(tmpdir, "config")
            backup_dir = os.path.join(tmpdir, "backup")
            os.makedirs(config_dir, exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)

            with open(os.path.join(config_dir, "old.txt"), "w", encoding="utf-8") as f:
                f.write("old")
            with open(os.path.join(backup_dir, "mpv.conf"), "w", encoding="utf-8") as f:
                f.write("new")

            copytree_calls = []
            move_calls = []
            real_copytree = shutil.copytree
            real_move = shutil.move

            def record_copytree(src, dst, *args, **kwargs):
                copytree_calls.append((src, dst))
                return real_copytree(src, dst, *args, **kwargs)

            def record_move(src, dst, *args, **kwargs):
                move_calls.append((src, dst))
                return real_move(src, dst, *args, **kwargs)

            with mock.patch("deploy.deployer.shutil.copytree", side_effect=record_copytree), \
                 mock.patch("deploy.deployer.shutil.move", side_effect=record_move):
                rollback_config(config_dir, backup_path=backup_dir)

            self.assertFalse(any(".rollback.tmp." in src for src, _ in copytree_calls))
            self.assertTrue(any(".rollback.tmp." in src for src, _ in move_calls))


if __name__ == "__main__":
    unittest.main()
