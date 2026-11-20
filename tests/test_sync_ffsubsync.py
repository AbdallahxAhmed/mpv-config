"""ffsubsync in sync-deps: uv tool, then pipx, never pip (constitution Principle III)."""

import itertools
import os
import unittest
from unittest import mock

from deploy import installer


def _is_pip_call(cmd):
    """True for `pip ...`, `pip3 ...` or `<python> -m pip ...` (pipx is not pip)."""
    exe = os.path.basename(str(cmd[0])).lower()
    if exe.startswith("pip") and not exe.startswith("pipx"):
        return True
    return any(a == "-m" and b == "pip" for a, b in zip(cmd, cmd[1:]))


class SyncFfsubsyncTests(unittest.TestCase):
    def _sync(self, tools, run_result=True):
        """Run _sync_ffsubsync_cli with only `tools` on PATH; return (result, cmds, ui)."""
        cmds = []

        def fake_which(name):
            return f"/usr/bin/{name}" if name in tools else None

        def fake_run(cmd, check=True, env=None, timeout=300):
            cmds.append(list(cmd))
            return run_result(cmd) if callable(run_result) else run_result

        with (
            mock.patch.object(installer.shutil, "which", side_effect=fake_which),
            mock.patch.object(installer, "_run", side_effect=fake_run),
            mock.patch.object(installer, "ui") as fake_ui,
        ):
            result = installer._sync_ffsubsync_cli()
        return result, cmds, fake_ui

    def test_pip_is_never_called(self):
        # Every combination of uv/pipx/python/pip/ffsubsync on PATH and of
        # commands succeeding or failing: no command may invoke pip.
        names = ("uv", "pipx", "python", "python3", "pip", "pip3", "ffsubsync")
        for present in itertools.product((False, True), repeat=len(names)):
            tools = {n for n, on in zip(names, present) if on}
            for ok in (True, False):
                with self.subTest(tools=sorted(tools), run_ok=ok):
                    _, cmds, _ = self._sync(tools, run_result=ok)
                    self.assertFalse(
                        [c for c in cmds if _is_pip_call(c)], f"pip was called: {cmds}"
                    )

    def test_uv_tool_is_tried_first(self):
        result, cmds, _ = self._sync({"uv", "pipx"})
        self.assertEqual(cmds, [["uv", "tool", "install", "--upgrade", "ffsubsync"]])
        self.assertEqual(result["status"], "ok")

    def test_pipx_upgrade_then_install_when_uv_missing(self):
        result, cmds, _ = self._sync({"pipx"}, run_result=lambda c: c[1] == "install")
        self.assertEqual(cmds, [["pipx", "upgrade", "ffsubsync"], ["pipx", "install", "ffsubsync"]])
        self.assertEqual(result["status"], "ok")

    def test_pipx_is_the_fallback_when_uv_fails(self):
        _, cmds, _ = self._sync({"uv", "pipx"}, run_result=lambda c: c[0] == "pipx")
        self.assertEqual(cmds[0][0], "uv")
        self.assertEqual(cmds[1], ["pipx", "upgrade", "ffsubsync"])

    def test_without_uv_or_pipx_nothing_is_installed_and_user_is_told(self):
        result, cmds, fake_ui = self._sync({"python3", "pip"})
        self.assertEqual(cmds, [])
        self.assertEqual(result["status"], "skipped")
        message = " ".join(str(c.args[0]) for c in fake_ui.warn.call_args_list)
        self.assertIn("uv", message)
        self.assertIn("pipx", message)

    def test_without_uv_or_pipx_an_existing_ffsubsync_is_kept(self):
        result, cmds, _ = self._sync({"ffsubsync"})
        self.assertEqual(cmds, [])
        self.assertEqual(result["status"], "ok")
        self.assertIn("not upgraded", result["detail"])


if __name__ == "__main__":
    unittest.main()
