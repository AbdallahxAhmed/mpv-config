"""
Unit tests for the downloader framework, GenericDownloader, and plugin registry.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from mpv_config.cli.main import main
from mpv_config.downloaders import (
    GenericDownloader,
    MediaItem,
    get_downloader,
)


class TestDownloaderFramework(unittest.TestCase):
    def test_media_item_fields(self):
        """Test MediaItem dataclass initialization, attributes, and defaults."""
        item = MediaItem(
            title="Sample Video",
            url="https://example.com/video.mp4",
            quality="1080p",
            subtitles=["en", "ja"],
        )
        self.assertEqual(item.title, "Sample Video")
        self.assertEqual(item.url, "https://example.com/video.mp4")
        self.assertEqual(item.quality, "1080p")
        self.assertEqual(item.subtitles, ["en", "ja"])

        # Test defaults
        item_defaults = MediaItem(title="Default Video", url="https://example.com/v")
        self.assertIsNone(item_defaults.quality)
        self.assertEqual(item_defaults.subtitles, [])

        # Test None subtitles converted to empty list
        item_none_subs = MediaItem(
            title="Video",
            url="https://example.com",
            quality="720p",
            subtitles=None,
        )
        self.assertEqual(item_none_subs.subtitles, [])

    def test_get_downloader_youtube(self):
        """Test that get_downloader returns GenericDownloader for YouTube URLs."""
        dl = get_downloader("https://youtube.com/watch?v=123")
        self.assertIsInstance(dl, GenericDownloader)
        self.assertEqual(dl.name, "generic")

    def test_get_downloader_fallback(self):
        """Test that get_downloader falls back to GenericDownloader for generic URLs."""
        dl = get_downloader("https://example.com/video.mp4")
        self.assertIsInstance(dl, GenericDownloader)
        self.assertEqual(dl.name, "generic")

    @patch("yt_dlp.YoutubeDL")
    def test_generic_downloader_extract_single(self, mock_ydl_cls):
        """Mock yt_dlp.YoutubeDL to verify extract() parses metadata without network calls."""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "title": "Test Single Video",
            "webpage_url": "https://youtube.com/watch?v=123",
            "height": 1080,
            "subtitles": {"en": [], "es": []},
        }

        dl = GenericDownloader()
        items = dl.extract("https://youtube.com/watch?v=123")

        mock_ydl.extract_info.assert_called_once_with(
            "https://youtube.com/watch?v=123", download=False
        )
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "Test Single Video")
        self.assertEqual(item.url, "https://youtube.com/watch?v=123")
        self.assertEqual(item.quality, "1080p")
        self.assertIn("en", item.subtitles)
        self.assertIn("es", item.subtitles)

    @patch("yt_dlp.YoutubeDL")
    def test_generic_downloader_extract_playlist(self, mock_ydl_cls):
        """Test that extract() correctly parses playlist/multi-entry responses."""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "_type": "playlist",
            "title": "Test Playlist",
            "entries": [
                {
                    "title": "Episode 1",
                    "webpage_url": "https://example.com/ep1",
                    "height": 720,
                    "subtitles": ["en"],
                },
                {
                    "title": "Episode 2",
                    "webpage_url": "https://example.com/ep2",
                    "height": 1080,
                    "subtitles": ["en", "fr"],
                },
            ],
        }

        dl = GenericDownloader()
        items = dl.extract("https://example.com/playlist")

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Episode 1")
        self.assertEqual(items[0].url, "https://example.com/ep1")
        self.assertEqual(items[0].quality, "720p")
        self.assertEqual(items[1].title, "Episode 2")
        self.assertEqual(items[1].quality, "1080p")

    @patch("yt_dlp.YoutubeDL")
    def test_generic_downloader_download(self, mock_ydl_cls):
        """Mock yt_dlp.YoutubeDL to verify download() executes and returns filename."""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "title": "Test Download",
            "id": "xyz987",
        }
        mock_ydl.prepare_filename.return_value = os.path.join("downloads", "Test Download.mp4")

        dl = GenericDownloader()
        item = MediaItem(
            title="Test Download",
            url="https://example.com/xyz987",
            quality="1080p",
            subtitles=["en"],
        )
        out = dl.download(item, output_dir="downloads")

        mock_ydl.extract_info.assert_called_once_with("https://example.com/xyz987", download=True)
        self.assertTrue(out.endswith(".mp4"))

    @patch("mpv_config.cli.main.get_downloader")
    def test_cli_download_command(self, mock_get_dl):
        """Test CLI download subcommand with mocked downloader."""
        mock_dl = MagicMock()
        mock_dl.name = "mock_downloader"
        mock_dl.extract.return_value = [
            MediaItem(title="Mock Video", url="https://example.com/test", quality="1080p")
        ]
        mock_dl.download.return_value = os.path.join("downloads", "Mock Video.mp4")
        mock_get_dl.return_value = mock_dl

        exit_code = main(["download", "https://example.com/test", "-o", "downloads"])
        self.assertEqual(exit_code, 0)
        mock_dl.extract.assert_called_once_with("https://example.com/test")
        mock_dl.download.assert_called_once()

    @patch("time.sleep")
    @patch("tools.core.clipboard.ClipboardService")
    @patch("mpv_config.cli.main.get_downloader")
    def test_cli_watch_exception_recovery(self, mock_get_dl, mock_clip_cls, mock_sleep):
        """Test that --watch handles per-URL exceptions without crashing the loop."""
        mock_clip_cls.is_url.return_value = True
        mock_clip_cls.get_text.side_effect = [
            "https://example.com/bad-link",
            "https://example.com/good-link",
        ]

        mock_bad_dl = MagicMock()
        mock_bad_dl.extract.side_effect = RuntimeError("Extraction failed")

        mock_good_dl = MagicMock()
        mock_good_dl.extract.return_value = [MediaItem("Good", "https://example.com/good-link")]
        mock_good_dl.download.return_value = "Good.mp4"

        mock_get_dl.side_effect = [mock_bad_dl, mock_good_dl]
        mock_sleep.side_effect = [None, KeyboardInterrupt]

        exit_code = main(["download", "--watch"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_get_dl.call_count, 2)
        mock_good_dl.download.assert_called_once()


if __name__ == "__main__":
    unittest.main()
