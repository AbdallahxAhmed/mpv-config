"""
metadata.py — AniList GraphQL Anime/Hentai Database integration.
Fetches official high-res posters, ratings, genres, and synopsis.
"""

import urllib.request
import json
import re
import os
import tempfile
from typing import Optional, Dict, Any

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

_CACHE_FILE = os.path.join(tempfile.gettempdir(), "mpv-hsearch-thumbs", "anilist_metadata_cache.json")


def clean_series_title(raw_title: str) -> str:
    """Normalize raw video title to search query for anime database."""
    # Remove bracketed tags e.g. [1080p], [Decensored], (Uncensored)
    t = re.sub(r"\[.*?\]|\(.*?\)", "", raw_title)
    # Remove resolution tags
    t = re.sub(r"(?i)\b(1080p|720p|480p|4k|fhd|hd|bdrip|webrip)\b", "", t)
    # Remove episode markers and suffixes
    t = re.sub(r"(?i)\b(episode|ep|ova|part|vol|season|s\d+)\b.*$", "", t)
    # Remove trailing digits e.g. 'Imaria 6' -> 'Imaria'
    t = re.sub(r"\s+\d+\s*$", "", t)
    # Remove words like English Subbed, Raw, Dual Audio
    t = re.sub(r"(?i)\b(english subbed|subbed|english dub|raw|uncensored|decensored)\b", "", t)
    # Clean whitespace and punctuation
    t = re.sub(r"[-–—_]+", " ", t).strip()
    return t if len(t) >= 2 else raw_title.strip()


def _load_cache() -> Dict[str, Any]:
    if os.path.isfile(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: Dict[str, Any]):
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_series_metadata(series_name: str) -> Optional[Dict[str, Any]]:
    """Query AniList GraphQL for series metadata and official high-res poster."""
    clean_name = clean_series_title(series_name)
    if not clean_name:
        return None

    cache_key = clean_name.lower()
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    query = """
    query ($search: String) {
      Media (search: $search, type: ANIME) {
        id
        title {
          romaji
          english
          native
        }
        coverImage {
          extraLarge
          large
          medium
        }
        bannerImage
        description(asHtml: false)
        averageScore
        genres
        episodes
        status
        startDate {
          year
        }
        studios(isMain: true) {
          nodes {
            name
          }
        }
      }
    }
    """

    payload = json.dumps({"query": query, "variables": {"search": clean_name}}).encode("utf-8")
    req = urllib.request.Request(ANILIST_GRAPHQL_URL, data=payload, headers=HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            media = data.get("data", {}).get("Media")
            if not media:
                cache[cache_key] = None
                _save_cache(cache)
                return None

            # Clean description
            raw_desc = media.get("description") or ""
            clean_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()
            # Truncate synopsis to reasonable preview length
            if len(clean_desc) > 320:
                clean_desc = clean_desc[:317] + "..."

            studios_list = [s["name"] for s in media.get("studios", {}).get("nodes", []) if s.get("name")]
            studio_str = studios_list[0] if studios_list else "Unknown Studio"

            cover_img = (
                media.get("coverImage", {}).get("extraLarge")
                or media.get("coverImage", {}).get("large")
                or media.get("coverImage", {}).get("medium")
            )

            result = {
                "id": media.get("id"),
                "romaji_title": media.get("title", {}).get("romaji") or clean_name,
                "english_title": media.get("title", {}).get("english") or media.get("title", {}).get("romaji"),
                "native_title": media.get("title", {}).get("native"),
                "cover_url": cover_img,
                "banner_url": media.get("bannerImage"),
                "score": media.get("averageScore"),  # 0 - 100
                "genres": media.get("genres") or [],
                "year": media.get("startDate", {}).get("year"),
                "episodes": media.get("episodes"),
                "status": (media.get("status") or "").capitalize(),
                "studio": studio_str,
                "synopsis": clean_desc,
            }

            cache[cache_key] = result
            _save_cache(cache)
            return result

    except Exception:
        return None
