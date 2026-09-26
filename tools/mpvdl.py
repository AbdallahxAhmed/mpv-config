#!/usr/bin/env python3
"""
mpvdl.py — Unified High-Speed Media Downloader & Streamer for MPV & yt-dlp.
Replaces dedicated per-site downloaders with a single, pluggable, zero-command CLI.
"""

import os
import sys
import time
import argparse
import subprocess
import pathlib
from typing import List, Optional, Dict, Any

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add repo root to sys.path so tools.core and plugins can be imported
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.core.registry import SiteRegistry
from tools.core.session import SessionManager
from tools.core.engine import EngineOrchestrator
from tools.core.clipboard import ClipboardService
from tools.core.telemetry import TelemetryBus


def get_default_download_dir() -> str:
    """Find user's Downloads folder."""
    if sys.platform == "win32":
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            d = os.path.join(userprofile, "Downloads")
            if os.path.isdir(d):
                return d
    home = pathlib.Path.home()
    d = home / "Downloads"
    if d.is_dir():
        return str(d)
    return os.getcwd()


def find_mpv() -> Optional[str]:
    """Locate MPV executable."""
    import shutil
    which = shutil.which("mpv")
    if which:
        return which
    candidates = [
        r"C:\Program Files\mpv\mpv.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\mpv.exe"),
        os.path.expandvars(r"%APPDATA%\mpv\mpv.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


class MpvDownloader:
    """Core download controller coordinating Registry, Session, and Engine."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or get_default_download_dir()
        self.registry = SiteRegistry()
        self.session = SessionManager()
        self.engine = EngineOrchestrator()
        self.telemetry = TelemetryBus()

    def download_url(self, url: str, quality_ceiling: int = 1080) -> int:
        """Download URL using in-process yt-dlp with automatic fallback chains."""
        import yt_dlp

        extractor = self.registry.find(url)
        site_name = getattr(extractor, "SITE_NAME", None) or getattr(extractor, "IE_NAME", "generic")

        print(f"\n[+] URL:      {url}")
        print(f"[+] Handler:  {site_name.title()} ({'Custom Plugin' if self.registry.is_custom(extractor) else 'yt-dlp core'})")
        print(f"[+] Output:   {self.output_dir}")
        print(f"[+] Quality:  Best up to {quality_ceiling}p (Capped, no 4K)")

        # Base options
        opts: Dict[str, Any] = {
            "paths": {"home": self.output_dir},
            "format": f"bestvideo[height<=?{quality_ceiling}]+bestaudio/best[height<=?{quality_ceiling}]/best",
            "merge_output_format": "mp4",
            "windowsfilenames": True,
            "no_mtime": True,
            "quiet": False,
            "no_warnings": False,
        }

        # Apply SiteKit options if extractor provides them
        if extractor and hasattr(extractor, "ytdl_opts"):
            opts.update(extractor.ytdl_opts())

        # Apply Session (cookies & curl_cffi)
        opts = self.session.apply_session_opts(opts, url, extractor)

        # Apply Engine (aria2c 16x vs native fragments)
        opts = self.engine.apply_engine_opts(opts, url, extractor)

        # Try download
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                rc = ydl.download([url])
                return rc
        except Exception as e:
            err_str = str(e)
            print(f"\n[!] Download encounter an error: {err_str}")

            # Check if Cloudflare 403 occurred and retry with browser cookies if not already done
            if "403" in err_str or "Forbidden" in err_str:
                print("[*] Attempting recovery: trying browser cookies fallback...")
                for browser in self.session.get_preferred_browsers(extractor):
                    if self.session._is_browser_installed(browser):
                        print(f"    -> Re-attempting with cookies from {browser}...")
                        opts["cookiesfrombrowser"] = (browser, None, None, None)
                        try:
                            with yt_dlp.YoutubeDL(opts) as ydl:
                                return ydl.download([url])
                        except Exception:
                            continue

                print("\n[!] Cloudflare challenge could not be bypassed automatically.")
                print("    Actionable hint:")
                print("    1. Open the video in Brave / Chrome once so Cloudflare verifies your session.")
                print("    2. Close the browser for 2 seconds and re-run this download.")
                print("    3. Or export cookies to 'cookies.txt' in the mpv-config directory.\n")
            return 1

    def stream_url(self, url: str, quality_ceiling: int = 1080) -> int:
        """Stream URL directly in MPV without writing to disk."""
        mpv_bin = find_mpv()
        if not mpv_bin:
            print("[!] mpv executable not found.")
            return 1

        print(f"\n[+] Streaming in MPV: {url}")
        cmd = [
            mpv_bin,
            f"--ytdl-format=bestvideo[height<=?{quality_ceiling}]+bestaudio/best[height<=?{quality_ceiling}]/best",
            url
        ]
        return subprocess.run(cmd).returncode

    def interactive_paste_loop(self):
        """Zero-command interactive paste mode for non-technical users."""
        os.makedirs(self.output_dir, exist_ok=True)

        print("\n" + "=" * 70)
        print("  [>] MPVDL: Universal High-Speed Media Downloader (16x Turbo)")
        print(f"  [+] Save folder: {self.output_dir}")
        print("  [*] Resolution: Best quality up to 1080p (Capped, no 4K)")
        print("=" * 70 + "\n")

        while True:
            clipboard = ClipboardService.get_text().strip()
            has_clip_url = ClipboardService.is_url(clipboard)

            if has_clip_url:
                print(f"[+] Link detected in clipboard:\n    -> {clipboard}")
                prompt = "[?] Press [ENTER] to download this link, or paste another link (or 'q' to quit): "
            else:
                prompt = "[?] Paste video link here and press [ENTER] (or 'q' to quit): "

            try:
                user_input = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[+] Exiting. Happy watching!")
                break

            if user_input.lower() in ("q", "quit", "exit"):
                print("[+] Exiting. Happy watching!")
                break

            target_url = None
            if not user_input and has_clip_url:
                target_url = clipboard
            elif ClipboardService.is_url(user_input):
                target_url = user_input
            elif user_input:
                print(f"[!] '{user_input}' does not look like a valid link. Please try again.\n")
                continue
            else:
                print("[!] No link entered and clipboard has no valid URL.\n")
                continue

            rc = self.download_url(target_url)
            if rc == 0:
                print(f"\n[OK] Download finished successfully! Saved to:\n    {self.output_dir}\n")
            else:
                print(f"\n[!] Download finished with status code {rc}\n")

    def watch_clipboard(self):
        """Background clipboard watcher: automatically downloads any copied video link."""
        os.makedirs(self.output_dir, exist_ok=True)
        seen_urls = set()

        print("\n" + "=" * 70)
        print("  [>] MPVDL: Clipboard Watcher Active (16x Turbo Speed)")
        print(f"  [+] Save folder: {self.output_dir}")
        print("  [*] Resolution: Best quality up to 1080p")
        print("  [*] Copy ANY video link in your browser to download automatically.")
        print("  [*] Press Ctrl+C to stop watching.")
        print("=" * 70 + "\n")

        while True:
            try:
                clip = ClipboardService.get_text().strip()
                if ClipboardService.is_url(clip) and clip not in seen_urls:
                    seen_urls.add(clip)
                    print(f"\n[+] New link copied: {clip}")
                    self.download_url(clip)
                    print("\n[*] Continuing to watch clipboard...\n")
                time.sleep(1.0)
            except KeyboardInterrupt:
                print("\n[+] Watcher stopped by user.")
                break


def main():
    parser = argparse.ArgumentParser(
        description="MPVDL: Unified High-Speed Media Downloader & Streamer for MPV & yt-dlp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Zero-Command Usage:
  # Just run with no arguments to enter Interactive Paste Mode (or double-click .cmd):
  python tools/mpvdl.py

  # Automatic Clipboard Watcher (downloads as soon as you copy any link in browser):
  python tools/mpvdl.py --watch

Command-Line Usage:
  # Download video directly:
  python tools/mpvdl.py "https://example.com/video"

  # Stream video directly in MPV without downloading:
  python tools/mpvdl.py "https://example.com/video" --play

  # Check browser and cookie session diagnostics:
  python tools/mpvdl.py --check-sessions
        """
    )
    parser.add_argument("urls", nargs="*", help="Optional URL(s) to download directly")
    parser.add_argument("-o", "--output", default=None, help="Output directory (default: ~/Downloads)")
    parser.add_argument("-q", "--quality", type=int, default=1080, help="Max resolution ceiling (default: 1080)")
    parser.add_argument("--watch", action="store_true", help="Watch clipboard in real-time and auto-download copied links")
    parser.add_argument("--play", "--stream", action="store_true", help="Stream directly in MPV instead of downloading")
    parser.add_argument("--check-sessions", action="store_true", help="Check session health, cookies, and TLS impersonation")

    args = parser.parse_args()
    downloader = MpvDownloader(output_dir=args.output)

    if args.check_sessions:
        health = downloader.session.check_health()
        print("\n=== MPVDL Session & Anti-Bot Diagnostics ===")
        print(f"curl_cffi (TLS Impersonation): {'Available' if health['curl_cffi_available'] else 'Not Installed (pip install curl_cffi)'}")
        print("Installed Browsers for Cookie Import:")
        for b, inst in health["installed_browsers"].items():
            print(f"  - {b.title():<10}: {'Installed' if inst else 'Not Detected'}")
        print(f"Cookies Cache Directory: {health['cookies_dir']}")
        print(f"Active Cached Cookie Files: {health['active_cookie_files'] or 'None'}")
        print("============================================\n")
        return 0

    if args.watch:
        downloader.watch_clipboard()
        return 0

    if args.urls:
        rc = 0
        for u in args.urls:
            if args.play:
                r = downloader.stream_url(u, quality_ceiling=args.quality)
            else:
                r = downloader.download_url(u, quality_ceiling=args.quality)
            if r != 0:
                rc = r
        return rc

    # Default to interactive paste mode
    downloader.interactive_paste_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
