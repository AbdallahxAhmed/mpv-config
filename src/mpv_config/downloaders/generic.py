"""
Generic yt-dlp downloader implementation.
"""

import os
import re
from typing import Any, Dict, List

import yt_dlp

from .base import BaseDownloader, MediaItem


class GenericDownloader(BaseDownloader):
    """Fallback generic downloader powered directly by yt-dlp."""

    name: str = "generic"
    domains: List[str] = []

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Generic downloader acts as fallback and handles any URL."""
        return True

    def extract(self, url: str) -> List[MediaItem]:
        """Extract media items/metadata using in-process yt-dlp."""
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return []

        entries = info.get("entries")
        if entries:
            items: List[MediaItem] = []
            for entry in entries:
                if entry:
                    items.append(self._info_to_media_item(entry, fallback_url=url))
            return items

        return [self._info_to_media_item(info, fallback_url=url)]

    def _info_to_media_item(self, info: Dict[str, Any], fallback_url: str) -> MediaItem:
        title = info.get("title") or "Unknown"
        item_url = info.get("webpage_url") or info.get("url") or fallback_url

        quality = info.get("quality")
        if not quality:
            height = info.get("height")
            if height:
                quality = f"{height}p"
            else:
                quality = info.get("format_note") or "best"
        else:
            quality = str(quality)

        subs = info.get("subtitles")
        subtitles: List[str] = []
        if isinstance(subs, dict):
            subtitles = list(subs.keys())
        elif isinstance(subs, list):
            subtitles = list(subs)

        return MediaItem(
            title=title,
            url=item_url,
            quality=quality,
            subtitles=subtitles,
        )

    def download(self, item: MediaItem, output_dir: str) -> str:
        """Download media item using yt-dlp with ffmpeg merging."""
        os.makedirs(output_dir, exist_ok=True)

        quality_ceiling = 1080
        if item.quality:
            match = re.search(r"\d+", str(item.quality))
            if match:
                quality_ceiling = int(match.group(0))

        opts: Dict[str, Any] = {
            "paths": {"home": output_dir},
            "format": f"bestvideo[height<=?{quality_ceiling}]+bestaudio/best[height<=?{quality_ceiling}]/best",
            "merge_output_format": "mp4",
            "windowsfilenames": True,
            "no_mtime": True,
            "quiet": False,
            "no_warnings": False,
        }

        if item.subtitles:
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = item.subtitles
            opts["embedsubtitles"] = True

        # Apply SiteKit/Session/Engine plugins from tools.core if available
        extractor = None
        try:
            from tools.core.engine import EngineOrchestrator
            from tools.core.registry import SiteRegistry
            from tools.core.session import SessionManager

            registry = SiteRegistry()
            session = SessionManager()
            engine = EngineOrchestrator()

            extractor = registry.find(item.url)
            if extractor and hasattr(extractor, "ytdl_opts"):
                opts.update(extractor.ytdl_opts())

            opts = session.apply_session_opts(opts, item.url, extractor)
            opts = engine.apply_engine_opts(opts, item.url, extractor)
        except Exception:
            pass

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item.url, download=True)
                if info:
                    filename = ydl.prepare_filename(info)
                    if opts.get("merge_output_format"):
                        ext = opts["merge_output_format"]
                        base, _ = os.path.splitext(str(filename))
                        merged_filename = f"{base}.{ext}"
                        if os.path.exists(merged_filename):
                            return merged_filename
                    return str(filename)
                return os.path.join(output_dir, f"{item.title}.mp4")
        except Exception as e:
            err_str = str(e)
            if "403" in err_str or "Forbidden" in err_str:
                try:
                    from tools.core.session import SessionManager

                    session = SessionManager()
                    for browser in session.get_preferred_browsers(extractor):
                        if session._is_browser_installed(browser):
                            opts["cookiesfrombrowser"] = (browser, None, None, None)
                            with yt_dlp.YoutubeDL(opts) as ydl:
                                info = ydl.extract_info(item.url, download=True)
                                if info:
                                    return str(ydl.prepare_filename(info))
                except Exception:
                    pass
            raise
