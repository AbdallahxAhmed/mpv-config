"""
Headless multi-threaded download worker for MPV.
Orchestrates yt-dlp with aria2c (16 connections) or native concurrent fragments (6 fragments),
forwards request headers/cookies, parses progress in real-time, and atomically updates a state file.
"""

import os
import sys
import re
import json
import time
import shutil
import pathlib
import argparse
import subprocess

def find_aria2c():
    """Locate aria2c executable in PATH or standard MPV / WinGet locations."""
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

    # Search WinGet package directory
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        pkg_dir = pathlib.Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if pkg_dir.exists():
            for p in pkg_dir.glob("**/aria2c.exe"):
                if p.is_file():
                    return str(p)

    return None

def find_ytdlp():
    """Locate yt-dlp executable."""
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

def parse_progress_line(line):
    """
    Parse a yt-dlp progress line.
    Returns dict with percent, percent_int, speed, and eta, or None if not a progress line.
    """
    if not line or "[download]" not in line:
        return None

    pct_match = re.search(r'\[download\]\s+([0-9.]+)%', line)
    if not pct_match:
        return None

    pct = float(pct_match.group(1))
    pct_int = int(round(pct))

    speed_match = re.search(r'at\s+([0-9.]+[kKMGT]?i?B/s)', line)
    speed = speed_match.group(1) if speed_match else None

    eta_match = re.search(r'ETA\s+([0-9:]+)', line)
    eta = eta_match.group(1) if eta_match else None

    return {
        "percent": pct,
        "percent_int": pct_int,
        "speed": speed,
        "eta": eta,
    }

def atomic_write_state(state_file, data):
    """Atomically write data to state_file using .tmp file and os.replace()."""
    if not state_file:
        return
    tmp_file = f"{state_file}.tmp"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(state_file)), exist_ok=True)
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_file, state_file)
    except Exception as e:
        sys.stderr.write(f"Warning: failed to write state file: {e}\n")

def build_ytdl_args(url, output, aria2c_path=None, ytdl_format=None, is_audio_only=False,
                    user_agent=None, referer=None, cookies=None, concurrent_fragments=6):
    """Build the command line arguments for yt-dlp."""
    ytdl_bin = find_ytdlp()
    args = [ytdl_bin, "--no-playlist", "--continue", "--no-overwrites", "--windows-filenames", "--no-mtime"]

    if is_audio_only:
        args.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    else:
        fmt = ytdl_format
        if not fmt or fmt == "" or "bestvideo" not in fmt:
            fmt = "bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best"
        args.extend(["-f", fmt, "--merge-output-format", "mp4"])

    # 16-Thread Acceleration
    # Use aria2c for single/progressive streams when available
    # HLS/DASH or fallback uses concurrent_fragments (default 6 to prevent HTTP 429)
    is_manifest = ".m3u8" in url or "manifest" in url or "/hls/" in url
    if aria2c_path and not is_audio_only and not is_manifest:
        args.extend([
            "--downloader", "aria2c",
            "--downloader-args", f"aria2c:-x 16 -s 16 -k 1M -j 16 --retry-wait=2 --max-tries=3 --max-file-not-found=3 --timeout=15"
        ])
    else:
        args.extend(["--concurrent-fragments", str(concurrent_fragments)])

    # Forward Authentication & Request Headers
    if user_agent and user_agent.strip():
        args.extend(["--user-agent", user_agent.strip()])
    if referer and referer.strip():
        args.extend(["--referer", referer.strip()])
    if cookies and cookies.strip():
        # If cookies is a file path, use --cookies; otherwise pass header
        if os.path.isfile(cookies.strip()):
            args.extend(["--cookies", cookies.strip()])
        else:
            args.extend(["--add-header", f"Cookie:{cookies.strip()}"])

    # Live Progress Output
    args.extend(["--newline", "--progress"])

    # Output Template and Target URL
    args.extend(["-o", output, url])
    return args

def run_worker(args):
    """Main worker execution loop."""
    aria2c_bin = find_aria2c()
    cmd = build_ytdl_args(
        url=args.url,
        output=args.output,
        aria2c_path=aria2c_bin,
        ytdl_format=args.format,
        is_audio_only=args.audio_only,
        user_agent=args.user_agent,
        referer=args.referer,
        cookies=args.cookies,
        concurrent_fragments=args.fragments,
    )

    state = {
        "status": "starting",
        "percent": 0.0,
        "percent_int": 0,
        "speed": None,
        "eta": None,
        "threads": 16 if aria2c_bin else args.fragments,
        "engine": "aria2c" if aria2c_bin else "native",
    }
    atomic_write_state(args.state_file, state)

    last_error = None
    last_write_time = 0.0

    # Execute yt-dlp in background
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
            startupinfo=startupinfo,
        )

        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            # Check for error lines
            if "ERROR:" in line:
                last_error = line

            # Parse progress
            prog = parse_progress_line(line)
            if prog:
                now = time.time()
                # Update at most once every 150ms to keep CPU minimal
                if now - last_write_time >= 0.15 or prog["percent"] >= 100.0:
                    last_write_time = now
                    state["status"] = "downloading"
                    state["percent"] = prog["percent"]
                    state["percent_int"] = prog["percent_int"]
                    state["speed"] = prog["speed"]
                    state["eta"] = prog["eta"]
                    atomic_write_state(args.state_file, state)

        proc.wait()
        exit_code = proc.returncode

        if exit_code == 0:
            state["status"] = "completed"
            state["percent"] = 100.0
            state["percent_int"] = 100
            state["code"] = 0
            atomic_write_state(args.state_file, state)
            return 0
        else:
            state["status"] = "error"
            state["code"] = exit_code
            state["message"] = last_error or f"yt-dlp exited with status {exit_code}"
            atomic_write_state(args.state_file, state)
            return exit_code

    except Exception as e:
        state["status"] = "error"
        state["code"] = -1
        state["message"] = str(e)
        atomic_write_state(args.state_file, state)
        return -1

def main():
    parser = argparse.ArgumentParser(description="Headless multi-threaded download worker for MPV")
    parser.add_argument("--url", required=True, help="Target stream/video URL")
    parser.add_argument("--output", required=True, help="Output filename template")
    parser.add_argument("--state-file", required=True, help="Path to write JSON progress updates")
    parser.add_argument("--format", default=None, help="yt-dlp format selector")
    parser.add_argument("--audio-only", action="store_true", help="Download audio only as MP3")
    parser.add_argument("--user-agent", default=None, help="User agent string")
    parser.add_argument("--referer", default=None, help="Referer header string")
    parser.add_argument("--cookies", default=None, help="Cookies header or cookies.txt file path")
    parser.add_argument("--fragments", type=int, default=6, help="Concurrent fragments for HLS/DASH (default: 6)")

    args = parser.parse_args()
    return run_worker(args)

if __name__ == "__main__":
    sys.exit(main())
