"""
muchohentai.py — MuchoHentai 1080p HLS provider.
"""

import urllib.request
import urllib.parse
import re
import json
from typing import List, Optional, Tuple
from ..models import SearchResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def _resolve_mucho_stream(episode_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract master HLS stream URL and poster image from MuchoHentai episode page."""
    try:
        req = urllib.request.Request(episode_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # 1. Poster thumbnail
        og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        thumb = og_img.group(1) if og_img else None

        # 2. Extract server name and relative HLS playlist
        servers_match = re.search(r"var\s+servers\s*=\s*\[(.*?)\]", html)
        files_match = re.search(r"var\s+files\s*=\s*\[(.*?)\]", html)

        if servers_match and files_match:
            servers_raw = servers_match.group(1)
            servers = [s.strip(" '\"") for s in servers_raw.split(",") if s.strip(" '\"")]
            server_name = servers[0] if servers else "va01"

            # Parse files array
            files_json = json.loads(f"[{files_match.group(1)}]")
            if files_json and isinstance(files_json, list) and files_json[0].get("file"):
                rel_path = files_json[0]["file"].replace(r"\/", "/")
                master_m3u8 = f"https://{server_name}.edge.tmncdn.io{rel_path}"
                return master_m3u8, thumb

    except Exception:
        pass

    return None, None


def search_muchohentai(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search MuchoHentai catalog for 1080p HLS episodes."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    search_url = f"https://muchohentai.com/?s={encoded_q}"

    try:
        req = urllib.request.Request(search_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Extract episode links
        links = re.findall(r'<a\s+href="([^"]*muchohentai\.com/[^"]+)"[^>]*>(.*?)</a>', html)
        seen_links = set()

        candidate_links = []
        for url, raw_title in links:
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
            # Filter navigation links
            if not clean_title or any(nav in clean_title.lower() for nav in ["home", "list", "preview", "random", "latest"]):
                continue

            # Prioritize English Subbed version if available
            t_lower = clean_title.lower()
            if "español" in t_lower or "espanol" in t_lower:
                continue

            if url in seen_links:
                continue
            seen_links.add(url)
            candidate_links.append((url, clean_title))
            if len(candidate_links) >= max_results:
                break

        if candidate_links:
            from concurrent.futures import ThreadPoolExecutor

            def _resolve_one(item):
                u, t = item
                stream_url, thumb = _resolve_mucho_stream(u)
                ep_match = re.search(r'(?:episode|ep|ova)[ -]*(\d+)', t, re.IGNORECASE)
                ep_num = ep_match.group(1) if ep_match else None
                return SearchResult(
                    title=t,
                    provider="MuchoHentai",
                    url=stream_url or u,
                    download_url=stream_url or u,
                    resolution="1080p",
                    quality_type="Master HLS (1080p)",
                    codec="H.264",
                    size="~350 MiB - 950 MiB",
                    censorship="Censored",
                    subtitles="English Subs (VTT)",
                    audio="Japanese (Original)",
                    delivery="Instant CDN",
                    thumbnail=thumb,
                    episode=ep_num,
                )

            with ThreadPoolExecutor(max_workers=min(len(candidate_links), 6)) as pool:
                results = list(pool.map(_resolve_one, candidate_links))

    except Exception:
        pass

    return results
