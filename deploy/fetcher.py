"""
fetcher.py — Download scripts and shaders from their upstream sources.

Supports three fetch strategies:
  1. github_raw    → single files via raw.githubusercontent.com
  2. github_release → zip assets from GitHub Releases
  3. github_clone   → shallow git clone (fallback)

All network operations use urllib (stdlib) — zero external dependencies.
"""

import hashlib
import io
import json
import os
import stat
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

from deploy import ui
from deploy.path_safety import relative_parts, safe_destination

# ─── Constants ───

GITHUB_RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
GITHUB_API = "https://api.github.com/repos/{repo}/releases"
USER_AGENT = "mpv-auto-deploy/1.0"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds, doubles each retry
ZIP_UNIX_MODE_SHIFT = 16
ZIP_UNIX_MODE_MASK = 0o7777
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10000


# ─── HTTP Helpers ───

def _request(url, binary=False):
    """Perform an HTTP GET with retries and exponential backoff."""
    headers = {"User-Agent": USER_AGENT}
    delay = RETRY_DELAY

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Download exceeds safety size limit")
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


def _safe_join(root, relative_path):
    return safe_destination(root, relative_path)


def _safe_zip_name(name):
    return "/".join(relative_parts(name, directory=True))


def _zip_member_is_symlink(info):
    return stat.S_ISLNK(info.external_attr >> ZIP_UNIX_MODE_SHIFT)


def _zip_mode(info):
    mode = info.external_attr >> ZIP_UNIX_MODE_SHIFT
    kind = stat.S_IFMT(mode)
    if info.create_system == 3 and kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise ValueError(f"Archive contains a link or special file: {info.filename}")
    return 0o644 | (mode & 0o111)


def _apply_zip_permissions(zip_info, dest_path):
    if os.name != "nt" and zip_info.create_system == 3:
        os.chmod(dest_path, _zip_mode(zip_info))


def _write_component(staging_dir, outputs):
    """Commit validated, fully downloaded files, cleaning partial writes on error."""
    seen = set()
    planned = []
    for relative, data, mode in outputs:
        dest = _safe_join(staging_dir, relative)
        key = "/".join(relative_parts(relative)).casefold()
        if key in seen or os.path.lexists(dest):
            raise ValueError(f"Duplicate or existing output destination: {relative}")
        seen.add(key)
        planned.append((relative, dest, data, mode))
    if not planned:
        raise FileNotFoundError("Component contained no expected output files")
    created_files, created_dirs = [], []
    try:
        for relative, dest, data, mode in planned:
            parent = os.path.abspath(staging_dir)
            for part in relative_parts(relative)[:-1]:
                parent = os.path.join(parent, part)
                if not os.path.exists(parent):
                    os.mkdir(parent)
                    created_dirs.append(parent)
            _safe_join(staging_dir, relative)
            with open(dest, "xb") as stream:
                created_files.append(dest)
                stream.write(data)
            if mode is not None and os.name != "nt":
                os.chmod(dest, mode)
    except BaseException:
        for created in reversed(created_files):
            os.unlink(created)
        for created in reversed(created_dirs):
            os.rmdir(created)
        raise
    return [relative for relative, _, _, _ in planned]


# ─── Fetch: Raw Files ───

def fetch_raw(script_entry, staging_dir):
    """Download a complete component before exposing any staged output."""
    source = script_entry["source"]
    repo = source["repo"]
    ref = source.get("pin") or source.get("branch", "master")
    name = script_entry["name"]
    files = source["files"]
    seen = set()
    for item in files:
        dest = _safe_join(staging_dir, item["dest"])
        key = "/".join(relative_parts(item["dest"])).casefold()
        if key in seen or os.path.lexists(dest):
            raise ValueError(f"Duplicate or existing destination: {item['dest']}")
        seen.add(key)
    if not files:
        raise FileNotFoundError(f"{name}: no configured files")
    ui.step(f"Fetching {name} from {repo}...")
    outputs = []
    with ui.spinner(f"Downloading {name}..."):
        for item in files:
            url = GITHUB_RAW.format(repo=repo, branch=ref, path=item["src"])
            data = _request(url, binary=True)
            if not data:
                raise ValueError(f"Empty download for {item['src']}")
            outputs.append((item["dest"], data, None))
        fetched = _write_component(staging_dir, outputs)
    ui.success(f"{name}: {len(fetched)} file(s) downloaded")
    return {
        "name": name, "source": f"github:{repo}@{ref}", "files": fetched,
        "sha256": {relative: hashlib.sha256(data).hexdigest() for relative, data, _ in outputs},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Fetch: GitHub Release ───

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

    with ui.spinner(f"Downloading {asset_name} ({tag})..."):
        zip_data = _request(asset_url, binary=True)

    # Validate every archive member and every mapped destination before writes.
    selected = []
    seen = set()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        members = zf.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS or sum(i.file_size for i in members) > MAX_EXPANDED_BYTES:
            raise ValueError("Archive exceeds extraction safety limits")
        install_map = entry.get("install", {}).get("map", {})
        matched_prefixes = {key: 0 for key in install_map}
        for info in members:
            mode = _zip_mode(info)
            safe_name = _safe_zip_name(info.filename)
            if info.is_dir():
                continue
            relative = None
            if is_shader:
                extensions = entry.get("extensions", [".glsl"])
                if any(safe_name.endswith(ext) for ext in extensions):
                    prefix = "/".join(relative_parts(entry.get("dest", "shaders/"), directory=True))
                    relative = prefix + "/" + safe_name.rsplit("/", 1)[-1]
            else:
                candidates = [safe_name]
                if "/" in safe_name:
                    candidates.append(safe_name.split("/", 1)[1])
                for src_prefix, dest_prefix in install_map.items():
                    prefix = "/".join(relative_parts(src_prefix, directory=True)) + "/"
                    for candidate in candidates:
                        if candidate.startswith(prefix):
                            dest_prefix = "/".join(relative_parts(dest_prefix, directory=True))
                            relative = dest_prefix + "/" + candidate[len(prefix):]
                            matched_prefixes[src_prefix] += 1
                            break
                    if relative:
                        break
            if relative is not None:
                dest = _safe_join(staging_dir, relative)
                key = relative.casefold()
                if key in seen or os.path.lexists(dest):
                    raise ValueError(f"Duplicate or existing archive output: {relative}")
                seen.add(key)
                selected.append((relative, info, mode if info.create_system == 3 else None))
        if not is_shader:
            missing = [key for key, count in matched_prefixes.items() if not count]
            if missing:
                raise FileNotFoundError(f"Release missing required mapped components: {', '.join(missing)}")
        outputs = [(relative, zf.read(info), mode) for relative, info, mode in selected]
    fetched = _write_component(staging_dir, outputs)
    extracted_count = len(fetched)

    ui.success(f"{name}: {extracted_count} file(s) extracted from {tag}")

    return {
        "name": name,
        "version": tag,
        "source": f"github:{repo}@{tag}",
        "files_count": extracted_count,
        "files": fetched,
        "sha256": {relative: hashlib.sha256(data).hexdigest() for relative, data, _ in outputs},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Orchestrator ───

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

    prog = ui.get_progress()
    if prog:
        task_id = prog.add_task("Fetching components...", total=total)
        prog.start()

    try:
        # Fetch scripts
        for script in scripts:
            current += 1
            if prog:
                prog.update(task_id, description=f"Fetching {script['name']}")
            else:
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
                    if prog: prog.advance(task_id)
                    continue

                results.append({"name": script["name"], "status": "ok", "detail": meta.get("version", "latest")})
                lockfile["scripts"][script["name"]] = meta

            except (FileNotFoundError, ConnectionError, zipfile.BadZipFile) as e:
                ui.error(f"{script['name']}: {e}")
                results.append({"name": script["name"], "status": "failed", "detail": str(e)})
            except Exception as e:
                ui.error(f"{script['name']}: unexpected error: {e}")
                results.append({"name": script["name"], "status": "failed", "detail": str(e)})
                
            if prog: prog.advance(task_id)

        # Fetch shaders
        current += 1
        if prog:
            prog.update(task_id, description=f"Fetching {shaders['name']}")
        else:
            ui.progress(current, total, shaders["name"])
            
        try:
            meta = fetch_release(shaders, staging_dir, is_shader=True)
            results.append({"name": shaders["name"], "status": "ok", "detail": meta.get("version", "")})
            lockfile["scripts"][shaders["name"]] = meta
        except Exception as e:
            ui.error(f"{shaders['name']}: {e}")
            results.append({"name": shaders["name"], "status": "failed", "detail": str(e)})
            
        if prog: prog.advance(task_id)

    finally:
        if prog:
            prog.stop()

    return results, lockfile
