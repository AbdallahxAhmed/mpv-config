"""Filesystem-level tests for the ``--rollback`` and ``--uninstall`` actions.

These use real directories (scratch space only) and the real ``tx`` / ``AuditLog``
code, with just detection and the console patched. They pin down behaviour that
mocked tests cannot: what ends up on disk, and what is deliberately left alone.
"""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from deploy import deployer

POSIX_ONLY = unittest.skipIf(os.name == "nt", "the install.sh launcher and venv are POSIX-only")


class ManagementCommandTestCase(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.config = self.root / "config" / "mpv"
        for directory in (self.home, self.data, self.config):
            directory.mkdir(parents=True)
        (self.config / "marker.txt").write_text("live", encoding="utf-8")
        self.env = SimpleNamespace(os="linux", config_dir=str(self.config))

        environ = {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "XDG_DATA_HOME": str(self.data),
        }
        patchers = [
            mock.patch.dict(os.environ, environ),
            mock.patch.object(deployer, "detect", autospec=True, return_value=self.env),
            mock.patch.object(
                deployer, "_is_interactive_session", autospec=True, return_value=False
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        ui_patcher = mock.patch.object(deployer, "ui", autospec=True)
        self.ui = ui_patcher.start()
        self.addCleanup(ui_patcher.stop)

    def make_backup(self, suffix, marker, mtime):
        backup = self.config.parent / f"mpv.backup.{suffix}"
        backup.mkdir()
        (backup / "marker.txt").write_text(marker, encoding="utf-8")
        os.utime(backup, (mtime, mtime))
        return backup

    def live_marker(self):
        return (self.config / "marker.txt").read_text(encoding="utf-8")

    def listing(self):
        return sorted(os.listdir(self.config.parent))

    def warnings(self):
        return " ".join(str(call.args[0]) for call in self.ui.warn.call_args_list)


class RollbackTests(ManagementCommandTestCase):
    def setUp(self):
        super().setUp()
        self.old = self.make_backup("20260101_000000", "old", 1_000_000)
        self.new = self.make_backup("20260102_000000", "new", 2_000_000)

    def test_a_directory_that_is_not_one_of_the_backups_is_refused(self):
        elsewhere = self.root / "elsewhere" / "mpv.backup.lookalike"
        elsewhere.mkdir(parents=True)
        (elsewhere / "marker.txt").write_text("fake", encoding="utf-8")
        sibling = self.config.parent / "documents"
        sibling.mkdir()
        (sibling / "marker.txt").write_text("fake", encoding="utf-8")
        for name, target in (
            ("right name, wrong place", elsewhere),
            ("sibling that is not a backup", sibling),
            ("the live config itself", self.config),
        ):
            with self.subTest(name):
                before = self.listing()
                self.assertEqual(deployer.main([f"--rollback={target}"]), 1)
                self.assertEqual(self.live_marker(), "live")
                self.assertEqual(self.listing(), before)  # no safety snapshot, nothing created
                self.assertIn("Not a backup", self.ui.error.call_args.args[0])

    def test_dry_run_validates_the_path_too(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.assertEqual(deployer.main([f"--rollback={elsewhere}", "--dry-run"]), 1)
        self.assertEqual(deployer.main([f"--rollback={self.old}", "--dry-run"]), 0)
        self.assertEqual(self.live_marker(), "live")

    def test_a_backup_can_be_named_by_its_full_path(self):
        before = self.listing()
        self.assertEqual(deployer.main([f"--rollback={self.old}"]), 0)
        self.assertEqual(self.live_marker(), "old")
        self.assertEqual(len(self.listing()), len(before) + 1)  # pre-rollback safety snapshot

    def test_a_backup_can_be_named_by_its_bare_name(self):
        self.assertEqual(deployer.main([f"--rollback={self.old.name}"]), 0)
        self.assertEqual(self.live_marker(), "old")

    def test_without_an_argument_the_newest_backup_is_restored(self):
        self.assertEqual(deployer.main(["--rollback"]), 0)
        self.assertEqual(self.live_marker(), "new")

    def test_the_error_lists_the_backups_that_can_be_chosen(self):
        self.assertEqual(deployer.main([f"--rollback={self.root}"]), 1)
        listed = " ".join(str(call.args[0]) for call in self.ui.info.call_args_list)
        self.assertIn(self.new.name, listed)
        self.assertIn(self.old.name, listed)


class UninstallTests(ManagementCommandTestCase):
    def make_launcher_dir(self):
        launcher_dir = self.home / ".local" / "bin"
        launcher_dir.mkdir(parents=True)
        return launcher_dir / "mpv-config"

    def make_private_venv(self):
        venv = self.data / "mpv-config" / "venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        target = venv / "bin" / "mpv-config"
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        return venv, target

    def test_an_unrelated_launcher_file_is_left_alone(self):
        launcher = self.make_launcher_dir()
        launcher.write_text("my own script", encoding="utf-8")
        self.assertEqual(deployer.main(["--uninstall"]), 0)
        self.assertEqual(launcher.read_text(encoding="utf-8"), "my own script")
        self.assertIn("install.sh", self.warnings())

    @POSIX_ONLY
    def test_the_launcher_symlink_created_by_install_sh_is_removed(self):
        launcher = self.make_launcher_dir()
        _, target = self.make_private_venv()
        launcher.symlink_to(target)
        self.assertEqual(deployer.main(["--uninstall"]), 0)
        self.assertFalse(os.path.lexists(launcher))

    @POSIX_ONLY
    def test_a_symlink_owned_by_another_tool_is_left_alone(self):
        launcher = self.make_launcher_dir()
        other = self.root / "pipx" / "mpv-config"
        other.parent.mkdir()
        other.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.symlink_to(other)
        self.assertEqual(deployer.main(["--uninstall"]), 0)
        self.assertTrue(os.path.islink(launcher))
        self.assertIn("install.sh", self.warnings())

    def test_purge_config_leaves_nothing_behind_but_keeps_a_backup(self):
        self.assertEqual(deployer.main(["--uninstall", "--purge-config"]), 0)
        self.assertFalse(os.path.lexists(self.config))  # the audit log must not resurrect it
        (backup,) = deployer.list_backups(str(self.config))
        self.assertEqual((Path(backup) / "marker.txt").read_text(encoding="utf-8"), "live")

    def test_remove_install_dir_removes_the_deploy_dir_and_the_private_venv(self):
        deploy_dir = self.home / ".mpv-config-deploy"
        deploy_dir.mkdir()
        (deploy_dir / "file.txt").write_text("x", encoding="utf-8")
        venv, _ = self.make_private_venv()
        self.assertEqual(deployer.main(["--uninstall", "--remove-install-dir"]), 0)
        self.assertFalse(deploy_dir.exists())
        self.assertFalse(venv.exists())
        self.assertFalse(venv.parent.exists())  # the now-empty data directory goes too

    def test_remove_install_dir_dry_run_removes_nothing(self):
        deploy_dir = self.home / ".mpv-config-deploy"
        deploy_dir.mkdir()
        venv, _ = self.make_private_venv()
        self.assertEqual(deployer.main(["--uninstall", "--remove-install-dir", "--dry-run"]), 0)
        self.assertTrue(deploy_dir.exists())
        self.assertTrue(venv.exists())
        shown = " ".join(str(call.args[0]) for call in self.ui.info.call_args_list)
        self.assertIn("private virtual environment", shown)

    def test_a_venv_directory_that_is_not_a_virtualenv_is_not_touched(self):
        keep = self.data / "mpv-config" / "venv" / "keep.txt"
        keep.parent.mkdir(parents=True)
        keep.write_text("not a venv", encoding="utf-8")
        self.assertEqual(deployer.main(["--uninstall", "--remove-install-dir"]), 0)
        self.assertTrue(keep.exists())

    def test_the_private_venv_is_kept_unless_asked_for(self):
        venv, _ = self.make_private_venv()
        self.assertEqual(deployer.main(["--uninstall"]), 0)
        self.assertTrue(venv.exists())


if __name__ == "__main__":
    unittest.main()
