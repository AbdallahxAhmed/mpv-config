"""Spec 005 C-008: the weekly uosc release check (contracts/uosc-release-check.md).

Everything runs offline: check_dir() on the fixture, and run() against a local
http.server on 127.0.0.1 that hangs, trickles or misbehaves on purpose.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tools import check_uosc_release as check

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "uosc-5.13.0"
MENU = (FIXTURE / "elements" / "Menu.lua").read_bytes()
MENU_KEY_ANCHOR = b"\tif info.event == 'up' then return end\n"
DEADLINE_TEXT = "did not finish within 1 s"


def zip_bytes(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


GOOD_ZIP = zip_bytes({check.MEMBER: MENU, "scripts/uosc/main.lua": b"-- main\n"})


class FakeGitHub:
    """A loopback server; routes map a path to handler(request, server)."""

    def __init__(self, test, routes):
        self.stop = threading.Event()
        self.seen = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.seen.append((self.path, dict(self.headers)))
                with contextlib.suppress(OSError):
                    routes[self.path](self, outer)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        test.addCleanup(self.close)

    def url(self, path):
        return f"http://127.0.0.1:{self.httpd.server_port}{path}"

    def close(self):
        self.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()


def send(request, body, status=200, headers=()):
    request.send_response(status)
    for name, value in headers:
        request.send_header(name, value)
    request.send_header("Content-Length", str(len(body)))
    request.end_headers()
    request.wfile.write(body)


def release(asset_path="/uosc.zip", name="uosc.zip", tag="5.99.0"):
    def route(request, server):
        assets = [{"name": name, "browser_download_url": server.url(asset_path)}]
        send(request, json.dumps({"tag_name": tag, "assets": assets}).encode())

    return route


def run_check(**kwargs):
    out = io.StringIO()
    started = time.monotonic()
    with contextlib.redirect_stdout(out):
        code = check.run(**kwargs)
    return code, out.getvalue(), time.monotonic() - started


class CheckDirTests(unittest.TestCase):
    def test_all_anchors_match_on_the_pinned_release(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, check.check_dir(FIXTURE, "5.13.0"))
        self.assertEqual(
            "uosc 5.13.0: all 8 anchors of uosc-playlist-reorder match\n", out.getvalue()
        )

    def test_a_broken_anchor_names_the_version_and_the_hunk(self):  # SC-009
        tmp = Path(tempfile.mkdtemp(prefix="uosc-release-check-"))
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(FIXTURE, tmp, dirs_exist_ok=True)
        broken = MENU.replace(MENU_KEY_ANCHOR, MENU_KEY_ANCHOR.replace(b"'up'", b"'Up'"))
        self.assertNotEqual(MENU, broken)
        (tmp / "elements" / "Menu.lua").write_bytes(broken)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(1, check.check_dir(tmp, "5.13.0"))
        self.assertEqual(
            "::error title=uosc release check::uosc 5.13.0: anchor menu-key matched 0× "
            "in elements/Menu.lua (expected 1)\n",
            out.getvalue(),
        )


class RunTests(unittest.TestCase):
    def test_latest_release_passes_through_a_redirect(self):
        server = FakeGitHub(
            self,
            {
                "/api": release(),
                "/uosc.zip": lambda r, s: send(r, b"", 302, [("Location", "/cdn/uosc.zip")]),
                "/cdn/uosc.zip": lambda r, s: send(r, GOOD_ZIP),
            },
        )
        code, out, _ = run_check(api_url=server.url("/api"))
        self.assertEqual(0, code)
        self.assertEqual("uosc 5.99.0: all 8 anchors of uosc-playlist-reorder match\n", out)

    def test_hung_server_stops_at_the_deadline(self):
        def hang(request, server):
            request.send_response(200)
            request.send_header("Content-Length", "1048576")
            request.end_headers()
            server.stop.wait(30)

        server = FakeGitHub(self, {"/api": hang})
        code, out, elapsed = run_check(api_url=server.url("/api"), download_timeout=1)
        self.assertEqual(2, code)
        self.assertLess(elapsed, 5)
        self.assertIn(DEADLINE_TEXT, out)
        self.assertIn(server.url("/api"), out)

    def test_trickled_body_stops_at_the_deadline(self):
        def trickle(request, server):
            request.send_response(200)
            request.send_header("Content-Length", "1048576")
            request.end_headers()
            while not server.stop.wait(0.2):
                request.wfile.write(b"x")

        server = FakeGitHub(self, {"/api": release(), "/uosc.zip": trickle})
        code, out, elapsed = run_check(api_url=server.url("/api"), download_timeout=1)
        self.assertEqual(2, code)
        self.assertLess(elapsed, 5)
        self.assertIn(DEADLINE_TEXT, out)
        self.assertIn("uosc 5.99.0:", out)

    def test_trickled_headers_stop_at_the_deadline(self):
        def trickle_headers(request, server):
            for byte in b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-Pad: abcdef\r\n":
                if server.stop.wait(0.2):
                    return
                request.wfile.write(bytes([byte]))

        server = FakeGitHub(self, {"/api": trickle_headers})
        code, out, elapsed = run_check(api_url=server.url("/api"), download_timeout=1)
        self.assertEqual(2, code)
        self.assertLess(elapsed, 5)
        self.assertIn(DEADLINE_TEXT, out)

    def test_http_error(self):
        server = FakeGitHub(self, {"/api": lambda r, s: send(r, b"boom", 500)})
        code, out, _ = run_check(api_url=server.url("/api"))
        self.assertEqual(2, code)
        self.assertEqual(
            f"::error title=uosc release check::uosc latest: HTTP 500 from {server.url('/api')}\n",
            out,
        )

    def test_invalid_zip(self):
        server = FakeGitHub(
            self, {"/api": release(), "/uosc.zip": lambda r, s: send(r, b"not a zip")}
        )
        code, out, _ = run_check(api_url=server.url("/api"))
        self.assertEqual(2, code)
        self.assertIn("uosc 5.99.0: uosc.zip is not a valid zip", out)

    def test_missing_asset(self):
        server = FakeGitHub(self, {"/api": release(name="uosc-src.zip")})
        code, out, _ = run_check(api_url=server.url("/api"))
        self.assertEqual(2, code)
        self.assertIn("uosc 5.99.0: release has no uosc.zip asset", out)

    def test_missing_member(self):
        other = zip_bytes({"scripts/uosc/main.lua": b"-- main\n"})
        server = FakeGitHub(self, {"/api": release(), "/uosc.zip": lambda r, s: send(r, other)})
        code, out, _ = run_check(api_url=server.url("/api"))
        self.assertEqual(2, code)
        self.assertIn("uosc.zip has no member scripts/uosc/elements/Menu.lua", out)

    def test_token_is_never_sent_off_api_github_com(self):
        server = FakeGitHub(self, {"/api": release(), "/uosc.zip": lambda r, s: send(r, GOOD_ZIP)})
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t0ken", "GH_TOKEN": "t0ken"}):
            code, _, _ = run_check(api_url=server.url("/api"))
        self.assertEqual(0, code)
        self.assertEqual(["/api", "/uosc.zip"], [path for path, _ in server.seen])
        for _path, headers in server.seen:
            self.assertNotIn("authorization", {name.lower() for name in headers})


class CliTests(unittest.TestCase):
    def test_cli_smoke_on_the_fixture(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.check_uosc_release",
                "--uosc-dir",
                str(FIXTURE),
                "--version",
                "5.13.0",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("all 8 anchors", proc.stdout)


if __name__ == "__main__":
    unittest.main()
