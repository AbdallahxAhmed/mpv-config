"""
models.py — Data models for multi-source search results and badges.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class SearchResult:
    title: str
    provider: str  # "HentaiMama", "Nyaa", "Hanime", "HentaiWorld", "HentaiHaven"
    url: str  # Streaming page, direct stream, or magnet link
    download_url: Optional[str] = None  # Direct MP4, .torrent, or magnet link
    resolution: str = "1080p"  # "1080p", "720p", "480p"
    quality_type: str = "Web Stream"  # "BD Remux", "60 FPS", "WEBRip", "Web Stream"
    codec: str = "H.264"  # "HEVC (10-bit)", "H.264", "x265", etc.
    size: str = ""  # e.g. "602 MiB", "1.2 GiB"
    seeders: Optional[int] = None  # for torrents
    censorship: str = "Censored"  # "Uncensored", "Decensored", "Censored"
    subtitles: str = "Hard-sub"  # "Soft-subs (MKV)", "Hard-sub", "Raw"
    audio: str = "Japanese (Original)"  # "Japanese (Original)", "Dual Audio", "English Dub"
    delivery: str = "Instant CDN"  # "Instant CDN", "Torrent (P2P)"
    thumbnail: Optional[str] = None
    score: float = 0.0
    badges: List[str] = field(default_factory=list)
    is_best: bool = False
    episode: Optional[str] = None
