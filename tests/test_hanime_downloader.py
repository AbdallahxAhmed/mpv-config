#!/usr/bin/env python3
"""
Unit tests for tools/hanime_downloader.py
"""

import unittest
from tools import hanime_downloader as hd

class TestHanimeDownloader(unittest.TestCase):

    def test_extract_slug(self):
        self.assertEqual(
            hd.extract_slug("https://hanime.tv/videos/hentai/overflow-1"),
            "overflow-1"
        )
        self.assertEqual(
            hd.extract_slug("https://hanime.tv/videos/hentai/overflow-1/"),
            "overflow-1"
        )
        self.assertEqual(
            hd.extract_slug("https://hanime.tv/hentai/video/overflow-1"),
            "overflow-1"
        )
        self.assertEqual(
            hd.extract_slug("https://hanime.tv/playlists/abc1234/video/overflow-1"),
            "overflow-1"
        )
        self.assertEqual(
            hd.extract_slug("overflow-1"),
            "overflow-1"
        )

    def test_sanitize_filename(self):
        self.assertEqual(hd.sanitize_filename("Clean Title"), "Clean Title")
        self.assertEqual(hd.sanitize_filename("Title: With <Special> / Invalid? *Chars*|"), "Title_ With _Special_ _ Invalid_ _Chars__")
        self.assertEqual(hd.sanitize_filename("   Multiple    Spaces   "), "Multiple Spaces")

    def test_select_format_1080p_ceiling(self):
        formats = [
            {"quality": "2160p", "height": 2160, "resolution": "3840x2160"},
            {"quality": "1440p", "height": 1440, "resolution": "2560x1440"},
            {"quality": "1080p", "height": 1080, "resolution": "1920x1080"},
            {"quality": "720p", "height": 720, "resolution": "1280x720"},
            {"quality": "480p", "height": 480, "resolution": "854x480"},
        ]

        # 'best' must cap at 1080p and never pick 4K
        best = hd.select_format(formats, "best")
        self.assertEqual(best["quality"], "1080p")
        self.assertEqual(best["height"], 1080)

        # '1080p' explicitly picks 1080p
        f1080 = hd.select_format(formats, "1080p")
        self.assertEqual(f1080["quality"], "1080p")

        # '720p' picks 720p
        f720 = hd.select_format(formats, "720p")
        self.assertEqual(f720["quality"], "720p")

        # 'worst' picks lowest
        worst = hd.select_format(formats, "worst")
        self.assertEqual(worst["quality"], "480p")

        # Explicit '4k' allows 2160p
        f4k = hd.select_format(formats, "4k")
        self.assertEqual(f4k["quality"], "2160p")

    def test_token_encryption_decryption_roundtrip(self):
        test_payload = {
            "directive": "htv_player_handshake",
            "slug": "overflow-1",
            "timestamp_unix": 1700000000
        }
        token = hd.digest_token(test_payload)
        self.assertTrue(isinstance(token, str))
        self.assertTrue(len(token) > 20)

        decrypted = hd.parse_token(token)
        self.assertEqual(decrypted, test_payload)

    def test_generate_credentials(self):
        sig, ts = hd.generate_credentials()
        self.assertTrue(isinstance(sig, str))
        self.assertEqual(len(sig), 64)  # SHA-256 hex string is 64 characters
        self.assertTrue(isinstance(ts, int))
        self.assertTrue(ts > 1700000000)

if __name__ == "__main__":
    unittest.main()
