#!/usr/bin/env python3
"""
cookie_sync_host.py — Chrome Native Messaging host for the MPV Companion extension.

The browser starts this process itself (stdio, length-prefixed JSON). It is
reachable ONLY from the extension IDs listed in the host manifest's
``allowed_origins``, which tools/register_extension.py generates outside the
repository. There is deliberately no network listener: an earlier HTTP daemon
on 127.0.0.1:8765 accepted commands from any web page (2026-11-20 audit, 4.1).

Actions (sent by tools/extension/background.js):
- sync_cookies    — write the site's cookies as a Netscape cookies.txt for yt-dlp/mpv.
- stream_captured — remember a signed M3U8 URL intercepted in the browser.
- play / download — launch mpv or ``mpv_config download`` on an http(s) URL.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

HOST_NAME = "com.mpv.cookiesync"
MAX_MESSAGE_BYTES = 8 * 1024 * 1024
MAX_COOKIE_BYTES = 1024 * 1024
MAX_URL_LENGTH = 8192
MAX_SLUG_LENGTH = 256
ALLOWED_URL_SCHEMES = ("http", "https")

# Windows process-creation flags; spelled out so the launch code is testable on POSIX.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_CONSOLE = 0x00000010

STREAM_CACHE: dict[str, dict] = {}


# ─── Locations ───────────────────────────────────────────────────────────


def _data_base() -> Path:
    """Base for cookie/stream files; matches tools/core/session.py, which reads them."""
    return Path(os.environ.get("APPDATA") or Path.home())


def active_streams_file() -> Path:
    return _data_base() / "mpv-config" / "active_streams.json"


def _repo_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def host_manifest_path() -> Path:
    """Where register_extension.py writes the manifest (must match its get_user_data_dir)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "mpv-config" / "extension" / f"{HOST_NAME}.json"


# ─── Caller origin ───────────────────────────────────────────────────────


def allowed_origins() -> list[str]:
    """Exact extension origins from the host manifest; anything malformed is dropped."""
    try:
        manifest = json.loads(host_manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    origins = manifest.get("allowed_origins") if isinstance(manifest, dict) else None
    if not isinstance(origins, list):
        return []
    return [
        o
        for o in origins
        if isinstance(o, str) and re.fullmatch(r"chrome-extension://[a-p]{32}/", o)
    ]


def origin_allowed(argv: list[str]) -> bool:
    """Chrome passes the caller's origin as the first argument; it must be one of ours.

    Chrome already enforces allowed_origins before starting the host; this check
    keeps a host started by anything else (a shell, another browser profile with a
    copied manifest) from acting at all.
    """
    if len(argv) < 2:
        return False
    return argv[1] in allowed_origins()


# ─── Validation ──────────────────────────────────────────────────────────

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # everything but \t and \n
_HOSTNAME = re.compile(r"(?=.{1,253}$)(?!.*\.\.)[a-z0-9_](?:[a-z0-9_.-]*[a-z0-9_])?")


def validate_url(url: object) -> str | None:
    """Return the URL if it is a plain http(s) URL, else None."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return None
    if url != url.strip() or _CONTROL_CHARS.search(url) or any(c.isspace() for c in url):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ALLOWED_URL_SCHEMES or not parts.hostname:
        return None
    return url


def _valid_domain(domain: object) -> str | None:
    if not isinstance(domain, str):
        return None
    domain = domain.strip().strip(".").lower()
    return domain if _HOSTNAME.fullmatch(domain) else None


def validate_netscape(text: str) -> str | None:
    """Return normalized Netscape cookies.txt text, or None if it is not one.

    Every non-comment line must have the 7 tab-separated fields yt-dlp expects;
    control characters (which could smuggle extra lines) are refused.
    """
    if not isinstance(text, str):
        return None
    text = text.replace("\r\n", "\n")
    if len(text.encode("utf-8")) > MAX_COOKIE_BYTES or _CONTROL_CHARS.search(text):
        return None
    cookies = 0
    for line in text.split("\n"):
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            return None
        domain, flag, path, secure, expiry, _name, _value = fields
        host = domain[len("#HttpOnly_") :] if domain.startswith("#HttpOnly_") else domain
        if not _valid_domain(host) or flag not in ("TRUE", "FALSE"):
            return None
        if not path.startswith("/") or secure not in ("TRUE", "FALSE"):
            return None
        if not re.fullmatch(r"-?\d{1,20}", expiry):
            return None
        cookies += 1
    if cookies == 0:
        return None
    return text if text.endswith("\n") else text + "\n"


# ─── Cookie Persistence ──────────────────────────────────────────────────

_NETSCAPE_HEADER = [
    "# Netscape HTTP Cookie File",
    "# Exported automatically by MPV Media Companion",
    "",
]


def _netscape_from_input(cookie_input: str | list | dict, domain: str) -> str:
    """Accept Netscape text, a document.cookie header, or a list of cookie dicts."""
    if isinstance(cookie_input, str):
        if cookie_input.strip().startswith("# Netscape") or "\t" in cookie_input:
            return cookie_input
        dom = _valid_domain(domain)
        if not dom:
            return ""
        expiry = int(time.time()) + 86400 * 30
        lines = list(_NETSCAPE_HEADER)
        for pair in cookie_input.split(";"):
            if "=" in pair:
                k, v = pair.strip().split("=", 1)
                if k.strip():
                    lines.append(f".{dom}\tTRUE\t/\tTRUE\t{expiry}\t{k.strip()}\t{v.strip()}")
        return "\n".join(lines) + "\n"
    if isinstance(cookie_input, list):
        lines = list(_NETSCAPE_HEADER)
        for c in cookie_input:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            dom = str(c.get("domain") or domain or "")
            dom = dom if dom.startswith(".") else "." + dom
            secure = "TRUE" if c.get("secure") else "FALSE"
            expiry = int(c.get("expirationDate") or c.get("expires") or (time.time() + 86400 * 30))
            lines.append(
                f"{dom}\tTRUE\t{c.get('path', '/')}\t{secure}\t{expiry}\t{c['name']}\t{c.get('value', '')}"
            )
        return "\n".join(lines) + "\n"
    return ""


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a private temp file in the same directory, then rename over the target.

    A reader never sees a half-written file, and the temp file is created 0600
    (cookies are credentials).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def cookie_targets(domain: str) -> list[Path]:
    targets = []
    if os.environ.get("APPDATA"):
        base = _data_base()
        targets.append(base / "yt-dlp" / "cookies.txt")
        cookies_dir = base / "mpv-config" / "cookies"
        dom = _valid_domain(domain)
        if dom:
            targets.append(cookies_dir / f"{dom}.txt")
        targets.append(cookies_dir / "cookies.txt")
    # tools/core/session.py looks here first
    if _repo_dir().is_dir():
        targets.append(_repo_dir() / "cookies.txt")
    return targets


def save_cookies(cookie_input: str | list | dict, domain: str = "") -> list[str]:
    """Validate and atomically save cookies; returns the paths written."""
    netscape_text = validate_netscape(_netscape_from_input(cookie_input, domain))
    if netscape_text is None:
        return []
    saved = []
    for path in cookie_targets(domain):
        try:
            atomic_write_text(path, netscape_text)
            saved.append(str(path))
        except OSError:
            continue
    return saved


# ─── Stream Cache ────────────────────────────────────────────────────────


def save_stream(slug: str, url: str, title: str = "", page_url: str = "") -> dict | None:
    """Cache an intercepted M3U8 URL (http/https only) for 24 hours."""
    if validate_url(url) is None or not isinstance(slug, str) or not slug:
        return None
    slug = slug[:MAX_SLUG_LENGTH]
    entry = {
        "slug": slug,
        "url": url,
        "title": str(title or "")[:512],
        "page_url": page_url if validate_url(page_url) else "",
        "timestamp": int(time.time()),
    }
    STREAM_CACHE[slug] = entry

    cache_file = active_streams_file()
    disk_cache: dict = {}
    try:
        disk_cache = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(disk_cache, dict):
            disk_cache = {}
    except (OSError, ValueError):
        disk_cache = {}
    disk_cache[slug] = entry
    now = time.time()
    disk_cache = {
        k: v
        for k, v in disk_cache.items()
        if isinstance(v, dict) and now - v.get("timestamp", 0) < 86400
    }
    try:
        atomic_write_text(cache_file, json.dumps(disk_cache, indent=2))
    except OSError:
        pass
    return entry


def get_cached_stream(slug: str) -> dict | None:
    """Retrieve a stream from the in-memory cache or the disk file."""
    if slug in STREAM_CACHE:
        return STREAM_CACHE[slug]
    try:
        disk_cache = json.loads(active_streams_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = disk_cache.get(slug) if isinstance(disk_cache, dict) else None
    if isinstance(entry, dict):
        STREAM_CACHE[slug] = entry
        return entry
    return None


# ─── Launchers ───────────────────────────────────────────────────────────


def find_mpv() -> str:
    """Locate the mpv binary."""
    which = shutil.which("mpv")
    if which:
        return which
    candidates = [Path(r"C:\Program Files\mpv\mpv.exe")]
    for var in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(var)
        if base:
            sub = ("Microsoft", "WinGet", "Links") if var == "LOCALAPPDATA" else ("mpv",)
            candidates.append(Path(base).joinpath(*sub, "mpv.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return "mpv"


def build_play_command(url: str) -> list[str]:
    # "--" ends option parsing: the URL can never be read as an mpv option.
    return [find_mpv(), "--", url]


def build_download_command(url: str) -> list[str]:
    return [sys.executable, "-m", "mpv_config", "download", "--", url]


def _popen_kwargs(new_console: bool) -> dict:
    """Never inherit our stdio: stdout IS the native-messaging channel to the browser."""
    if sys.platform == "win32":
        if new_console:
            # Visible progress window, like the old `start`, without cmd.exe. No std
            # handle may be passed here: naming any one makes Windows inherit the
            # others from this process, i.e. the browser pipes. With none given and
            # close_fds (the default) the child gets the new console's own handles.
            return {"creationflags": CREATE_NEW_CONSOLE}
        return {
            "creationflags": DETACHED_PROCESS,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
    return {
        "start_new_session": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }


def execute_play(url: str) -> bool:
    """Launch mpv on an http(s) URL. Returns False (and launches nothing) otherwise."""
    if validate_url(url) is None:
        return False
    subprocess.Popen(build_play_command(url), **_popen_kwargs(new_console=False))
    return True


def execute_download(url: str) -> bool:
    """Launch the MPV Turbo Downloader on an http(s) URL."""
    if validate_url(url) is None:
        return False
    subprocess.Popen(build_download_command(url), **_popen_kwargs(new_console=True))
    return True


# ─── Native Messaging Stdio Protocol ─────────────────────────────────────


def read_native_message(stream) -> dict | None:
    """Read one length-prefixed JSON object; None on EOF or a malformed message."""
    raw_length = stream.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    length = struct.unpack("@I", raw_length)[0]
    if length > MAX_MESSAGE_BYTES:
        return None
    data = stream.read(length)
    if len(data) < length:
        return None
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) else None


def send_native_message(stream, message: dict) -> None:
    content = json.dumps(message).encode("utf-8")
    stream.write(struct.pack("@I", len(content)))
    stream.write(content)
    stream.flush()


def handle_message(msg: dict) -> dict:
    action = msg.get("action", "")

    if action == "sync_cookies":
        saved = save_cookies(msg.get("cookies", ""), str(msg.get("domain", "")))
        if not saved:
            return {"status": "error", "message": "invalid cookies"}
        return {"status": "ok", "action": "synced", "saved": len(saved)}

    if action == "stream_captured":
        slug = msg.get("slug", "")
        page_url = msg.get("page_url", "")
        if not slug and isinstance(page_url, str) and page_url:
            slug = page_url.rstrip("/").split("/")[-1]
        if save_stream(slug, msg.get("url", ""), msg.get("title", ""), page_url) is None:
            return {"status": "error", "message": "invalid stream"}
        return {"status": "ok", "action": "stream_cached"}

    if action in ("play", "download"):
        launch = execute_play if action == "play" else execute_download
        try:
            launched = launch(msg.get("url", ""))
        except OSError as exc:
            return {"status": "error", "message": f"launch failed: {exc.strerror or exc}"}
        if not launched:
            return {"status": "error", "message": "only http(s) URLs are accepted"}
        return {"status": "ok", "action": "playing" if action == "play" else "downloading"}

    return {"status": "ok", "action": "pong"}


def main(argv: list[str] | None = None, stdin=None, stdout=None) -> int:
    argv = sys.argv if argv is None else argv
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout.buffer if stdout is None else stdout
    if not origin_allowed(argv):
        sys.stderr.write(f"{HOST_NAME}: caller origin not allowed\n")
        return 1
    while True:
        msg = read_native_message(stdin)
        if msg is None:
            return 0
        send_native_message(stdout, handle_message(msg))


if __name__ == "__main__":
    sys.exit(main())
