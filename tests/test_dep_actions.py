"""Shared dependency decisions (``deploy.dep_actions``).

The Installation Plan and ``installer.install_deps`` now consume the SAME
action list: computes install/refresh/skip per dependency, write-probes the
landing dir (falling back to a user-writable dir when Program Files is
read-only), and stamps file-method installs for the refresh gate. These
tests pin every decision the user-visible flows depend on:

- a refresh landing in the fallback dir stays "fresh" (non-admin loop
  does not re-download every run),
- read-only Program Files fails BEFORE any download, with an elevation
  hint, and optional tools skip the download instead of failing,
- a failed refresh of a WORKING binary is a skip, never a fatal row,
- the plan renders exactly the actions the installer executes.
"""

import os
import tempfile
import time
import unittest
from unittest import mock

from deploy import dep_actions, installer
from deploy.detector import Environment
from deploy.planner import build_install_plan
from deploy.registry import SYSTEM_DEPS


def _probe_table(truth):
    """dir_is_writable stand-in driven by a {path: bool} table (hermetic)."""
    return lambda path: bool(truth.get(path))


class StampFreshnessTests(unittest.TestCase):
    def test_refresh_stamp_ages_out_after_the_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            info = {"install_dir": tmpdir, "dest_name": "yt-dlp"}
            dest = os.path.join(tmpdir, "yt-dlp")

            # No binary at all → stamping is a no-op, never fresh.
            dep_actions.write_refresh_stamp(info)
            self.assertFalse(os.path.isfile(dest + ".stamp"))
            self.assertFalse(dep_actions.dep_is_fresh(info, 7))

            # Binary without a stamp (distro/apt class) counts as stale.
            with open(dest, "wb") as fh:
                fh.write(b"ELF")
            self.assertFalse(dep_actions.dep_is_fresh(info, 7))

            # An install stamps the binary fresh inside the window.
            dep_actions.write_refresh_stamp(info)
            self.assertTrue(dep_actions.dep_is_fresh(info, 7))

            # Stamp older than refresh_days → stale again (weekly refresh).
            old = time.time() - 8 * 86400
            os.utime(dest + ".stamp", (old, old))
            self.assertFalse(dep_actions.dep_is_fresh(info, 7))

    def test_freshness_considers_the_fallback_landing_stamp(self):
        """A refresh forced into the fallback dir stamps THERE.

        Without this, every non-admin session would re-read only the
        primary (Program Files) stamp, find none, and re-download yt-dlp
        despite having refreshed it minutes ago.
        """
        with tempfile.TemporaryDirectory() as primary, tempfile.TemporaryDirectory() as fallback:
            info = {
                "install_dir": primary,
                "dest_name": "yt-dlp.exe",
                "fallback_install_dir": fallback,
            }
            fb_bin = os.path.join(fallback, "yt-dlp.exe")
            with open(fb_bin, "wb") as fh:
                fh.write(b"MZ")
            dep_actions.write_refresh_stamp({**info, "install_dir": fallback})
            self.assertTrue(dep_actions.dep_is_fresh(info, 7))


class LandingProbeTests(unittest.TestCase):
    def test_probe_walks_up_without_creating_missing_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "freshly-created", "bin")
            self.assertTrue(dep_actions.dir_is_writable(target))
            self.assertEqual(os.listdir(tmpdir), [])

    def test_probe_reports_failure_when_the_write_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("os.open", side_effect=OSError(13, "denied")):
                self.assertFalse(dep_actions.dir_is_writable(tmpdir))

    def test_writable_primary_is_the_landing_dir(self):
        info = {
            "install_dir": r"C:\Program Files\mpv\yt-dlp",
            "fallback_install_dir": r"C:\mpv-config-tests\tools",
        }
        with mock.patch.object(dep_actions, "dir_is_writable", _probe_table({info["install_dir"]: True})):
            self.assertEqual(dep_actions._landing(info, dep_actions.dir_is_writable),
                             (info["install_dir"], True))

    def test_readonly_primary_lands_in_the_fallback_dir(self):
        info = {
            "install_dir": r"C:\Program Files\mpv\yt-dlp",
            "fallback_install_dir": r"C:\mpv-config-tests\tools",
        }
        probe = _probe_table({info["fallback_install_dir"]: True})
        self.assertEqual(dep_actions._landing(info, probe), (info["fallback_install_dir"], True))

    def test_neither_writable_keeps_primary_marked_unwritable(self):
        info = {
            "install_dir": r"C:\Program Files\mpv\yt-dlp",
            "fallback_install_dir": r"C:\mpv-config-tests\tools",
        }
        self.assertEqual(
            dep_actions._landing(info, _probe_table({})), (info["install_dir"], False)
        )


class ComputeActionTests(unittest.TestCase):
    def test_installed_deps_skip_missing_deps_install(self):
        env = Environment(
            os="linux",
            platform_key="ubuntu",
            installed={
                "mpv": True,
                "yt-dlp": True,
                "ffmpeg": True,
                "python": True,
                "uv": True,
                "ffsubsync": True,
            },
            mpv_version=(0, 41, 0),
        )
        with mock.patch.object(dep_actions, "dir_is_writable", lambda _path: True), \
                mock.patch.object(dep_actions, "dep_is_fresh", return_value=True):
            actions = dep_actions.compute_dep_actions(env)
        by_name = {action.name: action for action in actions}
        for name in ("mpv", "yt-dlp", "ffmpeg", "python", "uv", "ffsubsync"):
            self.assertEqual(by_name[name].kind, "skip", name)
        self.assertEqual(by_name["alass"].kind, "install")
        self.assertTrue(by_name["alass"].optional)
        self.assertNotIn("autohotkey", by_name)

    def test_windows_missing_deps_list_autohotkey_as_optional(self):
        env = Environment(os="windows", platform_key="windows", installed={})
        with mock.patch.object(dep_actions, "dir_is_writable", lambda _path: True):
            actions = dep_actions.compute_dep_actions(env)
        by_name = {action.name: action for action in actions}
        self.assertTrue(by_name["autohotkey"].optional)
        self.assertEqual(by_name["autohotkey"].kind, "install")

    def test_below_minimum_mpv_is_an_install_not_a_skip(self):
        env = Environment(
            os="linux",
            platform_key="ubuntu",
            installed={"mpv": True},
            mpv_version=(0, 36, 0),
        )
        with mock.patch.object(dep_actions, "dir_is_writable", lambda _path: True):
            mpv = dep_actions.compute_dep_actions(env)[0]
        self.assertEqual(mpv.name, "mpv")
        self.assertEqual(mpv.kind, "install")
        self.assertIn("installed 0.36.0", mpv.detail)
        self.assertIn("required", mpv.detail)

    def test_unstamped_stale_launcher_classifies_as_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_info = {
                "method": "direct_url",
                "install_dir": tmpdir,
                "dest_name": "yt-dlp",
                "ensure_in_dir": tmpdir,
                "refresh_days": 7,
            }
            env = Environment(
                os="linux", platform_key="ubuntu", installed={"yt-dlp": True}
            )
            with mock.patch.dict(SYSTEM_DEPS, {"yt-dlp": {"ubuntu": reg_info}}):
                ytdlp = next(
                    a for a in dep_actions.compute_dep_actions(env) if a.name == "yt-dlp"
                )
        self.assertEqual(ytdlp.kind, "refresh")
        self.assertIn("refreshing", ytdlp.detail)
        self.assertIn("older than 7 days", ytdlp.detail)

    def test_stale_install_through_fallback_names_the_landing_dir(self):
        with tempfile.TemporaryDirectory() as primary, tempfile.TemporaryDirectory() as fallback:
            reg_info = {
                "method": "direct_url",
                "install_dir": primary,
                "dest_name": "yt-dlp.exe",
                "refresh_days": 7,
                "fallback_install_dir": fallback,
            }
            env = Environment(
                os="windows", platform_key="windows", installed={"yt-dlp": True}
            )
            probe = _probe_table({fallback: True})
            with mock.patch.dict(SYSTEM_DEPS, {"yt-dlp": {"windows": reg_info}}):
                with mock.patch.object(dep_actions, "dir_is_writable", probe):
                    ytdlp = next(
                        a for a in dep_actions.compute_dep_actions(env) if a.name == "yt-dlp"
                    )
        self.assertIn(fallback, ytdlp.detail)
        self.assertIn("not writable in this shell", ytdlp.detail)

    def test_unwritable_everywhere_marks_the_row_needs_admin(self):
        reg_info = {
            "method": "direct_url",
            "install_dir": r"C:\Program Files\mpv\yt-dlp",
            "dest_name": "yt-dlp.exe",
            "refresh_days": 7,
            "fallback_install_dir": r"C:\mpv-config-tests\tools",
        }
        env = Environment(os="windows", platform_key="windows", installed={})
        with mock.patch.dict(SYSTEM_DEPS, {"yt-dlp": {"windows": reg_info}}):
            with mock.patch.object(dep_actions, "dir_is_writable", _probe_table({})):
                ytdlp = next(
                    a for a in dep_actions.compute_dep_actions(env) if a.name == "yt-dlp"
                )
        self.assertFalse(ytdlp.writable)
        self.assertIn("needs Administrator", ytdlp.detail)

    def test_plan_renders_exactly_the_dep_actions(self):
        env = Environment(
            os="linux",
            platform_key="ubuntu",
            installed={"mpv": True, "yt-dlp": True},
            mpv_version=(0, 41, 0),
            config_dir="",
        )
        with mock.patch.object(dep_actions, "dir_is_writable", lambda _path: True):
            actions = dep_actions.compute_dep_actions(env)
            plan = build_install_plan(env, dep_actions=actions)
            default_plan = build_install_plan(env)

        package_rows = [entry for entry in plan if entry.category == "package"]
        self.assertEqual(len(package_rows), len(actions))
        for entry, action in zip(package_rows, actions):
            with self.subTest(dep=action.name):
                self.assertEqual(entry.action, action.kind)
                self.assertEqual(entry.target, action.name)
                self.assertEqual(entry.detail, action.detail)

        default_rows = [
            entry for entry in default_plan if entry.category == "package"
        ]
        self.assertEqual(
            [(e.action, e.target, e.detail) for e in default_rows],
            [(e.action, e.target, e.detail) for e in package_rows],
        )


class InstallableTests(unittest.TestCase):
    def test_only_downloadable_actions_run_installs(self):
        cases = [
            # (kind, landing_dir, writable, expected)
            ("skip", None, None, False),
            ("install", None, None, True),  # pkg-manager method: no landing
            ("install", "C:\\writable", True, True),
            ("install", "C:\\locked", False, False),
            ("refresh", None, None, True),
            ("refresh", "C:\\locked", False, False),
        ]
        for kind, landing_dir, writable, expected in cases:
            with self.subTest(kind=kind, writable=writable):
                action = dep_actions.DepAction(
                    name="dep",
                    kind=kind,
                    optional=False,
                    landing_dir=landing_dir,
                    writable=writable,
                    detail="",
                )
                self.assertEqual(dep_actions.installable(action), expected)


class InstallerConsumptionTests(unittest.TestCase):
    """install_deps executing dep_actions: the two user-reported failures."""

    def _probe_false(self):
        return lambda _path: False

    def test_failed_refresh_of_working_binary_keeps_it_and_skips(self):
        """Refreshing yt-dlp failing must NOT abort the deploy (2026-10-27)."""
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

        def install_mock(name, _info, _env, mpv_version=None, landing_dir=None):
            return name != "yt-dlp"

        with mock.patch.object(dep_actions, "dep_is_fresh", return_value=False), \
                mock.patch.object(dep_actions, "dir_is_writable", lambda _path: True), \
                mock.patch.object(installer, "_install_one", side_effect=install_mock):
            results = installer.install_deps(env, dry_run=False)

        by_name = {r["name"]: r for r in results}
        self.assertEqual(by_name["yt-dlp"]["status"], "skipped")
        self.assertEqual(by_name["yt-dlp"]["detail"], "kept existing binary (refresh failed)")
        self.assertEqual(by_name["mpv"]["status"], "ok")
        self.assertEqual(by_name["ffmpeg"]["status"], "ok")

    def test_required_dep_without_writable_target_fails_before_download(self):
        """Non-elevated shell must not spend network time on unwritable lands."""
        env = Environment(
            os="windows",
            platform_key="windows",
            installed={"yt-dlp": True},
        )
        with mock.patch.object(dep_actions, "dep_is_fresh", return_value=False), \
                mock.patch.object(dep_actions, "dir_is_writable", self._probe_false()), \
                mock.patch.object(installer, "_install_one", side_effect=AssertionError("downloaded")):
            results = installer.install_deps(env, dry_run=False)

        by_name = {r["name"]: r for r in results}
        self.assertEqual(by_name["yt-dlp"]["status"], "failed")
        self.assertIn("did not download", by_name["yt-dlp"]["detail"])
        self.assertIn("needs Administrator", by_name["yt-dlp"]["detail"])

    def test_optional_dep_without_writable_target_skips_without_download(self):
        """ALass/AHK cannot be downloaded into Program Files by a plain user."""
        env = Environment(
            os="windows",
            platform_key="windows",
            installed={},
        )
        with mock.patch.object(
            dep_actions, "dir_is_writable", self._probe_false()
        ), mock.patch.object(installer, "_install_one", side_effect=AssertionError("downloaded")):
            results = installer.install_deps(env, dry_run=False)

        by_name = {r["name"]: r for r in results}
        for name in ("alass", "autohotkey"):
            self.assertEqual(by_name[name]["status"], "skipped", name)
            self.assertIn("did not download", by_name[name]["detail"])


if __name__ == "__main__":
    unittest.main()
