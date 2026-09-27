"""
hanime.py — Hanime.tv search provider via search page scraper.
"""

import urllib.request
import urllib.parse
import json
import re
import os
from typing import List
from ..models import SearchResult


def search_hanime(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search Hanime.tv catalog using search page."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    search_url = f"https://hanime.tv/search?q={encoded_q}"

    endpoint = "http://localhost:8191/v1"
    html = ""
    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps({"cmd": "request.get", "url": search_url, "maxTimeout": 25000}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data.get("status") == "ok":
                html = data.get("solution", {}).get("response", "")
    except Exception:
        pass

    if not html:
        try:
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=6) as r:
                html = r.read().decode("utf-8", errors="ignore")
        except Exception:
            pass

    if not html:
        return results

    # Find video paths
    cards = re.findall(r'href="(/videos/hentai/[^"]+)"', html)
    seen = set()
    for path in cards:
        if path in seen:
            continue
        seen.add(path)
        slug = path.split("/")[-1]
        title = slug.replace("-", " ").title()

        # Simple filter: check if query terms are in slug or title
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        if query_words and not any(w in slug.lower() for w in query_words):
            continue

        results.append(
            SearchResult(
                title=title,
                provider="Hanime",
                url=f"https://hanime.tv{path}",
                download_url=f"https://hanime.tv{path}",
                resolution="720p",
                quality_type="Web Stream (HLS)",
                codec="H.264",
                size="~200 MiB",
                censorship="Censored",
                subtitles="Hard-sub",
                audio="Japanese (Original)",
                delivery="Instant CDN",
            )
        )
        if len(results) >= max_results:
            break

    return results
