import unittest
import os
import json
import tempfile
import pathlib

# Import the module to test (will fail before implementation)
try:
    from tools import download_worker
except ImportError:
    download_worker = None

class TestDownloadWorker(unittest.TestCase):
    def setUp(self):
        if download_worker is None:
            self.skipTest("download_worker module not yet implemented")

    def test_parse_progress_line_standard(self):
        line = "[download]  45.2% of  50.00MiB at  4.20MiB/s ETA 00:07"
        data = download_worker.parse_progress_line(line)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data['percent'], 45.2)
        self.assertEqual(data['percent_int'], 45)
        self.assertEqual(data['speed'], '4.20MiB/s')
        self.assertEqual(data['eta'], '00:07')

    def test_parse_progress_line_approximate(self):
        line = "[download]  12.0% of ~150.00MiB at 12.5MiB/s ETA 00:15"
        data = download_worker.parse_progress_line(line)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data['percent'], 12.0)
        self.assertEqual(data['percent_int'], 12)
        self.assertEqual(data['speed'], '12.5MiB/s')
        self.assertEqual(data['eta'], '00:15')

    def test_parse_progress_line_completed(self):
        line = "[download] 100% of 10.50MiB in 00:02"
        data = download_worker.parse_progress_line(line)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data['percent'], 100.0)
        self.assertEqual(data['percent_int'], 100)

    def test_parse_progress_line_non_progress(self):
        line = "[info] 17007267: Downloading webpage"
        data = download_worker.parse_progress_line(line)
        self.assertIsNone(data)

    def test_build_ytdl_args_with_aria2(self):
        args = download_worker.build_ytdl_args(
            url="https://txxx.com/video.mp4",
            output="D:/Downloads/%(title)s.%(ext)s",
            aria2c_path="C:/aria2/aria2c.exe",
            user_agent="Mozilla/5.0 TestUA",
            referer="https://txxx.com/",
            cookies="sess=xyz123",
            concurrent_fragments=6,
        )
        cmd_str = " ".join(args)
        self.assertIn("yt-dlp", args[0])
        self.assertIn("--downloader", args)
        self.assertIn("aria2c", cmd_str)
        self.assertIn("-x 16 -s 16 -k 1M", cmd_str)
        self.assertIn("--retry-wait=2", cmd_str)
        self.assertIn("--no-mtime", args)
        self.assertIn("--newline", args)
        self.assertIn("Mozilla/5.0 TestUA", cmd_str)
        self.assertIn("https://txxx.com/", cmd_str)
        self.assertIn("Cookie:sess=xyz123", cmd_str)

    def test_build_ytdl_args_without_aria2(self):
        args = download_worker.build_ytdl_args(
            url="https://youtube.com/watch?v=123",
            output="D:/Downloads/%(title)s.%(ext)s",
            aria2c_path=None,
            concurrent_fragments=6,
        )
        self.assertIn("--concurrent-fragments", args)
        self.assertIn("6", args)
        self.assertNotIn("--downloader", args)

    def test_atomic_write_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            download_worker.atomic_write_state(state_file, {
                "status": "downloading",
                "percent": 54.3,
                "percent_int": 54,
                "speed": "8.5MiB/s",
                "eta": "00:10"
            })
            self.assertTrue(os.path.exists(state_file))
            self.assertFalse(os.path.exists(state_file + ".tmp"))

            with open(state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["percent_int"], 54)
            self.assertEqual(loaded["status"], "downloading")

if __name__ == '__main__':
    unittest.main()
