"""
hentaimama.py — HentaiMama search provider.
Extracts episodes and direct high-speed CDN MP4/HLS streams.
"""

import urllib.request
import urllib.parse
import re
import json
import base64
from typing import List, Optional
from ..models import SearchResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


import urllib.request
import urllib.parse
import re
import json
import base64
import html
from typing import List, Tuple, Optional
from ..models import SearchResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def _resolve_direct_stream(episode_url: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Extract direct 1080p/720p MP4 stream and thumbnail from HentaiMama episode page."""
    direct_url = None
    res = "720p"
    thumb = None

    try:
        req = urllib.request.Request(episode_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            page_html = r.read().decode("utf-8", errors="ignore")

        # 1. Extract snapshot / poster thumbnail
        og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', page_html)
        snap = re.search(r'src=["\']([^"\']*snapshot[^"\']*)["\']', page_html)
        thumb = (og_img.group(1) if og_img else None) or (snap.group(1) if snap else None)

        # 2. Extract post id
        pid_match = re.search(r"data-post-id=[\"'](\d+)[\"']", page_html) or re.search(r"a:\s*[\"'](\d+)[\"']", page_html)
        if not pid_match:
            return None, "720p", thumb
        post_id = pid_match.group(1)

        ajax_url = "https://hentaimama.io/wp-admin/admin-ajax.php"

        # Try player options in priority: 4 (1080p MP4), 3 (HLS Master), 1 (GDVid MP4)
        for opt in [4, 3, 1]:
            try:
                data = urllib.parse.urlencode({
                    "action": "get_player_contents",
                    "a": post_id,
                    "i": str(opt)
                }).encode("utf-8")

                ajax_req = urllib.request.Request(
                    ajax_url,
                    data=data,
                    headers={
                        **HEADERS,
                        "Referer": episode_url,
                        "X-Requested-With": "XMLHttpRequest",
                    }
                )
                with urllib.request.urlopen(ajax_req, timeout=5) as ar:
                    res_json = json.loads(ar.read().decode("utf-8", errors="ignore"))

                if not res_json or not isinstance(res_json, list) or opt - 1 >= len(res_json):
                    continue

                iframe_html = res_json[opt - 1]
                src_match = re.search(r'src=["\']([^"\']+)["\']', iframe_html)
                if not src_match:
                    continue

                embed_url = html.unescape(src_match.group(1))
                if not embed_url.startswith("http"):
                    embed_url = urllib.parse.urljoin("https://hentaimama.io", embed_url)

                # Fetch embed page to resolve direct stream URLs
                embed_req = urllib.request.Request(embed_url, headers={**HEADERS, "Referer": episode_url})
                with urllib.request.urlopen(embed_req, timeout=5) as er:
                    e_html = er.read().decode("utf-8", errors="ignore")

                # Check JWPlayer sources JSON array (e.g. 1080p, 720p, 480p)
                sm = re.search(r'sources:\s*(\[[^\]]+\])', e_html)
                if sm:
                    try:
                        arr = json.loads(sm.group(1))
                        # Look for 1080p first
                        for item in arr:
                            if item.get("label") == "1080p" and item.get("file"):
                                return item["file"], "1080p", thumb
                        # Otherwise first valid stream
                        for item in arr:
                            if item.get("file"):
                                lbl = item.get("label", "720p")
                                return item["file"], lbl, thumb
                    except Exception:
                        pass

                # Fallback: check file: "..."
                f_match = re.search(r'["\']?file["\']?\s*:\s*["\']([^"\']+)["\']', e_html)
                if f_match:
                    clean_f = f_match.group(1).replace(r"\/", "/")
                    f_res = "1080p" if "1080" in clean_f else "720p"
                    return clean_f, f_res, thumb

            except Exception:
                pass

    except Exception:
        pass

    return direct_url, res, thumb


def search_hentaimama(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search HentaiMama for series, episodes, and direct 1080p/720p streams."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    search_url = f"https://hentaimama.io/?s={encoded_q}"

    try:
        req = urllib.request.Request(search_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            html_text = r.read().decode("utf-8", errors="ignore")

        # Find series cards
        series_links = re.findall(r'<h[23][^>]*>\s*<a\s+href="([^"]*tvshows/[^"]*)"[^>]*>([^<]+)</a>', html_text)
        if not series_links:
            series_links = re.findall(r'<a\s+href="([^"]*tvshows/[^"]*)"[^>]*title="([^"]+)"', html_text)

        for show_url, show_title in series_links[:4]:
            try:
                # Fetch show page to get all episodes
                s_req = urllib.request.Request(show_url, headers=HEADERS)
                with urllib.request.urlopen(s_req, timeout=8) as sr:
                    show_html = sr.read().decode("utf-8", errors="ignore")

                ep_matches = re.findall(r'href="([^"]*episodes/[^"]*)"[^>]*>([^<]*)<', show_html)
                seen_eps = set()

                for ep_url, ep_text in ep_matches:
                    clean_ep_url = ep_url.strip()
                    if not clean_ep_url or clean_ep_url in seen_eps:
                        continue
                    seen_eps.add(clean_ep_url)

                    ep_slug = clean_ep_url.rstrip("/").split("/")[-1]
                    title_name = ep_slug.replace("-", " ").title()

                    # Resolve direct high speed stream link, resolution, and thumbnail
                    direct_url, res, thumb = _resolve_direct_stream(clean_ep_url)

                    play_url = direct_url if direct_url else clean_ep_url
                    q_type = f"Direct MP4 ({res})" if direct_url else "Web Stream"

                    results.append(
                        SearchResult(
                            title=title_name,
                            provider="HentaiMama",
                            url=play_url,
                            download_url=direct_url or clean_ep_url,
                            resolution=res,
                            quality_type=q_type,
                            codec="H.264",
                            size="~350 MiB - 850 MiB" if res == "1080p" else "~110 MiB - 350 MiB",
                            censorship="Censored",
                            subtitles="English Subs",
                            audio="Japanese (Original)",
                            delivery="Instant CDN",
                            thumbnail=thumb,
                        )
                    )
                    if len(results) >= max_results:
                        break
            except Exception:
                pass
            if len(results) >= max_results:
                break
    except Exception:
        pass

    return results
