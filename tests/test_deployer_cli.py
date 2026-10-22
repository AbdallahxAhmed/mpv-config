"""Tests for the ``python -m deploy.deployer`` command-line entry point.

The orchestration tests replace every collaborator that touches the network, the
package manager or the real configuration directory (with signature-checked
mocks), but keep the real ``tx`` helpers: config-path validation, the operation
lock and the staging directory. They therefore exercise the fail-closed
ordering itself rather than a mock of it.
"""

import inspect
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from deploy import deployer

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ok(name):
    return {"name": name, "status": "ok"}


def _failed(name):
    return {"name": name, "status": "failed"}


def _complete_fetch_results():
    names = [entry["name"] for entry in deployer.SCRIPTS] + [deployer.SHADERS["name"]]
    return [_ok(name) for name in names]


class DeployerParserTests(unittest.TestCase):
    def run_main_expecting_exit(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                deployer.main(list(argv))
        return raised.exception.code, out.getvalue(), err.getvalue()

    def test_help_documents_the_actions_and_exits_zero(self):
        code, out, _ = self.run_main_expecting_exit("--help")
        self.assertEqual(code, 0)
        self.assertIn("--install", out)
        self.assertIn("--verify", out)
        self.assertIn("--update", out)
        self.assertIn("--rollback", out)
        self.assertIn("--status", out)
        self.assertIn("--sync-deps", out)
        self.assertIn("--uninstall", out)
        self.assertIn("--dry-run", out)

    def test_an_action_is_required(self):
        code, _, err = self.run_main_expecting_exit()
        self.assertEqual(code, 2)
        self.assertIn("--install", err)

    def test_install_and_verify_are_mutually_exclusive(self):
        code, _, err = self.run_main_expecting_exit("--install", "--verify")
        self.assertEqual(code, 2)
        self.assertIn("not allowed", err)

    def test_invalid_choice_is_rejected(self):
        code, _, err = self.run_main_expecting_exit("--install", "--anime-preset", "Z")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)

    def test_defaults_follow_the_deploy_signature(self):
        args = deployer.build_arg_parser().parse_args(["--install"])
        parameters = inspect.signature(deployer.deploy).parameters
        for name in ("mpv_profile", "anime_preset", "scaler_tier", "display_mode", "dither_depth", "stream_quality"):
            with self.subTest(option=name):
                if name == "anime_preset":
                    # None means "not chosen yet": an interactive install
                    # asks for the Anime4K mode, an unattended one falls
                    # back to the deploy() default (see _resolve_anime_preset).
                    self.assertIsNone(getattr(args, name))
                    original = deployer._is_interactive_session
                    deployer._is_interactive_session = lambda: False
                    try:
                        self.assertEqual(
                            deployer._resolve_anime_preset(args), parameters[name].default
                        )
                    finally:
                        deployer._is_interactive_session = original
                    continue
                self.assertEqual(getattr(args, name), parameters[name].default)
        self.assertFalse(args.dry_run)
        self.assertIsNone(args.mpv_version)

    def test_the_installer_asks_for_the_anime_mode_when_interactive(self):
        parser = deployer.build_arg_parser()
        args = parser.parse_args(["--install"])
        original_interactive = deployer._is_interactive_session
        original_ask = deployer.ui.ask_choice
        asked = []

        def fake_ask(text, choices):
            asked.append((text, list(choices)))
            return "A+A"

        deployer._is_interactive_session = lambda: True
        deployer.ui.ask_choice = fake_ask
        try:
            chosen = deployer._resolve_anime_preset(args)
        finally:
            deployer._is_interactive_session = original_interactive
            deployer.ui.ask_choice = original_ask
        self.assertEqual(chosen, "A+A")
        self.assertEqual(len(asked), 1)
        for mode in ("A", "A+A", "B", "B+B", "C+A", "fast", "off"):
            self.assertIn(mode, asked[0][1])

    def test_an_explicit_anime_preset_skips_the_prompt(self):
        parser = deployer.build_arg_parser()
        args = parser.parse_args(["--install", "--anime-preset", "B"])
        original_interactive = deployer._is_interactive_session
        original_ask = deployer.ui.ask_choice

        def boom(*a, **k):
            raise AssertionError("must not prompt when the mode was given")

        deployer._is_interactive_session = lambda: True
        deployer.ui.ask_choice = boom
        try:
            self.assertEqual(deployer._resolve_anime_preset(args), "B")
        finally:
            deployer._is_interactive_session = original_interactive
            deployer.ui.ask_choice = original_ask

    def test_every_registry_preset_and_profile_is_selectable(self):
        parser = deployer.build_arg_parser()
        for preset in deployer.ANIME4K_CHAINS:
            args = parser.parse_args(["--install", "--anime-preset", preset])
            self.assertEqual(args.anime_preset, preset)
        for tier in deployer.SCALER_TIERS:
            args = parser.parse_args(["--install", "--scaler-tier", tier])
            self.assertEqual(args.scaler_tier, tier)
        for profile in deployer.MPV_EXPERIENCE_PROFILES:
            args = parser.parse_args(["--install", "--mpv-profile", profile])
            self.assertEqual(args.mpv_profile, profile)

    def test_repo_root_is_the_checkout_containing_the_module(self):
        self.assertEqual(deployer.REPO_ROOT, REPO_ROOT)
        module_file = Path(deployer.__file__).resolve()
        self.assertEqual((deployer.REPO_ROOT / "deploy" / "deployer.py").resolve(), module_file)


class InstallOrchestrationTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.config_dir = str(self.root / "config" / "mpv")
        self.env = SimpleNamespace(os="linux", config_dir=self.config_dir)

        # Scripted behaviour of the collaborators; individual tests override these.
        self.fetch_results = _complete_fetch_results()
        self.dep_results = [_ok("mpv")]
        self.deploy_results = [_ok("scripts")]
        self.fetch_error = None
        self.dep_error = None
        self.run_verify_callback = False
        self.calls = []
        self.staging_dirs = []
        self.audit_log = mock.MagicMock(name="audit_log")

        def fetch_all(scripts, shaders, staging):
            self.calls.append("fetch_all")
            self.staging_dirs.append(Path(staging))
            self.assertTrue(Path(staging).is_dir())
            if self.fetch_error:
                raise self.fetch_error
            return self.fetch_results, "lockfile-sentinel"

        def install_deps(env, dry_run=False, audit_log=None, mpv_version=None):
            self.calls.append("install_deps")
            if self.dep_error:
                raise self.dep_error
            return self.dep_results

        def deploy(staging_dir, env, repo_dir, **kwargs):
            self.calls.append("deploy")
            if self.run_verify_callback:
                kwargs["verify_callback"]()
            return self.deploy_results

        self.m = SimpleNamespace()
        patchers = {
            "ui": mock.patch.object(deployer, "ui", autospec=True),
            "detect": mock.patch.object(deployer, "detect", autospec=True, return_value=self.env),
            "build_install_plan": mock.patch.object(
                deployer, "build_install_plan", autospec=True, return_value=["plan"]
            ),
            "display_plan": mock.patch.object(deployer, "display_plan", autospec=True),
            "confirm_plan": mock.patch.object(
                deployer, "confirm_plan", autospec=True, return_value=True
            ),
            "interactive": mock.patch.object(
                deployer, "_is_interactive_session", autospec=True, return_value=False
            ),
            "fetch_all": mock.patch.object(
                deployer, "fetch_all", autospec=True, side_effect=fetch_all
            ),
            "validate_staging": mock.patch.object(deployer.tx, "validate_staging", autospec=True),
            "audit_for": mock.patch.object(
                deployer, "_audit_log_for", autospec=True, return_value=self.audit_log
            ),
            "install_deps": mock.patch.object(
                deployer, "install_deps", autospec=True, side_effect=install_deps
            ),
            "probe_mpv_version": mock.patch.object(
                deployer, "probe_mpv_version", autospec=True, return_value=(0, 41, 0)
            ),
            "verify": mock.patch.object(
                deployer, "verify", autospec=True, return_value=[_ok("mpv binary")]
            ),
            "deploy": mock.patch.object(deployer, "deploy", autospec=True, side_effect=deploy),
        }
        for name, patcher in patchers.items():
            setattr(self.m, name, patcher.start())
            self.addCleanup(patcher.stop)

    def error_message(self):
        return self.m.ui.error.call_args.args[0]

    def test_install_fetches_then_installs_dependencies_then_deploys(self):
        self.assertEqual(deployer.main(["--install"]), 0)
        self.assertEqual(self.calls, ["fetch_all", "install_deps", "deploy"])
        self.audit_log.start_session.assert_called_once_with("install", self.env)
        self.audit_log.complete_session.assert_called_once_with("completed")
        self.m.ui.panel.assert_called_once()
        self.m.ui.error.assert_not_called()

    def test_install_continues_after_mpv_dependency_failure(self):
        """mpv failure is non-fatal: deploy adapts the config to the actual mpv."""
        self.dep_results = [
            {"name": "mpv", "status": "failed", "detail": "add-apt-repository timed out"},
            _ok("yt-dlp"),
        ]
        self.assertEqual(deployer.main(["--install"]), 0)
        self.assertEqual(self.calls, ["fetch_all", "install_deps", "deploy"])
        self.audit_log.complete_session.assert_called_once_with("completed")
        self.assertTrue(self.m.ui.warn.called)

    def test_install_aborts_on_non_mpv_dependency_failure(self):
        """Anything other than mpv stays fail-closed (no deploy, no replace)."""
        self.dep_results = [_ok("mpv"), _failed("yt-dlp")]
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertEqual(self.calls, ["fetch_all", "install_deps"])
        self.assertIn("Dependency installation failed", self.error_message())
        self.audit_log.complete_session.assert_called_once_with("failed")

    def test_deploy_receives_its_actual_signature_arguments(self):
        # autospec makes any mismatch with deploy()'s real signature raise TypeError,
        # which main() would turn into exit status 1.
        self.assertEqual(deployer.main(["--install"]), 0)
        self.m.deploy.assert_called_once()
        args, kwargs = self.m.deploy.call_args
        staging, env, repo_dir = args
        self.assertTrue(os.path.basename(staging).startswith(".mpv-install-stage-"))
        self.assertIs(env, self.env)
        self.assertEqual(Path(repo_dir), deployer.REPO_ROOT)
        self.assertIs(kwargs["audit_log"], self.audit_log)
        self.assertEqual(kwargs["lockfile"], "lockfile-sentinel")
        self.assertTrue(callable(kwargs["verify_callback"]))
        for name in ("mpv_profile", "anime_preset", "scaler_tier", "display_mode", "dither_depth", "stream_quality"):
            self.assertEqual(kwargs[name], deployer._DEPLOY_DEFAULTS[name])

    def test_options_reach_deploy_and_install_deps(self):
        argv = [
            "--install",
            "--anime-preset=A+A",
            "--scaler-tier=quality",
            "--display-mode=vrr",
            "--dither-depth=10",
            "--mpv-profile=native",
            "--mpv-version=2025-01-15",
            "--stream-quality=720",
        ]
        self.assertEqual(deployer.main(argv), 0)
        kwargs = self.m.deploy.call_args.kwargs
        self.assertEqual(kwargs["anime_preset"], "A+A")
        self.assertEqual(kwargs["scaler_tier"], "quality")
        self.assertEqual(kwargs["display_mode"], "vrr")
        self.assertEqual(kwargs["dither_depth"], "10")
        self.assertEqual(kwargs["mpv_profile"], "native")
        self.assertEqual(kwargs["stream_quality"], "720")
        self.assertEqual(self.m.install_deps.call_args.kwargs["mpv_version"], "2025-01-15")
        self.assertFalse(self.m.install_deps.call_args.kwargs["dry_run"])

    def test_stream_quality_best_maps_to_uncapped_zero(self):
        self.assertEqual(deployer.main(["--install", "--stream-quality=best"]), 0)
        self.assertEqual(self.m.deploy.call_args.kwargs["stream_quality"], "0")

    def test_staging_is_beside_the_config_dir_and_removed_afterwards(self):
        self.assertEqual(deployer.main(["--install"]), 0)
        (staging,) = self.staging_dirs
        self.assertTrue(os.path.samefile(staging.parent, Path(self.config_dir).parent))
        self.assertFalse(staging.exists())

    def test_incomplete_fetch_aborts_before_dependencies_and_deploy(self):
        self.fetch_results = _complete_fetch_results()[:-1]
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertEqual(self.calls, ["fetch_all"])
        self.assertIn("Fetch was incomplete", self.error_message())
        self.audit_log.start_session.assert_not_called()

    def test_failed_download_aborts_before_dependencies_and_deploy(self):
        self.fetch_results = _complete_fetch_results()
        self.fetch_results[0] = _failed(self.fetch_results[0]["name"])
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertEqual(self.calls, ["fetch_all"])

    def test_failed_dependency_install_aborts_before_deploy(self):
        # mpv failures are tolerable (see test_install_continues_after_mpv_dependency_failure);
        # every other dependency stays fail-closed.
        self.dep_results = [_ok("mpv"), _failed("yt-dlp")]
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertEqual(self.calls, ["fetch_all", "install_deps"])
        self.assertIn("Dependency installation failed", self.error_message())
        self.audit_log.complete_session.assert_called_once_with("failed")

    def test_failed_deploy_result_is_reported(self):
        self.deploy_results = [_failed("scripts")]
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertIn("Deployment reported a failure", self.error_message())
        self.audit_log.complete_session.assert_called_once_with("failed")

    def test_failed_verification_callback_raises_so_deploy_can_roll_back(self):
        self.m.verify.return_value = [_failed("mpv binary")]
        self.run_verify_callback = True
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertIn("Verification failed", self.error_message())
        self.audit_log.complete_session.assert_called_once_with("failed")

    def test_dry_run_changes_nothing(self):
        self.assertEqual(deployer.main(["--install", "--dry-run"]), 0)
        self.assertEqual(self.calls, [])
        self.m.display_plan.assert_called_once()
        self.audit_log.start_session.assert_not_called()
        self.assertFalse(Path(self.config_dir).parent.exists())

    def test_declined_confirmation_cancels_without_changes(self):
        self.m.interactive.return_value = True
        self.m.confirm_plan.return_value = False
        self.assertEqual(deployer.main(["--install"]), 0)
        self.assertEqual(self.calls, [])
        self.m.ui.warn.assert_called_once()

    def test_confirmed_interactive_install_proceeds(self):
        self.m.interactive.return_value = True
        self.assertEqual(deployer.main(["--install"]), 0)
        self.m.confirm_plan.assert_called_once()
        self.assertEqual(self.calls, ["fetch_all", "install_deps", "deploy"])

    def test_interrupt_returns_130(self):
        self.fetch_error = KeyboardInterrupt()
        self.assertEqual(deployer.main(["--install"]), 130)
        self.m.ui.warn.assert_called_once()
        self.assertIn("Interrupted", self.m.ui.warn.call_args.args[0])

    def test_interrupt_after_the_session_started_marks_it_cancelled(self):
        self.dep_error = KeyboardInterrupt()
        self.assertEqual(deployer.main(["--install"]), 130)
        self.audit_log.complete_session.assert_called_once_with("cancelled")

    def test_unexpected_error_returns_one_with_a_message(self):
        self.fetch_error = RuntimeError("network exploded")
        self.assertEqual(deployer.main(["--install"]), 1)
        self.assertIn("network exploded", self.error_message())

    def test_debug_environment_variable_re_raises(self):
        self.fetch_error = RuntimeError("network exploded")
        with mock.patch.dict(os.environ, {"DEBUG": "1"}):
            with self.assertRaises(RuntimeError):
                deployer.main(["--install"])

    def test_verify_returns_zero_when_every_check_passes(self):
        self.assertEqual(deployer.main(["--verify"]), 0)
        self.m.verify.assert_called_once_with(self.env.config_dir, self.env)
        self.assertEqual(self.calls, [])

    def test_verify_returns_one_when_a_check_fails(self):
        self.m.verify.return_value = [_failed("mpv binary")]
        self.assertEqual(deployer.main(["--verify"]), 1)
        self.assertIn("verification failed", self.error_message())

    def test_update_dry_run_exits_zero_without_writes(self):
        self.assertEqual(deployer.main(["--update", "--dry-run"]), 0)
        self.m.display_plan.assert_called_once()
        self.audit_log.start_session.assert_not_called()

    def test_rollback_dry_run_exits_zero(self):
        backup_dir = Path(f"{self.config_dir}.backup.20260101_000000")
        backup_dir.mkdir(parents=True, exist_ok=True)
        self.assertEqual(deployer.main(["--rollback", "--dry-run"]), 0)
        self.audit_log.start_session.assert_not_called()

    def test_rollback_aborts_when_no_backups_found(self):
        self.assertEqual(deployer.main(["--rollback"]), 1)
        self.m.ui.warn.assert_called_once()
        self.audit_log.start_session.assert_not_called()

    def test_sync_deps_dry_run_exits_zero(self):
        self.assertEqual(deployer.main(["--sync-deps", "--dry-run"]), 0)
        self.audit_log.start_session.assert_not_called()

    def test_uninstall_dry_run_exits_zero(self):
        self.assertEqual(deployer.main(["--uninstall", "--dry-run"]), 0)
        self.audit_log.start_session.assert_not_called()


class DeployerModuleTests(unittest.TestCase):
    """Run the module the way users do. A module without an entry point exits 0 silently."""

    def run_module(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "deploy.deployer", *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            shell=False,
        )

    def test_help_is_printed_rather_than_silence(self):
        proc = self.run_module("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--install", proc.stdout)

    def test_missing_action_is_an_error_rather_than_silent_success(self):
        proc = self.run_module()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("required", proc.stderr)

    def test_conflicting_actions_are_rejected(self):
        proc = self.run_module("--install", "--verify")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not allowed", proc.stderr)


if __name__ == "__main__":
    unittest.main()
