#!/usr/bin/env python3
"""
cookie_sync_host.py — Native Messaging Host for MPV Media Companion Extension.

Listens on stdio for JSON messages from Chrome/Brave/Edge extension:
- Automatically syncs Cloudflare clearance cookies into %APPDATA%/yt-dlp/cookies.txt
- Launches MPV for 1-click video playback
- Launches MPV Turbo Downloader for 1-click background downloading
"""

import os
import sys
import json
import struct
import shutil
import subprocess

def read_message():
    """Read a length-prefixed JSON message from stdin."""
    try:
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length or len(raw_length) < 4:
            return None
        length = struct.unpack('@I', raw_length)[0]
        data = sys.stdin.buffer.read(length)
        if len(data) < length:
            return None
        return json.loads(data.decode('utf-8'))
    except Exception:
        return None

def send_message(message):
    """Send a length-prefixed JSON message to stdout."""
    try:
        content = json.dumps(message).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('@I', len(content)))
        sys.stdout.buffer.write(content)
        sys.stdout.buffer.flush()
    except Exception:
        pass

def save_cookies(netscape_text, domain=""):
    """Save cookies to standard yt-dlp and mpv config paths."""
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
            targets.append(os.path.join(mpv_cookies_dir, f"{domain}.txt"))
        targets.append(os.path.join(mpv_cookies_dir, "cookies.txt"))

    # 3. Local repo cookies.txt if script is inside repo
    repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

def find_mpv():
    """Locate mpv executable."""
    which = shutil.which("mpv")
    if which:
        return which
    candidates = [
        r"C:\Program Files\mpv\mpv.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\mpv.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "mpv"

def find_mpvdl():
    """Locate mpvdl.py script."""
    repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(repo_dir, "tools", "mpvdl.py")
    if os.path.isfile(candidate):
        return candidate
    deploy_candidate = os.path.expandvars(r"%USERPROFILE%\.mpv-deploy\tools\mpvdl.py")
    if os.path.isfile(deploy_candidate):
        return deploy_candidate
    return None

def main():
    while True:
        msg = read_message()
        if msg is None:
            break

        action = msg.get("action", "")

        if action == "sync_cookies":
            cookies = msg.get("cookies", "")
            domain = msg.get("domain", "")
            saved = save_cookies(cookies, domain)
            send_message({"status": "ok", "action": "synced", "saved": len(saved)})

        elif action == "play":
            url = msg.get("url", "")
            if url:
                mpv_bin = find_mpv()
                creationflags = 0x00000008  # DETACHED_PROCESS on Windows
                subprocess.Popen([mpv_bin, url], creationflags=creationflags)
                send_message({"status": "ok", "action": "playing", "url": url})
            else:
                send_message({"status": "error", "message": "no url provided"})

        elif action == "download":
            url = msg.get("url", "")
            mpvdl = find_mpvdl()
            if url and mpvdl:
                cmd = f'start "MPV Turbo Downloader" python "{mpvdl}" "{url}"'
                subprocess.Popen(cmd, shell=True)
                send_message({"status": "ok", "action": "downloading", "url": url})
            else:
                send_message({"status": "error", "message": "missing url or mpvdl.py"})

        else:
            send_message({"status": "ok", "action": "pong"})

if __name__ == "__main__":
    main()
