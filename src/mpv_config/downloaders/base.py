"""
Base classes and data models for the downloader framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MediaItem:
    """Represents a media item to be extracted or downloaded."""

    title: str
    url: str
    quality: Optional[str] = None
    subtitles: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.subtitles is None:
            self.subtitles = []


class BaseDownloader(ABC):
    """Abstract Base Class for downloader plugins."""

    name: str = ""
    domains: List[str] = []

    @classmethod
    @abstractmethod
    def can_handle(cls, url: str) -> bool:
        """Return True if this downloader can handle the given URL."""
        pass

    @abstractmethod
    def extract(self, url: str) -> List[MediaItem]:
        """Extract media items/metadata from the given URL without downloading."""
        pass

    @abstractmethod
    def download(self, item: MediaItem, output_dir: str) -> str:
        """Download the given media item into output_dir and return output path."""
        pass
