"""Offline, temporary-directory failure-injection tests; no installs/network."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from deploy import transaction as tx


def put(root, name, content="old"):
    path = Path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def tree(root):
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(current, name)
            relative = str(path.relative_to(root))
            if path.is_symlink():
                result[relative] = ("link", os.readlink(path))
            elif path.is_file():
                result[relative] = ("file", path.read_bytes())
            else:
                result[relative] = ("dir",)
    return result


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "config"
        self.stage = self.root / "stage"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for name in tx.ASSET_DIRS:
            put(self.stage, name + "/managed.txt", "new")
            put(self.config, name + "/managed.txt", "old")
        put(self.config, "scripts/custom.lua", "user custom")
        for name in ("mpv.conf", "mpv.conf.user", "input.conf", "script-opts/user.conf", ".git/config"):
            put(self.config, name, "preserved " + name)
        put(self.config, tx.MANIFEST, '{"old":true}')
        put(self.repo, "scripts/managed.txt", "vendored")

    def update(self):
        return tx.update_assets(str(self.config), str(self.stage), str(self.repo), {"scripts": {}})

    def make_legacy_links(self):
        deployed = self.config / "deployed"
        deployed.mkdir()
        try:
            for name in tx.ASSET_DIRS:
                os.replace(self.config / name, deployed / name)
                (self.config / name).symlink_to(deployed / name, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"OS does not permit symlink creation: {exc}")

    def test_update_preserves_custom_files_and_configs_and_vendored_precedence(self):
        before = tree(self.config)
        backup = self.update()
        self.assertEqual((self.config / "scripts/custom.lua").read_text(), "user custom")
        self.assertEqual((self.config / "scripts/managed.txt").read_text(), "vendored")
        for name, value in before.items():
            if name.startswith(("mpv.conf", "input.conf", "script-opts", ".git")):
                self.assertEqual(tree(self.config)[name], value)
        self.assertTrue(Path(backup).is_dir())
        self.assertEqual(Path(backup, "scripts/managed.txt").read_text(), "old")
        manifest = json.loads((self.config / tx.MANIFEST).read_text())
        self.assertIn("scripts/managed.txt", manifest["vendored_files"])
        self.assertNotIn("scripts/custom.lua", manifest["managed_files"])
        self.assertEqual(manifest["managed_files"]["scripts/managed.txt"], manifest["vendored_files"]["scripts/managed.txt"])

    def test_repeat_update_and_backup_names_are_unique(self):
        first, second = self.update(), self.update()
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).is_dir())
        self.assertEqual((self.config / "scripts/custom.lua").read_text(), "user custom")

    def test_legacy_links_become_real_dirs_without_changing_old_targets(self):
        self.make_legacy_links()
        previous = tree(self.config / "deployed")
        self.update()
        self.assertFalse((self.config / "scripts").is_symlink())
        self.assertEqual(tree(self.config / "deployed"), previous)

    def test_recovery_at_every_rename_before_and_after_failure(self):
        # Four managed roots, two renames apiece. Exercise interrupted syscalls
        # both before mutation and after a successful rename returns to Python.
        for legacy in (False, True):
            for after in (False, True):
                for failure_at in range(1, 9):
                    for error_type in (OSError, KeyboardInterrupt):
                        with self.subTest(legacy=legacy, after=after, step=failure_at, error=error_type):
                            with tempfile.TemporaryDirectory(dir=self.root) as fixture:
                                old_config = self.config
                                cloned = Path(fixture, "config")
                                shutil.copytree(self.config, cloned)
                                self.config = cloned
                                try:
                                    if legacy:
                                        self.make_legacy_links()
                                    before = tree(self.config)
                                    real_replace = os.replace
                                    calls = 0
                                    def fail_once(src, dst):
                                        nonlocal calls
                                        calls += 1
                                        if calls == failure_at:
                                            if after:
                                                real_replace(src, dst)
                                            raise error_type("injected rename failure")
                                        return real_replace(src, dst)
                                    with mock.patch.object(tx.os, "replace", side_effect=fail_once):
                                        with self.assertRaises(error_type):
                                            self.update()
                                    self.assertEqual(tree(self.config), before)
                                finally:
                                    self.config = old_config

    def test_missing_paths_and_missing_manifest_restored(self):
        shutil.rmtree(self.config / "fonts")
        (self.config / tx.MANIFEST).unlink()
        before = tree(self.config)
        real_replace = os.replace
        def fail_manifest(src, dst):
            if str(src).endswith(tx.MANIFEST):
                raise OSError("manifest commit failure")
            return real_replace(src, dst)
        with mock.patch.object(tx.os, "replace", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                self.update()
        self.assertEqual(tree(self.config), before)

    def test_preparation_and_manifest_write_failures_do_not_mutate_live_config(self):
        before = tree(self.config)
        with mock.patch.object(tx, "_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.update()
        self.assertEqual(tree(self.config), before)
        with mock.patch.object(tx, "copy_overlay", side_effect=OSError("copy failed")):
            with self.assertRaises(OSError):
                self.update()
        self.assertEqual(tree(self.config), before)

    def test_failed_recovery_keeps_previous_paths_and_journal(self):
        real_replace = os.replace
        def fail_commit_and_recovery(src, dst):
            if str(src).endswith("shaders") and ".mpv-prepared-" in str(src):
                raise OSError("commit failure")
            if ".recovery-" in str(src) and f"{os.sep}old{os.sep}" in str(src):
                raise OSError("recovery failure")
            return real_replace(src, dst)
        with mock.patch.object(tx.os, "replace", side_effect=fail_commit_and_recovery):
            with self.assertRaises(tx.RecoveryError) as caught:
                self.update()
        leftovers = list(self.root.glob(".config.recovery-*"))
        self.assertEqual(len(leftovers), 1)
        self.assertIn(str(leftovers[0]), str(caught.exception))
        self.assertTrue((leftovers[0] / "journal.json").is_file())
        self.assertEqual((leftovers[0] / "old/scripts/managed.txt").read_text(), "old")
        self.assertTrue(list(self.root.glob("config.backup.*")))

    def test_unsafe_nested_symlink_fails_before_changes(self):
        outside = put(self.root, "outside/untouched.txt", "external")
        try:
            (self.config / "scripts/link").symlink_to(outside)
        except OSError as exc:
            self.skipTest(str(exc))
        before = tree(self.config)
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual(tree(self.config), before)
        self.assertEqual(outside.read_text(), "external")

    def test_unmanaged_top_level_link_is_refused(self):
        outside = self.root / "outside"
        put(outside, "untouched.txt")
        shutil.rmtree(self.config / "scripts")
        try:
            (self.config / "scripts").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual((outside / "untouched.txt").read_text(), "old")

    def test_empty_required_staging_and_overlap_are_refused(self):
        (self.stage / "fonts/managed.txt").unlink()
        before = tree(self.config)
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual(tree(self.config), before)
        with self.assertRaises(ValueError):
            tx.assert_disjoint(str(self.config), str(self.config / "nested"))

    def test_lock_is_outside_config_and_never_restored_or_stolen(self):
        lock = self.root / ".config.mpv-config.lock"
        with tx.operation_lock(str(self.config)):
            self.assertTrue(lock.is_file())
            with self.assertRaises(RuntimeError):
                with tx.operation_lock(str(self.config)):
                    self.fail("acquired live lock")
            shutil.rmtree(self.config)
            self.assertTrue(lock.is_file())
        self.assertFalse(lock.exists())

    def test_replaced_lock_is_not_removed(self):
        lock = self.root / ".config.mpv-config.lock"
        with tx.operation_lock(str(self.config)):
            lock.unlink()
            lock.write_text('{"token":"another-owner"}')
        self.assertTrue(lock.is_file())

    def test_rollback_missing_config_preserves_git_and_ignores_old_lock(self):
        backup = self.root / "restore-source"
        put(backup, "mpv.conf", "restored")
        put(backup, ".git/config", "must not restore")
        put(backup, ".mpv-config.lock", "stale")
        old_git = (self.config / ".git/config").read_bytes()
        tx.restore_snapshot(str(self.config), str(backup))
        self.assertEqual((self.config / "mpv.conf").read_text(), "restored")
        self.assertEqual((self.config / ".git/config").read_bytes(), old_git)
        self.assertFalse((self.config / ".mpv-config.lock").exists())
        shutil.rmtree(self.config)
        tx.restore_snapshot(str(self.config), str(backup))
        self.assertEqual((self.config / "mpv.conf").read_text(), "restored")

    def test_rollback_dry_run_and_refused_overlap_are_read_only(self):
        before = tree(self.root)
        tx.restore_snapshot(str(self.config), str(self.stage), dry_run=True)
        self.assertEqual(tree(self.root), before)
        with self.assertRaises(ValueError):
            tx.restore_snapshot(str(self.config), str(self.config))
        self.assertEqual(tree(self.root), before)


if __name__ == "__main__":
    unittest.main()
