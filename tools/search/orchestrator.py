"""
orchestrator.py — Parallel multi-source search runner.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable
from .models import SearchResult
from .scorer import score_and_badge_results
from .providers.hentaimama import search_hentaimama
from .providers.nyaa import search_nyaa
from .providers.hanime import search_hanime
from .providers.hentaiworld import search_hentaiworld
from .providers.hentaihaven import search_hentaihaven
from .providers.muchohentai import search_muchohentai
from .metadata import fetch_series_metadata


def multi_search(query: str, progress_callback: Optional[Callable[[str], None]] = None) -> List[SearchResult]:
    """Query all providers in parallel, score, badge, and rank results."""
    all_results: List[SearchResult] = []
    series_meta: Optional[dict] = None

    tasks = {
        "AniList Database": lambda: fetch_series_metadata(query),
        "HentaiMama": lambda: search_hentaimama(query, max_results=8),
        "MuchoHentai": lambda: search_muchohentai(query, max_results=6),
        "Nyaa (Torrents)": lambda: search_nyaa(query, max_results=12),
        "Hanime": lambda: search_hanime(query, max_results=6),
        "HentaiWorld": lambda: search_hentaiworld(query, max_results=6),
        "HentaiHaven": lambda: search_hentaihaven(query, max_results=6),
    }

    with ThreadPoolExecutor(max_workers=7) as executor:
        future_to_provider = {executor.submit(func): name for name, func in tasks.items()}
        for future in as_completed(future_to_provider):
            provider_name = future_to_provider[future]
            try:
                res = future.result()
                if provider_name == "AniList Database":
                    series_meta = res
                    if progress_callback and res:
                        progress_callback(f"AniList matched: {res.get('romaji_title')}")
                else:
                    if progress_callback:
                        progress_callback(f"Fetched {len(res)} results from {provider_name}")
                    all_results.extend(res)
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Notice: {provider_name} check: {e}")

    # Attach official metadata & HD poster to results
    if series_meta:
        for r in all_results:
            r.poster_url = series_meta.get("cover_url")
            r.official_title = series_meta.get("romaji_title") or series_meta.get("english_title")
            r.rating = series_meta.get("score")
            r.genres = series_meta.get("genres", [])
            r.year = series_meta.get("year")
            r.synopsis = series_meta.get("synopsis")
            r.studio = series_meta.get("studio")
            r.episodes_count = series_meta.get("episodes")

    # Score, rank, and badge all items
    ranked_results = score_and_badge_results(all_results)
    return ranked_results

