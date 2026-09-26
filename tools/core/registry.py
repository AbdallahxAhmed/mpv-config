"""
registry.py — Discovers all extractors known to yt-dlp, both built-in and local plugin-directory extractors.
"""

import os
import sys
import inspect
import pkgutil
import importlib
from typing import Optional, Any, Dict
from yt_dlp.extractor.common import InfoExtractor


class SiteRegistry:
    """Discovers ALL extractors: local repo plugins in tools/yt_dlp_plugins/extractor,
    plus all built-in yt-dlp extractors. Custom plugins take immediate precedence."""

    def __init__(self):
        self._custom_ies: Dict[str, Any] = {}
        self._discover_local_plugins()

    def _discover_local_plugins(self):
        """Auto-discover all InfoExtractor classes in tools/yt_dlp_plugins/extractor."""
        try:
            import tools.yt_dlp_plugins.extractor as ext_pkg
            for _, name, _ in pkgutil.iter_modules(ext_pkg.__path__):
                if name.startswith("_"):
                    continue
                try:
                    mod = importlib.import_module(f"tools.yt_dlp_plugins.extractor.{name}")
                    for _, obj in inspect.getmembers(mod, inspect.isclass):
                        if issubclass(obj, InfoExtractor) and obj is not InfoExtractor:
                            # Instantiate instance
                            ie_instance = obj()
                            self._custom_ies[getattr(obj, "IE_NAME", name)] = ie_instance
                except Exception:
                    pass
        except Exception:
            pass

    def find(self, url: str) -> Optional[Any]:
        """Find matching InfoExtractor instance for given URL."""
        # 1. Custom repo plugins check first
        for name, ie in self._custom_ies.items():
            if ie.suitable(url):
                return ie

        # 2. Built-in yt-dlp extractors
        try:
            from yt_dlp.extractor import gen_extractors
            for ie in gen_extractors():
                if ie.suitable(url) and ie.IE_NAME != "generic":
                    return ie
        except Exception:
            pass

        return None

    def is_custom(self, ie: Any) -> bool:
        """Check if an extractor is from custom plugins."""
        if not ie:
            return False
        mod = getattr(ie, "__module__", "") or ""
        return "yt_dlp_plugins" in mod or ie.IE_NAME in self._custom_ies
