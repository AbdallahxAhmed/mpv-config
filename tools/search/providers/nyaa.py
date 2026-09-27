"""
nyaa.py — Sukebei Nyaa RSS and torrent provider.
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from typing import List
from ..models import SearchResult


def search_nyaa(query: str, max_results: int = 15) -> List[SearchResult]:
    """Search Sukebei Nyaa Anime category via fast RSS."""
    results = []
    encoded_q = urllib.parse.quote_plus(query)
    url = f"https://sukebei.nyaa.si/?page=rss&q={encoded_q}&c=1_1&f=0"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            root = ET.fromstring(r.read())

        nyaa_ns = {"nyaa": "https://nyaa.si/xmlns/nyaa"}
        items = root.findall(".//item")

        for it in items[:max_results]:
            title = it.find("title").text if it.find("title") is not None else ""
            torrent_url = it.find("link").text if it.find("link") is not None else ""
            guid = it.find("guid").text if it.find("guid") is not None else ""

            size_elem = it.find("nyaa:size", nyaa_ns)
            size = size_elem.text if size_elem is not None else ""

            seeders_elem = it.find("nyaa:seeders", nyaa_ns)
            seeders = int(seeders_elem.text) if seeders_elem is not None and seeders_elem.text.isdigit() else 0

            hash_elem = it.find("nyaa:infoHash", nyaa_ns)
            info_hash = hash_elem.text if hash_elem is not None else ""

            magnet = ""
            if info_hash:
                dn = urllib.parse.quote(title)
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce"

            # Detect resolution
            t_lower = title.lower()
            if "1080p" in t_lower or "1080" in t_lower or "fhd" in t_lower:
                res = "1080p"
            elif "720p" in t_lower or "720" in t_lower:
                res = "720p"
            elif "480p" in t_lower or "576p" in t_lower:
                res = "480p"
            else:
                res = "1080p" if ("bd" in t_lower or "remux" in t_lower) else "720p"

            # Detect quality type & codec
            if "remux" in t_lower:
                q_type = "BD Remux"
            elif "bdrip" in t_lower or "bd" in t_lower or "bluray" in t_lower:
                q_type = "Blu-Ray Rip"
            elif "webrip" in t_lower or "web-dl" in t_lower:
                q_type = "WEBRip"
            else:
                q_type = "Torrent Release"

            codec = "H.264"
            if "hevc" in t_lower or "x265" in t_lower or "10bit" in t_lower:
                codec = "HEVC (10-bit)"
            elif "x264" in t_lower:
                codec = "AVC / H.264"

            # Detect censorship
            if "decensored" in t_lower:
                censorship = "Decensored"
            elif "uncensored" in t_lower:
                censorship = "Uncensored"
            else:
                censorship = "Censored"

            # Detect subtitles & audio
            if "softsub" in t_lower or "mkv" in t_lower:
                sub = "Soft-subs (MKV)"
            elif "vostfr" in t_lower:
                sub = "French Subs"
            else:
                sub = "English Subs"

            if "dual" in t_lower or "dual-audio" in t_lower:
                audio = "Dual Audio"
            elif "dub" in t_lower and "eng" in t_lower:
                audio = "English Dub"
            else:
                audio = "Japanese (Original)"

            item_url = magnet if magnet else (torrent_url or guid)

            results.append(
                SearchResult(
                    title=title,
                    provider="Nyaa",
                    url=item_url,
                    download_url=torrent_url,
                    resolution=res,
                    quality_type=q_type,
                    codec=codec,
                    size=size,
                    seeders=seeders,
                    censorship=censorship,
                    subtitles=sub,
                    audio=audio,
                    delivery="Torrent (P2P)",
                )
            )
    except Exception:
        pass

    return results
