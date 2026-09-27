"""
scorer.py — Evaluates, ranks, and awards badges to search results.
"""

from typing import List
from .models import SearchResult


def score_and_badge_results(results: List[SearchResult]) -> List[SearchResult]:
    """Score each result based on resolution, source, censorship, audio/subs, speed,
    and provider preference (HentaiMama boosted to top)."""
    if not results:
        return []

    for r in results:
        score = 0.0
        badges = []

        # 1. Provider Badge
        badges.append(f"[{r.provider}]")

        # 2. Resolution (Max 35 pts)
        res_lower = r.resolution.lower()
        if "1080" in res_lower or "4k" in res_lower:
            score += 35.0
            badges.append("[1080p FHD]")
        elif "720" in res_lower:
            score += 20.0
            badges.append("[720p HD]")
        elif "480" in res_lower or "360" in res_lower:
            score += 10.0
            badges.append("[SD]")
        else:
            score += 15.0

        # 3. Source & Bitrate (Max 25 pts)
        q_lower = r.quality_type.lower()
        if "bd" in q_lower or "remux" in q_lower or "bluray" in q_lower:
            score += 25.0
            badges.append("[BD Remux]")
        elif "60" in q_lower or "60fps" in q_lower:
            score += 22.0
            badges.append("[60 FPS]")
        elif "webrip" in q_lower or "hevc" in r.codec.lower():
            score += 20.0
            badges.append("[HEVC 10-bit]")
        elif "direct mp4" in q_lower:
            score += 16.0
            badges.append("[Direct MP4]")
        else:
            score += 12.0

        # 4. Censorship (Max 20 pts)
        c_lower = r.censorship.lower()
        if "decensored" in c_lower:
            score += 20.0
            badges.append("[🔓 Decensored]")
        elif "uncensored" in c_lower:
            score += 20.0
            badges.append("[🔓 Uncensored]")
        else:
            score += 5.0

        # 5. Subtitles & Audio (Max 15 pts) - User preferred soft subs and original dub
        sub_lower = r.subtitles.lower()
        aud_lower = r.audio.lower()
        if "soft" in sub_lower and "jap" in aud_lower:
            score += 15.0
            badges.append("[Soft-Subs • JP Audio]")
        elif "soft" in sub_lower:
            score += 12.0
            badges.append("[Soft-Subs]")
        elif "jap" in aud_lower:
            score += 10.0
            badges.append("[JP Audio]")
        elif "dual" in aud_lower:
            score += 8.0
            badges.append("[Dual Audio]")
        else:
            score += 5.0

        # 6. Delivery Speed & Health (Max 15 pts)
        if "cdn" in r.delivery.lower():
            score += 15.0
            badges.append("[⚡ Instant CDN]")
        elif r.seeders is not None:
            if r.seeders >= 20:
                score += 14.0
                badges.append(f"[🧲 Peers: {r.seeders} S / Ultra Fast]")
            elif r.seeders >= 5:
                score += 10.0
                badges.append(f"[🧲 Peers: {r.seeders} S / Healthy]")
            elif r.seeders >= 1:
                score += 6.0
                badges.append(f"[🧲 Peers: {r.seeders} S / Low]")
            else:
                score += 1.0
                badges.append("[🧲 Stalled (0 Seeders)]")

        # 7. Provider Boost (User preference: "put in top hentai mama")
        if r.provider == "HentaiMama":
            score += 12.0

        # 8. AniList Rating Badge
        if r.rating and r.rating >= 50:
            badges.append(f"[⭐ {r.rating/10:.1f} AniList]")

        r.score = score
        r.badges = badges

    # Sort descending by score
    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)

    # Award the top pick badge
    if sorted_results:
        sorted_results[0].is_best = True
        sorted_results[0].badges.insert(0, "[⭐ TOP PICK]")

    return sorted_results
