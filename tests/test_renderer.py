"""Locating, verifying and launching the optional mpv-config-ui renderer."""

import gzip
import hashlib
import io
import json
import os
import signal
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mpv_config import renderer
from mpv_config.cli import main as cli

BINARY = b"\x7fELF fake renderer build"
DIGEST = hashlib.sha256(BINARY).hexdigest()


class Tty(io.StringIO):
    def isatty(self):
        return True


class PlatformAndModeTests(unittest.TestCase):
    def test_platform_keys(self):
        self.assertEqual(renderer.platform_key("linux", "x86_64"), "linux-amd64")
        self.assertEqual(renderer.platform_key("win32", "AMD64"), "windows-amd64")
        self.assertEqual(renderer.platform_key("win32", "ARM64"), "windows-arm64")
        self.assertEqual(renderer.platform_key("darwin", "arm64"), "darwin-arm64")
        self.assertIsNone(renderer.platform_key("linux", "riscv64"))
        self.assertIsNone(renderer.platform_key("sunos5", "x86_64"))

    def test_wanted_needs_two_terminals_and_respects_opt_outs(self):
        tty = Tty()
        self.assertTrue(renderer.wanted({}, tty, tty))
        self.assertFalse(renderer.wanted({}, io.StringIO(), tty))  # piped input
        self.assertFalse(renderer.wanted({}, tty, io.StringIO()))  # redirected output
        self.assertFalse(renderer.wanted({"MPV_CONFIG_UI": "plain"}, tty, tty))
        self.assertFalse(renderer.wanted({"TERM": "dumb"}, tty, tty))
        self.assertFalse(renderer.wanted({"CI": "true"}, tty, tty))
        self.assertTrue(renderer.wanted({"CI": "true", "MPV_CONFIG_UI": "fancy"}, tty, tty))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.repo = self.root / "repo"
        (self.repo / "ui").mkdir(parents=True)
        self.env = {
            "XDG_DATA_HOME": str(self.root / "data"),
            "LOCALAPPDATA": str(self.root / "data"),
        }
        key = renderer.platform_key()
        if key is None:
            self.skipTest("unsupported test platform")
        self.key = key
        self.write_manifest(DIGEST)

    def write_manifest(self, digest, key=None):
        manifest = {
            "version": "9.9.9",
            "tag": "ui-v9.9.9",
            "assets": {(key or self.key): {"file": "mpv-config-ui.gz", "sha256": digest}},
        }
        (self.repo / "ui" / "release.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_download_is_verified_cached_and_reused(self):
        fetch = mock.Mock(return_value=gzip.compress(BINARY))
        first = renderer.resolve(self.repo, env=self.env, fetch=fetch)
        self.assertIsNotNone(first)
        self.assertEqual(first.read_bytes(), BINARY)
        self.assertIn("ui-v9.9.9/mpv-config-ui.gz", fetch.call_args.args[0])
        if os.name == "posix":
            self.assertTrue(os.access(first, os.X_OK))
        again = renderer.resolve(self.repo, env=self.env, fetch=fetch)
        self.assertEqual(again, first)
        fetch.assert_called_once()  # cache hit: no second download

    def test_tampered_cache_is_replaced(self):
        fetch = mock.Mock(return_value=gzip.compress(BINARY))
        path = renderer.resolve(self.repo, env=self.env, fetch=fetch)
        path.write_bytes(b"tampered")
        self.assertEqual(
            renderer.resolve(self.repo, env=self.env, fetch=fetch).read_bytes(), BINARY
        )
        self.assertEqual(fetch.call_count, 2)

    def test_hash_mismatch_is_refused(self):
        notes = []
        fetch = mock.Mock(return_value=gzip.compress(b"something else"))
        self.assertIsNone(
            renderer.resolve(self.repo, env=self.env, fetch=fetch, notice=notes.append)
        )
        self.assertIn("SHA-256", notes[0])
        self.assertFalse(
            renderer.cache_dir(self.env).exists() and any(renderer.cache_dir(self.env).iterdir())
        )

    def test_offline_or_unpublished_falls_back_quietly(self):
        fetch = mock.Mock(side_effect=OSError("offline"))
        self.assertIsNone(renderer.resolve(self.repo, env=self.env, fetch=fetch))
        self.write_manifest("", key=self.key)  # release not built yet
        fetch.reset_mock()
        self.assertIsNone(renderer.resolve(self.repo, env=self.env, fetch=fetch))
        fetch.assert_not_called()

    def test_override_binary_wins(self):
        custom = self.root / "dev-build"
        custom.write_bytes(b"x")
        env = dict(self.env, MPV_CONFIG_UI_BIN=str(custom))
        self.assertEqual(renderer.resolve(self.repo, env=env, fetch=mock.Mock()), custom)


class CliLaunchTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.repo, ignore_errors=True))
        for patcher in (
            mock.patch.object(cli, "find_repo_root", return_value=self.repo),
            mock.patch.dict(os.environ, {}, clear=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, ui_binary):
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            seen["handler"] = signal.getsignal(signal.SIGINT)
            return SimpleNamespace(returncode=0)

        with (
            mock.patch.object(cli, "_renderer_for", return_value=ui_binary),
            mock.patch.object(cli.subprocess, "run", side_effect=fake_run),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["install", "--yes"]), 0)
        return seen

    def test_renderer_wraps_the_deployer_command(self):
        seen = self.run_cli(Path("/opt/mpv-config-ui"))
        self.assertEqual(seen["command"][:2], [str(Path("/opt/mpv-config-ui")), "--"])
        self.assertEqual(
            seen["command"][2:], [sys.executable, "-m", "deploy.deployer", "--install", "--yes"]
        )

    def test_plain_output_runs_the_deployer_directly(self):
        seen = self.run_cli(None)
        self.assertEqual(seen["command"][:3], [sys.executable, "-m", "deploy.deployer"])

    def test_ctrl_c_is_left_to_the_child_while_it_runs(self):
        before = signal.getsignal(signal.SIGINT)
        seen = self.run_cli(None)
        self.assertNotIn(seen["handler"], (signal.default_int_handler, signal.SIG_IGN))
        self.assertIs(signal.getsignal(signal.SIGINT), before, "handler restored afterwards")


if __name__ == "__main__":
    unittest.main()
