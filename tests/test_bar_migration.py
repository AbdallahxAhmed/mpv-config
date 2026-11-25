"""Tests for spec 006 bar migration (T007-T010).

Covers pure text operations (update_controls, drop_theme_lines, pending_changes)
and deployer integration (fresh install, update, backup before change, and dry-run).
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import bar_migration, deployer
from deploy.detector import Environment

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_CONFIG_DIR = REPO_ROOT / "config"
SPEC_CONTROLS = (
    "prev,play-pause,next,space,<video,audio>speed,space,"
    "command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,"
    "button:audio-tracks,<has_many_video>video,<stream>button:stream-quality,items,"
    "command:menu:script-message-to more_menu open?More,fullscreen"
)
OLD_CONTROLS = (
    "menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,"
    "gap,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,"
    "button:audio-tracks,<has_many_video>video,<has_many_edition>editions,"
    "<stream>button:stream-quality,<stream>button:download-video,button:stable-volume,"
    "gap,space,<video,audio>speed,space,shuffle,loop-playlist,loop-file,gap,prev,items,next,gap,fullscreen"
)
LOCKFILE = {"scripts": {"uosc": {"version": "5.13.0"}}}
# First lines of the P5 files (a60b5a8); every P1-P5 version starts the same way.
P5_UI_APPEARANCE_LUA = (
    "-- scripts/ui_appearance.lua: applies chosen UI style and look at load and opens More menu\n"
    "local utils = require 'mp.utils'\n"
)
P5_LOOKS_LUA = (
    "-- scripts/modules/looks.lua: pure appearance logic and look configurations (spec 006)\n"
    "local M = {}\nreturn M\n"
)


class PureTextMigrationTests(unittest.TestCase):
    def test_controls_line_reads_from_uosc_conf(self):
        line = bar_migration.controls_line(REPO_CONFIG_DIR)
        self.assertEqual(SPEC_CONTROLS, line)

    def test_update_controls_preserves_other_keys_comments_crlf_and_bom(self):
        shipped = SPEC_CONTROLS
        original = (
            "\ufeff# Custom header comment\r\n"
            "timeline_style=bar\r\n"
            "# Controls setting\r\n"
            "  controls  =  " + OLD_CONTROLS + "\r\n"
            "volume_size=40\r\n"
        )
        updated, changed = bar_migration.update_controls(original, shipped)
        self.assertTrue(changed)
        expected = (
            "\ufeff# Custom header comment\r\n"
            "timeline_style=bar\r\n"
            "# Controls setting\r\n"
            "  controls=" + shipped + "\r\n"
            "volume_size=40\r\n"
        )
        self.assertEqual(expected, updated)

    def test_update_controls_replaces_hand_edited_controls(self):
        shipped = SPEC_CONTROLS
        custom = "controls=custom,toolbar,items\nother=1\n"
        updated, changed = bar_migration.update_controls(custom, shipped)
        self.assertTrue(changed)
        self.assertEqual("controls=" + shipped + "\nother=1\n", updated)

    def test_update_controls_second_run_is_unchanged(self):
        shipped = SPEC_CONTROLS
        text = "controls=" + shipped + "\nother=1\n"
        updated, changed = bar_migration.update_controls(text, shipped)
        self.assertFalse(changed)
        self.assertEqual(text, updated)

    def test_update_controls_no_controls_line_is_unchanged(self):
        shipped = SPEC_CONTROLS
        text = "# Only comments\nvolume=50\n"
        updated, changed = bar_migration.update_controls(text, shipped)
        self.assertFalse(changed)
        self.assertEqual(text, updated)

    def test_drop_theme_lines_removes_both_lines_and_leaves_others(self):
        original = (
            "# Main options\n"
            "vo=gpu-next\n"
            "script-opts-append        = uosc-border_radius=10\n"
            "script-opts-append        = uosc-something_else=20\n"
            "script-opts-append = uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80\r\n"
            "hwdec=auto\n"
        )
        updated, count = bar_migration.drop_theme_lines(original)
        self.assertEqual(2, count)
        expected = (
            "# Main options\n"
            "vo=gpu-next\n"
            "script-opts-append        = uosc-something_else=20\n"
            "hwdec=auto\n"
        )
        self.assertEqual(expected, updated)

    def test_drop_theme_lines_when_none_present(self):
        original = "vo=gpu-next\nscript-opts-append=uosc-foo=bar\n"
        updated, count = bar_migration.drop_theme_lines(original)
        self.assertEqual(0, count)
        self.assertEqual(original, updated)


class DeployerMigrationIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mpv-bar-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config_dir = self.root / "home" / "mpv"
        self.staging = self.root / "staging"
        home = str(self.root / "home")
        self.env = Environment(
            os="linux",
            distro="arch",
            platform_key="linux",
            display="wayland",
            gpu_vendor="nvidia",
            config_dir=str(self.config_dir),
        )
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

    def stage_minimal(self):
        for folder in ("scripts", "shaders", "fonts"):
            d = self.staging / folder
            d.mkdir(parents=True, exist_ok=True)
            (d / "dummy").write_text("dummy", encoding="utf-8")

    def test_fresh_install_deploys_spec_controls_line(self):
        self.stage_minimal()
        deployer.deploy(str(self.staging), self.env, str(REPO_ROOT), lockfile=LOCKFILE)
        uosc_conf = self.config_dir / "script-opts" / "uosc.conf"
        self.assertTrue(uosc_conf.is_file())
        text = uosc_conf.read_text(encoding="utf-8")
        controls = [
            line.partition("=")[2] for line in text.splitlines() if line.startswith("controls=")
        ]
        self.assertEqual([SPEC_CONTROLS], controls)

    def test_update_over_old_config_migrates_files_and_is_idempotent(self):
        self.stage_minimal()
        # Seed an existing config
        opts_dir = self.config_dir / "script-opts"
        opts_dir.mkdir(parents=True, exist_ok=True)
        old_uosc = (
            "# uosc.conf\n"
            "volume_size=40\n"
            "controls=" + OLD_CONTROLS + "\n"
            "my_key=my_value\n"
        )
        (opts_dir / "uosc.conf").write_text(old_uosc, encoding="utf-8")
        (opts_dir / "ui_appearance.conf").write_text("style=calm\n", encoding="utf-8")
        old_mpv = (
            "vo=gpu-next\n"
            "script-opts-append        = uosc-border_radius=10\n"
            "script-opts-append        = uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80\n"
            "user_setting=1\n"
        )
        (self.config_dir / "mpv.conf").write_text(old_mpv, encoding="utf-8")

        fetch_results = [{"name": s["name"], "status": "ok"} for s in deployer.SCRIPTS]
        fetch_results.append({"name": deployer.SHADERS["name"], "status": "ok"})

        def mock_fetch(scripts, shaders, staging):
            for folder in ("scripts", "shaders", "fonts"):
                d = Path(staging) / folder
                d.mkdir(parents=True, exist_ok=True)
                (d / "dummy").write_text("dummy", encoding="utf-8")
            return fetch_results, LOCKFILE

        with (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "fetch_all", side_effect=mock_fetch),
            mock.patch.object(deployer, "display_plan"),
        ):
            # First run with --keep-conf
            ret = deployer.main(["--update", "--yes", "--keep-conf"])
            self.assertEqual(0, ret)

            # Check migrations applied
            uosc_text = (opts_dir / "uosc.conf").read_text(encoding="utf-8")
            self.assertIn("controls=" + SPEC_CONTROLS, uosc_text)
            self.assertIn("my_key=my_value", uosc_text)

            self.assertFalse((opts_dir / "ui_appearance.conf").exists())

            mpv_text = (self.config_dir / "mpv.conf").read_text(encoding="utf-8")
            self.assertNotIn("uosc-border_radius=10", mpv_text)
            self.assertNotIn("uosc-chapter_ranges=", mpv_text)
            self.assertIn("user_setting=1", mpv_text)

            # Record state before second run
            uosc_stat = (opts_dir / "uosc.conf").read_bytes()
            mpv_stat = (self.config_dir / "mpv.conf").read_bytes()

            # Second run changes nothing
            ret2 = deployer.main(["--update", "--yes", "--keep-conf"])
            self.assertEqual(0, ret2)
            self.assertEqual(uosc_stat, (opts_dir / "uosc.conf").read_bytes())
            self.assertEqual(mpv_stat, (self.config_dir / "mpv.conf").read_bytes())

    def test_update_keep_conf_backup_holds_old_files(self):
        self.stage_minimal()
        opts_dir = self.config_dir / "script-opts"
        opts_dir.mkdir(parents=True, exist_ok=True)
        old_uosc = "controls=" + OLD_CONTROLS + "\n"
        (opts_dir / "uosc.conf").write_text(old_uosc, encoding="utf-8")
        old_ui_app = "style=calm\n"
        (opts_dir / "ui_appearance.conf").write_text(old_ui_app, encoding="utf-8")

        fetch_results = [{"name": s["name"], "status": "ok"} for s in deployer.SCRIPTS]
        fetch_results.append({"name": deployer.SHADERS["name"], "status": "ok"})

        def mock_fetch(scripts, shaders, staging):
            for folder in ("scripts", "shaders", "fonts"):
                d = Path(staging) / folder
                d.mkdir(parents=True, exist_ok=True)
                (d / "dummy").write_text("dummy", encoding="utf-8")
            return fetch_results, LOCKFILE

        with (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "fetch_all", side_effect=mock_fetch),
            mock.patch.object(deployer, "display_plan"),
        ):
            deployer.main(["--update", "--yes", "--keep-conf"])

        # Check backup directory in parent
        backups = [p for p in self.config_dir.parent.iterdir() if p.name.startswith("mpv.backup.")]
        self.assertTrue(len(backups) >= 1)
        latest_backup = sorted(backups)[-1]

        backup_uosc = latest_backup / "script-opts" / "uosc.conf"
        self.assertTrue(backup_uosc.is_file())
        self.assertEqual(old_uosc, backup_uosc.read_text(encoding="utf-8"))

        backup_ui_app = latest_backup / "script-opts" / "ui_appearance.conf"
        self.assertTrue(backup_ui_app.is_file())
        self.assertEqual(old_ui_app, backup_ui_app.read_text(encoding="utf-8"))

    def test_dry_run_lists_pending_changes_and_leaves_files_identical(self):
        opts_dir = self.config_dir / "script-opts"
        opts_dir.mkdir(parents=True, exist_ok=True)
        old_uosc = "controls=" + OLD_CONTROLS + "\n"
        (opts_dir / "uosc.conf").write_text(old_uosc, encoding="utf-8")
        old_ui_app = "style=calm\n"
        (opts_dir / "ui_appearance.conf").write_text(old_ui_app, encoding="utf-8")
        old_mpv = "script-opts-append = uosc-border_radius=10\n"
        (self.config_dir / "mpv.conf").write_text(old_mpv, encoding="utf-8")

        displayed_plans = []
        with (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(
                deployer, "display_plan", side_effect=lambda p, title: displayed_plans.append((title, p))
            ),
        ):
            ret = deployer.main(["--update", "--dry-run", "--keep-conf"])
            self.assertEqual(0, ret)

        self.assertEqual(1, len(displayed_plans))
        plan_entries = displayed_plans[0][1]
        targets = {e.target: (e.action, e.detail) for e in plan_entries}

        uosc_path = str(opts_dir / "uosc.conf")
        ui_app_path = str(opts_dir / "ui_appearance.conf")
        mpv_path = str(self.config_dir / "mpv.conf")

        self.assertIn(uosc_path, targets)
        self.assertEqual("modify", targets[uosc_path][0])

        self.assertIn(ui_app_path, targets)
        self.assertEqual("remove", targets[ui_app_path][0])

        self.assertIn(mpv_path, targets)
        self.assertEqual("modify", targets[mpv_path][0])

        # Verify files are byte-identical
        self.assertEqual(old_uosc, (opts_dir / "uosc.conf").read_text(encoding="utf-8"))
        self.assertEqual(old_ui_app, (opts_dir / "ui_appearance.conf").read_text(encoding="utf-8"))
        self.assertEqual(old_mpv, (self.config_dir / "mpv.conf").read_text(encoding="utf-8"))

        # Verify no backup was created
        backups = [p for p in self.config_dir.parent.iterdir() if p.name.startswith("mpv.backup.")]
        self.assertEqual([], backups)

    def _seed_old_config(self):
        opts_dir = self.config_dir / "script-opts"
        opts_dir.mkdir(parents=True, exist_ok=True)
        old = {
            opts_dir / "uosc.conf": "controls=" + OLD_CONTROLS + "\nmy_key=1\n",
            opts_dir / "ui_appearance.conf": "style=calm\n",
            self.config_dir / "scripts" / "ui_appearance.lua": P5_UI_APPEARANCE_LUA,
            self.config_dir / "scripts" / "modules" / "looks.lua": P5_LOOKS_LUA,
            self.config_dir / "mpv.conf": (
                "vo=gpu-next\n"
                "script-opts-append        = uosc-border_radius=10\n"
                "script-opts-append        = uosc-chapter_ranges=openings:7cc4fa64,"
                "endings:7cc4fa64,ads:c54e4e80\n"
            ),
        }
        for path, text in old.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return old

    def _assert_theme_files_gone(self):
        scripts = self.config_dir / "scripts"
        self.assertFalse((scripts / "ui_appearance.lua").exists())
        self.assertFalse((scripts / "modules" / "looks.lua").exists())
        self.assertFalse((self.config_dir / "script-opts" / "ui_appearance.conf").exists())
        # Other modules stay: the directory is shared.
        self.assertTrue((scripts / "modules" / "stream_policy.lua").is_file())

    def _mock_update(self):
        def mock_fetch(scripts, shaders, staging):
            for folder in ("scripts", "shaders", "fonts"):
                d = Path(staging) / folder
                d.mkdir(parents=True, exist_ok=True)
                (d / "dummy").write_text("dummy", encoding="utf-8")
            results = [{"name": s["name"], "status": "ok"} for s in deployer.SCRIPTS]
            results.append({"name": deployer.SHADERS["name"], "status": "ok"})
            return results, LOCKFILE

        return (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "fetch_all", side_effect=mock_fetch),
        )

    def _only_backup(self):
        backups = [p for p in self.config_dir.parent.iterdir() if p.name.startswith("mpv.backup.")]
        self.assertEqual(1, len(backups))
        return backups[0]

    def _assert_backup_holds(self, backup, old):
        for path, text in old.items():
            kept = backup / path.relative_to(self.config_dir)
            self.assertEqual(text, kept.read_text(encoding="utf-8"), kept)

    def test_install_over_existing_config_backs_up_before_migrating(self):
        old = self._seed_old_config()
        self.stage_minimal()
        deployer.deploy(str(self.staging), self.env, str(REPO_ROOT), lockfile=LOCKFILE)
        self._assert_backup_holds(self._only_backup(), old)
        live = self.config_dir / "script-opts" / "uosc.conf"
        self.assertIn("controls=" + SPEC_CONTROLS + "\n", live.read_text(encoding="utf-8"))
        self.assertNotIn("uosc-border_radius=10", (self.config_dir / "mpv.conf").read_text())
        self._assert_theme_files_gone()

    def test_update_without_keep_conf_backs_up_before_migrating(self):
        old = self._seed_old_config()

        def mock_fetch(scripts, shaders, staging):
            for folder in ("scripts", "shaders", "fonts"):
                d = Path(staging) / folder
                d.mkdir(parents=True, exist_ok=True)
                (d / "dummy").write_text("dummy", encoding="utf-8")
            results = [{"name": s["name"], "status": "ok"} for s in deployer.SCRIPTS]
            results.append({"name": deployer.SHADERS["name"], "status": "ok"})
            return results, LOCKFILE

        with (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "fetch_all", side_effect=mock_fetch),
            mock.patch.object(deployer, "display_plan"),
        ):
            self.assertEqual(0, deployer.main(["--update", "--yes"]))
        self._assert_backup_holds(self._only_backup(), old)
        live = self.config_dir / "script-opts" / "uosc.conf"
        self.assertIn("controls=" + SPEC_CONTROLS + "\n", live.read_text(encoding="utf-8"))
        self._assert_theme_files_gone()

    def test_second_update_finds_no_leftover_theme_files(self):
        self._seed_old_config()
        detect, fetch = self._mock_update()
        shown = []
        with detect, fetch, mock.patch.object(
            deployer, "display_plan", side_effect=lambda plan, title: shown.append(plan)
        ):
            self.assertEqual(0, deployer.main(["--update", "--yes"]))
            self._assert_theme_files_gone()
            self.assertEqual(0, deployer.main(["--update", "--yes"]))
            self._assert_theme_files_gone()
        theme = ("ui_appearance", "looks.lua")
        first, second = shown
        self.assertEqual(3, sum(any(t in e.target for t in theme) for e in first))
        self.assertEqual([], [e.target for e in second if any(t in e.target for t in theme)])

    def test_same_named_user_script_is_kept_and_shown_as_skip(self):
        own = self.config_dir / "scripts" / "ui_appearance.lua"
        own.parent.mkdir(parents=True)
        own.write_text("-- my own appearance script\n", encoding="utf-8")
        link = self.config_dir / "scripts" / "modules" / "looks.lua"
        link.parent.mkdir()
        target = self.root / "elsewhere.lua"
        target.write_text(P5_LOOKS_LUA, encoding="utf-8")
        link.symlink_to(target)
        changes = bar_migration.pending_changes(self.config_dir, REPO_CONFIG_DIR)
        self.assertEqual([("skip", str(own))], [(a, p) for a, p, _ in changes])
        self.assertFalse(deployer._remove_leftover_theme_files(str(self.config_dir)))
        self.assertTrue(own.is_file())
        self.assertTrue(link.is_symlink())
        self.assertEqual(P5_LOOKS_LUA, target.read_text(encoding="utf-8"))

    def test_install_dry_run_lists_pending_changes_and_writes_nothing(self):
        old = self._seed_old_config()
        before = {
            p: p.read_bytes() for p in self.config_dir.rglob("*") if p.is_file()
        }
        shown = []
        with (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "compute_dep_actions", return_value=[]),
            mock.patch.object(
                deployer, "display_plan", side_effect=lambda plan, title: shown.append(plan)
            ),
            mock.patch.object(deployer, "fetch_all") as fetch,
        ):
            self.assertEqual(0, deployer.main(["--install", "--dry-run"]))
        fetch.assert_not_called()
        targets = {e.target: e.action for e in shown[0]}
        opts = self.config_dir / "script-opts"
        self.assertEqual("modify", targets[str(opts / "uosc.conf")])
        self.assertEqual("remove", targets[str(opts / "ui_appearance.conf")])
        scripts = self.config_dir / "scripts"
        self.assertEqual("remove", targets[str(scripts / "ui_appearance.lua")])
        self.assertEqual("remove", targets[str(scripts / "modules" / "looks.lua")])
        self.assertEqual("modify", targets[str(self.config_dir / "mpv.conf")])
        after = {p: p.read_bytes() for p in self.config_dir.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(sorted(old), sorted(p for p in after if p in old))
        backups = [p for p in self.config_dir.parent.iterdir() if p.name.startswith("mpv.backup.")]
        self.assertEqual([], backups)

if __name__ == "__main__":
    unittest.main()
