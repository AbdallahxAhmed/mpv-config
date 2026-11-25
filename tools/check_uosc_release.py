"""Check that the playlist-reorder patch anchors still match a uosc release.

Spec 005 (C-008, SC-009); contract: specs/005-playlist-drag-reorder/contracts/
uosc-release-check.md. Nothing is patched, written, imported or executed: the
release's elements/Menu.lua is read into memory and only its anchors are counted.

    python -m tools.check_uosc_release --latest [--download-timeout SECONDS]
    python -m tools.check_uosc_release --uosc-dir DIR --version TAG

Exit 0: every anchor matches. Exit 1: an anchor failed. Exit 2: could not run.
"""

import argparse
import http.client
import io
import json
import os
import socket
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from deploy import fetcher
from tools import patch_uosc_playlist_reorder as patcher

API_URL = "https://api.github.com/repos/tomasklaen/uosc/releases/latest"
DEFAULT_DOWNLOAD_TIMEOUT_S = 120.0
MEMBER = "scripts/uosc/elements/Menu.lua"
ASSET = "uosc.zip"
MAX_REDIRECTS = 5
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
TOKEN_HOST = "api.github.com"
ERROR = "::error title=uosc release check::"


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


def check_dir(uosc_dir: Path, version: str) -> int:
    try:
        data = (Path(uosc_dir) / patcher.TARGET).read_bytes()
    except OSError as exc:
        print(f"{ERROR}uosc {version}: cannot read {patcher.TARGET}: {exc.strerror or exc}")
        return 2
    return check_bytes(data, version)


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


def _menu_from_zip(data: bytes) -> bytes:
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
        for info in infos:
            try:
                name = fetcher._safe_zip_name(info.filename)
            except ValueError:
                continue
            if name == MEMBER and not info.is_dir():
                try:
                    return archive.read(info)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise CheckError(f"{ASSET} is not a valid zip") from exc
    raise CheckError(f"{ASSET} has no member {MEMBER}")


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


def run(api_url: str = API_URL, download_timeout: float = DEFAULT_DOWNLOAD_TIMEOUT_S) -> int:
    tag = "latest"
    downloader = _Downloader(download_timeout)
    try:
        tag, url = _release_asset(downloader.get(api_url, send_token=True))
        if url is None:
            raise CheckError(f"release has no {ASSET} asset")
        data = _menu_from_zip(downloader.get(url))
    except DeadlineExceeded as exc:
        print(
            f"{ERROR}uosc {tag}: download did not finish within {download_timeout:g} s "
            f"({exc.url}); the release check could not run"
        )
        return 2
    except CheckError as exc:
        print(f"{ERROR}uosc {tag}: {exc}")
        return 2
    return check_bytes(data, tag)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--latest", action="store_true", help="check the latest GitHub release")
    mode.add_argument("--uosc-dir", type=Path, help="check an unpacked uosc directory")
    parser.add_argument("--version", help="tag to name in the output (with --uosc-dir)")
    parser.add_argument(
        "--download-timeout",
        type=float,
        default=DEFAULT_DOWNLOAD_TIMEOUT_S,
        help="one deadline in seconds for the whole download (default %(default)g)",
    )
    args = parser.parse_args(argv)
    if args.latest:
        return run(download_timeout=args.download_timeout)
    if not args.version:
        parser.error("--uosc-dir needs --version")
    return check_dir(args.uosc_dir, args.version)


if __name__ == "__main__":
    raise SystemExit(main())
