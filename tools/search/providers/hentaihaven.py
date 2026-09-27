"""
hentaihaven.py — HentaiHaven search provider.
"""

import urllib.request
import urllib.parse
import re
from typing import List
from ..models import SearchResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def search_hentaihaven(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search HentaiHaven catalog."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    search_url = f"https://hentaihaven.xxx/?s={encoded_q}"

    try:
        req = urllib.request.Request(search_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read().decode("utf-8", errors="ignore")

        items = re.findall(r'<div[^>]*class="[^"]*post-title[^"]*"[^>]*>\s*<h[234][^>]*>\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', html)
        if not items:
            items = re.findall(r'<a\s+href="([^"]*hentaihaven\.xxx/[^"]*)"[^>]*title="([^"]+)"', html)

        for url, raw_title in items[:max_results]:
            clean_title = raw_title.strip()
            if not clean_title or len(clean_title) < 3:
                continue

            results.append(
                SearchResult(
                    title=clean_title,
                    provider="HentaiHaven",
                    url=url,
                    download_url=url,
                    resolution="720p",
                    quality_type="Web Stream",
                    codec="H.264",
                    size="~200 MiB",
                    censorship="Censored",
                    subtitles="English Subs",
                    audio="Japanese (Original)",
                    delivery="Instant CDN",
                )
            )
    except Exception:
        pass

    return results
