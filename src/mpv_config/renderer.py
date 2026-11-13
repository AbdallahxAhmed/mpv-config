"""Locate the mpv-config-ui renderer (ui/ in the repository) for this machine.

The renderer is an optional, prebuilt Go binary that draws the deployer's
progress. It is published as a GitHub release asset and pinned by SHA-256 in
``ui/release.json`` inside the checkout, so the code that runs is exactly the
code the checkout vouches for. Anything unexpected (no TTY, unsupported
platform, offline, hash mismatch, no release yet) silently falls back to the
built-in plain output: the renderer is a nicety, never a requirement.

Environment:
    MPV_CONFIG_UI=plain     never use the renderer
    MPV_CONFIG_UI=fancy     use it and explain why when it is unavailable
    MPV_CONFIG_UI_BIN=PATH  use this binary (development builds)
"""

import gzip
import hashlib
import json
import os
import platform
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

RELEASE_URL = "https://github.com/AbdallahxAhmed/mpv-config/releases/download/{tag}/{file}"
MAX_ASSET_BYTES = 32 * 1024 * 1024
DOWNLOAD_TIMEOUT = 20

_ARCH = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}


def platform_key(system: Optional[str] = None, machine: Optional[str] = None) -> Optional[str]:
    system = (system or sys.platform).lower()
    os_name = (
        "windows"
        if system.startswith("win")
        else "darwin"
        if system == "darwin"
        else "linux"
        if system.startswith("linux")
        else None
    )
    arch = _ARCH.get((machine or platform.machine() or "").lower())
    if not os_name or not arch:
        return None
    return f"{os_name}-{arch}"


def wanted(env=None, stdin=None, stdout=None) -> bool:
    """The renderer needs a real terminal on both ends and an opt-in-able mode."""
    env = os.environ if env is None else env
    mode = env.get("MPV_CONFIG_UI", "").strip().lower()
    if mode in ("plain", "0", "off", "no", "false"):
        return False
    if env.get("TERM") == "dumb" or (env.get("CI") and mode != "fancy"):
        return False
    for stream in (stdin or sys.stdin, stdout or sys.stdout):
        try:
            if not stream.isatty():
                return False
        except (AttributeError, ValueError, OSError):
            return False
    return True


def cache_dir(env=None) -> Path:
    env = os.environ if env is None else env
    if sys.platform == "win32":
        base = env.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return Path(base) / "mpv-config" / "bin"
    base = env.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "mpv-config" / "bin"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "mpv-config"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
        data = response.read(MAX_ASSET_BYTES + 1)
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError("renderer asset exceeds the size limit")
    return data


def resolve(
    repo_root: Path,
    env=None,
    fetch: Callable[[str], bytes] = _fetch,
    notice: Callable[[str], None] = lambda text: None,
) -> Optional[Path]:
    """Return a verified renderer binary path, downloading it once if needed."""
    env = os.environ if env is None else env
    override = env.get("MPV_CONFIG_UI_BIN")
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
        notice(f"MPV_CONFIG_UI_BIN={override} does not exist")
        return None

    manifest_path = Path(repo_root) / "ui" / "release.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version, tag = manifest["version"], manifest["tag"]
    except (OSError, ValueError, KeyError, TypeError):
        notice("ui/release.json is missing or unreadable")
        return None
    key = platform_key()
    asset = (manifest.get("assets") or {}).get(key or "")
    if not asset or not asset.get("sha256") or not asset.get("file"):
        notice(f"no renderer build is published for {key or 'this platform'}")
        return None

    suffix = ".exe" if key.startswith("windows") else ""
    target = cache_dir(env) / f"mpv-config-ui-{version}{suffix}"
    expected = asset["sha256"].lower()
    if target.is_file():
        try:
            if _sha256(target) == expected:
                return target
        except OSError:
            pass

    url = RELEASE_URL.format(tag=tag, file=asset["file"])
    try:
        data = fetch(url)
        if asset["file"].endswith(".gz"):
            data = gzip.decompress(data)
        if hashlib.sha256(data).hexdigest() != expected:
            notice(f"renderer download did not match its pinned SHA-256 ({url})")
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".mpv-config-ui-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.chmod(tmp, 0o755)
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as exc:  # offline, 404 before the first release, disk errors
        notice(f"renderer unavailable ({exc.__class__.__name__}: {exc})")
        return None
    return target
