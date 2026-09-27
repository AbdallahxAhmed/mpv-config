"""
test_hsearch.py — Unit tests for hsearch quality scoring, models, and badging.
"""

import unittest
from tools.search.models import SearchResult
from tools.search.scorer import score_and_badge_results
from tools.search.ui import format_preview_text


class TestHSearchQualityScorer(unittest.TestCase):
    def test_top_pick_and_resolution_scoring(self):
        item_1080p = SearchResult(
            title="Anime Test 1080p",
            provider="HentaiMama",
            url="https://example.com/1080",
            resolution="1080p",
            quality_type="Direct MP4",
            censorship="Uncensored",
            subtitles="Soft-subs (MKV)",
            audio="Japanese (Original)",
            delivery="Instant CDN"
        )
        item_720p = SearchResult(
            title="Anime Test 720p",
            provider="Hanime",
            url="https://example.com/720",
            resolution="720p",
            quality_type="Web Stream",
            censorship="Censored",
            subtitles="Hard-sub",
            audio="Japanese (Original)",
            delivery="Instant CDN"
        )

        ranked = score_and_badge_results([item_720p, item_1080p])
        self.assertEqual(len(ranked), 2)
        # 1080p with Uncensored + HentaiMama boost should rank #1
        self.assertEqual(ranked[0].title, "Anime Test 1080p")
        self.assertTrue(ranked[0].is_best)
        self.assertIn("[⭐ TOP PICK]", ranked[0].badges)
        self.assertIn("[1080p FHD]", ranked[0].badges)
        self.assertIn("[🔓 Uncensored]", ranked[0].badges)
        self.assertIn("[Soft-Subs • JP Audio]", ranked[0].badges)

    def test_nyaa_bd_remux_scoring(self):
        nyaa_bd = SearchResult(
            title="Anime BD Remux",
            provider="Nyaa",
            url="magnet:?xt=urn:btih:123",
            resolution="1080p",
            quality_type="BD Remux",
            codec="HEVC (10-bit)",
            size="1.8 GiB",
            seeders=25,
            censorship="Decensored",
            subtitles="Soft-subs (MKV)",
            audio="Japanese (Original)",
            delivery="Torrent (P2P)"
        )
        ranked = score_and_badge_results([nyaa_bd])
        self.assertTrue(any("BD Remux" in b for b in ranked[0].badges))
        self.assertTrue(any("Decensored" in b for b in ranked[0].badges))
        self.assertTrue(any("Ultra Fast" in b for b in ranked[0].badges))

    def test_preview_formatter_output(self):
        item = SearchResult(
            title="Sample Title",
            provider="HentaiMama",
            url="https://example.com/sample",
            resolution="1080p",
            quality_type="Direct MP4",
            censorship="Uncensored",
            subtitles="Soft-subs (MKV)",
            audio="Japanese (Original)",
            delivery="Instant CDN",
            score=90.0,
            badges=["[⭐ TOP PICK]", "[1080p FHD]", "[🔓 Uncensored]"],
            is_best=True
        )
        preview_text = format_preview_text(item)
        self.assertIn("TOP PICK", preview_text)
        self.assertIn("HentaiMama", preview_text)
        self.assertIn("1080p", preview_text)
        self.assertIn("Enter", preview_text)


if __name__ == "__main__":
    unittest.main()
