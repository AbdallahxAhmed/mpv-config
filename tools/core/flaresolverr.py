"""
flaresolverr.py — FlareSolverr client for automated Cloudflare Turnstile & clearance solving.

Integrates with local FlareSolverr instance (default http://localhost:8191/v1) or auto-starts
flaresolverr.exe from C:\Tools\FlareSolverr or custom path.
Exports solved clearance cookies directly into yt-dlp Netscape cookie storage.
"""

from __future__ import annotations

import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List


DEFAULT_FLARESOLVERR_URL = "http://localhost:8191"

KNOWN_PATHS = [
    r"C:\Tools\FlareSolverr\flaresolverr.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\FlareSolverr\flaresolverr.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\FlareSolverr\flaresolverr.exe"),
]


def is_flaresolverr_running(base_url: str = DEFAULT_FLARESOLVERR_URL, timeout: float = 1.0) -> bool:
    """Check if FlareSolverr service is active and responsive."""
    try:
        req = urllib.request.Request(base_url, headers={"User-Agent": "mpv-config/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return "FlareSolverr is ready!" in data.get("msg", "")
    except Exception:
        return False


def ensure_flaresolverr_running(base_url: str = DEFAULT_FLARESOLVERR_URL) -> bool:
    """Ensure FlareSolverr is running; auto-launch flaresolverr.exe if present on disk."""
    if is_flaresolverr_running(base_url):
        return True

    exe_path = os.environ.get("FLARESOLVERR_PATH")
    if not exe_path or not os.path.isfile(exe_path):
        for candidate in KNOWN_PATHS:
            if candidate and os.path.isfile(candidate):
                exe_path = candidate
                break

    if not exe_path or not os.path.isfile(exe_path):
        return False

    try:
        # Launch detached background process on Windows
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        subprocess.Popen(
            [exe_path],
            cwd=os.path.dirname(exe_path),
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait up to 10 seconds for service to bind port
        for _ in range(20):
            time.sleep(0.5)
            if is_flaresolverr_running(base_url):
                return True
    except Exception:
        pass

    return False


def format_netscape_cookies(cookies: List[Dict[str, Any]]) -> str:
    """Convert FlareSolverr cookie dicts to Netscape cookie file format."""
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically by mpv-config via FlareSolverr",
        "",
    ]
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        domain = c.get("domain", "")
        if domain and not domain.startswith("."):
            domain = "." + domain
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expiry = int(c.get("expiry") or c.get("expires") or 0)
        flag = "TRUE"
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

    return "\n".join(lines) + "\n"


def save_cookies_to_disk(cookie_text: str, domain: str = "hanime.tv") -> List[str]:
    """Save exported cookies to yt-dlp and mpv-config known cookie paths."""
    targets = [
        os.path.join(os.environ.get("APPDATA", ""), "yt-dlp", "cookies.txt"),
        os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "cookies", f"{domain}.txt"),
        os.path.join(os.path.expanduser("~"), "Desktop", "mpv-config", "cookies.txt"),
    ]
    written = []
    for target in targets:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(cookie_text)
            written.append(target)
        except Exception:
            pass
    return written


def solve_cloudflare(
    url: str,
    base_url: str = DEFAULT_FLARESOLVERR_URL,
    max_timeout: int = 60000,
) -> Optional[Dict[str, Any]]:
    """
    Request FlareSolverr to solve Cloudflare challenge for given URL.
    Returns dict with cookies, cookie_str, user_agent, solution or None.
    """
    if not ensure_flaresolverr_running(base_url):
        return None

    endpoint = f"{base_url.rstrip('/')}/v1"
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": max_timeout,
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=max_timeout // 1000 + 10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != "ok":
                return None

            solution = data.get("solution", {})
            cookies = solution.get("cookies", [])
            user_agent = solution.get("userAgent", "")

            cookie_str = "; ".join(f"{c.get('name')}={c.get('value')}" for c in cookies if c.get("name"))
            cookie_file_content = format_netscape_cookies(cookies)

            # Extract domain for filename
            domain = "hanime.tv"
            try:
                domain = urllib.request.urlparse(url).netloc or "hanime.tv"
            except Exception:
                pass

            save_cookies_to_disk(cookie_file_content, domain)

            return {
                "status": "ok",
                "cookies": cookies,
                "cookie_str": cookie_str,
                "user_agent": user_agent,
                "solution": solution,
                "netscape_content": cookie_file_content,
            }
    except Exception as exc:
        sys.stderr.write(f"[FlareSolverr] Request failed: {exc}\n")
        return None
