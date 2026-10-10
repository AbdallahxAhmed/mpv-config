"""Tests for the ``mpv-config install`` / ``verify`` hand-off to the deployer.

Both subcommands used to be placeholders that printed ``Executing: ...`` and
returned success. They must start ``python -m deploy.deployer`` (no shell,
``PYTHONPATH`` pinned to the checkout) and return its exit status.
"""

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

from mpv_config.cli import main as cli

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_checkout(root):
    """Create the minimum that makes a directory look like an mpv-config checkout."""
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "deployer.py").write_text("# stub\n", encoding="utf-8")
    (root / "config").mkdir()
    return root


class HandOffTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.repo = _make_checkout(Path(scratch.name) / "checkout")

        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PYTHONPATH", None)
        os.environ.pop("PYTHONDONTWRITEBYTECODE", None)

        find = mock.patch.object(cli, "find_repo_root", return_value=self.repo)
        self.find_mock = find.start()
        self.addCleanup(find.stop)
        run = mock.patch.object(cli.subprocess, "run", return_value=SimpleNamespace(returncode=0))
        self.run_mock = run.start()
        self.addCleanup(run.stop)

    def invoke(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def spawned(self):
        self.run_mock.assert_called_once()
        return self.run_mock.call_args.args[0], self.run_mock.call_args.kwargs

    def test_install_runs_the_deployer_module_without_a_shell(self):
        code, out, err = self.invoke("install")
        self.assertEqual(code, 0)
        command, kwargs = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--install"])
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["cwd"], str(self.repo))
        self.assertNotIn("Executing:", out + err)

    def test_verify_runs_the_deployer_verify_action(self):
        self.assertEqual(self.invoke("verify")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--verify"])

    def test_update_runs_the_deployer_update_action(self):
        self.assertEqual(self.invoke("update")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--update"])

    def test_rollback_runs_the_deployer_rollback_action(self):
        self.assertEqual(self.invoke("rollback")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--rollback"])

    def test_rollback_with_custom_path_forwards_target(self):
        self.assertEqual(self.invoke("rollback", "/custom/backup")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(
            command, [sys.executable, "-m", "deploy.deployer", "--rollback=/custom/backup"]
        )

    def test_status_runs_the_deployer_status_action(self):
        self.assertEqual(self.invoke("status")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--status"])

    def test_sync_deps_runs_the_deployer_sync_deps_action(self):
        self.assertEqual(self.invoke("sync-deps")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--sync-deps"])

    def test_uninstall_runs_the_deployer_uninstall_action(self):
        self.assertEqual(self.invoke("uninstall")[0], 0)
        command, _ = self.spawned()
        self.assertEqual(command, [sys.executable, "-m", "deploy.deployer", "--uninstall"])

    def test_extra_options_are_forwarded_in_order(self):
        self.invoke("install", "--dry-run", "--anime-preset", "A+A", "--mpv-version=2025-01-15")
        command, _ = self.spawned()
        self.assertEqual(
            command[3:],
            ["--install", "--dry-run", "--anime-preset", "A+A", "--mpv-version=2025-01-15"],
        )

    def test_the_deployer_exit_status_is_returned(self):
        for status in (0, 1, 2, 130):
            with self.subTest(status=status):
                self.run_mock.return_value = SimpleNamespace(returncode=status)
                self.assertEqual(self.invoke("install")[0], status)

    def test_pythonpath_is_pinned_to_the_checkout(self):
        self.invoke("install")
        _, kwargs = self.spawned()
        self.assertEqual(kwargs["env"]["PYTHONPATH"], str(self.repo))

    def test_an_existing_pythonpath_is_kept_after_the_checkout(self):
        os.environ["PYTHONPATH"] = os.pathsep.join(["/somewhere/else", "/and/another"])
        self.invoke("install")
        _, kwargs = self.spawned()
        parts = kwargs["env"]["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts, [str(self.repo), "/somewhere/else", "/and/another"])

    def test_bytecode_writing_is_disabled_unless_the_user_chose_otherwise(self):
        self.invoke("install")
        self.assertEqual(self.spawned()[1]["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.run_mock.reset_mock()
        os.environ["PYTHONDONTWRITEBYTECODE"] = "0"
        self.invoke("install")
        self.assertEqual(self.spawned()[1]["env"]["PYTHONDONTWRITEBYTECODE"], "0")

    def test_a_missing_checkout_is_reported_without_spawning_anything(self):
        self.find_mock.side_effect = cli.RepositoryNotFoundError("no checkout here")
        code, _, err = self.invoke("install")
        self.assertEqual(code, 1)
        self.assertIn("no checkout here", err)
        self.run_mock.assert_not_called()

    def test_ctrl_c_returns_130(self):
        self.run_mock.side_effect = KeyboardInterrupt()
        self.assertEqual(self.invoke("install")[0], 130)

    def test_a_failure_to_start_the_deployer_is_reported(self):
        self.run_mock.side_effect = OSError("cannot start")
        code, _, err = self.invoke("install")
        self.assertEqual(code, 1)
        self.assertIn("cannot start", err)


class ParserBehaviourTests(unittest.TestCase):
    def test_unknown_options_are_still_rejected_outside_forwarding_commands(self):
        for argv in (["download", "--bogus"], ["--bogus"]):
            with self.subTest(argv=argv):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        cli.main(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_no_subcommand_prints_help(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main([]), 0)
        self.assertIn("install", out.getvalue())

    def test_install_help_mentions_the_forwarded_options(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            cli.main(["install", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--dry-run", out.getvalue())


class FindRepoRootTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.tmp = Path(scratch.name).resolve()

        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(cli.REPO_ENV_VAR, None)

        self.home = self.tmp / "home"
        self.home.mkdir()
        # Where a non-editable install lives: none of its ancestors is a checkout.
        self.package_file = self.tmp / "site-packages" / "mpv_config" / "cli" / "main.py"
        self.nowhere = self.tmp / "nowhere"
        self.nowhere.mkdir()

    def locate(self, **overrides):
        arguments = {
            "cwd": self.nowhere,
            "package_file": self.package_file,
            "home": self.home,
        }
        arguments.update(overrides)
        return cli.find_repo_root(**arguments)

    def checkout(self, name):
        return _make_checkout(self.tmp / name).resolve()

    def test_the_environment_variable_wins(self):
        explicit, other = self.checkout("explicit"), self.checkout("other")
        os.environ[cli.REPO_ENV_VAR] = str(explicit)
        self.assertEqual(self.locate(cwd=other), explicit)

    def test_an_invalid_environment_variable_is_an_error_not_a_fallback(self):
        os.environ[cli.REPO_ENV_VAR] = str(self.tmp / "does-not-exist")
        with self.assertRaises(cli.RepositoryNotFoundError) as raised:
            self.locate(cwd=self.checkout("valid"))
        self.assertIn(cli.REPO_ENV_VAR, str(raised.exception))

    def test_the_current_directory_is_used_for_bootstrap_runs(self):
        checkout = self.checkout("clone")
        self.assertEqual(self.locate(cwd=checkout), checkout)

    def test_the_checkout_the_package_came_from_is_used_for_editable_installs(self):
        checkout = self.checkout("dev")
        package_file = checkout / "src" / "mpv_config" / "cli" / "main.py"
        self.assertEqual(self.locate(package_file=package_file), checkout)

    def test_the_bootstrap_clone_in_home_is_the_last_resort(self):
        clone = _make_checkout(self.home / cli.BOOTSTRAP_DIR_NAME).resolve()
        self.assertEqual(self.locate(), clone)

    def test_search_order_is_cwd_then_package_then_home(self):
        cwd_checkout, dev_checkout = self.checkout("cwd"), self.checkout("dev")
        _make_checkout(self.home / cli.BOOTSTRAP_DIR_NAME)
        package_file = dev_checkout / "src" / "mpv_config" / "cli" / "main.py"
        self.assertEqual(self.locate(cwd=cwd_checkout, package_file=package_file), cwd_checkout)
        self.assertEqual(self.locate(package_file=package_file), dev_checkout)

    def test_a_directory_without_the_config_templates_is_not_a_checkout(self):
        half = self.tmp / "half"
        (half / "deploy").mkdir(parents=True)
        (half / "deploy" / "deployer.py").write_text("# stub\n", encoding="utf-8")
        with self.assertRaises(cli.RepositoryNotFoundError):
            self.locate(cwd=half)

    def test_nothing_found_gives_actionable_guidance(self):
        with self.assertRaises(cli.RepositoryNotFoundError) as raised:
            self.locate()
        message = str(raised.exception)
        self.assertIn(cli.REPO_ENV_VAR, message)
        self.assertIn("install.sh", message)


class FrontEndToDeployerTests(unittest.TestCase):
    """No mocks: the front-end must reach the real deployer's argument parser."""

    def test_install_options_are_validated_by_the_real_deployer(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
        env.pop(cli.REPO_ENV_VAR, None)
        proc = subprocess.run(
            [sys.executable, "-m", "mpv_config", "install", "--verify"],
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
        output = proc.stdout + proc.stderr
        # --verify conflicts with the --install the front-end adds: only the real
        # deployer can say so, and it must do so with a usage error, not silent success.
        self.assertEqual(proc.returncode, 2, output)
        self.assertIn("not allowed with argument --install", output)
        self.assertNotIn("Executing:", output)


if __name__ == "__main__":
    unittest.main()
