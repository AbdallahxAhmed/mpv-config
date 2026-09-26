"""
session.py — Anti-Bot resiliency, cookie extraction fallback chain, and session management.
"""

import os
import shutil
import urllib.parse
from typing import Optional, List, Dict, Any


class SessionManager:
    """Manages session tokens, browser cookie import fallbacks, and TLS impersonation."""

    def __init__(self, cookies_dir: Optional[str] = None):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        self.cookies_dir = cookies_dir or os.path.join(appdata, "mpv-config", "cookies")
        os.makedirs(self.cookies_dir, exist_ok=True)

    def get_cookie_file_for(self, url: str) -> Optional[str]:
        """Locate any available cookie file for the target URL."""
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # 1. Check repo root / local directory cookies.txt
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        repo_cookie = os.path.join(root_dir, "cookies.txt")
        if os.path.isfile(repo_cookie):
            return repo_cookie

        local_cookie = os.path.abspath("cookies.txt")
        if os.path.isfile(local_cookie):
            return local_cookie

        # 2. Check cached site-specific cookie files in APPDATA
        site_cookie = os.path.join(self.cookies_dir, f"{domain}.txt")
        if os.path.isfile(site_cookie):
            return site_cookie

        # 3. Check generic names
        for candidate in ["hanime_cookies.txt", "perverzija_cookies.txt"]:
            cpath = os.path.join(root_dir, candidate)
            if os.path.isfile(cpath):
                return cpath

        return None

    def get_preferred_browsers(self, extractor: Any) -> List[str]:
        """Return the prioritized list of browsers to import cookies from."""
        if extractor and hasattr(extractor, "PREFERRED_BROWSERS"):
            return list(extractor.PREFERRED_BROWSERS)
        return ["brave", "chrome", "edge", "firefox"]

    def apply_session_opts(self, ytdl_opts: Dict[str, Any], url: str, extractor: Optional[Any] = None) -> Dict[str, Any]:
        """Enrich yt-dlp options with cookies and TLS impersonation."""
        # Check for cookies file
        cookie_file = self.get_cookie_file_for(url)
        if cookie_file:
            ytdl_opts["cookiefile"] = cookie_file
        elif extractor and getattr(extractor, "REQUIRES_COOKIES", False):
            # For sites with strict bot barriers (like Hanime), try reading browser cookies if available
            browsers = self.get_preferred_browsers(extractor)
            # Pick the first installed browser if detected
            for b in browsers:
                if self._is_browser_installed(b):
                    ytdl_opts["cookiesfrombrowser"] = (b, None, None, None)
                    break

        # Apply curl_cffi impersonation if installed
        try:
            import curl_cffi  # noqa: F401
            # yt-dlp recognizes 'impersonate' when curl_cffi is available
            ytdl_opts["impersonate"] = "chrome"
        except ImportError:
            pass

        return ytdl_opts

    def _is_browser_installed(self, browser: str) -> bool:
        """Check if a browser binary or profile directory is likely present on Windows."""
        local = os.environ.get("LOCALAPPDATA", "")
        roaming = os.environ.get("APPDATA", "")
        prog = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

        paths = {
            "brave": [
                os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
                os.path.join(prog, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ],
            "chrome": [
                os.path.join(local, "Google", "Chrome", "User Data"),
                os.path.join(prog, "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "edge": [
                os.path.join(local, "Microsoft", "Edge", "User Data"),
                os.path.join(prog_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            ],
            "firefox": [
                os.path.join(roaming, "Mozilla", "Firefox", "Profiles"),
            ]
        }
        for p in paths.get(browser.lower(), []):
            if os.path.exists(p):
                return True
        return False

    def check_health(self) -> Dict[str, Any]:
        """Produce a diagnostic health snapshot of session capabilities."""
        installed = {b: self._is_browser_installed(b) for b in ["brave", "chrome", "edge", "firefox"]}
        has_curl_cffi = False
        try:
            import curl_cffi
            has_curl_cffi = True
        except ImportError:
            pass

        return {
            "curl_cffi_available": has_curl_cffi,
            "installed_browsers": installed,
            "cookies_dir": self.cookies_dir,
            "active_cookie_files": os.listdir(self.cookies_dir) if os.path.isdir(self.cookies_dir) else [],
        }
