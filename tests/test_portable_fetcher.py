import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from unittest import mock

from deploy import fetcher
from deploy.path_safety import relative_parts


def archive(members):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as zf:
        for name, content in members:
            zf.writestr(name, content)
    return target.getvalue()


class PortableFetcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stage = self.root / "stage"
        self.stage.mkdir()
        self.entry = {"name": "uosc", "source": {"repo": "fixture/uosc", "pin": "v1", "asset_pattern": "uosc.zip"}, "install": {"map": {"scripts/uosc/": "scripts/uosc/", "fonts/": "fonts/"}}}

    def release(self, members, shader=False, entry=None):
        payload = json.dumps({"tag_name": "v1", "assets": [{"name": "uosc.zip", "browser_download_url": "https://example.invalid/test.zip"}]})
        with mock.patch.object(fetcher, "_request", side_effect=[payload, archive(members)]), contextlib.redirect_stdout(io.StringIO()):
            return fetcher.fetch_release(entry or self.entry, str(self.stage), is_shader=shader)

    def test_portable_path_rejection(self):
        bad = ["../outside", "/absolute", "C:/absolute", "C:relative", r"\\server\share", "scripts/../../out", "scripts/x:stream", "scripts/CON", "scripts/AUX.txt", "scripts/com1.lua", "scripts/lpt2", "scripts/trailing.", "scripts/trailing ", "scripts/a\\b", "scripts//b", "scripts/./b", "scripts/\x00bad"]
        for value in bad:
            with self.subTest(path=value), self.assertRaises(ValueError):
                relative_parts(value)

    def test_archive_traversal_has_no_side_effects(self):
        for name in ("scripts/uosc/../../../outside", "/scripts/uosc/main.lua", "scripts/uosc/x:stream", "scripts/uosc/CON.lua"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.release([("scripts/uosc/good.lua", "ok"), (name, "bad"), ("fonts/icons.ttf", "font")])
            self.assertEqual(list(self.stage.iterdir()), [])
            self.assertFalse((self.root / "outside").exists())

    def test_legitimate_uosc_layout_and_executable(self):
        executable = zipfile.ZipInfo("root/scripts/uosc/bin/ziggy")
        executable.create_system = 3
        executable.external_attr = (stat.S_IFREG | 0o6755) << 16
        meta = self.release([("root/scripts/uosc/main.lua", "return {}"), (executable, "fixture"), ("root/fonts/icons.ttf", "font")])
        self.assertEqual(meta["files_count"], 3)
        self.assertIn("scripts/uosc/bin/ziggy", meta["sha256"])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.stage / "scripts/uosc/bin/ziggy").stat().st_mode), 0o755)

    def test_zip_file_types_rejected_including_symlinks(self):
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK):
            info = zipfile.ZipInfo("scripts/uosc/unsafe.lua")
            info.create_system = 3
            info.external_attr = (kind | 0o777) << 16
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.release([(info, "../outside"), ("fonts/icons.ttf", "font")])
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_empty_missing_and_substring_components_refused(self):
        for members in ([('README', 'empty')], [('scripts/uosc/main.lua', 'no font')], [('unrelated-scripts/uosc/main.lua', 'wrong'), ('fonts/icons.ttf', 'font')]):
            with self.subTest(members=members), self.assertRaises(FileNotFoundError):
                self.release(members)
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_shader_collision_case_collision_and_destination_escape(self):
        shader = {"name": "shaders", "source": self.entry["source"], "dest": "shaders/", "extensions": [".glsl"]}
        for second in ("same.glsl", "SAME.glsl"):
            with self.subTest(second=second), self.assertRaises(ValueError):
                self.release([("a/same.glsl", "first"), ("b/" + second, "second")], True, shader)
            self.assertEqual(list(self.stage.iterdir()), [])
        shader["dest"] = "../outside/"
        with self.assertRaises(ValueError):
            self.release([("a/one.glsl", "first")], True, shader)
        self.assertFalse((self.root / "outside").exists())

    def test_legitimate_shader_archive(self):
        shader = {"name": "shaders", "source": self.entry["source"], "extensions": [".glsl"]}
        meta = self.release([("root/a.glsl", "a"), ("root/b.glsl", "b"), ("LICENSE", "notice")], True, shader)
        self.assertEqual(meta["files_count"], 2)

    def raw_entry(self):
        return {"name": "raw", "source": {"repo": "fixture/raw", "files": [{"src": "one.lua", "dest": "scripts/one.lua"}, {"src": "two.lua", "dest": "scripts/two.lua"}]}}

    def test_midway_raw_failure_leaves_no_partial_output(self):
        with mock.patch.object(fetcher, "_request", side_effect=[b"first", ConnectionError("offline")]), self.assertRaises(ConnectionError):
            fetcher.fetch_raw(self.raw_entry(), str(self.stage))
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_raw_duplicate_and_traversal_validated_before_download(self):
        for dest in ("../outside", "scripts/one.lua", "scripts/ONE.lua"):
            entry = self.raw_entry()
            entry["source"]["files"][1]["dest"] = dest
            with mock.patch.object(fetcher, "_request") as request, self.assertRaises(ValueError):
                fetcher.fetch_raw(entry, str(self.stage))
            request.assert_not_called()
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_staging_symlink_is_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.stage / "scripts").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        with mock.patch.object(fetcher, "_request") as request, self.assertRaises(ValueError):
            fetcher.fetch_raw(self.raw_entry(), str(self.stage))
        request.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    def test_raw_write_failure_removes_created_files_and_directories(self):
        real_open = open
        def injected_open(path, mode="r", *args, **kwargs):
            if str(path).endswith("two.lua") and "x" in mode:
                raise OSError("disk full")
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(fetcher, "_request", return_value=b"valid"), mock.patch("builtins.open", side_effect=injected_open), self.assertRaises(OSError):
            fetcher.fetch_raw(self.raw_entry(), str(self.stage))
        self.assertEqual(list(self.stage.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
