#!/usr/bin/env python3
"""
tube.perverzija downloader & stream extractor.

Supports:
- Direct video downloading with multi-threaded fragment acceleration (yt-dlp / aria2c)
- Quality selection (1080p, 720p, 480p, best)
- Direct streaming in MPV with proper referrer headers
- Metadata extraction (title, studio, stars, tags, poster)
- Batch downloading from URL lists or text files
- Auto-installation of yt-dlp native plugin for system-wide support
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
from typing import Dict, List, Optional, Any

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def sanitize_filename(name: str) -> str:
    """Sanitize string for Windows/Linux filenames."""
    # Replace illegal filesystem characters: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized[:200] if len(sanitized) > 200 else sanitized

def create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

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
                return ctypes.c_wchar_p(ptr).value or ""
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""

def get_default_download_dir() -> str:
    """Return the user's Downloads directory, fallback to current directory."""
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        return downloads
    return os.getcwd()

def fetch_url(url: str, referer: Optional[str] = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=create_ssl_context(), timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def find_ytdlp() -> str:
    which = shutil.which("yt-dlp")
    if which:
        return which

    candidates = [
        r"C:\Program Files\mpv\yt-dlp.exe",
        os.path.expandvars(r"%APPDATA%\mpv\yt-dlp.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\yt-dlp.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "yt-dlp"

def find_mpv() -> Optional[str]:
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

def find_aria2c() -> Optional[str]:
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
    return None

def find_ffmpeg() -> Optional[str]:
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

def download_with_aria2c(
    info: Dict[str, Any],
    selected_format: Dict[str, Any],
    output_filepath: str,
    connections: int = 24,
) -> bool:
    """
    High-performance native HLS fragment downloader using aria2c C++ multi-connection socket pool.
    Saturates 100% of available bandwidth by pulling fragments in parallel with persistent sockets,
    then instantly muxes into MP4 container with zero re-encoding via ffmpeg.
    """
    aria2c_bin = find_aria2c()
    ffmpeg_bin = find_ffmpeg()
    if not aria2c_bin or not os.path.isfile(aria2c_bin):
        return False
    if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
        return False

    sub_m3u8 = fetch_url(selected_format["url"], referer=info.get("player_url"))
    fragments = []
    for line in sub_m3u8.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            frag_url = urllib.parse.urljoin(selected_format["url"], line)
            fragments.append(frag_url)

    if not fragments:
        return False

    temp_dir = os.path.join(os.path.dirname(os.path.abspath(output_filepath)), f".turbo_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)
    input_file = os.path.join(temp_dir, "aria2_chunks.txt")
    headers = info["stream_headers"]

    print(f"\n[+] SPEEDSTORM TURBO ENGINE: aria2c C++ Multi-Connection ({connections} parallel streams)")
    print(f"[+] Total video fragments: {len(fragments)}")
    print(f"[+] Destination: {output_filepath}")

    try:
        with open(input_file, "w", encoding="utf-8") as f:
            for idx, f_url in enumerate(fragments):
                f.write(f"{f_url}\n")
                f.write(f"  out={idx:06d}.ts\n")
                f.write(f"  header=Referer: {headers['Referer']}\n")
                f.write(f"  header=Origin: {headers['Origin']}\n")
                f.write(f"  header=User-Agent: {headers['User-Agent']}\n")

        cmd = [
            aria2c_bin,
            "-i", input_file,
            "--dir", temp_dir,
            "-j", str(connections),
            "-x", "16",
            "-s", "16",
            "--check-certificate=false",
            "--min-split-size=1M",
            "--file-allocation=none",
            "--auto-file-renaming=false",
            "--allow-overwrite=true",
            "--summary-interval=1",
            "--download-result=hide",
            "--console-log-level=warn",
        ]

        print("[+] Saturating line bandwidth...\n")
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(f"[!] aria2c returned exit code {proc.returncode}")
            return False

        ts_files = sorted([f for f in os.listdir(temp_dir) if f.endswith(".ts")])
        if len(ts_files) < len(fragments) * 0.95:
            print("[!] Incomplete chunk download, falling back to yt-dlp")
            return False

        concat_list = os.path.join(temp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for ts in ts_files:
                f.write(f"file '{os.path.abspath(os.path.join(temp_dir, ts))}'\n")

        print(f"\n[+] Muxing {len(ts_files)} video fragments into pristine MP4 container...")
        ff_cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            "-movflags", "+faststart",
            output_filepath
        ]
        ff_proc = subprocess.run(ff_cmd, capture_output=True, text=True)
        if ff_proc.returncode != 0:
            print(f"[!] ffmpeg muxing error: {ff_proc.stderr}")
            return False

        print(f"[OK] Successfully downloaded and muxed to:\n    {output_filepath}")
        return True
    except Exception as e:
        print(f"[!] Turbo engine encountered error: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def parse_video_page(page_url: str) -> Dict[str, Any]:
    """
    Extract metadata, player iframe, and stream information from a tube.perverzija.com page.
    """
    html = fetch_url(page_url, referer="https://tube.perverzija.com/")

    # 1. Title
    title_match = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if not title_match:
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    raw_title = title_match.group(1).strip() if title_match else "Perverzija Video"
    # Clean HTML tags and site suffixes
    title = re.sub(r'<[^>]+>', '', raw_title)
    title = re.sub(r'&#8211;', '-', title)
    title = re.sub(r'&#8217;', "'", title)
    title = re.sub(r'&amp;', '&', title)
    if title.lower().startswith("watch "):
        title = title[6:].strip()
    for suffix in [" | Perverzija.com", " - Perverzija", " | Perverzija"]:
        if title.endswith(suffix):
            title = title[:-len(suffix)].strip()

    # 2. Taxonomy / Metadata from item-tax-list
    tax_match = re.search(r'<div[^>]*class=["\'][^"\']*item-tax-list[^"\']*["\'][^>]*>(.*?)</div>\s*</div>', html, re.DOTALL | re.IGNORECASE)
    tax_section = tax_match.group(1) if tax_match else html

    studio_match = re.search(r'<strong>\s*Studio:\s*</strong>.*?href=["\'][^"\']*/studio/([^/\'"]+)/?["\'][^>]*>([^<]+)<', tax_section, re.DOTALL | re.IGNORECASE)
    studio = studio_match.group(2).strip() if studio_match else None

    stars_section = re.search(r'<strong>\s*Stars:\s*</strong>(.*?)(?:</div>|$)', tax_section, re.DOTALL | re.IGNORECASE)
    stars = re.findall(r'href=["\'][^"\']*/stars/[^/\'"]+/?["\'][^>]*>([^<]+)<', stars_section.group(1) if stars_section else "")

    tags_section = re.search(r'<strong>\s*Tags:\s*</strong>(.*?)(?:</div>|$)', tax_section, re.DOTALL | re.IGNORECASE)
    tags = re.findall(r'href=["\'][^"\']*/tag/[^/\'"]+/?["\'][^>]*>([^<]+)<', tags_section.group(1) if tags_section else "")


    # Poster / Thumbnail
    og_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    poster = og_img.group(1) if og_img else None

    # Description
    og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    description = og_desc.group(1) if og_desc else None

    # 3. Iframe Player Extraction
    iframe_match = re.search(
        r'<iframe[^>]+src=["\'](https?://[^"\']+/player/index\.php\?data=[^"\']+)["\']',
        html, re.IGNORECASE
    )
    iframe_src = iframe_match.group(1) if iframe_match else None

    if not iframe_src:
        # Fallback to data attributes
        data_id_match = re.search(r'data-folderid=["\']([^"\']+)["\']', html)
        host_match = re.search(r'data-xtremestream=["\']([^"\']+)["\']', html)
        if data_id_match and host_match:
            iframe_src = f"https://{host_match.group(1)}.xtremestream.xyz/player/index.php?data={data_id_match.group(1)}"

    if not iframe_src:
        raise ValueError(f"Could not locate xtremestream player on page: {page_url}")

    parsed_iframe = urllib.parse.urlparse(iframe_src)
    qs = urllib.parse.parse_qs(parsed_iframe.query)
    data_id = qs.get("data", [None])[0]
    if not data_id:
        raise ValueError(f"Could not extract video data ID from player URL: {iframe_src}")

    player_base = f"{parsed_iframe.scheme}://{parsed_iframe.netloc}"
    master_m3u8_url = f"{player_base}/player/xs1.php?data={data_id}"

    # 4. Fetch Master M3U8 Playlist
    m3u8_text = fetch_url(master_m3u8_url, referer=iframe_src)
    formats = parse_m3u8_formats(m3u8_text, master_m3u8_url)

    return {
        "page_url": page_url,
        "title": title,
        "studio": studio,
        "stars": list(dict.fromkeys(stars)),
        "tags": list(dict.fromkeys(tags)),
        "poster": poster,
        "description": description,
        "player_url": iframe_src,
        "player_origin": player_base,
        "master_m3u8": master_m3u8_url,
        "formats": formats,
        "stream_headers": {
            "User-Agent": USER_AGENT,
            "Referer": iframe_src,
            "Origin": player_base,
        }
    }

def parse_m3u8_formats(m3u8_text: str, base_url: str) -> List[Dict[str, Any]]:
    """Parse resolution streams from Master M3U8."""
    formats = []
    lines = [line.strip() for line in m3u8_text.splitlines() if line.strip()]

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            # Extract resolution
            res_match = re.search(r'RESOLUTION=(\d+x\d+)', line)
            resolution = res_match.group(1) if res_match else None
            height = int(resolution.split('x')[1]) if resolution else None

            # Extract bandwidth
            bw_match = re.search(r'BANDWIDTH=(\d+)', line)
            bandwidth = int(bw_match.group(1)) if bw_match else None

            # Next line is stream URL
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

    # Sort formats from highest to lowest quality
    formats.sort(key=lambda x: x.get("height") or 0, reverse=True)
    return formats

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

    if pref in ("worst", "min"):
        return formats[-1]

    # Best quality up to 1080p (<= 1080)
    if pref in ("best", "max", "1080", "1080p", "best1080", "best1080p", "auto"):
        up_to_1080 = [f for f in formats if (f.get("height") or 0) <= 1080]
        if up_to_1080:
            return up_to_1080[0]
        # If all streams are above 1080 (e.g. only 4K exists), return the lowest available above 1080
        return formats[-1]

    # Search by height (e.g. 720p, 480p)
    target_height = int(re.sub(r'[^\d]', '', pref)) if re.search(r'\d+', pref) else None
    if target_height:
        for f in formats:
            if f.get("height") == target_height:
                return f
        # Find closest height
        return min(formats, key=lambda f: abs((f.get("height") or 0) - target_height))

    # Default fallback: best up to 1080p
    up_to_1080 = [f for f in formats if (f.get("height") or 0) <= 1080]
    return up_to_1080[0] if up_to_1080 else formats[-1]

def install_ytdlp_plugin():
    """Install the yt-dlp plugin to %APPDATA%/yt-dlp/plugins so yt-dlp supports tube.perverzija natively."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("[!] APPDATA environment variable not set. Cannot auto-install plugin.")
        return False

    plugin_dir = os.path.join(appdata, "yt-dlp", "plugins", "perverzija", "yt_dlp_plugins", "extractor")
    os.makedirs(plugin_dir, exist_ok=True)
    dst_file = os.path.join(plugin_dir, "perverzija.py")

    src_file = os.path.join(os.path.dirname(__file__), "yt_dlp_plugins", "extractor", "perverzija.py")
    if not os.path.isfile(src_file):
        print(f"[!] Extractor source not found at {src_file}")
        return False

    shutil.copyfile(src_file, dst_file)
    print(f"[+] Successfully installed yt-dlp plugin to:\n    {dst_file}")
    print("[+] Now you can download directly with: yt-dlp \"https://tube.perverzija.com/...\"")
    return True

def probe_connection_speed(info: Dict[str, Any], selected_format: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rapidly probe CDN latency and line speed to adaptively calibrate parallel fragment streams.
    Ensures maximum IDM-like throughput without overloading slower connections.
    """
    try:
        sub_url = selected_format["url"]
        sub_m3u8 = fetch_url(sub_url, referer=info.get("player_url"))
        first_chunk_url = None
        for line in sub_m3u8.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                first_chunk_url = urllib.parse.urljoin(sub_url, line)
                break

        if not first_chunk_url:
            return {
                "concurrency": 16,
                "buffersize": "64K",
                "http_chunk_size": "10M",
                "tier_name": "Standard High-Speed (16 connections)",
                "speed_mbps": None,
                "latency_ms": None,
            }

        headers = info["stream_headers"].copy()
        headers["Range"] = "bytes=0-262143"  # Read 256KB sample
        req = urllib.request.Request(first_chunk_url, headers=headers)
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, context=create_ssl_context(), timeout=6) as resp:
            t_connect = time.perf_counter()
            chunk_data = resp.read(256 * 1024)
            t_done = time.perf_counter()

        latency_ms = (t_connect - t0) * 1000
        download_time = t_done - t_connect
        bytes_read = len(chunk_data)

        speed_mbps = (bytes_read * 8) / (download_time * 1_000_000) if download_time > 0 and bytes_read > 20000 else None

        # Adaptive profile selection
        if speed_mbps is not None:
            if speed_mbps >= 40 or (speed_mbps >= 25 and latency_ms > 150):
                concurrency = 32
                tier_name = f"Ultra-Fast Gigabit ({speed_mbps:.1f} Mbps | 32 parallel connections)"
                buffersize = "128K"
                http_chunk = "15M"
            elif speed_mbps >= 15 or (speed_mbps >= 8 and latency_ms > 100):
                concurrency = 20
                tier_name = f"High-Speed Fiber/Cable ({speed_mbps:.1f} Mbps | 20 parallel connections)"
                buffersize = "64K"
                http_chunk = "10M"
            elif speed_mbps >= 6:
                concurrency = 12
                tier_name = f"Standard Broadband ({speed_mbps:.1f} Mbps | 12 parallel connections)"
                buffersize = "32K"
                http_chunk = "5M"
            else:
                concurrency = 6
                tier_name = f"Light Connection ({speed_mbps:.1f} Mbps | 6 parallel connections)"
                buffersize = "16K"
                http_chunk = "2M"
        else:
            concurrency = 16
            tier_name = "Adaptive Default (16 parallel connections)"
            buffersize = "64K"
            http_chunk = "10M"

        return {
            "concurrency": concurrency,
            "buffersize": buffersize,
            "http_chunk_size": http_chunk,
            "tier_name": tier_name,
            "speed_mbps": speed_mbps,
            "latency_ms": round(latency_ms, 1),
        }
    except Exception:
        return {
            "concurrency": 16,
            "buffersize": "64K",
            "http_chunk_size": "10M",
            "tier_name": "High-Speed Fallback (16 connections)",
            "speed_mbps": None,
            "latency_ms": None,
        }

def download_video(
    info: Dict[str, Any],
    quality: str = "best",
    output_dir: str = ".",
    use_aria2c: bool = True,
    concurrent_fragments: Optional[int] = None,
    turbo: bool = False,
    engine: str = "auto",
) -> int:
    """Download video with maximum speed using aria2c Turbo Engine or yt-dlp fallback."""
    selected = select_format(info["formats"], quality)
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{sanitize_filename(info['title'])} [{selected.get('resolution', selected['quality'])}].mp4"
    target_filepath = os.path.join(output_dir, filename)

    # Determine concurrency
    if turbo:
        concurrency = 32
    elif concurrent_fragments is not None:
        concurrency = concurrent_fragments
    else:
        concurrency = 24

    # Try high-speed aria2c turbo engine first
    if engine in ("auto", "aria2c") and use_aria2c and find_aria2c() and find_ffmpeg():
        success = download_with_aria2c(info, selected, target_filepath, connections=concurrency)
        if success:
            return 0
        print("[!] Falling back to yt-dlp native fragment downloader...")

    # Fallback to yt-dlp
    ytdlp_path = find_ytdlp()
    buffersize = "128K" if concurrency >= 24 else "64K"
    http_chunk_size = "15M" if concurrency >= 24 else "10M"

    print(f"\n[+] Video:   {info['title']}")
    print(f"[+] Quality: {selected['quality']} ({selected.get('resolution')})")
    print(f"[+] Engine:  yt-dlp ({concurrency} parallel streams)")

    filename_template = os.path.join(output_dir, "%(title)s [%(resolution)s].%(ext)s")
    headers = info["stream_headers"]
    cmd = [
        ytdlp_path,
        "--add-header", f"Referer: {headers['Referer']}",
        "--add-header", f"Origin: {headers['Origin']}",
        "--add-header", f"User-Agent: {headers['User-Agent']}",
        "--output", filename_template,
        "--concurrent-fragments", str(concurrency),
        "--buffersize", buffersize,
        "--http-chunk-size", http_chunk_size,
        "--retries", "10",
        "--fragment-retries", "10",
        "--no-mtime",
        selected["url"]
    ]

    print(f"[+] Starting yt-dlp download process...\n")
    proc = subprocess.run(cmd)
    return proc.returncode

def stream_in_mpv(info: Dict[str, Any], quality: str = "best"):
    """Launch MPV to stream the video immediately with necessary HTTP headers."""
    mpv_path = find_mpv()
    if not mpv_path:
        print("[!] mpv executable not found. Please install mpv or add it to PATH.")
        return 1

    selected = select_format(info["formats"], quality)
    headers = info["stream_headers"]
    print(f"[+] Streaming in MPV: {info['title']} [{selected['quality']}]")

    header_field = f"Referer: {headers['Referer']},Origin: {headers['Origin']},User-Agent: {headers['User-Agent']}"
    cmd = [
        mpv_path,
        f"--http-header-fields={header_field}",
        f"--force-media-title={info['title']}",
        selected["url"]
    ]
    return subprocess.call(cmd)

def interactive_paste_loop(quality: str = "best", output_dir: Optional[str] = None, use_aria2c: bool = True):
    """
    Zero-command interactive mode: detects clipboard links automatically
    and accepts pasted links in a continuous loop.
    """
    save_dir = output_dir if output_dir and output_dir != "." else get_default_download_dir()
    os.makedirs(save_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("  [>] Tube.Perverzija Zero-Command Turbo Downloader")
    print(f"  [+] Save folder: {save_dir}")
    print("  [*] Turbo Speed: C++ aria2c multi-connection acceleration")
    print("=" * 70 + "\n")

    while True:
        clipboard = get_clipboard_text().strip()
        has_clip_url = "tube.perverzija.com" in clipboard

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
        elif "tube.perverzija.com" in user_input:
            target_url = user_input
        elif user_input:
            print(f"[!] '{user_input}' is not a valid tube.perverzija.com link. Please try again.\n")
            continue
        else:
            print("[!] No link entered and clipboard has no Perverzija link.\n")
            continue

        try:
            print(f"\n[*] Processing: {target_url}")
            info = parse_video_page(target_url)
            rc = download_video(
                info,
                quality=quality,
                output_dir=save_dir,
                use_aria2c=use_aria2c,
                concurrent_fragments=None
            )
            if rc == 0:
                print(f"\n[OK] Download finished successfully! Saved to:\n    {save_dir}")
            else:
                print(f"\n[!] Download completed with status {rc}")
        except Exception as e:
            print(f"[!] Error: {e}", file=sys.stderr)

        print("\n" + "-" * 70)
        print("Ready for next link!")

def watch_clipboard_loop(quality: str = "best", output_dir: Optional[str] = None, use_aria2c: bool = True):
    """
    Background clipboard watcher: automatically downloads any copied Perverzija link.
    """
    save_dir = output_dir if output_dir and output_dir != "." else get_default_download_dir()
    os.makedirs(save_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("  [>] Tube.Perverzija Clipboard Watcher Active")
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
                if "tube.perverzija.com" in clip and clip not in seen_urls:
                    seen_urls.add(clip)
                    print(f"\n[+] New link copied to clipboard!\n    -> {clip}")
                    info = parse_video_page(clip)
                    download_video(
                        info,
                        quality=quality,
                        output_dir=save_dir,
                        use_aria2c=use_aria2c,
                        concurrent_fragments=None
                    )
                    print(f"\n[OK] Download finished! Waiting for next copied link...")
        except KeyboardInterrupt:
            print("\n[+] Clipboard watcher stopped.")
            break
        except Exception as e:
            print(f"[!] Error in watcher: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Adaptive high-speed downloader and player for tube.perverzija.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Zero-Command Usage:
  # Just run with no arguments to enter Interactive Paste Mode (or double-click Download-Perverzija.cmd):
  python tools/perverzija_downloader.py

  # Automatic Clipboard Watcher (downloads as soon as you copy any link in browser):
  python tools/perverzija_downloader.py --watch

Command-Line Usage:
  # Download with auto-adaptive speed calibration:
  python tools/perverzija_downloader.py "https://tube.perverzija.com/some-video/"

  # Download with 32 turbo connections for maximum line speed:
  python tools/perverzija_downloader.py "https://tube.perverzija.com/some-video/" --idm

  # Stream video directly in MPV without downloading:
  python tools/perverzija_downloader.py "https://tube.perverzija.com/some-video/" --play
        """
    )
    parser.add_argument("urls", nargs="*", help="URL(s) or file containing URLs")
    parser.add_argument("-q", "--quality", default="best", help="Quality (1080p, 720p, 480p, best, worst). Default: best")
    parser.add_argument("-o", "--output", default=".", help="Output directory. Default: current directory (or ~/Downloads in paste mode)")
    parser.add_argument("-N", "--concurrent-fragments", "--threads", "--connections", dest="concurrent_fragments", type=int, default=None, help="Force specific number of concurrent connections (default: 24 for aria2c / adaptive)")
    parser.add_argument("--idm", "--turbo", action="store_true", help="Force Turbo mode: 32 parallel connections")
    parser.add_argument("--watch", action="store_true", help="Watch clipboard in real-time and auto-download any copied video links")
    parser.add_argument("--aria2c", dest="use_aria2c", action="store_true", default=True, help="Accelerate with aria2c multi-connection (default: enabled)")
    parser.add_argument("--no-aria2c", dest="use_aria2c", action="store_false", help="Disable aria2c and use yt-dlp only")
    parser.add_argument("--engine", choices=["auto", "aria2c", "ytdlp"], default="auto", help="Engine preference (default: auto)")
    parser.add_argument("--play", "--stream", action="store_true", help="Stream directly in MPV instead of downloading")
    parser.add_argument("--info", action="store_true", help="Print video information and available formats without downloading")
    parser.add_argument("--get-url", action="store_true", help="Print direct M3U8 stream URL and exit")
    parser.add_argument("--json", action="store_true", help="Print full metadata as JSON")
    parser.add_argument("--install-plugin", action="store_true", help="Install yt-dlp plugin to APPDATA for native CLI support")

    args = parser.parse_args()

    # Ensure both args.aria2c and args.use_aria2c are available interchangeably
    if not hasattr(args, "aria2c"):
        setattr(args, "aria2c", getattr(args, "use_aria2c", True))
    if not hasattr(args, "use_aria2c"):
        setattr(args, "use_aria2c", getattr(args, "aria2c", True))

    if args.install_plugin:
        install_ytdlp_plugin()
        if not args.urls and not args.watch:
            return 0

    if args.watch:
        watch_clipboard_loop(quality=args.quality, output_dir=args.output, use_aria2c=args.use_aria2c)
        return 0

    # If no URLs are provided, launch the zero-command interactive paste session
    if not args.urls:
        interactive_paste_loop(quality=args.quality, output_dir=args.output, use_aria2c=args.use_aria2c)
        return 0

    # Collect URLs
    targets = []
    for item in args.urls:
        if os.path.isfile(item):
            with open(item, "r", encoding="utf-8") as f:
                for line in f:
                    u = line.strip()
                    if u and not u.startswith("#") and "tube.perverzija.com" in u:
                        targets.append(u)
        elif "tube.perverzija.com" in item:
            targets.append(item)
        else:
            print(f"[!] Ignoring unrecognized argument/URL: {item}")

    if not targets:
        print("[!] No valid tube.perverzija.com URLs specified.")
        return 1

    for url in targets:
        try:
            print(f"[*] Resolving: {url}")
            info = parse_video_page(url)

            if args.json:
                print(json.dumps(info, indent=2))
                continue

            if args.get_url:
                selected = select_format(info["formats"], args.quality)
                print(selected["url"])
                continue

            if args.info:
                print("\n" + "=" * 60)
                print(f"Title:    {info['title']}")
                if info.get("studio"):
                    print(f"Studio:   {info['studio']}")
                if info.get("stars"):
                    print(f"Stars:    {', '.join(info['stars'])}")
                if info.get("tags"):
                    print(f"Tags:     {', '.join(info['tags'])}")
                if info.get("poster"):
                    print(f"Poster:   {info['poster']}")
                print(f"Player:   {info['player_url']}")
                print("\nAvailable Formats:")
                for f in info["formats"]:
                    print(f"  - {f['quality']}: {f.get('resolution')} (Bandwidth: {f.get('bandwidth')})")
                print("=" * 60 + "\n")
                continue

            if args.play:
                stream_in_mpv(info, quality=args.quality)
                continue

            # Default: download
            download_video(
                info,
                quality=args.quality,
                output_dir=args.output,
                use_aria2c=args.use_aria2c,
                concurrent_fragments=args.concurrent_fragments,
                turbo=args.idm,
                engine=args.engine
            )

        except Exception as e:
            print(f"[!] Error processing {url}: {e}", file=sys.stderr)

    return 0

if __name__ == "__main__":
    sys.exit(main())
