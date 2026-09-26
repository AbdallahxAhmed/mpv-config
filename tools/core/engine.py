"""
engine.py — Concurrency, download engine orchestration, and stream-adaptive routing.
"""

import os
import shutil
import pathlib
from typing import Dict, Any, Optional


class EngineOrchestrator:
    """Orchestrates download backends: aria2c for progressive MP4, native concurrent fragments for HLS/DASH."""

    def __init__(self):
        self.aria2c_path = self.locate_aria2c()
        self.ffmpeg_path = self.locate_ffmpeg()

    @staticmethod
    def locate_aria2c() -> Optional[str]:
        """Locate aria2c executable in PATH or standard MPV / WinGet locations."""
        which = shutil.which("aria2c")
        if which:
            return which
        candidates = [
            r"C:\Program Files\mpv\aria2c.exe",
            r"C:\Program Files\mpv\aria2\aria2c.exe",
            os.path.expandvars(r"%APPDATA%\mpv\aria2c.exe"),
            os.path.expandvars(r"%APPDATA%\mpv\tools\aria2c.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\aria2c.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            pkg_dir = pathlib.Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
            if pkg_dir.exists():
                for p in pkg_dir.glob("**/aria2c.exe"):
                    if p.is_file():
                        return str(p)
        return None

    @staticmethod
    def locate_ffmpeg() -> Optional[str]:
        """Locate ffmpeg executable."""
        which = shutil.which("ffmpeg")
        if which:
            return which
        candidates = [
            r"C:\Program Files\mpv\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\mpv\ffmpeg.exe",
            os.path.expandvars(r"%APPDATA%\mpv\ffmpeg.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def apply_engine_opts(self, ytdl_opts: Dict[str, Any], url: str, extractor: Optional[Any] = None) -> Dict[str, Any]:
        """
        Enforce correct download engine:
        - Sites with SiteKit.ENGINE == 'native' or manifest streams use native fragment downloader.
        - Progressive media files use aria2c 16-connection acceleration.
        """
        engine_type = "auto"
        if extractor and hasattr(extractor, "ENGINE"):
            engine_type = extractor.ENGINE

        # If site explicitly specifies native (like Hanime HLS or Perverzija xs1 m3u8)
        if engine_type == "native":
            ytdl_opts["concurrent_fragment_downloads"] = 16
            ytdl_opts["hls_use_mpegts"] = False
            # Ensure aria2c is NOT forced onto HLS segments
            ytdl_opts.pop("external_downloader", None)
            ytdl_opts.pop("external_downloader_args", None)
            return ytdl_opts

        # For progressive streams (or auto where aria2c is available)
        if self.aria2c_path:
            ytdl_opts["external_downloader"] = {
                "http": self.aria2c_path,
                "https": self.aria2c_path,
            }
            ytdl_opts["external_downloader_args"] = {
                "aria2c": [
                    "-x", "16",
                    "-s", "16",
                    "-k", "1M",
                    "--file-allocation=none",
                    "--check-certificate=false"
                ]
            }

        ytdl_opts["concurrent_fragment_downloads"] = 16
        return ytdl_opts
