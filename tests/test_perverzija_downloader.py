#!/usr/bin/env python3
"""
Unit tests for tools/perverzija_downloader.py
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from tools import perverzija_downloader as pd

SAMPLE_M3U8 = """#EXTM3U
#EXT-X-VERSION:3
## Written by inside83 ##
#EXT-X-STREAM-INF:BANDWIDTH=4995851,RESOLUTION=1920x1080,CLOSED-CAPTIONS=NONE
https://moviekh.xtremestream.xyz/player/xs1.php?data=abc12345&q=1080
#EXT-X-STREAM-INF:BANDWIDTH=2274000,RESOLUTION=1280x720,CLOSED-CAPTIONS=NONE
https://moviekh.xtremestream.xyz/player/xs1.php?data=abc12345&q=720
#EXT-X-STREAM-INF:BANDWIDTH=1098000,RESOLUTION=854x480,CLOSED-CAPTIONS=NONE
https://moviekh.xtremestream.xyz/player/xs1.php?data=abc12345&q=480
"""

SAMPLE_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<title>Watch Sample Studio - Jane Doe - Amazing Video | Perverzija.com</title>
<meta property="og:title" content="Sample Studio - Jane Doe - Amazing Video" />
<meta property="og:image" content="https://tube.perverzija.com/wp-content/uploads/poster.jpg" />
<meta property="og:description" content="This is a test description." />
</head>
<body>
<h1 class="light-title entry-title">Sample Studio &#8211; Jane Doe &#8211; Amazing Video</h1>
<div class="player-content-inner">
  <iframe src="https://moviekh.xtremestream.xyz/player/index.php?data=deadbeef123456" width="100%"></iframe>
</div>
<div class="item-tax-list">
  <div><strong>Studio: </strong><a href="https://tube.perverzija.com/studio/sample-studio/" rel="category tag">Sample Studio</a></div>
  <div><strong>Stars: </strong><a href="https://tube.perverzija.com/stars/jane-doe/" rel="tag">Jane Doe</a></div>
  <div><strong>Tags: </strong><a href="https://tube.perverzija.com/tag/blonde/" rel="tag">Blonde</a>, <a href="https://tube.perverzija.com/tag/pov/" rel="tag">POV</a></div>
</div>
</body>
</html>
"""

class TestPerverzijaDownloader(unittest.TestCase):

    def test_sanitize_filename(self):
        self.assertEqual(pd.sanitize_filename("Clean Title"), "Clean Title")
        self.assertEqual(pd.sanitize_filename("Title: With <Special> / Invalid? *Chars*|"), "Title_ With _Special_ _ Invalid_ _Chars__")
        self.assertEqual(pd.sanitize_filename("   Multiple    Spaces   "), "Multiple Spaces")

    def test_parse_m3u8_formats(self):
        formats = pd.parse_m3u8_formats(SAMPLE_M3U8, "https://moviekh.xtremestream.xyz/player/xs1.php?data=abc12345")
        self.assertEqual(len(formats), 3)

        # Formats should be ordered highest to lowest quality
        self.assertEqual(formats[0]["quality"], "1080p")
        self.assertEqual(formats[0]["resolution"], "1920x1080")
        self.assertEqual(formats[0]["height"], 1080)
        self.assertEqual(formats[0]["bandwidth"], 4995851)
        self.assertEqual(formats[0]["url"], "https://moviekh.xtremestream.xyz/player/xs1.php?data=abc12345&q=1080")

        self.assertEqual(formats[1]["quality"], "720p")
        self.assertEqual(formats[1]["height"], 720)

        self.assertEqual(formats[2]["quality"], "480p")
        self.assertEqual(formats[2]["height"], 480)

    def test_select_format(self):
        formats = pd.parse_m3u8_formats(SAMPLE_M3U8, "https://moviekh.xtremestream.xyz/player/xs1.php?data=abc12345")

        best = pd.select_format(formats, "best")
        self.assertEqual(best["quality"], "1080p")

        worst = pd.select_format(formats, "worst")
        self.assertEqual(worst["quality"], "480p")

        f720 = pd.select_format(formats, "720p")
        self.assertEqual(f720["quality"], "720p")

        f480 = pd.select_format(formats, "480")
        self.assertEqual(f480["quality"], "480p")

    def test_select_format_caps_at_1080p_when_4k_present(self):
        formats_with_4k = [
            {"quality": "2160p", "height": 2160, "resolution": "3840x2160"},
            {"quality": "1440p", "height": 1440, "resolution": "2560x1440"},
            {"quality": "1080p", "height": 1080, "resolution": "1920x1080"},
            {"quality": "720p", "height": 720, "resolution": "1280x720"},
            {"quality": "480p", "height": 480, "resolution": "854x480"},
        ]

        # 'best' must cap at 1080p and not choose 4K or 1440p
        best = pd.select_format(formats_with_4k, "best")
        self.assertEqual(best["quality"], "1080p")
        self.assertEqual(best["height"], 1080)

        # '1080' or '1080p' must choose 1080p
        best1080 = pd.select_format(formats_with_4k, "1080p")
        self.assertEqual(best1080["quality"], "1080p")

        # Explicit '4k' request allows 2160p
        f4k = pd.select_format(formats_with_4k, "4k")
        self.assertEqual(f4k["quality"], "2160p")

    @patch("tools.perverzija_downloader.fetch_url")
    def test_parse_video_page(self, mock_fetch):
        def side_effect(url, referer=None):
            if "xs1.php" in url:
                return SAMPLE_M3U8
            return SAMPLE_PAGE_HTML

        mock_fetch.side_effect = side_effect

        info = pd.parse_video_page("https://tube.perverzija.com/sample-studio-jane-doe-amazing-video/")
        self.assertEqual(info["title"], "Sample Studio - Jane Doe - Amazing Video")
        self.assertEqual(info["studio"], "Sample Studio")
        self.assertEqual(info["stars"], ["Jane Doe"])
        self.assertEqual(info["tags"], ["Blonde", "POV"])
        self.assertEqual(info["poster"], "https://tube.perverzija.com/wp-content/uploads/poster.jpg")
        self.assertEqual(info["description"], "This is a test description.")
        self.assertEqual(info["player_url"], "https://moviekh.xtremestream.xyz/player/index.php?data=deadbeef123456")
        self.assertEqual(info["master_m3u8"], "https://moviekh.xtremestream.xyz/player/xs1.php?data=deadbeef123456")
        self.assertEqual(len(info["formats"]), 3)

    @patch("tools.perverzija_downloader.fetch_url")
    def test_parse_video_page_data_attr_fallback(self, mock_fetch):
        fallback_html = """
        <html>
        <head><title>Fallback Video | Perverzija</title></head>
        <body>
        <h1 class="entry-title">Fallback Video</h1>
        <button class="download-button" data-folderid="fallback999" data-xtremestream="pervl4"></button>
        </body>
        </html>
        """
        def side_effect(url, referer=None):
            if "xs1.php" in url:
                return SAMPLE_M3U8
            return fallback_html

        mock_fetch.side_effect = side_effect

        info = pd.parse_video_page("https://tube.perverzija.com/fallback-video/")
        self.assertEqual(info["title"], "Fallback Video")
        self.assertEqual(info["player_url"], "https://pervl4.xtremestream.xyz/player/index.php?data=fallback999")
        self.assertEqual(info["master_m3u8"], "https://pervl4.xtremestream.xyz/player/xs1.php?data=fallback999")

    def test_find_ytdlp(self):
        ytdlp = pd.find_ytdlp()
        self.assertTrue(len(ytdlp) > 0)

    def test_get_default_download_dir(self):
        d = pd.get_default_download_dir()
        self.assertTrue(os.path.isdir(d))

    def test_probe_connection_speed_fallback(self):
        # When network is unreachable or dummy format is passed, it safely falls back
        dummy_info = {"stream_headers": {}, "player_url": "https://dummy"}
        dummy_format = {"url": "https://invalid-nonexistent-domain-xyz123.com/stream.m3u8"}
        res = pd.probe_connection_speed(dummy_info, dummy_format)
        self.assertIn("concurrency", res)
        self.assertIn("buffersize", res)
        self.assertIn("http_chunk_size", res)
        self.assertEqual(res["concurrency"], 16)

if __name__ == "__main__":
    unittest.main()
