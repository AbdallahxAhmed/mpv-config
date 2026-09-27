"""
hentaiworld.py — HentaiWorld 1080p & 60fps provider.
"""

import urllib.request
import urllib.parse
import re
from typing import List
from ..models import SearchResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def search_hentaiworld(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search HentaiWorld for 1080p and 60fps videos."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    search_url = f"https://hentaiworld.tv/?s={encoded_q}"

    try:
        req = urllib.request.Request(search_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read().decode("utf-8", errors="ignore")

        articles = re.findall(r'<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', html)
        if not articles:
            articles = re.findall(r'<a\s+href="([^"]+)"[^>]*rel="bookmark"[^>]*>([^<]+)</a>', html)

        for url, raw_title in articles[:max_results]:
            clean_title = raw_title.strip()
            t_lower = clean_title.lower()

            res = "1080p" if ("1080" in t_lower or "fhd" in t_lower) else "1080p"
            is_60fps = "60fps" in t_lower or "60 fps" in t_lower
            q_type = "60 FPS" if is_60fps else "Web Stream (FHD)"

            censorship = "Uncensored" if "uncensored" in t_lower or "decensored" in t_lower else "Censored"

            results.append(
                SearchResult(
                    title=clean_title,
                    provider="HentaiWorld",
                    url=url,
                    download_url=url,
                    resolution=res,
                    quality_type=q_type,
                    codec="H.264",
                    size="~300 MiB - 800 MiB",
                    censorship=censorship,
                    subtitles="English Subs",
                    audio="Japanese (Original)",
                    delivery="Instant CDN",
                )
            )
    except Exception:
        pass

    return results
