#!/usr/bin/env python3
"""
Hanime.tv high-speed downloader & stream extractor.

Supports:
- Direct video downloading with multi-threaded fragment acceleration (aria2c / yt-dlp)
- Quality ceiling: Best quality up to 1080p (no 4K bloat)
- AES-256-GCM handshake token decryption & reverse-engineered credential synthesis
- Automatic cookie detection from Brave/Chrome/Edge/Firefox or local cookies.txt
- Zero-command interactive paste mode (auto-detects clipboard, press Enter to download)
- Hands-free clipboard watcher mode (--watch)
- Direct streaming in MPV (--play)
- Auto-installation of yt-dlp native plugin for system-wide CLI support
"""

import os
import sys
import re
import time
import json
import ssl
import shutil
import pathlib
import argparse
import subprocess
import urllib.request
import urllib.parse
from base64 import urlsafe_b64encode, urlsafe_b64decode
from typing import Dict, List, Optional, Any

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Cryptodome for AES-256-GCM and SHA256
try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Hash import SHA256
    from Cryptodome.Random import get_random_bytes
except ImportError:
    try:
        from Crypto.Cipher import AES
        from Crypto.Hash import SHA256
        from Crypto.Random import get_random_bytes
    except ImportError:
        AES = None
        SHA256 = None
        get_random_bytes = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

AUTH_API_URL = "https://auth.hanime.tv"
HOST_URL = "https://hanime.tv/"
HANIME_SLUG_REGEX = re.compile(
    r'(?:https?://(?:www\.)?hanime\.tv/(?:videos/hentai|hentai/video|playlists/[0-9a-z]+/video)/)?([0-9a-z\-]+)',
    re.IGNORECASE
)

AES_KEY = bytes.fromhex("5d657a4dcb0bad1c637ff2e221059b10ff17ae39fe855003e846918941f4ebe3")
AES_HEADER = b"htv-insecure-v1"

def into_base64(o: bytes) -> str:
    """Encode bytes to base64url string without padding."""
    return urlsafe_b64encode(o).decode('ascii').rstrip('=')

def from_base64(o: Any) -> bytes:
    """Decode base64url string with flexible padding."""
    if isinstance(o, str):
        o = o.encode('ascii', errors='ignore')
    return urlsafe_b64decode(o.ljust((len(o) // 4 + 1) * 4, b'='))

def digest_token(o: Dict[str, Any]) -> str:
    """Encrypt handshake payload using AES-256-GCM."""
    if not AES or not get_random_bytes:
        raise RuntimeError("PyCryptodome is required for Hanime token encryption. Please install pycryptodomex.")
    raw = json.dumps(o, separators=(',', ':')).encode('utf-8')
    iv = get_random_bytes(12)
    cipher = AES.new(AES_KEY, AES.MODE_GCM, iv)
    cipher.update(AES_HEADER)
    ciphertext, tag = cipher.encrypt_and_digest(raw)
    return into_base64(json.dumps({
        'v': 1,
        'alg': 'AES-256-GCM',
        'iv': into_base64(iv),
        'tag': into_base64(tag),
        'data': into_base64(ciphertext)
    }, separators=(',', ':')).encode('utf-8'))

def parse_token(o: str) -> Dict[str, Any]:
    """Decrypt and verify AES-256-GCM encrypted manifest X-Token."""
    if not AES:
        raise RuntimeError("PyCryptodome is required for Hanime token decryption.")
    decoded = json.loads(from_base64(o))
    iv = from_base64(decoded['iv'])
    tag = from_base64(decoded['tag'])
    data = from_base64(decoded['data'])
    cipher = AES.new(AES_KEY, AES.MODE_GCM, iv)
    cipher.update(AES_HEADER)
    plaintext = cipher.decrypt_and_verify(data, tag)
    return json.loads(plaintext.decode('utf-8'))

def generate_credentials():
    """Generate X-Signature and X-Time credentials for handshake."""
    if not SHA256:
        import hashlib
        ts = int(time.time())
        digest = hashlib.sha256(f'{ts},Xkdi29,https://hanime.tv,mn2,{ts}'.encode('utf-8')).hexdigest()
        return digest, ts
    ts = int(time.time())
    digest = SHA256.new(f'{ts},Xkdi29,https://hanime.tv,mn2,{ts}'.encode('utf-8')).hexdigest()
    return digest, ts

def sanitize_filename(name: str) -> str:
    """Sanitize string for Windows/Linux filenames."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized[:200] if len(sanitized) > 200 else sanitized

def extract_slug(url_or_slug: str) -> Optional[str]:
    """Extract clean video slug from hanime.tv URL or raw slug."""
    clean = url_or_slug.strip().rstrip('/')
    if not clean:
        return None
    match = HANIME_SLUG_REGEX.search(clean)
    if match:
        return match.group(1).lower()
    return clean.split('/')[-1].lower()

def get_clipboard_text() -> str:
    """Retrieve UTF-16 text directly from Windows clipboard without external dependencies."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        CF_UNICODETEXT = 13
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""

def get_default_download_dir() -> str:
    """Return standard user Downloads directory."""
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

def find_aria2c() -> Optional[str]:
    """Locate aria2c executable."""
    which = shutil.which("aria2c")
    if which:
        return which
    candidates = [
        r"C:\Program Files\mpv\aria2c.exe",
        os.path.expandvars(r"%APPDATA%\mpv\aria2c.exe"),
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

def find_ffmpeg() -> Optional[str]:
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

def find_mpv() -> Optional[str]:
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
    return None

def find_ytdlp() -> str:
    """Locate yt-dlp executable."""
    which = shutil.which("yt-dlp")
    if which:
        return which
    candidates = [
        r"C:\Program Files\mpv\yt-dlp.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\yt-dlp.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "yt-dlp"

def find_cookie_file() -> Optional[str]:
    """Find local cookies.txt file if available."""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt"),
        "cookies.txt",
        "hanime_cookies.txt",
        os.path.expandvars(r"%APPDATA%\yt-dlp\cookies.txt"),
        os.path.expandvars(r"%USERPROFILE%\cookies.txt"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def select_format(formats: List[Dict[str, Any]], quality_preference: str = "best") -> Dict[str, Any]:
    """
    Select the requested quality format from available formats.
    Default 'best' selects the highest quality up to 1080p (ceiling of 1080p, avoiding 4K/2160p).
    """
    if not formats:
        raise ValueError("No formats available")

    pref = quality_preference.lower().strip() if quality_preference else "best"

    # Explicitly requested 4K / 2160p / uncapped
    if pref in ("4k", "2160", "2160p", "unlimited", "all"):
        return formats[0]

    if pref in ("worst", "min", "360", "360p"):
        return formats[-1]

    # Best quality up to 1080p (<= 1080)
    if pref in ("best", "max", "1080", "1080p", "best1080", "best1080p", "auto"):
        up_to_1080 = [f for f in formats if (f.get("height") or 0) <= 1080]
        if up_to_1080:
            return up_to_1080[0]
        return formats[-1]

    target_height = int(re.sub(r'[^\d]', '', pref)) if re.search(r'\d+', pref) else None
    if target_height:
        for f in formats:
            if f.get("height") == target_height:
                return f
        return min(formats, key=lambda f: abs((f.get("height") or 0) - target_height))

    up_to_1080 = [f for f in formats if (f.get("height") or 0) <= 1080]
    return up_to_1080[0] if up_to_1080 else formats[-1]

def fetch_hanime_manifest_direct(slug: str, cookie_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Directly perform API handshake with auth.hanime.tv to extract streams."""
    try:
        ssignature, stime = generate_credentials()
        payload = digest_token({
            'timestamp_unix': stime,
            'directive': 'htv_player_handshake',
            'slug': slug,
        })

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://hanime.tv',
            'Referer': 'https://hanime.tv/',
            'User-Agent': USER_AGENT,
            'X-Csrf-Token': 'null',
            'X-Signature': ssignature,
            'X-Time': str(stime),
            'X-Signature-Version': 'web2'
        }

        # If a cookie file exists, add cookies
        if cookie_file and os.path.isfile(cookie_file):
            cookie_items = []
            with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.strip().split('\t')
                    if len(parts) >= 7 and 'hanime' in parts[0]:
                        cookie_items.append(f"{parts[5]}={parts[6]}")
            if cookie_items:
                headers['Cookie'] = '; '.join(cookie_items)

        data = json.dumps({'token': payload}).encode('ascii')
        req = urllib.request.Request(f"{AUTH_API_URL}/api/v11/handshake", data=data, headers=headers, method='POST')

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            xtoken = resp.headers.get('X-Token')
            if xtoken:
                manifest = parse_token(xtoken)
                return manifest
    except Exception as e:
        # Handshake encountered an error (e.g. Cloudflare challenge on direct socket)
        pass
    return None

def parse_m3u8_formats(m3u8_text: str, base_url: str) -> List[Dict[str, Any]]:
    """Parse resolution streams from Master M3U8."""
    formats = []
    lines = [line.strip() for line in m3u8_text.splitlines() if line.strip()]

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            res_match = re.search(r'RESOLUTION=(\d+x\d+)', line)
            resolution = res_match.group(1) if res_match else None
            height = int(resolution.split('x')[1]) if resolution else None

            bw_match = re.search(r'BANDWIDTH=(\d+)', line)
            bandwidth = int(bw_match.group(1)) if bw_match else None

            if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                stream_url = urllib.parse.urljoin(base_url, lines[i + 1])
                quality_label = f"{height}p" if height else "unknown"
                formats.append({
                    "quality": quality_label,
                    "height": height,
                    "resolution": resolution,
                    "bandwidth": bandwidth,
                    "url": stream_url
                })

    formats.sort(key=lambda x: x.get("height") or 0, reverse=True)
    return formats

def install_ytdlp_plugin():
    """Install the native yt-dlp plugin for hanime.tv."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("[!] APPDATA environment variable not set.")
        return False

    plugin_dir = os.path.join(appdata, "yt-dlp", "plugins", "hanime", "yt_dlp_plugins", "extractor")
    os.makedirs(plugin_dir, exist_ok=True)
    dst_file = os.path.join(plugin_dir, "htv.py")

    src_candidates = [
        os.path.join(os.path.dirname(__file__), "yt_dlp_plugins", "extractor", "htv.py"),
        r"C:\Users\Abdallah_Ahmed\AppData\Local\Programs\Python\Python311\Lib\site-packages\yt_dlp_plugins\extractor\htv.py",
    ]

    for src in src_candidates:
        if os.path.isfile(src):
            shutil.copy2(src, dst_file)
            print(f"[OK] Hanime.tv native plugin installed to:\n    {dst_file}")
            return True

    print("[!] Could not locate source htv.py plugin.")
    return False

def download_video(
    slug_or_url: str,
    quality: str = "best",
    output_dir: str = ".",
    cookie_file: Optional[str] = None,
    browser_cookie: Optional[str] = None,
) -> int:
    """Download hanime video using yt-dlp with aria2c turbo acceleration and 1080p cap."""
    os.makedirs(output_dir, exist_ok=True)
    slug = extract_slug(slug_or_url)
    if not slug:
        print(f"[!] Invalid URL or slug: {slug_or_url}")
        return 1

    clean_url = f"https://hanime.tv/videos/hentai/{slug}"
    ytdlp_bin = find_ytdlp()

    # Build yt-dlp command
    # Quality format: best up to 1080p (no 4K bloat)
    if quality in ("best", "max", "1080", "1080p", "auto"):
        fmt_spec = "bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best"
    elif quality in ("4k", "2160", "2160p", "unlimited"):
        fmt_spec = "bestvideo+bestaudio/best"
    else:
        h = re.sub(r'[^\d]', '', quality)
        fmt_spec = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best" if h else "best"

    cmd = [
        ytdlp_bin,
        clean_url,
        "-P", output_dir,
        "-f", fmt_spec,
        "--windows-filenames",
        "--no-mtime"
    ]

    # Cookie configuration
    active_cookie = cookie_file or find_cookie_file()
    if active_cookie:
        cmd.extend(["--cookies", active_cookie])
    elif browser_cookie:
        cmd.extend(["--cookies-from-browser", browser_cookie])

    print(f"\n[+] Video:   {slug.replace('-', ' ').title()}")
    print(f"[+] Quality: Up to 1080p (Capped, no 4K)")
    print(f"[+] URL:     {clean_url}")
    print("[*] Starting download with 16-connection turbo acceleration...\n")

    proc = subprocess.run(cmd)

    # If Cloudflare 403 occurs and browser cookie wasn't tried, provide helpful guidance
    if proc.returncode != 0:
        print("\n[!] If Cloudflare challenge was encountered:")
        print("    1. Close Brave/Chrome for 2 seconds so cookies can be read, OR")
        print("    2. Export cookies to 'cookies.txt' in this directory.")

    return proc.returncode

def stream_in_mpv(slug_or_url: str, quality: str = "best") -> int:
    """Stream hanime video directly in MPV."""
    mpv_bin = find_mpv()
    if not mpv_bin:
        print("[!] mpv executable not found.")
        return 1

    slug = extract_slug(slug_or_url)
    clean_url = f"https://hanime.tv/videos/hentai/{slug}"
    print(f"\n[+] Streaming in MPV: {slug.replace('-', ' ').title()}")

    cmd = [
        mpv_bin,
        f"--ytdl-format=bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best",
        clean_url
    ]
    return subprocess.call(cmd)

def interactive_paste_loop(quality: str = "best", output_dir: Optional[str] = None):
    """
    Zero-command interactive mode: detects clipboard links automatically
    and accepts pasted links in a continuous loop.
    """
    save_dir = output_dir if output_dir and output_dir != "." else get_default_download_dir()
    os.makedirs(save_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("  [>] Hanime.tv Zero-Command Turbo Downloader")
    print(f"  [+] Save folder: {save_dir}")
    print("  [*] Quality: Best up to 1080p (Capped, no 4K)")
    print("  [*] Turbo Speed: 16-Connection aria2c Multi-Stream Engine")
    print("=" * 70 + "\n")

    while True:
        clipboard = get_clipboard_text().strip()
        has_clip_url = "hanime.tv" in clipboard

        if has_clip_url:
            print(f"[+] Link detected in clipboard:\n    -> {clipboard}")
            prompt = "[?] Press [ENTER] to download this link, or paste another link (or 'q' to quit): "
        else:
            prompt = "[?] Paste hanime link here and press [ENTER] (or 'q' to quit): "

        try:
            user_input = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[+] Exiting. Happy watching!")
            break

        if user_input.lower() in ("q", "quit", "exit"):
            print("[+] Exiting. Happy watching!")
            break

        target = None
        if not user_input and has_clip_url:
            target = clipboard
        elif "hanime.tv" in user_input or (user_input and not user_input.startswith("http")):
            target = user_input
        elif user_input:
            print(f"[!] '{user_input}' is not a valid hanime.tv link. Please try again.\n")
            continue
        else:
            print("[!] No link entered and clipboard has no Hanime link.\n")
            continue

        try:
            rc = download_video(target, quality=quality, output_dir=save_dir)
            if rc == 0:
                print(f"\n[OK] Download finished successfully! Saved to:\n    {save_dir}")
            else:
                print(f"\n[!] Download completed with status {rc}")
        except Exception as e:
            print(f"[!] Error: {e}", file=sys.stderr)

        print("\n" + "-" * 70)
        print("Ready for next link!")

def watch_clipboard_loop(quality: str = "best", output_dir: Optional[str] = None):
    """
    Background clipboard watcher: automatically downloads any copied Hanime link.
    """
    save_dir = output_dir if output_dir and output_dir != "." else get_default_download_dir()
    os.makedirs(save_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("  [>] Hanime.tv Clipboard Watcher Active")
    print(f"  [+] Save folder: {save_dir}")
    print("  [*] Just copy ('Ctrl+C') any video link in your browser!")
    print("  Press Ctrl+C in this terminal to stop.")
    print("=" * 70 + "\n")

    seen_urls = set()
    last_clip = ""

    while True:
        try:
            time.sleep(0.8)
            clip = get_clipboard_text().strip()
            if clip and clip != last_clip:
                last_clip = clip
                if "hanime.tv" in clip and clip not in seen_urls:
                    seen_urls.add(clip)
                    print(f"\n[+] New link copied to clipboard!\n    -> {clip}")
                    download_video(clip, quality=quality, output_dir=save_dir)
                    print(f"\n[OK] Download finished! Waiting for next copied link...")
        except KeyboardInterrupt:
            print("\n[+] Clipboard watcher stopped.")
            break
        except Exception as e:
            print(f"[!] Error in watcher: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Turbo high-speed downloader and player for hanime.tv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Zero-Command Usage:
  # Just run with no arguments to enter Interactive Paste Mode (or double-click Download-Hanime.cmd):
  python tools/hanime_downloader.py

  # Automatic Clipboard Watcher (downloads as soon as you copy any link in browser):
  python tools/hanime_downloader.py --watch
        """
    )
    parser.add_argument("urls", nargs="*", help="URL(s) or video slug(s) to download")
    parser.add_argument("-q", "--quality", default="best", help="Quality (1080p, 720p, 480p, best). Default: best (caps at 1080p)")
    parser.add_argument("-o", "--output", default=None, help="Output directory (default: ~/Downloads)")
    parser.add_argument("--watch", action="store_true", help="Watch clipboard in real-time and auto-download copied links")
    parser.add_argument("--play", "--stream", action="store_true", help="Stream directly in MPV without saving")
    parser.add_argument("--cookies", default=None, help="Path to cookies.txt file")
    parser.add_argument("--cookies-from-browser", dest="browser_cookie", default=None, help="Browser to extract cookies from (e.g. brave, chrome)")
    parser.add_argument("--install-plugin", action="store_true", help="Install native yt-dlp plugin to APPDATA")

    args = parser.parse_args()

    if args.install_plugin:
        install_ytdlp_plugin()
        if not args.urls and not args.watch:
            return 0

    if args.watch:
        watch_clipboard_loop(quality=args.quality, output_dir=args.output)
        return 0

    if not args.urls:
        interactive_paste_loop(quality=args.quality, output_dir=args.output)
        return 0

    save_dir = args.output if args.output and args.output != "." else get_default_download_dir()

    for item in args.urls:
        if args.play:
            stream_in_mpv(item, quality=args.quality)
        else:
            download_video(item, quality=args.quality, output_dir=save_dir, cookie_file=args.cookies, browser_cookie=args.browser_cookie)

    return 0

if __name__ == "__main__":
    sys.exit(main())
