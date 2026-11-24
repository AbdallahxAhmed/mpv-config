"""Check that uosc releases maintain patch anchors, owned options, and bindings.

Spec 005 (C-008, SC-009) and Spec 006 (FR-016, R9); contracts:
specs/005-playlist-drag-reorder/contracts/uosc-release-check.md.
Nothing is patched, written, imported or executed: the release's
elements/Menu.lua and scripts/uosc/main.lua are read into memory and checked.

    python -m tools.check_uosc_release --latest [--download-timeout SECONDS]
    python -m tools.check_uosc_release --tag TAG [--write-options PATH] [--compare-options PATH]
    python -m tools.check_uosc_release --uosc-dir DIR --version TAG

Exit 0: every anchor matches and options present. Exit 1: an anchor or option check failed. Exit 2: could not run.
"""

import argparse
import hashlib
import http.client
import io
import json
import os
import re
import socket
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from deploy import fetcher
from tools import patch_uosc_playlist_reorder as patcher

API_URL = "https://api.github.com/repos/tomasklaen/uosc/releases/latest"
API_TAG_URL = "https://api.github.com/repos/tomasklaen/uosc/releases/tags/{tag}"
DEFAULT_DOWNLOAD_TIMEOUT_S = 120.0
MEMBER = "scripts/uosc/elements/Menu.lua"
MEMBER_MAIN = "scripts/uosc/main.lua"
ASSET = "uosc.zip"
MAX_REDIRECTS = 5
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
TOKEN_HOST = "api.github.com"
ERROR = "::error title=uosc release check::"
REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKS_LUA = REPO_ROOT / "scripts" / "modules" / "looks.lua"

MENU_CONSTANTS = (
    "(item.active and 0.8 or 0) + (is_selected and 0.15 or 0)",
    "opacity = 0.5 * menu_opacity,",
    "opacity = menu_opacity * (item.muted and 0.5 or 1),",
    "item.active and fgt or bgt",
)


class CheckError(Exception):
    """The check could not run (exit 2); the message is the reason."""


class DeadlineExceeded(Exception):
    def __init__(self, url):
        super().__init__(url)
        self.url = url


def check_bytes(data: bytes, tag: str) -> int:
    failures = patcher.check_anchors(data)
    for failure in failures:
        print(
            f"{ERROR}uosc {tag}: anchor {failure.hunk_id} matched {failure.found}× "
            f"in {patcher.TARGET} (expected 1)"
        )
    if failures:
        return 1
    print(f"uosc {tag}: all {len(patcher.HUNKS)} anchors of {patcher.PATCH_NAME} match")
    return 0


def check_menu_constants(menu_lua: bytes, version: str = "5.13.0") -> list[str]:
    problems = []
    for const in MENU_CONSTANTS:
        if const.encode("utf-8") not in menu_lua:
            problems.append(f'uosc {version}: menu constant "{const}" missing')
    return problems


def read_looks_keys(looks_lua: Path = LOOKS_LUA) -> tuple[list[str], list[str], list[str], list[str]]:
    text = Path(looks_lua).read_text(encoding="utf-8")

    def _parse_table(name: str) -> list[str]:
        m = re.search(rf"^[ \t]*local\s+{name}\s*=\s*\{{([^}}]*)\}}", text, re.MULTILINE | re.DOTALL)
        if not m:
            raise CheckError(f"looks.lua: table {name} not found")
        return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))

    owned_keys = _parse_table("OWNED_KEYS")
    color_keys = _parse_table("OWNED_COLOR_KEYS")
    opacity_keys = _parse_table("OWNED_OPACITY_KEYS")
    bindings = _parse_table("MORE_UOSC_BINDINGS")
    return owned_keys, color_keys, opacity_keys, bindings


def extract_uosc_facts(main_lua: bytes, version: str) -> dict:
    text = main_lua.decode("utf-8", errors="replace")

    m_defaults = re.search(r"^[ \t]*defaults\s*=\s*\{[ \t]*$(.*?)^[ \t]*\}", text, re.MULTILINE | re.DOTALL)
    if not m_defaults:
        raise CheckError("main.lua: defaults block not found")
    defaults_block = m_defaults.group(1)
    options = {}
    for line in defaults_block.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        m = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*(.*?)(?:,)?$", line)
        if m:
            options[m.group(1)] = m.group(2).rstrip(",")

    m_config = re.search(r"^[ \t]*(?:local\s+)?config_defaults\s*=\s*\{", text, re.MULTILINE)
    if not m_config:
        raise CheckError("main.lua: config_defaults block not found")
    config_section = text[m_config.start():]

    m_color = re.search(r"^[ \t]*color\s*=\s*\{[ \t]*$(.*?)^[ \t]*\}", config_section, re.MULTILINE | re.DOTALL)
    if not m_color:
        raise CheckError("main.lua: color block not found")
    color = {}
    for line in m_color.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        m = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*serialize_rgba\(['\"]([0-9a-fA-F]+)['\"]\)", line)
        if m:
            color[m.group(1)] = m.group(2)

    m_opacity = re.search(r"^[ \t]*opacity\s*=\s*\{[ \t]*$(.*?)^[ \t]*\}", config_section, re.MULTILINE | re.DOTALL)
    if not m_opacity:
        raise CheckError("main.lua: opacity block not found")
    opacity = {}
    for line in m_opacity.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        m = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*([0-9.]+)", line)
        if m:
            opacity[m.group(1)] = m.group(2)

    runtime_handler = bool(
        re.search(r"opt\.read_options\(\s*options\s*,\s*['\"]uosc['\"]\s*,\s*handle_options\s*\)", text)
    )
    bindings = sorted(set(re.findall(r"bind_command\(\s*['\"]([^'\"]+)['\"]", text)))

    return {
        "bindings": bindings,
        "color": color,
        "main_lua_sha256": hashlib.sha256(main_lua).hexdigest(),
        "opacity": opacity,
        "options": options,
        "runtime_handler": runtime_handler,
        "uosc_version": version,
    }


def check_options(
    facts: dict,
    owned: list[str],
    color_keys: list[str],
    opacity_keys: list[str],
    bindings: list[str],
) -> list[str]:
    ver = facts.get("uosc_version", "unknown")
    problems = []
    options = facts.get("options") or {}
    for key in owned:
        if key not in options:
            problems.append(f"uosc {ver}: option {key} missing")

    color = facts.get("color") or {}
    for key in color_keys:
        if key not in color:
            problems.append(f"uosc {ver}: color {key} missing")

    opacity = facts.get("opacity") or {}
    for key in opacity_keys:
        if key not in opacity:
            problems.append(f"uosc {ver}: opacity {key} missing")

    if not facts.get("runtime_handler"):
        problems.append(f"uosc {ver}: runtime option handler missing")

    fact_bindings = set(facts.get("bindings") or [])
    for key in bindings:
        if key not in fact_bindings:
            problems.append(f"uosc {ver}: binding {key} missing")

    return problems


def _first_diff_key(current: dict, expected: dict) -> str | None:
    for k in sorted(set(current.keys()) | set(expected.keys())):
        if k not in current or k not in expected:
            return k
        val_cur = current[k]
        val_exp = expected[k]
        if val_cur != val_exp:
            if isinstance(val_cur, dict) and isinstance(val_exp, dict):
                for subk in sorted(set(val_cur.keys()) | set(val_exp.keys())):
                    if val_cur.get(subk) != val_exp.get(subk):
                        return f"{k}.{subk}"
            return k
    return None


class _Downloader:
    """GET under one monotonic deadline that covers every hop and every read."""

    def __init__(self, timeout_s: float):
        self.deadline = time.monotonic() + timeout_s

    def remaining(self) -> float:
        return max(0.01, self.deadline - time.monotonic())

    def get(self, url: str, *, send_token: bool = False) -> bytes:
        for _hop in range(MAX_REDIRECTS + 1):
            status, location, body = self._request(url, send_token)
            if location is None:
                if status != 200:
                    raise CheckError(f"HTTP {status} from {url}")
                return body
            url, send_token = urljoin(url, location), False
        raise CheckError(f"more than {MAX_REDIRECTS} redirects from {url}")

    def _connection(self, url: str):
        parts = urlsplit(url)
        if parts.scheme == "https":
            return parts, http.client.HTTPSConnection(
                parts.hostname, parts.port, timeout=self.remaining()
            )
        if parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS:
            return parts, http.client.HTTPConnection(
                parts.hostname, parts.port, timeout=self.remaining()
            )
        raise CheckError(f"refusing to fetch {url}")

    def _request(self, url: str, send_token: bool):
        parts, conn = self._connection(url)
        headers = {"User-Agent": "mpv-config-uosc-release-check", "Accept": "*/*"}
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token and send_token and parts.scheme == "https" and parts.hostname == TOKEN_HOST:
            headers["Authorization"] = f"Bearer {token}"
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        fired = threading.Event()
        timer = None
        try:
            conn.request("GET", target, headers=headers)  # connects within remaining()
            sock = conn.sock

            def shutdown():
                fired.set()
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = threading.Timer(max(0.0, self.deadline - time.monotonic()), shutdown)
            timer.daemon = True
            timer.start()
            sock.settimeout(self.remaining())
            resp = conn.getresponse()
            if 300 <= resp.status < 400 and resp.getheader("Location"):
                return resp.status, resp.getheader("Location"), b""
            if resp.status != 200:
                return resp.status, None, b""
            return resp.status, None, self._read_body(resp, sock, url)
        except (OSError, http.client.HTTPException) as exc:
            if fired.is_set() or isinstance(exc, TimeoutError) or self._expired():
                raise DeadlineExceeded(url) from exc
            raise CheckError(f"{type(exc).__name__} from {url}: {exc}") from exc
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()

    def _read_body(self, resp, sock, url: str) -> bytes:
        chunks, total = [], 0
        while not resp.isclosed():  # it closes itself once Content-Length is read
            sock.settimeout(self.remaining())
            chunk = resp.read1(65536)
            if self._expired():
                raise DeadlineExceeded(url)
            if not chunk:
                break
            total += len(chunk)
            if total > fetcher.MAX_DOWNLOAD_BYTES:
                raise CheckError(f"{url} is larger than {fetcher.MAX_DOWNLOAD_BYTES} bytes")
            chunks.append(chunk)
        if resp.length:  # a short body is a cut-off download, not an empty file
            raise http.client.IncompleteRead(b"".join(chunks), resp.length)
        return b"".join(chunks)

    def _expired(self) -> bool:
        return time.monotonic() >= self.deadline


def _members_from_zip(data: bytes, wanted: tuple[str, ...] = (MEMBER, MEMBER_MAIN)) -> dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CheckError(f"{ASSET} is not a valid zip") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > fetcher.MAX_ARCHIVE_MEMBERS:
            raise CheckError(f"{ASSET} has more than {fetcher.MAX_ARCHIVE_MEMBERS} members")
        if sum(info.file_size for info in infos) > fetcher.MAX_EXPANDED_BYTES:
            raise CheckError(f"{ASSET} expands beyond {fetcher.MAX_EXPANDED_BYTES} bytes")
        wanted_set = set(wanted)
        members = {}
        for info in infos:
            try:
                name = fetcher._safe_zip_name(info.filename)
            except ValueError:
                continue
            if name in wanted_set and not info.is_dir():
                try:
                    members[name] = archive.read(info)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise CheckError(f"{ASSET} is not a valid zip") from exc
        return members


def _menu_from_zip(data: bytes) -> bytes:
    members = _members_from_zip(data, wanted=(MEMBER,))
    if MEMBER not in members:
        raise CheckError(f"{ASSET} has no member {MEMBER}")
    return members[MEMBER]


def _release_asset(release_json: bytes) -> tuple[str, str | None]:
    """(tag, browser_download_url of uosc.zip, or None when the release has none)."""
    try:
        release = json.loads(release_json)
        tag = str(release["tag_name"])
        assets = release.get("assets") or []
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CheckError("the release API answer is not a release") from exc
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == ASSET:
            url = asset.get("browser_download_url")
            if isinstance(url, str) and url:
                return tag, url
    return tag, None


def _check_release(
    menu_data: bytes,
    main_data: bytes | None,
    version: str,
    write_options: Path | None = None,
    compare_options: Path | None = None,
    looks_path: Path = LOOKS_LUA,
) -> int:
    failures = patcher.check_anchors(menu_data)
    for failure in failures:
        print(
            f"{ERROR}uosc {version}: anchor {failure.hunk_id} matched {failure.found}× "
            f"in {patcher.TARGET} (expected 1)"
        )

    menu_problems = check_menu_constants(menu_data, version)
    for prob in menu_problems:
        print(f"{ERROR}{prob}")

    facts = None
    owned = color_keys = opacity_keys = bindings = []
    opt_problems = []
    if main_data is not None:
        try:
            facts = extract_uosc_facts(main_data, version)
        except CheckError as exc:
            print(f"{ERROR}uosc {version}: {exc}")
            return 2

        try:
            owned, color_keys, opacity_keys, bindings = read_looks_keys(looks_path)
        except (CheckError, OSError) as exc:
            print(f"{ERROR}uosc {version}: cannot read looks keys: {exc}")
            return 2

        opt_problems = check_options(facts, owned, color_keys, opacity_keys, bindings)
        for prob in opt_problems:
            print(f"{ERROR}{prob}")

    if failures or menu_problems or opt_problems:
        return 1

    if write_options and facts is not None:
        try:
            target_path = Path(write_options)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"{ERROR}uosc {version}: cannot write {write_options}: {exc}")
            return 2

    if compare_options and facts is not None:
        try:
            expected = json.loads(Path(compare_options).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{ERROR}uosc {version}: cannot read {compare_options}: {exc}")
            return 2
        diff_key = _first_diff_key(facts, expected)
        if diff_key:
            print(f"{ERROR}uosc {version}: options differ from {compare_options} at {diff_key}")
            return 1

    print(f"uosc {version}: all {len(patcher.HUNKS)} anchors of {patcher.PATCH_NAME} match")
    if main_data is not None:
        print(f"uosc {version}: {len(owned)} owned options, runtime handler and {len(bindings)} bindings present")
    return 0


def run(
    api_url: str | None = None,
    download_timeout: float = DEFAULT_DOWNLOAD_TIMEOUT_S,
    tag: str | None = None,
    write_options: Path | None = None,
    compare_options: Path | None = None,
    looks_path: Path = LOOKS_LUA,
) -> int:
    tag_name = tag or "latest"
    downloader = _Downloader(download_timeout)
    target_api = api_url
    if target_api is None:
        target_api = API_TAG_URL.format(tag=tag) if tag else API_URL
    try:
        release_tag, url = _release_asset(downloader.get(target_api, send_token=True))
        tag_name = release_tag
        if url is None:
            raise CheckError(f"release has no {ASSET} asset")
        members = _members_from_zip(downloader.get(url), wanted=(MEMBER, MEMBER_MAIN))
        if MEMBER not in members:
            raise CheckError(f"{ASSET} has no member {MEMBER}")
        if MEMBER_MAIN not in members:
            raise CheckError(f"release zip has no {MEMBER_MAIN}")
        menu_data = members[MEMBER]
        main_data = members[MEMBER_MAIN]
    except DeadlineExceeded as exc:
        print(
            f"{ERROR}uosc {tag_name}: download did not finish within {download_timeout:g} s "
            f"({exc.url}); the release check could not run"
        )
        return 2
    except CheckError as exc:
        print(f"{ERROR}uosc {tag_name}: {exc}")
        return 2

    return _check_release(
        menu_data=menu_data,
        main_data=main_data,
        version=tag_name,
        write_options=write_options,
        compare_options=compare_options,
        looks_path=looks_path,
    )


def check_dir(
    uosc_dir: Path,
    version: str,
    write_options: Path | None = None,
    compare_options: Path | None = None,
    looks_path: Path = LOOKS_LUA,
) -> int:
    uosc_dir = Path(uosc_dir)
    try:
        menu_data = (uosc_dir / patcher.TARGET).read_bytes()
    except OSError as exc:
        print(f"{ERROR}uosc {version}: cannot read {patcher.TARGET}: {exc.strerror or exc}")
        return 2

    main_path = uosc_dir / "main.lua"
    main_data = None
    if main_path.is_file():
        main_data = main_path.read_bytes()
    else:
        print(f"uosc {version}: main.lua not found in {uosc_dir}; option checks skipped")

    return _check_release(
        menu_data=menu_data,
        main_data=main_data,
        version=version,
        write_options=write_options,
        compare_options=compare_options,
        looks_path=looks_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--latest", action="store_true", help="check the latest GitHub release")
    mode.add_argument("--tag", help="check a specific GitHub release tag")
    mode.add_argument("--uosc-dir", type=Path, help="check an unpacked uosc directory")
    parser.add_argument("--version", help="tag to name in the output (with --uosc-dir)")
    parser.add_argument(
        "--download-timeout",
        type=float,
        default=DEFAULT_DOWNLOAD_TIMEOUT_S,
        help="one deadline in seconds for the whole download (default %(default)g)",
    )
    parser.add_argument("--write-options", type=Path, help="write extracted facts to PATH")
    parser.add_argument("--compare-options", type=Path, help="fail if extracted facts differ from PATH")
    args = parser.parse_args(argv)
    if args.latest:
        return run(
            download_timeout=args.download_timeout,
            write_options=args.write_options,
            compare_options=args.compare_options,
        )
    if args.tag:
        return run(
            tag=args.tag,
            download_timeout=args.download_timeout,
            write_options=args.write_options,
            compare_options=args.compare_options,
        )
    if not args.version:
        parser.error("--uosc-dir needs --version")
    return check_dir(
        args.uosc_dir,
        args.version,
        write_options=args.write_options,
        compare_options=args.compare_options,
    )


if __name__ == "__main__":
    raise SystemExit(main())
