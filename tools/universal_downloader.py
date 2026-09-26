#!/usr/bin/env python3
"""
Universal Zero-Command Video Downloader & Clipboard Watcher.
Downloads from ANY site supported by yt-dlp with:
- 16-connection aria2c turbo acceleration (bypassing server throttles)
- 1080p quality ceiling (no 4K bloat)
- Auto-detects clipboard links with zero typing required.
"""

import os
import sys
import re
import time
import shutil
import pathlib
import argparse
import subprocess

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

def is_valid_url(text: str) -> bool:
    """Check if text looks like an http/https URL."""
    return bool(re.match(r'^https?://[^\s/$.?#].[^\s]*$', text.strip(), re.IGNORECASE))

def download_url(url: str, output_dir: str) -> int:
    """Download video using yt-dlp."""
    print(f"\n[*] Starting Turbo Download for:\n    -> {url}")
    print(f"[*] Target Directory: {output_dir}\n")

    cmd = ["yt-dlp", "-P", output_dir, url]
    proc = subprocess.run(cmd)
    return proc.returncode

def interactive_paste_loop(output_dir: str):
    """Zero-command interactive paste mode."""
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("  [>] Universal High-Speed Video Downloader (16x aria2c Turbo)")
    print(f"  [+] Save folder: {output_dir}")
    print("  [*] Resolution: Best quality up to 1080p (Capped, no 4K)")
    print("=" * 70 + "\n")

    while True:
        clipboard = get_clipboard_text().strip()
        has_clip_url = is_valid_url(clipboard)

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
        elif is_valid_url(user_input):
            target_url = user_input
        elif user_input:
            print(f"[!] '{user_input}' does not look like a valid link. Please try again.\n")
            continue
        else:
            print("[!] No link entered and clipboard has no valid URL.\n")
            continue

        rc = download_url(target_url, output_dir)
        if rc == 0:
            print(f"\n[OK] Download finished successfully! Saved to:\n    {output_dir}")
        else:
            print(f"\n[!] Download finished with status code {rc}")

        print("\n" + "-" * 70)
        print("Ready for next link!")

def watch_clipboard_loop(output_dir: str):
    """Hands-free clipboard watcher: auto-downloads when a URL is copied."""
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("  [>] Universal Clipboard Watcher Active (16x aria2c Turbo)")
    print(f"  [+] Save folder: {output_dir}")
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
                if is_valid_url(clip) and clip not in seen_urls:
                    seen_urls.add(clip)
                    print(f"\n[+] New link copied to clipboard!\n    -> {clip}")
                    rc = download_url(clip, output_dir)
                    if rc == 0:
                        print(f"\n[OK] Download complete! Waiting for next copied link...")
                    else:
                        print(f"\n[!] Download completed with code {rc}")
        except KeyboardInterrupt:
            print("\n[+] Clipboard watcher stopped.")
            break
        except Exception as e:
            print(f"[!] Watcher error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Universal High-Speed Video Downloader")
    parser.add_argument("urls", nargs="*", help="Optional URL(s) to download directly")
    parser.add_argument("-o", "--output", default=None, help="Output directory (default: ~/Downloads)")
    parser.add_argument("--watch", action="store_true", help="Watch clipboard in real-time and auto-download copied links")
    args = parser.parse_args()

    save_dir = args.output if args.output and args.output != "." else get_default_download_dir()

    if args.watch:
        watch_clipboard_loop(save_dir)
        return 0

    if not args.urls:
        interactive_paste_loop(save_dir)
        return 0

    for u in args.urls:
        if is_valid_url(u):
            download_url(u, save_dir)
        else:
            print(f"[!] Invalid URL: {u}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
