import os
import tempfile
import unittest
from unittest import mock

from deploy.deployer import rollback_config


class TestRollback(unittest.TestCase):
    def test_rollback_swaps_live_paths_by_rename(self):
        """Rollback must swap entries by rename, never by copying the live tree.

        The previous implementation staged a copy under a `.rollback.tmp.`
        directory, so the old test asserted that filename. The transaction
        engine renames instead, so this asserts the observable property: a
        rename lands the restored file directly in the live config directory.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = os.path.join(tmpdir, "config")
            backup_dir = os.path.join(tmpdir, "backup")
            os.makedirs(config_dir, exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)

            with open(os.path.join(config_dir, "old.txt"), "w", encoding="utf-8") as f:
                f.write("old")
            with open(os.path.join(backup_dir, "mpv.conf"), "w", encoding="utf-8") as f:
                f.write("new")

            renamed_into_config = []
            real_replace = os.replace

            def record_replace(src, dst, *args, **kwargs):
                if os.path.dirname(os.path.abspath(dst)) == os.path.abspath(config_dir):
                    renamed_into_config.append(os.path.basename(dst))
                return real_replace(src, dst, *args, **kwargs)

            with mock.patch("deploy.transaction.os.replace", side_effect=record_replace):
                result = rollback_config(config_dir, backup_path=backup_dir)

            self.assertEqual(result["status"], "ok")
            self.assertIn("mpv.conf", renamed_into_config)

            with open(os.path.join(config_dir, "mpv.conf"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "new")

            # The pre-rollback state must be retained, not destroyed.
            siblings = os.listdir(tmpdir)
            self.assertTrue(
                any(name.startswith("config.backup.") for name in siblings),
                f"no pre-rollback safety backup was kept: {siblings}",
            )

    def test_rollback_creates_missing_config_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = os.path.join(tmpdir, "config")
            backup_dir = os.path.join(tmpdir, "backup")
            os.makedirs(backup_dir, exist_ok=True)
            with open(os.path.join(backup_dir, "mpv.conf"), "w", encoding="utf-8") as f:
                f.write("restored")

            result = rollback_config(config_dir, backup_path=backup_dir)
            self.assertEqual(result["status"], "ok")
            self.assertTrue(os.path.isfile(os.path.join(config_dir, "mpv.conf")))

    def test_rollback_failure_recovers_and_preserves_git_dir(self):
        """A failed rollback must roll itself back and leave `.git` alone.

        The old test injected the failure into `deploy.deployer.shutil.move`,
        which the rewritten path no longer calls, so the failure was never
        raised at all. The injection now targets the rename the engine really
        performs, and additionally asserts the original file is restored.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = os.path.join(tmpdir, "config")
            backup_dir = os.path.join(tmpdir, "backup")
            os.makedirs(config_dir, exist_ok=True)
            os.makedirs(os.path.join(config_dir, ".git"), exist_ok=True)
            with open(os.path.join(config_dir, "old.txt"), "w", encoding="utf-8") as f:
                f.write("old")
            os.makedirs(backup_dir, exist_ok=True)
            with open(os.path.join(backup_dir, "mpv.conf"), "w", encoding="utf-8") as f:
                f.write("new")

            state = {"failed": False}
            real_replace = os.replace

            def flaky_replace(src, dst, *args, **kwargs):
                # Fail the first rename into the live config directory, then
                # let the engine's own recovery renames proceed normally.
                if (not state["failed"]
                        and os.path.dirname(os.path.abspath(dst)) == os.path.abspath(config_dir)):
                    state["failed"] = True
                    raise RuntimeError("boom")
                return real_replace(src, dst, *args, **kwargs)

            with mock.patch("deploy.transaction.os.replace", side_effect=flaky_replace):
                with self.assertRaises(RuntimeError):
                    rollback_config(config_dir, backup_path=backup_dir)

            self.assertTrue(state["failed"], "the injected failure never fired")
            self.assertTrue(os.path.isdir(os.path.join(config_dir, ".git")))
            with open(os.path.join(config_dir, "old.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "old")


if __name__ == "__main__":
    unittest.main()
