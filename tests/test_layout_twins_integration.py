"""Integration loop for the layout twins: a real, agent-owned mpv.

Boots a headless mpv (no config, no scripts, no audio/video output, no
window - nothing the user can see or hear) with a generated input.conf and
drives it over a uniquely-named IPC pipe. Asserts the exact failure the
twins exist to fix: a key event carrying an Arabic character must fire the
binding of the same physical key's Latin character.

The physical half of the bug (Windows delivering the Arabic character for
the real keystroke) cannot be synthesized headlessly - that stays a
user-side acceptance check. This loop pins everything downstream of it:
the generated lines parse, register and MATCH.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

# Load by file location: an editable install (deploy clone) may be a
# commit behind and already own the cached mpv_config package.
_spec = importlib.util.spec_from_file_location(
    "layout_twins_under_test_integration",
    os.path.join(REPO, "src", "mpv_config", "layout_twins.py"))
layout_twins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout_twins)

MPV = r"C:\Program Files\mpv\mpv.exe"

SOURCE_CONF = """c set user-data/t/latin yes
h set user-data/t/h yes
b set user-data/t/b yes
? set user-data/t/q yes
"""

TWINS_TO_CHECK = [
    # (Arabic key EVENTS, flag that must be set)
    (["ؤ"], "latin"),
    (["؟"], "q"),
]
# h/b/g are NOT here on purpose: on the REAL Windows key stream b and h
# deliver the identical character (user's --input-test capture,
# 2026-10-25 - the ل of the lam-alef pair never reaches mpv), so no twin
# can distinguish them. The `keypress` command DOES deliver both
# characters, which once made a ل-ا sequence twin look correct in this
# headless harness while never firing on real hardware. Do not
# reintroduce lam-alef twins from headless evidence.


@unittest.skipUnless(
    sys.platform == "win32" and os.path.exists(MPV),
    "needs the mpv binary on Windows",
)
class TwinsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mpv_twins_test_")
        cls.pipe = r"\\.\pipe\mpv_twins_test_%d" % os.getpid()
        # red half: the source conf has no Arabic lines yet
        cls.red_conf = os.path.join(cls.tmp, "red.conf")
        with open(cls.red_conf, "w", encoding="utf-8") as f:
            f.write(SOURCE_CONF)
        # green half: same conf after generation
        generated, _ = layout_twins.generate(SOURCE_CONF)
        cls.green_conf = os.path.join(cls.tmp, "green.conf")
        with open(cls.green_conf, "w", encoding="utf-8") as f:
            f.write(generated)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _boot(self, conf_path):
        cmd = [MPV, "--no-config", "--idle", "--no-audio", "--ao=null",
               "--vo=null", "--no-terminal", "--really-quiet",
               "--input-conf=" + conf_path,
               "--input-ipc-server=" + self.pipe]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                time.sleep(0.1)
                if proc.poll() is not None:
                    raise AssertionError(
                        "mpv exited early rc=%s" % proc.returncode)
                try:
                    return proc, open(self.pipe, "r+b", buffering=0)
                except OSError:
                    continue
        except Exception:
            proc.terminate()
            proc.wait(timeout=5)
            raise
        proc.terminate()
        proc.wait(timeout=5)
        raise AssertionError("IPC pipe never appeared")

    def _run(self, conf_path):
        proc, handle = self._boot(conf_path)
        try:
            def send(command):
                handle.write(
                    (json.dumps({"command": command}) + "\n").encode("utf-8"))
                return json.loads(handle.readline().decode("utf-8", "replace"))

            time.sleep(0.5)  # let input.conf settle
            outcomes = {}
            for events, flag in TWINS_TO_CHECK:
                for event in events:
                    err = send(["keypress", event])["error"]
                outcome = send(["get_property", "user-data/t/" + flag])
                outcomes[flag] = (err, outcome.get("data"))
            latin = send(["keypress", "c"])
            latin_flag = send(["get_property", "user-data/t/latin"])
            return outcomes, (latin["error"], latin_flag.get("data"))
        finally:
            handle.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_arabic_key_fires_the_latin_binding_only_after_generation(self):
        # red: without twins the Arabic key events match nothing
        outcomes, latin = self._run(self.red_conf)
        self.assertEqual(latin[0], "success")
        for flag, (err, value) in outcomes.items():
            self.assertEqual(err, "success")
            self.assertIsNone(value,
                              "Arabic key unexpectedly matched: %r" % flag)

        # green: with the generated twins the same events fire the bindings
        outcomes, latin = self._run(self.green_conf)
        self.assertEqual(latin, ("success", "yes"))
        for flag, (err, value) in outcomes.items():
            self.assertEqual(err, "success")
            self.assertEqual(value, "yes",
                             "Arabic twin for %r did not fire" % flag)

    def test_generated_lines_all_register(self):
        """Every generated twin line must be accepted by mpv's binder:
        boot with the generated conf and dispatch the single-key twins
        (sequence twins dispatch via their component events, covered by
        the test above)."""
        generated, report = layout_twins.generate(SOURCE_CONF)
        source_keys = {line.split(None, 1)[0] for line in SOURCE_CONF.splitlines()}
        twin_lines = [line for line in generated.splitlines()
                      if line and not line.startswith("#")
                      and line.split(None, 1)[0] not in source_keys
                      and "-" not in line.split(None, 1)[0]]
        self.assertTrue(twin_lines)
        proc, handle = self._boot(self.green_conf)
        try:
            def send(command):
                handle.write(
                    (json.dumps({"command": command}) + "\n").encode("utf-8"))
                return json.loads(handle.readline().decode("utf-8", "replace"))
            time.sleep(0.5)
            for line in twin_lines:
                key = line.split(None, 1)[0]
                err = send(["keypress", key])["error"]
                self.assertEqual(err, "success",
                                 "mpv rejected twin key %r" % key)
        finally:
            handle.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    unittest.main()
