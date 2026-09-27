#!/usr/bin/env python3
"""
fetch_image.py — High-speed poster and thumbnail downloader with caching and referer support.
"""

import sys
import os
import hashlib
import urllib.request
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(REPO_ROOT, "cache", "posters")
os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_path(url: str) -> str:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    # Keep original extension if present
    parsed = urllib.parse.urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"
    return os.path.join(CACHE_DIR, f"{url_hash}{ext}")


def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    url = sys.argv[1].strip()
    if not url:
        sys.exit(1)

    cached = get_cache_path(url)
    if os.path.isfile(cached) and os.path.getsize(cached) > 500:
        # Cache hit
        print(cached)
        return

    # Download with appropriate headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }
    if "hentaimama" in url.lower():
        headers["Referer"] = "https://hentaimama.io/"
    elif "hanime" in url.lower():
        headers["Referer"] = "https://hanime.tv/"
    elif "muchohentai" in url.lower():
        headers["Referer"] = "https://muchohentai.com/"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) > 200:
                with open(cached, "wb") as f:
                    f.write(data)
                print(cached)
                return
    except Exception as e:
        sys.stderr.write(f"Error fetching image {url}: {e}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
