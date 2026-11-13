"""The structured event protocol spoken to the Go renderer (ui/).

Plain (Rich/ANSI) output must stay exactly as before when the protocol is
off; when it is on, every ui call becomes one record-separator-prefixed JSON
line and prompts are answered over stdin.
"""

import io
import json
import os
import subprocess
import sys
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from deploy import installer, ui, ui_protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
RS = ui_protocol.RECORD_SEPARATOR


def _events(text):
    # Not str.splitlines(): it treats the record separator itself as a line break.
    return [json.loads(line[1:]) for line in text.split("\n") if line.startswith(RS)]


class ProtocolCapture:
    """Turn the protocol on in-process and collect what it emits."""

    def __enter__(self):
        self.out = io.StringIO()
        self._patches = [
            mock.patch.object(ui_protocol, "ACTIVE", True),
            mock.patch.object(ui_protocol, "_out", self.out),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()

    @property
    def events(self):
        return _events(self.out.getvalue())


class EventShapeTests(unittest.TestCase):
    def test_log_levels_and_markup_is_stripped(self):
        with ProtocolCapture() as cap:
            ui.step("[bold]Fetching[/bold] uosc")
            ui.success("done")
            ui.warn("[DRY RUN] stays literal")
            ui.warn("retrying", transient=True)
            ui.error("boom")
        kinds = [(e["level"], e["text"]) for e in cap.events]
        self.assertEqual(
            kinds,
            [
                ("step", "Fetching uosc"),
                ("ok", "done"),
                ("warn", "[DRY RUN] stays literal"),
                ("warn", "retrying"),
                ("error", "boom"),
            ],
        )
        self.assertTrue(cap.events[3]["transient"])
        self.assertNotIn("transient", cap.events[2])

    def test_header_table_summary_panel(self):
        with ProtocolCapture() as cap:
            ui.header("Fetching Scripts & Shaders", key="fetch")
            ui.table("Results", ["Status", "Check"], [["[green]OK[/green]", "mpv"]])
            ui.summary(
                [{"name": "a", "status": "ok"}, {"name": "b", "status": "failed", "detail": "x"}]
            )
            ui.panel("Deployment complete.\nConfig: /c", title="Success", style="green")
        phase, table, summary, panel = cap.events
        self.assertEqual((phase["t"], phase["key"]), ("phase", "fetch"))
        self.assertEqual(table["rows"], [["OK", "mpv"]])
        self.assertEqual(summary["succeeded"], 1)
        self.assertEqual(summary["failed"], [{"name": "b", "detail": "x"}])
        self.assertEqual(panel["text"], "Deployment complete.\nConfig: /c")

    def test_download_progress_reports_numbers_instead_of_drawing(self):
        with ProtocolCapture() as cap:
            progress = ui.InlineDownloadProgress("Downloading uosc", update_interval=0.0)
            progress.start_connect_ticks()
            progress.settle()
            progress.total = 10
            progress.update(4)
            progress.finish()
        states = [(e["state"], e.get("done"), e.get("total")) for e in cap.events]
        self.assertEqual(states[0], ("connect", 0, None))
        self.assertIn(("run", 4, 10), states)
        self.assertEqual(states[-1], ("done", 4, 10))
        self.assertIsNone(progress._tick_thread, "no local tick thread in protocol mode")

    def test_plan_uses_short_labels(self):
        from deploy.planner import PlanEntry, display_plan

        plan = [
            PlanEntry("package", "install", "mpv", "via apt"),
            PlanEntry("fetch", "fetch", "uosc", ""),
        ]
        with ProtocolCapture() as cap:
            display_plan(plan, "Installation Plan")
        plan_event = [e for e in cap.events if e["t"] == "plan"][0]
        self.assertEqual([g["label"] for g in plan_event["groups"]], ["Packages", "Downloads"])
        self.assertEqual(plan_event["groups"][0]["entries"][0]["target"], "mpv")


class PromptRoundTripTests(unittest.TestCase):
    """Prompts block on stdin for the renderer's answer (real subprocess)."""

    def run_child(self, code, replies):
        env = dict(
            os.environ,
            MPV_CONFIG_UI_PROTOCOL="1",
            MPV_CONFIG_UI_INTERACTIVE="1",
            PYTHONPATH=str(REPO_ROOT),
        )
        proc = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            input="".join(json.dumps(r) + "\n" for r in replies),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_confirm_and_menu_answers(self):
        out = self.run_child(
            """
            from deploy import ui
            print("interactive", ui.is_interactive())
            print("confirm", ui.confirm("Proceed?"))
            print("menu", ui.menu_select("Mode", [("A+A", "x"), ("off", "y")], 0))
            """,
            # a stale/foreign reply first: it must be skipped, not consumed as the answer
            [{"id": 999, "value": True}, {"id": 1, "value": False}, {"id": 2, "value": "off"}],
        )
        self.assertIn("interactive True", out)
        self.assertIn("confirm False", out)
        self.assertIn("menu off", out)
        prompts = [e for e in _events(out) if e["t"] == "prompt"]
        self.assertEqual([p["kind"] for p in prompts], ["confirm", "menu"])

    def test_eof_and_invalid_answers_fall_back_safely(self):
        out = self.run_child(
            """
            from deploy import ui
            print("menu", ui.menu_select("Mode", [("A+A", "x"), ("off", "y")], 1))
            print("confirm", ui.confirm("Proceed?"))
            """,
            [{"id": 1, "value": "not-a-preset"}],
        )
        self.assertIn("menu off", out)  # invalid value → default row
        self.assertIn("confirm False", out)  # EOF → "no", like the plain prompt


@unittest.skipUnless(os.name == "posix", "POSIX child shell")
class CommandEventsTests(unittest.TestCase):
    def test_run_reports_start_and_end_and_never_shares_stdin(self):
        with ProtocolCapture() as cap, redirect_stdout(io.StringIO()) as plain:
            # `cat` would block forever (or eat renderer replies) if it got our stdin.
            ok = installer._run(["/bin/sh", "-c", "cat; echo out; exit 3"], timeout=20)
        self.assertFalse(ok)
        self.assertEqual(plain.getvalue(), "", "protocol mode prints nothing directly")
        commands = [e for e in cap.events if e["t"] == "command"]
        start, end = commands[0], commands[-1]
        self.assertEqual(start["state"], "start")
        self.assertFalse(end["ok"])
        self.assertIn("out", end["tail"])

    def test_plain_mode_output_is_unchanged(self):
        with redirect_stdout(io.StringIO()) as out:
            installer._run(["/bin/sh", "-c", "exit 0"], timeout=20)
        self.assertTrue(out.getvalue().startswith("  $ /bin/sh -c 'exit 0'"))
        self.assertNotIn(RS, out.getvalue())


@unittest.skipUnless(os.name == "posix", "sudo exists on POSIX only")
class PrivilegeHandshakeTests(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(ui_protocol, "ACTIVE", True),
            mock.patch.object(installer.shutil, "which", return_value="/usr/bin/sudo"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_cached_credentials_run_non_interactively(self):
        with (
            mock.patch.object(installer, "_sudo_cached", return_value=True),
            mock.patch.object(ui, "request_sudo") as ask,
        ):
            cmd, ok = installer._prepare_privileges(["sudo", "apt-get", "install", "-y", "mpv"])
        self.assertTrue(ok)
        self.assertEqual(cmd[:2], ["sudo", "-n"])
        ask.assert_not_called()

    def test_missing_credentials_ask_the_renderer_once(self):
        with (
            mock.patch.object(installer, "_sudo_cached", side_effect=[False, True]),
            mock.patch.object(ui, "request_sudo", return_value=True) as ask,
        ):
            cmd, ok = installer._prepare_privileges(["sudo", "pacman", "-S", "mpv"])
        self.assertTrue(ok)
        ask.assert_called_once()
        self.assertEqual(cmd[:2], ["sudo", "-n"])

    def test_refused_password_blocks_the_command(self):
        with (
            mock.patch.object(installer, "_sudo_cached", return_value=False),
            mock.patch.object(ui, "request_sudo", return_value=False),
            mock.patch.object(ui, "error"),
        ):
            _cmd, ok = installer._prepare_privileges(["paru", "-S", "--noconfirm", "x"])
        self.assertFalse(ok)

    def test_shell_pipelines_with_sudo_are_detected(self):
        self.assertTrue(installer._needs_sudo(["/bin/sh", "-c", "printf x | sudo tee /etc/x"]))
        self.assertFalse(installer._needs_sudo(["/bin/sh", "-c", "curl -LsSf x | sh"]))
        self.assertFalse(installer._needs_sudo(["mpv", "--version"]))


if __name__ == "__main__":
    unittest.main()
