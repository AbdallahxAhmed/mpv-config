"""Spec 005: the deployer applies the uosc playlist-reorder patch.

The patch runs on the prepared copy, before replace_items, for install
(deploy()) and update (cmd_update). The uosc pin lives here too (plan Test
Strategy "Registry").
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import deployer, registry
from deploy import transaction as tx
from deploy.detector import Environment
from tools import patch_uosc_playlist_reorder as patcher

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_MENU = REPO_ROOT / "tests" / "fixtures" / "uosc-5.13.0" / "elements" / "Menu.lua"
UPSTREAM = FIXTURE_MENU.read_bytes()
PATCHED = patcher.patch_bytes(UPSTREAM)
NOT_PINNED = UPSTREAM.replace(b"-- Handles all key", b"-- handles all key")
MENU = Path("scripts", "uosc", "elements", "Menu.lua")
ROW = "uosc-playlist-reorder-patch"
LOCKFILE = {"scripts": {"uosc": {"version": "5.13.0"}}}


class RegistryPinTests(unittest.TestCase):
    def test_uosc_is_pinned_to_the_patched_release(self):
        (uosc,) = [entry for entry in registry.SCRIPTS if entry["name"] == "uosc"]
        self.assertEqual("5.13.0", uosc["source"]["pin"])


class DeployerTestCase(unittest.TestCase):
    """A scratch home, config dir and staging tree; slow side effects mocked."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mpv-reorder-deploy-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.staging = self.root / "staging"
        self.config_dir = self.root / "home" / "mpv"
        self.env = Environment(
            os="linux",
            distro="arch",
            platform_key="linux",
            display="wayland",
            gpu_vendor="nvidia",
            config_dir=str(self.config_dir),
        )
        home = str(self.root / "home")
        self.ui = mock.MagicMock()
        for patch in (
            mock.patch.dict(
                os.environ,
                {
                    "HOME": home,
                    "XDG_DATA_HOME": os.path.join(home, "data"),
                    "XDG_CACHE_HOME": os.path.join(home, "cache"),
                    "XDG_CONFIG_HOME": os.path.join(home, "config"),
                },
            ),
            mock.patch.object(deployer, "_resolve_preferred_font", return_value="Tahoma"),
            mock.patch.object(deployer, "_sync_linux_uosc_fonts"),
            mock.patch.object(deployer, "_deploy_linux_fontconfig_conf"),
            mock.patch.object(deployer, "ui", self.ui),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def stage(self, menu=UPSTREAM):
        """A staging tree as fetch_all leaves it; menu=None stages no uosc."""
        for folder, name in (("scripts", "x.lua"), ("shaders", "x.glsl"), ("fonts", "x.ttf")):
            (self.staging / folder).mkdir(parents=True, exist_ok=True)
            (self.staging / folder / name).write_text("x", encoding="utf-8")
        if menu is not None:
            target = self.staging / MENU
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(menu)

    def live(self, menu):
        target = self.config_dir / MENU
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(menu)

    def live_menu(self):
        return (self.config_dir / MENU).read_bytes()

    def row(self, results):
        (row,) = [r for r in results if r["name"] == ROW]
        return row


class InstallTests(DeployerTestCase):
    """The real deploy() (it also guards the removed local `Path` import)."""

    def deploy(self, **kwargs):
        return deployer.deploy(str(self.staging), self.env, str(REPO_ROOT), **kwargs)

    def test_staged_uosc_is_patched_before_the_commit(self):
        self.stage()
        order = []
        real_patch, real_replace = deployer._patch_prepared_uosc, tx.replace_items
        with (
            mock.patch.object(
                deployer,
                "_patch_prepared_uosc",
                side_effect=lambda *a: order.append("patch") or real_patch(*a),
            ),
            mock.patch.object(
                tx,
                "replace_items",
                side_effect=lambda *a, **k: order.append("replace") or real_replace(*a, **k),
            ),
        ):
            results = self.deploy(lockfile=LOCKFILE)
        self.assertEqual(["patch", "replace"], order)
        self.assertEqual(
            {"name": ROW, "status": "ok", "detail": "patched (staged, 5.13.0)"}, self.row(results)
        )
        self.assertEqual(PATCHED, self.live_menu())
        manifest = json.loads((self.config_dir / tx.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(
            patcher.hashlib.sha256(PATCHED).hexdigest(),
            manifest["managed_files"]["scripts/uosc/elements/Menu.lua"],
        )

    def test_nothing_staged_live_upstream_is_patched(self):
        self.stage(menu=None)
        self.live(UPSTREAM)
        results = self.deploy()
        self.assertEqual("patched (live, unknown)", self.row(results)["detail"])
        self.assertEqual(PATCHED, self.live_menu())

    def test_nothing_staged_live_patched_stays_as_it_is(self):
        self.stage(menu=None)
        self.live(PATCHED)
        results = self.deploy()
        self.assertEqual("already patched (live, unknown)", self.row(results)["detail"])
        self.assertEqual(PATCHED, self.live_menu())

    def test_no_uosc_at_all_is_skipped(self):
        self.stage(menu=None)
        results = self.deploy()
        self.assertEqual(
            {
                "name": ROW,
                "status": "skipped",
                "detail": "uosc not present in this deployment; nothing to patch",
            },
            self.row(results),
        )

    def test_hash_mismatch_is_a_warning_and_the_fetched_bytes_are_kept(self):
        self.stage(NOT_PINNED)
        results = self.deploy(lockfile=LOCKFILE)
        row = self.row(results)
        self.assertEqual("warn", row["status"])
        self.assertIn("does not match uosc 5.13.0", row["detail"])
        self.assertFalse([r for r in results if r.get("status") == "failed"])
        self.assertEqual(NOT_PINNED, self.live_menu())

    def test_failed_verification_restores_the_live_scripts(self):
        self.stage()
        self.live(b"-- the user's previous uosc\n")
        with self.assertRaises(RuntimeError):
            self.deploy(verify_callback=mock.Mock(side_effect=RuntimeError("mpv exit 3")))
        self.assertEqual(b"-- the user's previous uosc\n", self.live_menu())


class UpdateTests(DeployerTestCase):
    """deployer.main(["--update"]) with the real tx.update_assets."""

    def setUp(self):
        super().setUp()
        self.fetched = UPSTREAM
        self.audit_log = mock.MagicMock()
        fetch_results = [{"name": s["name"], "status": "ok"} for s in deployer.SCRIPTS]
        fetch_results.append({"name": deployer.SHADERS["name"], "status": "ok"})

        def fetch_all(scripts, shaders, staging):
            self.staging = Path(staging)
            self.stage(self.fetched)
            return fetch_results, LOCKFILE

        for patch in (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "fetch_all", side_effect=fetch_all),
            mock.patch.object(deployer, "_audit_log_for", return_value=self.audit_log),
            mock.patch.object(deployer, "display_plan"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.live(b"-- the user's previous uosc\n")

    def update(self):
        return deployer.main(["--update", "--yes", "--keep-conf"])

    def summary_rows(self):
        return [row for call in self.ui.summary.call_args_list for row in call.args[0]]

    def test_update_patches_before_the_swap_and_a_second_run_changes_nothing(self):
        order = []
        real_patch, real_replace = deployer._patch_prepared_uosc, tx.replace_items
        with (
            mock.patch.object(
                deployer,
                "_patch_prepared_uosc",
                side_effect=lambda *a: order.append("patch") or real_patch(*a),
            ),
            mock.patch.object(
                tx,
                "replace_items",
                side_effect=lambda *a, **k: order.append("replace") or real_replace(*a, **k),
            ),
        ):
            self.assertEqual(0, self.update())
        self.assertEqual(["patch", "replace"], order)
        self.assertEqual(PATCHED, self.live_menu())
        self.assertIn(mock.call(f"{ROW}: patched (staged, 5.13.0)"), self.ui.success.call_args_list)
        self.assertEqual(0, self.update())
        self.assertEqual(PATCHED, self.live_menu())

    def test_hash_mismatch_is_shown_once_in_the_warnings_block(self):  # SC-008
        self.fetched = NOT_PINNED
        self.assertEqual(0, self.update())
        warn_rows = [r for r in self.summary_rows() if r["name"] == ROW]
        self.assertEqual(1, len(warn_rows))
        self.assertEqual("warn", warn_rows[0]["status"])
        said = " ".join(str(c) for c in self.ui.warn.call_args_list + self.ui.info.call_args_list)
        self.assertNotIn(ROW, said)
        self.assertEqual(NOT_PINNED, self.live_menu())

    def test_a_failed_swap_restores_the_live_scripts(self):
        real_replace = os.replace

        def failing_replace(src, dst, *args, **kwargs):
            if ".mpv-prepared-" in str(src) and os.path.basename(str(src)) == "shaders":
                raise OSError("disk full")
            return real_replace(src, dst, *args, **kwargs)

        with mock.patch.object(tx.os, "replace", side_effect=failing_replace):
            self.assertEqual(1, self.update())
        self.ui.error.assert_called_once_with("Fatal error: disk full")
        self.assertEqual(b"-- the user's previous uosc\n", self.live_menu())


if __name__ == "__main__":
    unittest.main()
