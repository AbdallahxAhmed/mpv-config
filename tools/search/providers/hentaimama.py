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


def _resolve_direct_stream(episode_url: str) -> Optional[str]:
    """Extract direct MP4 video link from HentaiMama episode page via player AJAX."""
    try:
        req = urllib.request.Request(episode_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Find post id (e.g. data-post-id="14274" or a: '14274')
        pid_match = re.search(r"data-post-id=[\"'](\d+)[\"']", html) or re.search(r"a:\s*[\"'](\d+)[\"']", html)
        if not pid_match:
            return None
        post_id = pid_match.group(1)

        ajax_url = "https://hentaimama.io/wp-admin/admin-ajax.php"
        data = urllib.parse.urlencode({
            "action": "get_player_contents",
            "a": post_id,
            "i": "1"
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
        with urllib.request.urlopen(ajax_req, timeout=6) as ar:
            res_text = ar.read().decode("utf-8", errors="ignore")
            res_json = json.loads(res_text)

        if not res_json or not isinstance(res_json, list):
            return None

        iframe_html = res_json[0]
        src_match = re.search(r'src=["\']([^"\']+)["\']', iframe_html)
        if not src_match:
            return None

        embed_url = src_match.group(1).replace("&amp;", "&")
        if not embed_url.startswith("http"):
            embed_url = urllib.parse.urljoin("https://hentaimama.io", embed_url)

        # Check embed URL for direct stream
        p_param = re.search(r"[?&]p=([a-zA-Z0-9+/=]+)", embed_url)
        if p_param:
            try:
                decoded_path = base64.b64decode(p_param.group(1)).decode("utf-8", errors="ignore")
                if decoded_path:
                    clean_path = decoded_path.lstrip("/")
                    direct_mp4 = f"https://gdvid.info/{clean_path}"
                    return direct_mp4
            except Exception:
                pass

        # Alternatively inspect embed HTML
        embed_req = urllib.request.Request(embed_url, headers={**HEADERS, "Referer": episode_url})
        with urllib.request.urlopen(embed_req, timeout=6) as er:
            e_html = er.read().decode("utf-8", errors="ignore")
            f_match = re.search(r'["\']?file["\']?\s*:\s*["\']([^"\']+)["\']', e_html)
            if f_match:
                return f_match.group(1).replace(r"\/", "/")

    except Exception:
        pass
    return None


def search_hentaimama(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search HentaiMama for series and episodes."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    search_url = f"https://hentaimama.io/?s={encoded_q}"

    try:
        req = urllib.request.Request(search_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Find series cards
        series_links = re.findall(r'<h[23][^>]*>\s*<a\s+href="([^"]*tvshows/[^"]*)"[^>]*>([^<]+)</a>', html)
        if not series_links:
            series_links = re.findall(r'<a\s+href="([^"]*tvshows/[^"]*)"[^>]*title="([^"]+)"', html)

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

                    # Try resolving direct high speed stream link
                    direct_url = _resolve_direct_stream(clean_ep_url)

                    # Default to direct stream if found, else episode page
                    play_url = direct_url if direct_url else clean_ep_url

                    # Check resolution
                    res = "1080p" if ("1080" in title_name.lower()) else "720p"

                    results.append(
                        SearchResult(
                            title=title_name,
                            provider="HentaiMama",
                            url=play_url,
                            download_url=direct_url or clean_ep_url,
                            resolution=res,
                            quality_type="Direct MP4" if direct_url else "Web Stream",
                            codec="H.264",
                            size="~110 MiB - 350 MiB",
                            censorship="Censored",
                            subtitles="English Subs",
                            audio="Japanese (Original)",
                            delivery="Instant CDN",
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
