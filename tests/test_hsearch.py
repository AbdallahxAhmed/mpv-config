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


    def test_muchohentai_stream_resolution_logic(self):
        from unittest.mock import patch, MagicMock
        from tools.search.providers.muchohentai import _resolve_mucho_stream

        mock_html = """
        <html>
        <meta property="og:image" content="https://muchohentai.com/thumb.jpg">
        <script>
        var servers = ["va01"];
        var files = [{"file":"\\/wp-content\\/uploads\\/test\\/ja.m3u8"}];
        </script>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            stream_url, thumb = _resolve_mucho_stream("https://muchohentai.com/test-episode")
            self.assertEqual(stream_url, "https://va01.edge.tmncdn.io/wp-content/uploads/test/ja.m3u8")
            self.assertEqual(thumb, "https://muchohentai.com/thumb.jpg")

    def test_chafa_engine_discovery(self):
        from tools.search.ui import find_chafa
        chafa_path = find_chafa()
        self.assertIsNotNone(chafa_path)
        self.assertTrue(chafa_path.endswith("chafa.exe") or "chafa" in chafa_path.lower())


if __name__ == "__main__":
    unittest.main()

