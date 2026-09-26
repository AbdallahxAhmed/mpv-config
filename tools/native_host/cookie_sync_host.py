#!/usr/bin/env python3
"""
cookie_sync_host.py — Dual-Mode Native Messaging Host & Local HTTP Sync Daemon for MPV & yt-dlp.

Features:
- Native Messaging Protocol over stdio for Chromium browsers (Chrome, Helium, Brave, Edge).
- High-performance local HTTP server on http://127.0.0.1:8765 for browser extensions and userscripts (Tampermonkey).
- Zero-latency cookie sync: Writes Cloudflare Turnstile & session cookies to %APPDATA%/yt-dlp/cookies.txt.
- Stream Manifest Bridge: Stores signed M3U8 URLs intercepted in the browser so CLI (dl / yt-dlp) can download without Cloudflare challenges.
- 1-click playback and turbo download actions.
"""

from __future__ import annotations

import os
import sys
import json
import time
import struct
import shutil
import pathlib
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HTTP_PORT = 8765
ACTIVE_STREAMS_FILE = os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "active_streams.json")
STREAM_CACHE: dict[str, dict] = {}


# ─── Cookie Persistence ──────────────────────────────────────────────────

def save_cookies(cookie_input: str | list | dict, domain: str = "") -> list[str]:
    """Save cookies to standard yt-dlp and mpv-config paths in Netscape format."""
    netscape_text = ""

    if isinstance(cookie_input, str):
        if cookie_input.strip().startswith("# Netscape") or "\t" in cookie_input:
            netscape_text = cookie_input
        else:
            # Parse document.cookie header syntax: "name1=val1; name2=val2"
            lines = [
                "# Netscape HTTP Cookie File",
                "# Exported automatically by MPV Media Companion",
                ""
            ]
            dom = domain if domain else ".hanime.tv"
            if not dom.startswith("."):
                dom = "." + dom
            for pair in cookie_input.split(";"):
                if "=" in pair:
                    k, v = pair.strip().split("=", 1)
                    if k.strip():
                        # domain flag path secure expiry name value
                        lines.append(f"{dom}\tTRUE\t/\tTRUE\t{int(time.time()) + 86400 * 30}\t{k.strip()}\t{v.strip()}")
            netscape_text = "\n".join(lines) + "\n"

    elif isinstance(cookie_input, list):
        lines = [
            "# Netscape HTTP Cookie File",
            "# Exported automatically by MPV Media Companion",
            ""
        ]
        for c in cookie_input:
            dom = c.get("domain", domain or ".hanime.tv")
            if not dom.startswith("."):
                dom = "." + dom
            flag = "TRUE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure") else "FALSE"
            expiry = int(c.get("expirationDate") or c.get("expires") or (time.time() + 86400 * 30))
            name = c.get("name", "")
            val = c.get("value", "")
            if name:
                lines.append(f"{dom}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{val}")
        netscape_text = "\n".join(lines) + "\n"

    if not netscape_text:
        return []

    appdata = os.environ.get("APPDATA", "")
    targets = []

    # 1. Global yt-dlp cookies.txt
    if appdata:
        ytdl_dir = os.path.join(appdata, "yt-dlp")
        os.makedirs(ytdl_dir, exist_ok=True)
        targets.append(os.path.join(ytdl_dir, "cookies.txt"))

        # 2. mpv-config cookies dir
        mpv_cookies_dir = os.path.join(appdata, "mpv-config", "cookies")
        os.makedirs(mpv_cookies_dir, exist_ok=True)
        if domain:
            safe_dom = domain.replace("/", "").replace("\\", "").strip(".")
            targets.append(os.path.join(mpv_cookies_dir, f"{safe_dom}.txt"))
        targets.append(os.path.join(mpv_cookies_dir, "cookies.txt"))

    # 3. Local repo cookies.txt
    repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.isdir(repo_dir):
        targets.append(os.path.join(repo_dir, "cookies.txt"))

    saved_paths = []
    for path in targets:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(netscape_text)
            saved_paths.append(path)
        except Exception:
            pass

    return saved_paths


# ─── Stream Cache ────────────────────────────────────────────────────────

def save_stream(slug: str, url: str, title: str = "", page_url: str = "") -> dict:
    """Cache intercepted M3U8 stream manifest URL."""
    entry = {
        "slug": slug,
        "url": url,
        "title": title,
        "page_url": page_url,
        "timestamp": int(time.time())
    }
    STREAM_CACHE[slug] = entry

    try:
        os.makedirs(os.path.dirname(ACTIVE_STREAMS_FILE), exist_ok=True)
        disk_cache = {}
        if os.path.isfile(ACTIVE_STREAMS_FILE):
            try:
                with open(ACTIVE_STREAMS_FILE, "r", encoding="utf-8") as f:
                    disk_cache = json.load(f)
            except Exception:
                disk_cache = {}
        disk_cache[slug] = entry
        # Trim entries older than 24 hours
        now = time.time()
        disk_cache = {k: v for k, v in disk_cache.items() if now - v.get("timestamp", 0) < 86400}
        with open(ACTIVE_STREAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(disk_cache, f, indent=2)
    except Exception:
        pass

    return entry


def get_cached_stream(slug: str) -> dict | None:
    """Retrieve stream from in-memory cache or disk file."""
    if slug in STREAM_CACHE:
        return STREAM_CACHE[slug]

    if os.path.isfile(ACTIVE_STREAMS_FILE):
        try:
            with open(ACTIVE_STREAMS_FILE, "r", encoding="utf-8") as f:
                disk_cache = json.load(f)
            if slug in disk_cache:
                entry = disk_cache[slug]
                STREAM_CACHE[slug] = entry
                return entry
        except Exception:
            pass
    return None


# ─── Launchers ───────────────────────────────────────────────────────────

def find_mpv() -> str:
    """Locate MPV binary."""
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
    return "mpv"


def find_mpvdl() -> str | None:
    """Locate mpvdl.py script."""
    repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(repo_dir, "tools", "mpvdl.py")
    if os.path.isfile(candidate):
        return candidate
    deploy_candidate = os.path.expandvars(r"%USERPROFILE%\.mpv-deploy\tools\mpvdl.py")
    if os.path.isfile(deploy_candidate):
        return deploy_candidate
    return None


def execute_play(url: str):
    """Launch MPV to play video."""
    mpv_bin = find_mpv()
    creationflags = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS
    subprocess.Popen([mpv_bin, url], creationflags=creationflags)


def execute_download(url: str):
    """Launch MPV Turbo Downloader."""
    mpvdl = find_mpvdl()
    if mpvdl:
        cmd = f'start "MPV Turbo Downloader" python "{mpvdl}" "{url}"'
        subprocess.Popen(cmd, shell=True)


# ─── Local HTTP Daemon ───────────────────────────────────────────────────

class SyncHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP server handling cookie sync & stream dispatching."""

    def log_message(self, format, *args):
        pass  # Suppress default server access logs to prevent console noise

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health" or path == "/":
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "mpv-cookie-sync"}).encode("utf-8"))

        elif path == "/stream":
            slug = query.get("slug", [""])[0]
            if slug:
                entry = get_cached_stream(slug)
                if entry:
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "stream": entry}).encode("utf-8"))
                    return
            # Return all active streams
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "streams": STREAM_CACHE}).encode("utf-8"))

        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        data = {}
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {"raw": body.decode("utf-8", errors="ignore")}

        if path == "/sync":
            cookies = data.get("cookies") or data.get("raw") or ""
            domain = data.get("domain", "hanime.tv")
            saved = save_cookies(cookies, domain)
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "saved_targets": len(saved)}).encode("utf-8"))

        elif path == "/stream":
            slug = data.get("slug", "")
            url = data.get("url", "")
            title = data.get("title", "")
            page_url = data.get("page_url", "")
            if not slug and page_url:
                slug = page_url.rstrip("/").split("/")[-1]

            if slug and url:
                entry = save_stream(slug, url, title, page_url)
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "cached": entry}).encode("utf-8"))
            else:
                self.send_response(400)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "missing slug or url"}).encode("utf-8"))

        elif path == "/play":
            url = data.get("url", "")
            if url:
                execute_play(url)
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "action": "playing"}).encode("utf-8"))
            else:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()

        elif path == "/download":
            url = data.get("url", "")
            if url:
                execute_download(url)
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "action": "downloading"}).encode("utf-8"))
            else:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()

        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()


def start_http_server(port=HTTP_PORT) -> HTTPServer | None:
    """Start local HTTP server in a daemon thread."""
    try:
        server = HTTPServer(("127.0.0.1", port), SyncHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server
    except OSError:
        # Port already in use by an existing instance
        return None


# ─── Native Messaging Stdio Protocol ─────────────────────────────────────

def read_native_message():
    """Read length-prefixed JSON message from stdin."""
    try:
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length or len(raw_length) < 4:
            return None
        length = struct.unpack("@I", raw_length)[0]
        data = sys.stdin.buffer.read(length)
        if len(data) < length:
            return None
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def send_native_message(message):
    """Send length-prefixed JSON message to stdout."""
    try:
        content = json.dumps(message).encode("utf-8")
        sys.stdout.buffer.write(struct.pack("@I", len(content)))
        sys.stdout.buffer.write(content)
        sys.stdout.buffer.flush()
    except Exception:
        pass


def run_native_host_loop():
    """Stdio loop for Native Messaging Host."""
    while True:
        msg = read_native_message()
        if msg is None:
            break

        action = msg.get("action", "")

        if action == "sync_cookies":
            cookies = msg.get("cookies", "")
            domain = msg.get("domain", "")
            saved = save_cookies(cookies, domain)
            send_native_message({"status": "ok", "action": "synced", "saved": len(saved)})

        elif action == "stream_captured":
            slug = msg.get("slug", "")
            url = msg.get("url", "")
            title = msg.get("title", "")
            page_url = msg.get("page_url", "")
            if not slug and page_url:
                slug = page_url.rstrip("/").split("/")[-1]
            if slug and url:
                save_stream(slug, url, title, page_url)
            send_native_message({"status": "ok", "action": "stream_cached"})

        elif action == "play":
            url = msg.get("url", "")
            if url:
                execute_play(url)
                send_native_message({"status": "ok", "action": "playing", "url": url})
            else:
                send_native_message({"status": "error", "message": "no url provided"})

        elif action == "download":
            url = msg.get("url", "")
            if url:
                execute_download(url)
                send_native_message({"status": "ok", "action": "downloading", "url": url})
            else:
                send_native_message({"status": "error", "message": "no url provided"})

        else:
            send_native_message({"status": "ok", "action": "pong"})


# ─── Entry Point ─────────────────────────────────────────────────────────

def main():
    # Always ensure background HTTP server is running on 127.0.0.1:8765
    server = start_http_server(HTTP_PORT)

    # If --daemon or --http-only, keep process running standalone
    if "--daemon" in sys.argv or "--http-only" in sys.argv:
        print(f"[MPV Sync Daemon] Listening on http://127.0.0.1:{HTTP_PORT}...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            if server:
                server.shutdown()
        return

    # Default: Native Messaging Host stdio loop
    run_native_host_loop()


if __name__ == "__main__":
    main()
