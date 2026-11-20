"""Security contract of the browser native-messaging host (2026-11-20 audit, 4.1).

The host used to run an HTTP daemon on 127.0.0.1:8765 that any web page could
drive. It is now native messaging only; these tests pin the rules that keep it so.
"""

import ast
import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import register_extension
from tools.native_host import cookie_sync_host as host

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_SOURCE = REPO_ROOT / "tools" / "native_host" / "cookie_sync_host.py"
EXTENSION_JS = REPO_ROOT / "tools" / "extension" / "background.js"

OUR_ID = "abcdefghijklmnopabcdefghijklmnop"
OUR_ORIGIN = f"chrome-extension://{OUR_ID}/"
FOREIGN_ORIGIN = "chrome-extension://ponmlkjihgfedcbaponmlkjihgfedcba/"

INJECTION_URLS = [
    "--script=/tmp/evil.lua",
    "--ytdl-raw-options=exec=evil",
    "-v",
    "--",
]
NON_HTTP_URLS = [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "ytdl://ytsearch:anything",
    "ftp://example.com/video.mp4",
    "data:text/html,hi",
    "https://",
    "https://exa mple.com/v",
    "https://example.com/v\n--script=evil.lua",
    "",
    None,
    42,
]


def isolate_host(test: unittest.TestCase) -> Path:
    """Point every location the host reads or writes at a scratch directory.

    save_cookies()/save_stream() write under %APPDATA% and next to the repository
    (cookies.txt); the host manifest lives under LOCALAPPDATA / XDG_DATA_HOME. A
    test run must never touch a real cookie jar or leave files in the working tree.
    """
    scratch = tempfile.TemporaryDirectory()
    test.addCleanup(scratch.cleanup)
    root = Path(scratch.name)
    (root / "repo").mkdir()
    patchers = [
        mock.patch.dict(
            os.environ,
            {
                "APPDATA": str(root / "appdata"),
                "LOCALAPPDATA": str(root / "localappdata"),
                "XDG_DATA_HOME": str(root / "xdg-data"),
            },
        ),
        mock.patch.object(host, "_repo_dir", return_value=root / "repo"),
        mock.patch.dict(host.STREAM_CACHE, clear=True),
    ]
    for patcher in patchers:
        patcher.start()
        test.addCleanup(patcher.stop)
    return root


def frame(message) -> bytes:
    payload = json.dumps(message).encode("utf-8")
    return struct.pack("@I", len(payload)) + payload


def responses(raw: bytes) -> list:
    out, stream = [], io.BytesIO(raw)
    while True:
        head = stream.read(4)
        if len(head) < 4:
            return out
        out.append(json.loads(stream.read(struct.unpack("@I", head)[0])))


class HostTestCase(unittest.TestCase):
    def setUp(self):
        self.root = isolate_host(self)
        popen = mock.patch.object(host.subprocess, "Popen")
        self.popen = popen.start()
        self.addCleanup(popen.stop)

    def write_manifest(self, origins):
        path = host.host_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"name": host.HOST_NAME, "type": "stdio", "allowed_origins": origins}),
            encoding="utf-8",
        )

    def run_host(self, argv, *messages):
        stdout = io.BytesIO()
        rc = host.main(argv, io.BytesIO(b"".join(frame(m) for m in messages)), stdout)
        return rc, responses(stdout.getvalue())


class CallerOriginTests(HostTestCase):
    PLAY = {"action": "play", "url": "https://example.com/watch?v=1"}

    def setUp(self):
        super().setUp()
        self.write_manifest([OUR_ORIGIN])

    def test_a_request_from_a_foreign_origin_is_rejected(self):
        rc, out = self.run_host(["host", FOREIGN_ORIGIN], self.PLAY)
        self.assertEqual(1, rc)
        self.assertEqual([], out)
        self.popen.assert_not_called()

    def test_a_web_page_origin_or_no_origin_is_rejected(self):
        for argv in (["host"], ["host", "https://evil.example"], ["host", "--daemon"]):
            with self.subTest(argv=argv):
                rc, out = self.run_host(argv, self.PLAY)
                self.assertEqual((1, []), (rc, out))
        self.popen.assert_not_called()

    def test_a_wildcard_in_the_manifest_never_matches(self):
        self.write_manifest(["chrome-extension://*/", "*"])
        for origin in ("chrome-extension://*/", "*"):
            with self.subTest(origin=origin):
                self.assertEqual(1, self.run_host(["host", origin], self.PLAY)[0])
        self.popen.assert_not_called()

    def test_no_manifest_rejects_everything(self):
        host.host_manifest_path().unlink()
        self.assertEqual(1, self.run_host(["host", OUR_ORIGIN], self.PLAY)[0])
        self.popen.assert_not_called()

    def test_our_extension_is_served(self):
        rc, out = self.run_host(["host", OUR_ORIGIN, "--parent-window=0"], self.PLAY)
        self.assertEqual(0, rc)
        self.assertEqual([{"status": "ok", "action": "playing"}], out)
        self.popen.assert_called_once()

    def test_host_and_registrar_agree_on_the_manifest_path(self):
        expected = register_extension.get_user_data_dir() / "extension" / f"{host.HOST_NAME}.json"
        self.assertEqual(expected, host.host_manifest_path())

    def test_the_registered_manifest_allows_only_our_extension(self):
        target = self.root / "registered.json"
        with (
            mock.patch.object(register_extension, "host_manifest_path", target),
            mock.patch.object(register_extension, "log"),
        ):
            register_extension.create_native_host_manifest(OUR_ID)
        manifest = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual("stdio", manifest["type"])
        self.assertEqual([OUR_ORIGIN], manifest["allowed_origins"])


class NoNetworkListenerTests(unittest.TestCase):
    def test_the_host_opens_no_socket(self):
        tree = ast.parse(HOST_SOURCE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        network = {"http", "socket", "socketserver", "asyncio", "ssl", "urllib3", "xmlrpc"}
        self.assertEqual(set(), imported & network)
        self.assertFalse(hasattr(host, "start_http_server"))

    def test_the_extension_talks_to_no_local_port(self):
        source = EXTENSION_JS.read_text(encoding="utf-8")
        self.assertNotIn("127.0.0.1", source)
        self.assertNotIn("localhost", source)
        self.assertNotIn("fetch(", source)


class LaunchArgumentTests(HostTestCase):
    def test_a_url_starting_with_dashes_cannot_inject_an_option(self):
        for url in INJECTION_URLS:
            for launch in (host.execute_play, host.execute_download):
                with self.subTest(url=url, launch=launch.__name__):
                    self.assertFalse(launch(url))
        self.popen.assert_not_called()

    def test_the_url_always_follows_the_option_separator(self):
        url = "https://example.com/--script=evil.lua?x=--ytdl-raw-options"
        for build in (host.build_play_command, host.build_download_command):
            with self.subTest(build=build.__name__):
                argv = build(url)
                self.assertEqual(["--", url], argv[-2:])
                self.assertEqual(1, argv.count(url))
                self.assertLess(argv.index("--"), argv.index(url))

    def test_a_non_http_url_is_rejected(self):
        for url in NON_HTTP_URLS:
            for action in ("play", "download"):
                with self.subTest(url=url, action=action):
                    reply = host.handle_message({"action": action, "url": url})
                    self.assertEqual("error", reply["status"])
        self.popen.assert_not_called()

    def test_http_and_https_urls_are_accepted(self):
        for url in ("http://example.com/v.mp4", "HTTPS://Example.com/watch?v=1"):
            with self.subTest(url=url):
                self.assertEqual(url, host.validate_url(url))

    def test_the_windows_launch_path_never_uses_cmd(self):
        url = "https://example.com/watch?v=1&calc|whoami"
        mpv_exe = r"C:\Program Files\mpv\mpv.exe"
        with (
            mock.patch.object(host, "find_mpv", return_value=mpv_exe),
            mock.patch.object(host.sys, "platform", "win32"),
        ):
            self.assertTrue(host.execute_play(url))
            self.assertTrue(host.execute_download(url))
        self.assertEqual(2, self.popen.call_count)
        for call in self.popen.call_args_list:
            argv, kwargs = call.args[0], call.kwargs
            self.assertIsInstance(argv, list)
            self.assertNotIn(Path(argv[0]).name.lower(), ("cmd", "cmd.exe"))
            self.assertNotIn("start", argv)
            self.assertNotIn("/c", argv)
            self.assertFalse(kwargs.get("shell", False))
            self.assertEqual(url, argv[-1])
        play_kwargs = self.popen.call_args_list[0].kwargs
        download_kwargs = self.popen.call_args_list[1].kwargs
        self.assertEqual(host.DETACHED_PROCESS, play_kwargs["creationflags"])
        self.assertEqual({"creationflags": host.CREATE_NEW_CONSOLE}, download_kwargs)
        source = HOST_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn('"cmd"', source)
        self.assertNotIn("shell=True", source)

    def test_posix_children_never_inherit_the_browser_pipes(self):
        with mock.patch.object(host.sys, "platform", "linux"):
            host.execute_play("https://example.com/v")
        kwargs = self.popen.call_args.kwargs
        for stream in ("stdin", "stdout", "stderr"):
            self.assertIs(host.subprocess.DEVNULL, kwargs[stream])
        self.assertTrue(kwargs["start_new_session"])

    def test_a_missing_player_is_reported_not_crashed(self):
        self.popen.side_effect = FileNotFoundError(2, "No such file or directory")
        reply = host.handle_message({"action": "play", "url": "https://example.com/v"})
        self.assertEqual("error", reply["status"])


GOOD_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    "# Exported automatically by MPV Companion Extension\n"
    "\n"
    ".example.com\tTRUE\t/\tTRUE\t1893456000\tcf_clearance\tabc123\n"
    "#HttpOnly_.example.com\tTRUE\t/\tFALSE\t0\tsession\txyz\n"
)


class CookieFileTests(HostTestCase):
    def targets(self):
        return host.cookie_targets("example.com")

    def test_valid_cookies_are_written_to_every_target(self):
        saved = host.save_cookies(GOOD_COOKIES, "example.com")
        self.assertEqual([str(p) for p in self.targets()], saved)
        for path in self.targets():
            self.assertEqual(GOOD_COOKIES, path.read_text(encoding="utf-8"))
            if os.name == "posix":
                self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_malformed_content_is_rejected_and_nothing_written(self):
        bad = {
            "wrong field count": ".example.com\tTRUE\t/\tTRUE\t0\tname\n",
            "extra field": ".example.com\tTRUE\t/\tTRUE\t0\tname\tvalue\textra\n",
            "nul byte": ".example.com\tTRUE\t/\tTRUE\t0\tname\tva\x00lue\n",
            "bare carriage return": ".example.com\tTRUE\t/\tTRUE\t0\tname\tva\rlue\n",
            "bad flag": ".example.com\tMAYBE\t/\tTRUE\t0\tname\tvalue\n",
            "bad expiry": ".example.com\tTRUE\t/\tTRUE\tsoon\tname\tvalue\n",
            "bad path": ".example.com\tTRUE\tnope\tTRUE\t0\tname\tvalue\n",
            "bad domain": "../../etc\tTRUE\t/\tTRUE\t0\tname\tvalue\n",
            "comments only": "# Netscape HTTP Cookie File\n\n",
        }
        for label, text in bad.items():
            with self.subTest(label):
                self.assertEqual([], host.save_cookies(text, "example.com"))
        for path in self.targets():
            self.assertFalse(path.exists())

    def test_oversized_content_is_rejected(self):
        line = ".example.com\tTRUE\t/\tTRUE\t0\tname\t" + "v" * 1000 + "\n"
        huge = line * (host.MAX_COOKIE_BYTES // len(line) + 1)
        self.assertEqual([], host.save_cookies(huge, "example.com"))

    def test_an_existing_jar_survives_a_rejected_or_failed_write(self):
        self.assertTrue(host.save_cookies(GOOD_COOKIES, "example.com"))
        self.assertEqual([], host.save_cookies("garbage", "example.com"))
        with mock.patch.object(Path, "replace", side_effect=OSError("disk full")):
            self.assertEqual(
                [], host.save_cookies(GOOD_COOKIES.replace("abc123", "new"), "example.com")
            )
        for path in self.targets():
            self.assertEqual(GOOD_COOKIES, path.read_text(encoding="utf-8"))
            leftovers = [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")]
            self.assertEqual([], leftovers)

    def test_a_hostile_domain_cannot_choose_the_file_name(self):
        saved = host.save_cookies(GOOD_COOKIES, "../../outside")
        self.assertTrue(saved)
        for path in map(Path, saved):
            self.assertNotIn("outside", path.name)
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertEqual([], host.save_cookies("name=value", "../../outside"))


class ProtocolTests(unittest.TestCase):
    def test_an_oversized_message_is_refused_before_it_is_read(self):
        stream = io.BytesIO(struct.pack("@I", host.MAX_MESSAGE_BYTES + 1) + b"{}")
        self.assertIsNone(host.read_native_message(stream))
        self.assertEqual(4, stream.tell())

    def test_a_non_object_message_is_ignored(self):
        self.assertIsNone(host.read_native_message(io.BytesIO(frame(["play"]))))


class CookieAndStreamCacheTests(unittest.TestCase):
    def setUp(self):
        self.root = isolate_host(self)

    def test_save_cookies_netscape(self):
        sample = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t9999999999\tcf_clearance\ttestval\n"
        targets = host.save_cookies(sample, "example.com")
        self.assertEqual(4, len(targets))
        for target in targets:
            self.assertEqual(sample, Path(target).read_text(encoding="utf-8"))

    def test_save_cookies_header_format(self):
        targets = host.save_cookies("cf_clearance=test12345; in_d4=1", "example.com")
        self.assertGreater(len(targets), 0)
        text = Path(targets[0]).read_text(encoding="utf-8")
        self.assertIn(".example.com\tTRUE\t/\tTRUE\t", text)
        self.assertIn("\tcf_clearance\ttest12345\n", text)

    def test_stream_cache(self):
        slug = "test-video-unit"
        m3u8 = "https://example.com/stream/index.m3u8"
        self.assertIsNotNone(host.save_stream(slug, m3u8, title="Unit Video"))

        host.STREAM_CACHE.clear()  # force the disk round trip
        cached = host.get_cached_stream(slug)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["url"], m3u8)
        self.assertEqual(cached["title"], "Unit Video")
        self.assertTrue((self.root / "appdata" / "mpv-config" / "active_streams.json").is_file())

    def test_unknown_slug_returns_none(self):
        self.assertIsNone(host.get_cached_stream("non-existent-slug-xyz"))

    def test_stream_with_a_non_http_url_is_not_cached(self):
        self.assertIsNone(host.save_stream("slug", "file:///etc/passwd"))
        self.assertIsNone(host.get_cached_stream("slug"))


if __name__ == "__main__":
    unittest.main()
