"""
Downloader registry and plugin exports.
"""

from .base import BaseDownloader, MediaItem
from .generic import GenericDownloader

DOWNLOADERS: list[BaseDownloader] = [GenericDownloader()]


def get_downloader(url: str) -> BaseDownloader:
    """Find a matching downloader for url, falling back to generic."""
    for dl in DOWNLOADERS:
        if dl.can_handle(url):
            return dl
    return DOWNLOADERS[-1]  # Fallback to generic


__all__ = [
    "BaseDownloader",
    "MediaItem",
    "GenericDownloader",
    "DOWNLOADERS",
    "get_downloader",
]
