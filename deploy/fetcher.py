"""
fetcher.py — Download scripts and shaders from their upstream sources.

Supports three fetch strategies:
  1. github_raw    → single files via raw.githubusercontent.com
  2. github_release → zip assets from GitHub Releases
  3. github_clone   → shallow git clone (fallback)

All network operations use urllib (stdlib) — zero external dependencies.
"""

import io
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

from deploy import ui

# ─── Constants ─────────────────────────────────────────────────────────

GITHUB_RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
GITHUB_API = "https://api.github.com/repos/{repo}/releases"
USER_AGENT = "mpv-auto-deploy/1.0"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds, doubles each retry
ZIP_UNIX_MODE_SHIFT = 16
ZIP_UNIX_MODE_MASK = 0o7777


# ─── HTTP Helpers ──────────────────────────────────────────────────────

def _request(url, binary=False):
    """Perform an HTTP GET with retries and exponential backoff."""
    headers = {"User-Agent": USER_AGENT}
    delay = RETRY_DELAY

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                return data if binary else data.decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise FileNotFoundError(f"404 Not Found: {url}")
            if e.code == 403:  # rate limit
                ui.warn(f"Rate limited (attempt {attempt}/{MAX_RETRIES}), waiting {delay}s...")
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES:
                ui.warn(f"Network error (attempt {attempt}/{MAX_RETRIES}): {e}, retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise ConnectionError(f"Failed after {MAX_RETRIES} attempts: {url}") from e
    raise ConnectionError(f"Failed after {MAX_RETRIES} attempts: {url}")


def _ensure_dir(path):
    """Create directory and all parents if they don't exist."""
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _apply_zip_permissions(zip_info, dest_path):
    """Restore Unix permission bits from zip metadata when available."""
    if os.name == "nt":
        return
    # Per zip spec, Unix mode is stored in high 16 bits of external_attr.
    mode = (zip_info.external_attr >> ZIP_UNIX_MODE_SHIFT) & ZIP_UNIX_MODE_MASK
    if mode:
        try:
            os.chmod(dest_path, mode)
        except OSError as e:
            ui.warn(f"Could not restore permissions on {dest_path}: {e}")


# ─── Fetch: Raw Files ─────────────────────────────────────────────────

def fetch_raw(script_entry, staging_dir):
    """
    Download individual files from a GitHub repo's default branch.
    Returns metadata dict or raises on failure.
    """
    source = script_entry["source"]
    repo = source["repo"]
    branch = source.get("branch", "master")
    files = source["files"]
    name = script_entry["name"]

    ui.step(f"Fetching {name} from {repo}...")

    fetched = []
    for f in files:
        url = GITHUB_RAW.format(repo=repo, branch=branch, path=f["src"])
        dest = os.path.join(staging_dir, f["dest"])
        _ensure_dir(dest)

        try:
            data = _request(url, binary=True)
            with open(dest, "wb") as fh:
                fh.write(data)
            fetched.append(f["dest"])
        except FileNotFoundError:
            raise FileNotFoundError(
                f"File not found: {f['src']} in {repo}. "
                f"The repository structure may have changed."
            )

    ui.success(f"{name}: {len(fetched)} file(s) downloaded")

    return {
        "name": name,
        "source": f"github:{repo}@{branch}",
        "files": fetched,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Fetch: GitHub Release ────────────────────────────────────────────

def fetch_release(entry, staging_dir, is_shader=False):
    """
    Download a zip asset from a GitHub Release.
    Supports version pinning and asset pattern matching.
    Returns metadata dict or raises on failure.
    """
    source = entry["source"]
    repo = source["repo"]
    pattern = source["asset_pattern"]
    pin = source.get("pin")
    name = entry["name"]

    ui.step(f"Fetching {name} release from {repo}...")

    # Get releases list
    api_url = GITHUB_API.format(repo=repo)
    if pin:
        api_url += f"/tags/{pin}"
        try:
            release = json.loads(_request(api_url))
        except FileNotFoundError:
            raise FileNotFoundError(f"Release {pin} not found for {repo}")
        releases = [release]
    else:
        data = _request(api_url)
        releases = json.loads(data)
        if not releases:
            raise FileNotFoundError(f"No releases found for {repo}")
        releases = [releases[0]]  # latest

    release = releases[0]
    tag = release.get("tag_name", "unknown")
    assets = release.get("assets", [])

    # Find matching asset
    asset_url = None
    asset_name = None
    for asset in assets:
        aname = asset["name"]
        if pattern in aname:
            asset_url = asset["browser_download_url"]
            asset_name = aname
            break

    if not asset_url:
        raise FileNotFoundError(
            f"No asset matching '{pattern}' in release {tag} of {repo}. "
            f"Available: {[a['name'] for a in assets]}"
        )

    ui.step(f"Downloading {asset_name} ({tag})...")
    zip_data = _request(asset_url, binary=True)

    # Extract
    extracted_count = 0
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        if is_shader:
            # Shader mode: extract all files with matching extensions
            dest_dir = os.path.join(staging_dir, entry.get("dest", "shaders/"))
            os.makedirs(dest_dir, exist_ok=True)
            extensions = entry.get("extensions", [".glsl"])
            for zi in zf.infolist():
                if zi.is_dir():
                    continue
                if any(zi.filename.endswith(ext) for ext in extensions):
                    basename = os.path.basename(zi.filename)
                    dest_path = os.path.join(dest_dir, basename)
                    with zf.open(zi) as src, open(dest_path, "wb") as dst:
                        dst.write(src.read())
                    _apply_zip_permissions(zi, dest_path)
                    extracted_count += 1
        else:
            # Script mode: use install.map to route files
            install_map = entry.get("install", {}).get("map", {})
            for zi in zf.infolist():
                if zi.is_dir():
                    continue
                # Check if this file matches any map entry
                for src_prefix, dest_prefix in install_map.items():
                    # Normalize: zip entries may have a root dir like "uosc/"
                    # Try both with and without the first path component
                    zpath = zi.filename
                    parts = zpath.split("/", 1)
                    zpath_stripped = parts[1] if len(parts) > 1 else zpath

                    for candidate in (zpath, zpath_stripped):
                        if candidate.startswith(src_prefix) or f"{src_prefix}" in candidate:
                            rel = candidate
                            # Map source prefix to dest prefix
                            if candidate.startswith(src_prefix):
                                rel = dest_prefix + candidate[len(src_prefix):]
                            else:
                                # Find where src_prefix starts in candidate
                                idx = candidate.find(src_prefix)
                                if idx >= 0:
                                    rel = dest_prefix + candidate[idx + len(src_prefix):]

                            dest_path = os.path.join(staging_dir, rel)
                            _ensure_dir(dest_path)
                            with zf.open(zi) as src, open(dest_path, "wb") as dst:
                                dst.write(src.read())
                            _apply_zip_permissions(zi, dest_path)
                            extracted_count += 1
                            break
                    else:
                        continue
                    break

    ui.success(f"{name}: {extracted_count} file(s) extracted from {tag}")

    return {
        "name": name,
        "version": tag,
        "source": f"github:{repo}@{tag}",
        "files_count": extracted_count,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Orchestrator ──────────────────────────────────────────────────────

def fetch_all(scripts, shaders, staging_dir):
    """
    Fetch all scripts and shaders into a staging directory.
    Returns (results, lockfile_data).
    Continues on individual failures.
    """
    results = []
    lockfile = {"fetched_at": datetime.now(timezone.utc).isoformat(), "scripts": {}}

    total = len(scripts) + 1  # +1 for shaders
    current = 0

    ui.header("Fetching Scripts & Shaders")

    # Fetch scripts
    for script in scripts:
        current += 1
        ui.progress(current, total, script["name"])

        source_type = script["source"]["type"]
        try:
            if source_type == "github_raw":
                meta = fetch_raw(script, staging_dir)
            elif source_type == "github_release":
                meta = fetch_release(script, staging_dir)
            elif source_type == "github_clone":
                # Fallback: try raw download for clone-type
                meta = fetch_raw(script, staging_dir)
            else:
                ui.warn(f"Unknown source type '{source_type}' for {script['name']}")
                results.append({"name": script["name"], "status": "failed", "detail": f"unknown source type: {source_type}"})
                continue

            results.append({"name": script["name"], "status": "ok", "detail": meta.get("version", "latest")})
            lockfile["scripts"][script["name"]] = meta

        except (FileNotFoundError, ConnectionError, zipfile.BadZipFile) as e:
            ui.error(f"{script['name']}: {e}")
            results.append({"name": script["name"], "status": "failed", "detail": str(e)})
        except Exception as e:
            ui.error(f"{script['name']}: unexpected error: {e}")
            results.append({"name": script["name"], "status": "failed", "detail": str(e)})

    # Fetch shaders
    current += 1
    ui.progress(current, total, shaders["name"])
    try:
        meta = fetch_release(shaders, staging_dir, is_shader=True)
        results.append({"name": shaders["name"], "status": "ok", "detail": meta.get("version", "")})
        lockfile["scripts"][shaders["name"]] = meta
    except Exception as e:
        ui.error(f"{shaders['name']}: {e}")
        results.append({"name": shaders["name"], "status": "failed", "detail": str(e)})

    return results, lockfile
