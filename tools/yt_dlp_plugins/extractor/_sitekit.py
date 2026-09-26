"""
_sitekit.py — Shared base mixin for custom yt-dlp extractor plugins.
Provides site-specific download policies, quality ceilings, engine overrides, and options.
"""

from typing import Dict, Any, Tuple


class SiteKit:
    """Mixin: site-specific download policy and engine routing. Pure data + hooks, no I/O."""
    SITE_NAME: str = ""
    REQUIRES_COOKIES: bool = False
    PREFERRED_BROWSERS: Tuple[str, ...] = ("brave", "chrome", "edge", "firefox")
    QUALITY_CEILING: int = 1080
    # Engine override: 'aria2c' (progressive MP4) | 'native' (HLS/DASH fragments) | 'auto'
    ENGINE: str = "auto"
    EXTRA_YTDL_OPTS: Dict[str, Any] = {}

    @classmethod
    def ytdl_opts(cls) -> Dict[str, Any]:
        """Generate yt-dlp option overrides for this site."""
        opts: Dict[str, Any] = {
            "format": (
                f"bestvideo[height<=?{cls.QUALITY_CEILING}]+bestaudio/"
                f"best[height<=?{cls.QUALITY_CEILING}]/best"
            ),
            "merge_output_format": "mp4",
        }
        if cls.ENGINE == "native":
            opts["concurrent_fragment_downloads"] = 16
        opts.update(cls.EXTRA_YTDL_OPTS)
        return opts
