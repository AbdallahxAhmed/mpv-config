"""
installer.py — Install system dependencies.

Handles package installation via winget, pacman, apt, brew, dnf, pipx,
and github_asset (direct GitHub release downloads) based on the
detected environment.
"""

import collections
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

from deploy import ui
from deploy.detector import probe_mpv_version
from deploy.registry import MPV_MINIMUM_VERSION, SYSTEM_DEPS

# WHY: package-manager operations legitimately run far longer than the
# default 5-minute _run timeout — a full `apt-get update`/`add-apt-repository`
# refresh against slow or distant mirrors routinely exceeded 300 s, and the
# killed step left machines without the very package they were installing
# (report: mpv PPA setup "times out and eventually not installed"). Package
# installs/updates/PPA setup get a 30-minute budget instead.
PKG_TIMEOUT = 1800  # seconds

# Apt transport options applied to EVERY apt call in this module:
# - ForceIPv4: some struggling-Mint-class networks resolve Launchpad to AAAA
#   records whose route black-holes (curl -4 succeeded, everything else
#   hung for minutes). Forcing IPv4 makes apt match the proven-working
#   transport; on healthy networks it is harmless.
# - Retries=3: flaky/constrained networks still converge without human
#   babysitting.
_APT_OPTIONS = ("-o", "Acquire::ForceIPv4=true", "-o", "Acquire::Retries=3")

# Seconds of output silence before _run prints a heartbeat line that
# shows elapsed time and the remaining budget — the anti-"frozen spinner".
_HEARTBEAT_INTERVAL = 15

# How long the pump loop waits per slice; keeps the loop responsive right
# after EOF (proc.poll() can lag process exit, so EOF is trusted instead).
_POLL_SLICE = 0.2

# Quiet-by-default output discipline for _run (professional feed):
# - command echoes once, compact and truncated;
# - child output is CAPTURED — package managers ship walls of text
#   (apt fetch lines, pacman -Syu unpack logs) that drown the narrative;
# - silence still ticks a heartbeat so "working" and "hung" differ;
# - failure prints ONLY a short tail of recent output (bounded).
# MPV_VERBOSE=1 restores full live streaming for interactive diagnosis.
_VERBOSE_ON = ("1", "true", "yes")
_TAIL_KEEP = 40        # recent lines retained in memory for diagnostics
_TAIL_SHOW = 6         # lines shown after a failed command
_CMD_ECHO_LIMIT = 120  # command echo truncation width

# Output that matters for interaction (password prompts, confirm prompts)
# is forwarded immediately even in quiet mode — never swallowed.
_PROMPT_RE = re.compile(
    r"\[sudo\]\s*password|\[[ynYN]/[npNP]\]|Overwrite\?|\(y/n\)"
)

# The PPA used to bring the latest stable mpv to Ubuntu/Mint (installer
# branch in the registry). Direct HTTPS registration below reads its
# signing key via Launchpad's public API, so it stays in one place.
PPA_OWNER = "ubuntuhandbook1"
PPA_ARCHIVE = "mpv"


def _verbose():
    """MPV_VERBOSE=1 switches _run to full live streaming (diagnosis mode)."""
    return os.environ.get("MPV_VERBOSE", "").strip().lower() in _VERBOSE_ON


def _echo_command(cmd):
    """Print the command once, compact and truncated to a tidy line."""
    text = shlex.join(cmd)
    if len(text) > _CMD_ECHO_LIMIT:
        text = text[: _CMD_ECHO_LIMIT - 1].rstrip() + "…"
    print(f"  $ {text}", flush=True)


def _show_captures(tail, seen_lines, verbose):
    """After a failed command, surface a short tail of its captured output."""
    if verbose:
        return  # everything already streamed live
    shown = list(tail)[-_TAIL_SHOW:]
    if not shown:
        return
    suppressed = seen_lines - len(shown)
    if suppressed > 0:
        print(
            f"      ⌄ last {len(shown)} of {seen_lines} output lines:",
            flush=True,
        )
    else:
        print("      ⌄ output:", flush=True)
    for line in shown:
        print(f"      │ {line}", flush=True)


def _run(cmd, check=True, env=None, timeout=300):
    """Run a command with tidy, low-noise live feedback; returns success bool.

    WHY still heartbeat-based: package managers can go silent for minutes
    (apt between mirror fetches, curl over a stalled route) and the old
    fire-and-forget runner showed only a spinner — "working" and "hung"
    must never be indistinguishable. Quiet mode keeps that guarantee
    without flooding the feed: the command echoes once, output is
    captured, and failure reveals a short tail of what went wrong.
    """
    verbose = _verbose()
    start = time.monotonic()
    _echo_command(cmd)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError:
        ui.error(f"Command not found: {cmd[0]}")
        return False
    except OSError as exc:
        ui.error(f"Could not start {cmd[0]}: {exc}")
        return False

    lines = queue.Queue()
    reader = threading.Thread(
        target=_pump_lines, args=(proc.stdout, lines), daemon=True
    )
    reader.start()

    tail = collections.deque(maxlen=_TAIL_KEEP)
    seen_lines = 0
    deadline = None if timeout is None else start + timeout
    got_eof = False
    last_beat = start

    def on_line(item):
        nonlocal seen_lines
        seen_lines += 1
        tail.append(item)
        # Interaction-critical prompts are always forwarded; everything
        # else streams only in verbose mode.
        if verbose or _PROMPT_RE.search(item):
            print(f"      {item}", flush=True)

    try:
        while not got_eof and proc.poll() is None:
            try:
                item = lines.get(timeout=_POLL_SLICE)
            except queue.Empty:
                now = time.monotonic()
                elapsed = int(now - start)
                # ONE line per _HEARTBEAT_INTERVAL — the poll slice fires
                # 5x/s, and a heartbeat on every slice drowned the sudo
                # password prompt before it could be answered.
                if now - last_beat >= _HEARTBEAT_INTERVAL:
                    print(
                        f"      ... running {elapsed}s / limit {timeout}s",
                        flush=True,
                    )
                    last_beat = now
                if timeout is not None and elapsed >= timeout:
                    proc.kill()
                    proc.wait()
                    ui.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
                    _show_captures(tail, seen_lines, verbose)
                    return False
                continue
            if item is None:
                # The child closed its output — trust EOF rather than racing
                # proc.poll(), which can lag process exit by a few ms and
                # otherwise cost one full heartbeat interval of dead waiting.
                got_eof = True
                break
            on_line(item)
            if deadline is not None and time.monotonic() >= deadline:
                proc.kill()
                proc.wait()
                ui.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
                _show_captures(tail, seen_lines, verbose)
                return False
        # Drain what the child wrote after the last poll / before EOF.
        time.sleep(0.05)
        while True:
            try:
                item = lines.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                on_line(item)
    except KeyboardInterrupt:
        proc.kill()
        proc.wait()
        ui.warn(f"Interrupted: {' '.join(cmd)}")
        raise

    # Reap the child BEFORE reading its exit code — proc.returncode stays
    # None until wait() lands, and None != 0 would read success as failure.
    rc = proc.wait()

    success = rc == 0
    if not success:
        _show_captures(tail, seen_lines, verbose)
    if verbose:
        elapsed = int(time.monotonic() - start)
        print(f"      (finished in {elapsed}s, exit {rc})", flush=True)
    # Success = child's own exit code, in BOTH check modes. The pre-streaming
    # runner behaved this way (check=False + returncode → bool) and callers
    # build fallback logic on it: the add-apt-repository attempt must read as
    # FAILED when Mint's fork rejects our options, or the HTTPS/IPv4 fallback
    # never fires. `check` only ever meant "suppress the raise", not
    # "lie about the result".
    return success


def _pump_lines(stream, sink):
    """Drain a child's stdout into a queue; None marks end-of-stream."""
    try:
        for line in iter(stream.readline, ""):
            sink.put(line.rstrip("\r\n"))
    finally:
        try:
            stream.close()
        except Exception:
            pass
        sink.put(None)


def _ensure_pipx(env):
    """Ensure pipx is available, installing via OS package manager if missing."""
    if shutil.which("pipx"):
        return True

    ui.step("pipx not found — attempting to install via OS package manager...")
    if env.os == "linux":
        if env.distro in ("ubuntu", "debian", "mint", "pop"):
            return _run(
                ["sudo", "apt", "install", "-y", *_APT_OPTIONS, "pipx"],
                timeout=PKG_TIMEOUT,
            )
        elif env.distro == "fedora":
            return _run(
                ["sudo", "dnf", "install", "-y", "pipx"], timeout=PKG_TIMEOUT
            )
    elif env.os == "macos":
        return _run(["brew", "install", "pipx"], timeout=PKG_TIMEOUT)

    ui.warn("Could not automatically install pipx. Please install it manually.")
    return False


def _ensure_7zip():
    """Ensure 7-Zip is available, installing via winget if missing."""
    if shutil.which("7z"):
        return True
    # Check common install paths
    for path in [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]:
        if os.path.isfile(path):
            return True

    ui.step("7-Zip not found — installing via winget...")
    return _run(
        [
            "winget",
            "install",
            "--id",
            "7zip.7zip",
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        timeout=PKG_TIMEOUT,
    )


def _find_7z():
    """Return the path to 7z.exe."""
    path = shutil.which("7z")
    if path:
        return path
    for candidate in [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


SHA256_HEX_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


def _fetch_latest_release(repo):
    """Fetch GitHub latest release metadata."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={"Accept": "application/json", "User-Agent": "mpv-config"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _select_release_asset(release, patterns):
    """Select an asset matching the first regex pattern."""
    assets = release.get("assets", [])
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for asset in assets:
            name = asset.get("name", "")
            if regex.search(name):
                return asset
    return None


def _human_bytes(num_bytes):
    """Compact byte count for progress lines ("999.0 B", "12.4 MB")."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class _InlineDownloadProgress:
    """In-place, single-line progress for binary HTTP downloads.

    Renders on a TTY while the transfer runs and is fully silent on piped
    output (curl | bash, CI logs) — matching the previous behavior there:

        > yt-dlp.exe  45% |##########.........|  8.4/18.7 MB  2.1 MB/s  ETA 5s

    Whole-transfer average speed keeps the readout stable; updates are
    throttled so a hot chunk cadence does not redraw faster than the eye.
    """

    BAR_WIDTH = 24

    def __init__(self, label, total=None, stdout=None, clock=time.monotonic,
                 update_interval=0.1, tick_interval=1.0):
        self.label = (label or "download")
        if len(self.label) > 40:
            self.label = self.label[:37] + "..."
        try:
            self.total = int(total) if total is not None and int(total) > 0 else None
        except (TypeError, ValueError):
            self.total = None
        self._stdout = stdout if stdout is not None else sys.stdout
        self._clock = clock
        self._interval = max(0.0, update_interval)
        self._tick_interval = max(0.0, tick_interval)
        self._done = 0
        self._started = None
        self._last_render = float("-inf")
        self._last_len = 0
        self._rendered = False
        self._stop_ticks = None
        self._tick_thread = None
        try:
            self._tty = bool(self._stdout.isatty())
        except Exception:
            self._tty = False

    def start(self):
        """Anchor the elapsed-time base (called when the transfer begins)."""
        if self._started is None:
            self._started = self._clock()
        self._stop_ticks_and_join()

    def settle(self):
        """First byte arrived: restart the elapsed clock on the body phase.

        Speed/ETA then reflect the actual transfer rate instead of being
        diluted by the (sometimes slow) connect time before it.
        """
        self._started = self._clock()
        self._stop_ticks_and_join()

    def start_connect_ticks(self):
        """Liveness during the connect phase (DNS/TLS/CDN), where no bytes flow.

        urlopen() blocks the main thread; a 30+ s connect previously looked
        identical to a hang. A tick thread re-renders 'connecting Ns' every
        second until the first byte arrives.
        """
        self._started = self._clock()
        self._stop_ticks_and_join()
        if not self._tty:
            return
        self._stop_ticks = threading.Event()
        self._write_line(self._connect_line())
        event = self._stop_ticks
        self._tick_thread = threading.Thread(
            target=self._tick_loop, args=(event,), daemon=True
        )
        self._tick_thread.start()

    def _tick_loop(self, stop_event):
        while not stop_event.wait(self._tick_interval):
            self._write_line(self._connect_line())

    def _connect_line(self):
        elapsed = self._clock() - self._started
        return f"> {self.label}  connecting" + (f" {int(elapsed)}s" if elapsed >= 1 else "")

    def _stop_ticks_and_join(self):
        event = self._stop_ticks
        if event is None:
            return
        self._stop_ticks = None
        event.set()
        thread = self._tick_thread
        self._tick_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def update(self, chunk_size):
        """Account for one received chunk; render when the throttle allows."""
        self.start()
        self._done += max(0, int(chunk_size))
        now = self._clock()
        if self._tty and now - self._last_render >= self._interval:
            self._render()

    def finish(self):
        """Final render at the real byte count, then close the line."""
        self._stop_ticks_and_join()
        if not self._tty:
            return
        self._render()
        if self._rendered:
            self._stdout.write("\n")
            self._stdout.flush()

    def abort(self):
        """Close the in-place line after a failure so logs stay readable."""
        self._stop_ticks_and_join()
        if self._tty and self._rendered:
            self._stdout.write("\n")
            self._stdout.flush()

    def _render(self):
        now = self._clock()
        self._last_render = now
        elapsed = now - self._started if self._started is not None else 0.0
        speed = self._done / elapsed if elapsed > 0 else 0.0
        speed_text = f"{_human_bytes(speed)}/s"

        parts = [f"> {self.label}"]
        if self.total and self._done <= self.total:
            pct = min(100, int(self._done * 100 / self.total))
            filled = int(self.BAR_WIDTH * self._done / self.total)
            bar = ui.S.BLOCK * filled + ui.S.LIGHT * (self.BAR_WIDTH - filled)
            parts.append(f"{pct:3d}% |{bar}|")
            parts.append(f"{_human_bytes(self._done)}/{_human_bytes(self.total)}")
            if speed > 0:
                eta = max(0, int((self.total - self._done) / speed))
                parts.append(f"{speed_text}  ETA {eta}s")
            else:
                parts.append(speed_text)
        else:
            parts.append(f"{_human_bytes(self._done)}")
            parts.append(speed_text)

        line = "  ".join(parts)
        self._write_line(line)

    def _write_line(self, line):
        """Overwrite the current console line in place (carriage return)."""
        pad = max(0, self._last_len - len(line))
        self._last_len = len(line)
        self._rendered = True
        if not self._tty:
            return
        try:
            self._stdout.write("\r" + line + " " * pad)
            self._stdout.flush()
        except Exception:
            # Closed/odd console → stop rendering, keep counting bytes.
            self._tty = False


def _create_tmp_file(dest_path):
    """Create a .mpvdl-* temp file next to dest_path, failing fast on denial.

    tempfile.mkstemp is a landmine on Windows: _mkstemp_inner catches
    PermissionError and keeps drawing new random names for eons when
    os.access(dir, W_OK) claims the directory writable but the ACL actually
    denies creation (C:\\Program Files\\mpv in a non-elevated shell).
    The installer then froze silently inside 'Downloading yt-dlp.exe...',
    with no temp file, no error and no timeout — the user cannot even tell
    it apart from a network stall. A bounded loop that raises one clear,
    actionable PermissionError beats both that freeze and the os.access lie.
    """
    dest_dir = os.path.dirname(dest_path) or "."
    for seq in range(32):
        tmp_path = os.path.join(dest_dir, f".mpvdl-{seq:02d}-{os.urandom(6).hex()}")
        try:
            fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            continue  # astronomically unlikely; bounded retries
        except PermissionError as exc:
            raise PermissionError(
                f"{dest_dir} is not writable for this user ({exc}). "
                "Re-run the installer from an elevated (Administrator) "
                "PowerShell to install into C:\\Program Files\\mpv."
            ) from exc
        return fd, tmp_path
    raise FileExistsError(f"No usable temporary file name found in {dest_dir}")


def _download_asset(url, dest_path, label=None, stdout=None):
    """Download an asset to dest_path atomically (tmp file + rename).

    Never leaves a half-written binary at dest when a download dies
    mid-flight — a truncated yt-dlp/alass would spawn-fail inside mpv until
    the next successful deploy.

    Streams in chunks (256 KiB) with an in-place progress readout on a TTY:
    the step previously relied on a bare urlretrieve that printed nothing,
    so a slow yt-dlp.exe fetch looked like a frozen installer. Piped output
    stays silent, exactly like before.
    """
    label = label or os.path.basename(dest_path) or "download"
    tmp_fd, tmp_path = _create_tmp_file(dest_path)
    os.close(tmp_fd)
    progress = _InlineDownloadProgress(label, stdout=stdout)
    request = urllib.request.Request(
        url, headers={"User-Agent": "mpv-config installer", "Accept-Encoding": "identity"}
    )
    try:
        # Liveness during the connect stretch (DNS/TLS/CDN), where no byte
        # progress exists yet; must run before urlopen() so a stalled
        # connection shows 'connecting Ns' instead of silence.
        progress.start_connect_ticks()
        # 60 s connect/read timeout: a dead CDN connection cannot strand the
        # installer forever with no output either way.
        resp = urllib.request.urlopen(request, timeout=60)
        progress.settle()
        try:
            length = resp.headers.get("Content-Length")
            try:
                length = int(length) if length else None
            except (TypeError, ValueError):
                length = None
            if length and length > 0:
                progress.total = length
            with open(tmp_path, "wb") as fh:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    progress.update(len(chunk))
        finally:
            resp.close()
        progress.finish()
        os.replace(tmp_path, dest_path)
    except Exception:
        progress.abort()
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _extract_zip(archive_path, dest_dir):
    """Extract a zip archive to dest_dir."""
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)


def _flatten_single_dir(dest_dir):
    """Flatten single top-level directory if present."""
    entries = os.listdir(dest_dir)
    if len(entries) != 1:
        return False
    inner = os.path.join(dest_dir, entries[0])
    if not os.path.isdir(inner):
        return False
    for item in os.listdir(inner):
        shutil.move(os.path.join(inner, item), os.path.join(dest_dir, item))
    shutil.rmtree(inner, ignore_errors=True)
    return True


def _find_bin_dir(root, expected_bins):
    """Find the directory containing any of the expected binaries."""
    for dirpath, _, filenames in os.walk(root):
        for name in expected_bins:
            if name in filenames:
                return dirpath
    return None


def _add_to_path(directory):
    """Add a directory to the user's PATH on Windows (persistent)."""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$p = [Environment]::GetEnvironmentVariable('PATH','User');"
                f"if ($p -notlike '*{directory}*') {{"
                f"  [Environment]::SetEnvironmentVariable('PATH', $p + ';{directory}', 'User');"
                f"  Write-Output 'added'"
                f"}} else {{ Write-Output 'exists' }}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if "added" in result.stdout:
            ui.success(f"Added {directory} to user PATH")
            # Also update current process PATH so mpv is findable immediately
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + directory
            broadcast_cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "$sig=@'\n"
                '[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]\n'
                "public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);\n"
                "'@; "
                "Add-Type -MemberDefinition $sig -Name NativeMethods -Namespace Win32; "
                "$HWND_BROADCAST = [intptr]0xffff; "
                "$WM_SETTINGCHANGE = 0x1A; "
                "$result = [uintptr]::Zero; "
                "[Win32.NativeMethods]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [uintptr]::Zero, 'Environment', 2, 5000, [ref]$result) | Out-Null",
            ]
            broadcast_result = subprocess.run(
                broadcast_cmd, capture_output=True, text=True, timeout=10
            )
            if broadcast_result.returncode != 0:
                ui.warn("Failed to broadcast PATH change to other processes.")
        else:
            ui.info(f"{directory} already in PATH")
        return True
    except Exception as e:
        ui.warn(f"Could not update PATH: {e}")
        return False


def _fetch_release(repo, pin=None):
    """Fetch GitHub release metadata (latest or pinned tag)."""
    if pin:
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{pin}"
    else:
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={"Accept": "application/json", "User-Agent": "mpv-config"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _install_github_asset(name, info, env):
    """
    Download a GitHub release asset (.7z), verify SHA-256, extract, PATH.

    SHA-256 verification strategy (first source that yields a hex digest wins):
       1. asset["digest"]  — the canonical source since June 2025. GitHub
         computes this on upload and exposes it on every asset. Both zhongfly
         and shinchiro releases carry it. No extra HTTP round-trip.
       2. <asset>.sha256  — companion file. Older releases / some forks use
         this convention. We keep it for backward compatibility.
       3. sha256.txt      — single aggregated checksum file (used by
         zhongfly). Downloaded once and parsed for our asset name.
       4. No SHA found    — emit a warning and continue, UNLESS the env var
         MPV_REQUIRE_SHA256=1 is set, in which case we abort. HTTPS already
         provides transport integrity; this matches Scoop/winget behavior.

    Asset selection strategy:
       - Read per-repo patterns from info["asset_patterns"][<repo>].
      - Pick the AVX2 variant if env.has_avx2, else the plain variant.
      - If AVX2 was requested but no v3 asset exists in this release, warn
        and fall back to the plain variant (instead of failing outright).
      - Last-resort fallback uses info["asset_pattern_generic"].
    """
    import hashlib

    repo = info["repo"]
    fallback_repo = info.get("fallback_repo")
    pin = info.get("pin")
    install_dir = info.get("install_dir", r"C:\Program Files\mpv")
    patterns_map = info.get("asset_patterns", {}) or {}
    generic_pat = info.get("asset_pattern_generic")
    require_sha = os.environ.get("MPV_REQUIRE_SHA256") == "1"

    def _digest_from_asset(asset):
        """Extract sha256 hex from GitHub's `digest` field on an asset."""
        d = asset.get("digest")
        if isinstance(d, str) and d.lower().startswith("sha256:"):
            hex_part = d.split(":", 1)[1].strip()
            if SHA256_HEX_PATTERN.fullmatch(hex_part):
                return hex_part.lower()
        return None

    def _digest_from_companion(assets, asset_name):
        """Look for <asset_name>.sha256 in the release assets."""
        for a in assets:
            if a.get("name") == f"{asset_name}.sha256":
                try:
                    with urllib.request.urlopen(a["browser_download_url"], timeout=15) as resp:
                        body = resp.read().decode("utf-8", errors="replace").strip()
                    first = body.split()[0] if body else ""
                    if SHA256_HEX_PATTERN.fullmatch(first):
                        return first.lower()
                except Exception:
                    pass
        return None

    def _digest_from_aggregate(assets, asset_name):
        """
        Look for an aggregate checksum file (sha256.txt / SHA256SUMS / etc.)
        and find the line matching our asset.
        """
        candidates = ("sha256.txt", "SHA256SUMS", "SHA256SUMS.txt", "checksums.txt")
        for a in assets:
            if a.get("name") in candidates:
                try:
                    with urllib.request.urlopen(a["browser_download_url"], timeout=15) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                except Exception:
                    continue
                for line in body.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and asset_name in parts[-1]:
                        if SHA256_HEX_PATTERN.fullmatch(parts[0]):
                            return parts[0].lower()
        return None

    def _select_asset(release, target_repo):
        """Pick (asset, label) for this repo + AVX2 preference, with fallbacks."""
        assets = release.get("assets", [])
        repo_pats = patterns_map.get(target_repo, {})

        # Build the ordered list of (label, regex) to try.
        attempts = []
        if env.has_avx2 and repo_pats.get("avx2"):
            attempts.append(("v3 (AVX2)", repo_pats["avx2"]))
            # If AVX2 build is missing, gracefully accept the plain build.
            if repo_pats.get("plain"):
                attempts.append(
                    ("x86_64 (AVX2 build unavailable, using plain)", repo_pats["plain"])
                )
        elif repo_pats.get("plain"):
            attempts.append(("x86_64", repo_pats["plain"]))
            # If user truly has AVX2 but we couldn't detect it, still try v3
            # opportunistically — costs nothing if it doesn't match.
            if repo_pats.get("avx2"):
                attempts.append(("v3 (AVX2, opportunistic)", repo_pats["avx2"]))

        # Generic last-resort pattern.
        if generic_pat:
            attempts.append(("generic", generic_pat))

        for label, pat in attempts:
            regex = re.compile(pat, re.IGNORECASE)
            for a in assets:
                if regex.match(a.get("name", "")):
                    return a, label
        return None, None

    def _attempt_repo(target_repo):
        ui.step(f"Fetching release from {target_repo}...")
        try:
            release = _fetch_release(target_repo, pin=pin)
        except Exception as e:
            ui.error(f"Failed to fetch release info: {e}")
            return False

        asset, label = _select_asset(release, target_repo)
        if not asset:
            ui.error(f"No matching mpv asset found in {target_repo} release")
            return False

        download_url = asset["browser_download_url"]
        asset_name = asset["name"]
        asset_size_mb = asset.get("size", 0) / (1024 * 1024)
        assets = release.get("assets", [])

        # Resolve expected SHA-256 from the most authoritative source available.
        expected_sha = (
            _digest_from_asset(asset)
            or _digest_from_companion(assets, asset_name)
            or _digest_from_aggregate(assets, asset_name)
        )

        if not expected_sha:
            if require_sha:
                ui.error(
                    f"No SHA-256 available for {asset_name} and "
                    "MPV_REQUIRE_SHA256=1 is set — aborting."
                )
                return False
            ui.warn(
                f"No SHA-256 metadata found for {asset_name}. Continuing "
                "(HTTPS still guarantees transport integrity). Set "
                "MPV_REQUIRE_SHA256=1 to make this a hard error."
            )

        # 7-Zip is needed for .7z extraction.
        if not _ensure_7zip():
            ui.error("Cannot extract .7z archive without 7-Zip.")
            return False
        sevenz = _find_7z()
        if not sevenz:
            ui.error("7z.exe not found even after installation.")
            return False

        os.makedirs(install_dir, exist_ok=True)
        archive_path = os.path.join(install_dir, asset_name)

        ui.step(f"Downloading {asset_name} ({label}, {asset_size_mb:.1f} MB)...")
        try:
            _download_asset(download_url, archive_path, asset_name)
        except Exception as e:
            ui.error(f"Download failed: {e}")
            return False

        # Verify SHA-256 if we have an expected value.
        if expected_sha:
            try:
                h = hashlib.sha256()
                with open(archive_path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                actual = h.hexdigest().lower()
                if actual != expected_sha.lower():
                    ui.error(
                        f"SHA-256 mismatch for {asset_name}\n"
                        f"  expected: {expected_sha}\n"
                        f"  actual:   {actual}"
                    )
                    try:
                        os.remove(archive_path)
                    except OSError:
                        pass
                    return False
                ui.success(f"SHA-256 verified ({expected_sha[:16]}…)")
            except Exception as e:
                ui.error(f"SHA-256 verification error: {e}")
                try:
                    os.remove(archive_path)
                except OSError:
                    pass
                return False

        ui.step(f"Extracting to {install_dir}...")
        ok = _run([sevenz, "x", "-y", f"-o{install_dir}", archive_path])
        if not ok:
            ui.error("Extraction failed.")
            return False

        try:
            os.remove(archive_path)
        except OSError:
            pass

        _flatten_single_dir(install_dir)
        _add_to_path(install_dir)

        if env.os == "windows":
            try:
                from deploy.deployer import ensure_windows_shortcuts

                ensure_windows_shortcuts(env)
            except Exception:
                pass

        ui.success(f"mpv {label} installed to {install_dir}")
        return True

    ok = _attempt_repo(repo)
    if not ok and fallback_repo:
        ui.warn(f"Primary mpv repo failed, trying fallback: {fallback_repo}")
        ok = _attempt_repo(fallback_repo)
    return ok


def _install_github_release_zip(name, info, env):
    """Download a GitHub release zip asset and extract to install_dir."""
    repo = info.get("repo")
    install_dir = info.get("install_dir")
    patterns = info.get("asset_patterns") or []
    if not repo or not install_dir or not patterns:
        ui.error(f"{name}: missing repo/install_dir/asset_patterns for github_release_zip")
        return False

    ui.step(f"Fetching latest release from {repo}...")
    try:
        release = _fetch_latest_release(repo)
    except Exception as e:
        ui.error(f"Failed to fetch release info: {e}")
        return False

    asset = _select_release_asset(release, patterns)
    if not asset:
        ui.error(f"No matching asset found for {name} in {repo} release")
        return False

    download_url = asset["browser_download_url"]
    asset_name = asset["name"]
    asset_size_mb = asset.get("size", 0) / (1024 * 1024)

    ui.step(f"Downloading {asset_name} ({asset_size_mb:.1f} MB)...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, asset_name)
            _download_asset(download_url, archive_path)
            if os.path.isdir(install_dir):
                shutil.rmtree(install_dir)
            os.makedirs(install_dir)
            _extract_zip(archive_path, install_dir)
    except Exception as e:
        ui.error(f"Download or extraction failed: {e}")
        return False

    _flatten_single_dir(install_dir)

    bin_dir = None
    bin_subdir = info.get("bin_subdir")
    if bin_subdir:
        candidate = os.path.join(install_dir, bin_subdir)
        if os.path.isdir(candidate):
            bin_dir = candidate

    expected_bins = info.get("expected_bins") or []
    if not bin_dir and expected_bins:
        bin_dir = _find_bin_dir(install_dir, expected_bins)

    if env.os == "windows":
        _add_to_path(bin_dir or install_dir)

    ui.success(f"{name}: installed to {install_dir}")
    return True


def _install_github_release_file(name, info, env):
    """Download a GitHub release asset file to install_dir."""
    repo = info.get("repo")
    install_dir = info.get("install_dir")
    patterns = info.get("asset_patterns") or []
    if not repo or not install_dir or not patterns:
        ui.error(f"{name}: missing repo/install_dir/asset_patterns for github_release_file")
        return False

    ui.step(f"Fetching latest release from {repo}...")
    try:
        release = _fetch_latest_release(repo)
    except Exception as e:
        ui.error(f"Failed to fetch release info: {e}")
        return False

    asset = _select_release_asset(release, patterns)
    if not asset:
        ui.error(f"No matching asset found for {name} in {repo} release")
        return False

    dest_name = info.get("dest_name") or asset["name"]
    os.makedirs(install_dir, exist_ok=True)
    dest_path = os.path.join(install_dir, dest_name)

    ui.step(f"Downloading {asset['name']}...")
    try:
        _download_asset(asset["browser_download_url"], dest_path)
    except Exception as e:
        ui.error(f"Download failed: {e}")
        return False

    if env.os != "windows":
        os.chmod(dest_path, 0o755)
        # The install dir (e.g. a freshly created ~/.local/bin) may not be on
        # the PATH of the current session. Best effort: symlink into
        # /usr/local/bin so the binary is immediately callable; harmless if
        # sudo is unavailable (verify reports it politely).
        if not shutil.which(dest_name):
            _run(
                ["sudo", "ln", "-sf", dest_path, os.path.join("/usr/local/bin", dest_name)],
                check=False,
                timeout=60,
            )
    else:
        _add_to_path(install_dir)

    _write_refresh_stamp(info)
    ui.success(f"{name}: installed to {dest_path}")
    return True


def _install_direct_url(name, info, env):
    """Download a direct URL asset to install_dir."""
    url = info.get("url")
    install_dir = info.get("install_dir")
    if not url or not install_dir:
        ui.error(f"{name}: missing url/install_dir for direct_url")
        return False

    dest_name = info.get("dest_name") or os.path.basename(url)
    os.makedirs(install_dir, exist_ok=True)
    dest_path = os.path.join(install_dir, dest_name)

    ui.step(f"Downloading {dest_name}...")
    try:
        _download_asset(url, dest_path)
    except Exception as e:
        ui.error(f"Download failed: {e}")
        return False

    if env.os != "windows":
        os.chmod(dest_path, 0o755)
    else:
        _add_to_path(install_dir)

    _write_refresh_stamp(info)
    ui.success(f"{name}: installed to {dest_path}")
    return True


def _os_release_id():
    """First ID= from /etc/os-release ('ubuntu', 'linuxmint', 'debian', …)."""
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("ID="):
                    return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return ""


def _mpv_install_gate(installed_ok):
    """Post-install honesty gate for the mpv upgrade path.

    apt can "successfully" install the DISTRO build (Ubuntu 24.04: 0.37)
    while the upgrade itself failed — that is below MPV_MINIMUM_VERSION and
    must not be reported as ok (a green step after an unfulfilled upgrade
    promise hides the problem). Returning False routes the flow into the
    tolerate-mpv branch, which explains the adapted config and how to
    complete the upgrade.
    """
    if not installed_ok:
        return False
    version = probe_mpv_version()
    if version is None or version < MPV_MINIMUM_VERSION:
        if version is None:
            detail = "no mpv detected after install — the upgrade did not take effect"
        else:
            detail = (
                f"still version {'.'.join(map(str, version))} — the PPA upgrade did not "
                "take effect (add-apt-repository could not reach ppa.launchpadcontent.net)"
            )
        ui.warn(
            f"{detail}; deploying a config adapted to the installed mpv. Retry later, "
            "or upgrade mpv manually and re-run `mpv-config install` to restore the "
            "full option set."
        )
        if version is None:
            # Nothing to adapt to — genuinely failed.
            ui.error("mpv is not installed; playback will not work until it is.")
        return False
    return True


def _capture(cmd, timeout=60):
    """Run a command capturing output; returns (ok, stdout_text)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return proc.returncode == 0, (proc.stdout or "")


def _ubuntu_series():
    """Ubuntu base-series codename ('noble', 'jammy', …) from /etc/os-release.

    Mint/Pop rename VERSION_CODENAME after themselves ('wilma', …), so the
    Debian-family UBUNTU_CODENAME key is preferred — it is what the PPA's
    dists/ layout actually uses.
    """
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return ""
    for key in ("UBUNTU_CODENAME", "VERSION_CODENAME"):
        match = re.search(rf'^{key}="?([^"\n]+)"?\s*$', content, re.MULTILINE)
        if match:
            return match.group(1).strip().lower()
    return ""


def _direct_ppa_register():
    """Register ppa:ubuntuhandbook1/mpv using ONLY plain HTTPS over IPv4.

    WHY it exists: the struggling Mint machine proved https://
    ppa.launchpadcontent.net answers 200 over IPv4 while every dependent
    step of add-apt-repository can still hang — minimal installs lack the
    tool entirely, and its Python-side negotiation (Launchpad API + HKP
    keyserver) is exactly what IPv6-blackholed networks stall for minutes
    on. This rebuilds the same result with the proven transport:

      1. curl -4 → Launchpad API for the PPA's signing key fingerprint.
      2. curl -4 → keyserver HTTPS armor for that fingerprint.
      3. gpg --dearmor into /usr/share/keyrings (signed-by keyring).
      4. Write the signed-by sources file for the detected series.
    """
    series = _ubuntu_series()
    if not series:
        ui.warn("No Ubuntu series codename in /etc/os-release — direct PPA registration unavailable.")
        return False
    ui.step(f"Registering PPA directly for series {series} (HTTPS/IPv4-only path)...")
    ui.step("Fetching the PPA signing-key fingerprint (Launchpad API, HTTPS/IPv4)...")
    ok, body = _capture(
        [
            "curl",
            "-m",
            "30",
            "-4",
            "-fsSL",
            f"https://api.launchpad.net/1.0/~{PPA_OWNER}/+archive/ubuntu/{PPA_ARCHIVE}",
        ]
    )
    if not ok:
        ui.warn("Launchpad API unreachable even over IPv4 — direct registration failed.")
        return False
    fp_match = re.search(r'"signing_key_fingerprint":\s*"([0-9a-fA-F]{40})"', body)
    if not fp_match:
        ui.warn("PPA metadata is missing its signing key fingerprint — direct registration failed.")
        return False
    fingerprint = fp_match.group(1)
    ui.step("Downloading the PPA signing key (HTTPS keyserver, IPv4)...")
    ok, armor = _capture(
        [
            "curl",
            "-m",
            "30",
            "-4",
            "-fsSL",
            f"https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x{fingerprint}",
        ]
    )
    if not ok or "BEGIN PGP PUBLIC KEY BLOCK" not in armor:
        ui.warn("Signing key not obtainable over the HTTPS keyserver — direct registration failed.")
        return False
    keyring = f"/usr/share/keyrings/{PPA_OWNER}-{PPA_ARCHIVE}-archive-keyring.gpg"
    armor_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".asc", delete=False) as fh:
            fh.write(armor)
            armor_path = fh.name
        if not _run(
            ["sudo", "gpg", "--batch", "--yes", "--dearmor", "--output", keyring, armor_path],
            check=False,
        ):
            ui.warn("Could not write the PPA keyring — direct registration failed.")
            return False
    finally:
        if armor_path and os.path.isfile(armor_path):
            try:
                os.unlink(armor_path)
            except OSError:
                pass
    sources_path = f"/etc/apt/sources.list.d/{PPA_OWNER}-ubuntu-{PPA_ARCHIVE}-{series}.list"
    sources_line = (
        f"deb [signed-by={keyring}] "
        f"https://ppa.launchpadcontent.net/{PPA_OWNER}/{PPA_ARCHIVE}/ubuntu {series} main\n"
    )
    if not _run(
        [
            "/bin/sh",
            "-c",
            f"printf '%s' {shlex.quote(sources_line)} | sudo tee {shlex.quote(sources_path)} >/dev/null",
        ],
        check=False,
    ):
        ui.warn("Could not write the PPA sources file — direct registration failed.")
        return False
    ui.success(f"PPA registered directly → {sources_path}")
    return True


def _install_mpv_latest(env):
    """Install or upgrade mpv to the latest stable release (classic .deb).

    Ubuntu/Mint repos ship outdated mpv (Noble: 0.37) that lacks options the
    templates use (clipboard-monitor, sub-ass-use-video-data).
    ppa:ubuntuhandbook1/mpv publishes the latest stable mpv for Ubuntu
    22.04/24.04/25.x on amd64/arm64 (Mint 22.x/21.x uses the Ubuntu base
    series, so the PPA works there too).  Debian has no matching PPA series
    and stays on its own apt build.

    Registration order (struggling-Mint diagnostics drove this):
      1. add-apt-repository with a SHORT budget — healthy machines register
         in seconds; a wedging attempt (IPv6-blackhole / minimal install)
         must fail fast, not burn the half-hour budget.
      2. _direct_ppa_register — HTTPS/IPv4-only rebuild of the same result,
         needing neither the tool nor its Python-side negotiation.
      3. Installing software-properties-common + one more tool attempt —
         only when both of the above failed.
    The cache refresh that follows is exactly ONE apt-get update (add-apt-
    repository's own refresh would re-update every configured source and
    was the step that timed out past 300 s originally).
    """
    if env.os == "linux" and _os_release_id() not in ("ubuntu", "linuxmint", "pop", ""):
        # Debian & derivatives: ubuntuhandbook1's PPA has no matching
        # series there — stay on the distro's own mpv build.
        installed = _run(
            ["sudo", "apt", "install", "-y", *_APT_OPTIONS, "mpv"],
            check=False,
            timeout=PKG_TIMEOUT,
        )
        return _mpv_install_gate(installed)

    ui.step(
        "Registering ppa:ubuntuhandbook1/mpv (tool attempt, 5-min cap, then an IPv4-only fallback)..."
    )
    added = False
    if shutil.which("add-apt-repository"):
        # -n: register the source only; the cache refresh below is ours.
        added = _run(
            ["sudo", "add-apt-repository", "-y", "-n", f"ppa:{PPA_OWNER}/{PPA_ARCHIVE}"],
            check=False,
            timeout=300,
        )
    if not added:
        ui.info(
            "Tool attempt did not register the PPA — trying the HTTPS/IPv4-only path..."
        )
        added = _direct_ppa_register()
    if not added and not shutil.which("add-apt-repository"):
        # Last resort: bootstrap the standard tool and let it try once.
        _run(
            ["sudo", "apt-get", "install", "-y", *_APT_OPTIONS, "software-properties-common"],
            check=False,
            timeout=PKG_TIMEOUT,
        )
        if shutil.which("add-apt-repository"):
            added = _run(
                ["sudo", "add-apt-repository", "-y", "-n", f"ppa:{PPA_OWNER}/{PPA_ARCHIVE}"],
                check=False,
                timeout=300,
            )
    if not added:
        ui.warn(
            "Could not add ppa:ubuntuhandbook1/mpv — mpv may remain an old distro build."
        )
    ui.step(
        "Refreshing apt cache (single pass; the PPA index downloads over IPv4)..."
    )
    _run(
        ["sudo", "apt-get", "update", *_APT_OPTIONS],
        check=False,
        timeout=PKG_TIMEOUT,
    )
    ui.step("Installing mpv from the PPA (apt shows its own download progress)...")
    installed = _run(
        ["sudo", "apt-get", "install", "-y", *_APT_OPTIONS, "mpv"],
        timeout=PKG_TIMEOUT,
    )
    return _mpv_install_gate(installed)


def _install_uv(name, info, env):
    """Install uv with OS-specific fallbacks."""
    if shutil.which("uv"):
        return True

    if env.os == "macos":
        if shutil.which("brew") and _run(["brew", "install", "uv"], timeout=PKG_TIMEOUT):
            return True
    elif env.os == "linux":
        if env.distro == "arch":
            if _run(
                ["sudo", "pacman", "-S", "--noconfirm", "--needed", "uv"],
                timeout=PKG_TIMEOUT,
            ):
                return True
        elif env.distro in ("ubuntu", "debian", "mint", "pop"):
            if _run(
                ["sudo", "apt", "install", "-y", *_APT_OPTIONS, "uv"], timeout=PKG_TIMEOUT
            ):
                return True
        elif env.distro == "fedora":
            if _run(["sudo", "dnf", "install", "-y", "uv"], timeout=PKG_TIMEOUT):
                return True

    if env.os == "windows":
        if info.get("repo") and info.get("asset_patterns"):
            return _install_github_release_zip(name, info, env)
        ui.warn("uv install on Windows requires a release asset configuration.")
        return False

    ui.step("Installing uv via official installer script...")
    ok = _run(["/bin/sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], timeout=900)
    if ok:
        local_bin = os.path.expanduser("~/.local/bin")
        if local_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
    return ok


def _uninstall_uv(info, env):
    """Uninstall uv with OS-specific fallbacks."""
    if env.os == "macos" and shutil.which("brew"):
        return _run(["brew", "uninstall", "uv"], check=False)
    if env.os == "linux":
        if env.distro == "arch":
            return _run(["sudo", "pacman", "-Rns", "--noconfirm", "uv"], check=False)
        if env.distro in ("ubuntu", "debian", "mint", "pop"):
            return _run(["sudo", "apt", "remove", "-y", "uv"], check=False)
        if env.distro == "fedora":
            return _run(["sudo", "dnf", "remove", "-y", "uv"], check=False)

    if shutil.which("uv"):
        return _run(["uv", "self", "uninstall"], check=False)

    uv_bin = os.path.expanduser("~/.local/bin/uv")
    if os.path.isfile(uv_bin):
        try:
            os.remove(uv_bin)
            return True
        except OSError:
            return False
    return False


def _install_uv_tool(info, env):
    """Install a Python tool via uv tool install."""
    pkg = info.get("pkg")
    uv_python = info.get("uv_python")
    uv_no_fallback = info.get("uv_no_fallback", False)
    if not pkg:
        ui.error("uv_tool missing pkg")
        return False

    if not shutil.which("uv"):
        uv_info = SYSTEM_DEPS.get("uv", {}).get(env.platform_key, {})
        uv_method = uv_info.get("method")
        if uv_method == "github_release_zip":
            ok = _install_github_release_zip("uv", uv_info, env)
        elif uv_method == "github_release_file":
            ok = _install_github_release_file("uv", uv_info, env)
        elif uv_method == "direct_url":
            ok = _install_direct_url("uv", uv_info, env)
        else:
            ok = _install_uv("uv", uv_info, env)
        if not ok:
            if uv_no_fallback:
                ui.warn("uv not available; skipping pipx fallback to avoid source builds.")
                return False
            ui.warn("uv not available; falling back to pipx if possible")
            if not _ensure_pipx(env):
                return False
            return _run(["pipx", "install", pkg])

    bin_dir = info.get("bin_dir")
    if not bin_dir and env.os != "windows":
        bin_dir = os.path.expanduser("~/.local/bin")
    if bin_dir:
        os.makedirs(bin_dir, exist_ok=True)

    cmd = ["uv", "tool", "install", pkg]
    if uv_python:
        ui.info(f"{pkg}: using uv with Python {uv_python} to prefer prebuilt wheels")
        cmd += ["--python", uv_python]
    cmd_env = os.environ.copy()
    if bin_dir:
        cmd_env["UV_TOOL_BIN_DIR"] = bin_dir
    ok = _run(cmd, env=cmd_env)
    if not ok:
        if uv_no_fallback:
            ui.warn("uv tool install failed; build fallbacks disabled for this tool.")
            return False
        ui.warn("uv tool install failed; trying pipx fallback")
        if not _ensure_pipx(env):
            return False
        ok = _run(["pipx", "install", pkg])

    if ok and bin_dir:
        if env.os == "windows":
            _add_to_path(bin_dir)
        else:
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return ok


def _uninstall_uv_tool(info, env):
    """Uninstall a Python tool installed via uv tool."""
    pkg = info.get("pkg")
    if not pkg:
        return False

    bin_dir = info.get("bin_dir")
    cmd_env = os.environ.copy()
    if bin_dir:
        cmd_env["UV_TOOL_BIN_DIR"] = bin_dir

    ok = False
    if shutil.which("uv"):
        ok = _run(["uv", "tool", "uninstall", pkg], check=False, env=cmd_env)
    if not ok and shutil.which("pipx"):
        ok = _run(["pipx", "uninstall", pkg], check=False)

    bin_dir = info.get("bin_dir")
    bin_names = info.get("bin_names") or []
    if bin_dir and bin_names:
        for name in bin_names:
            path = os.path.join(bin_dir, name)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
    return ok


# --- CachyOS x86-64-v3/v4 optimized repos ------------------------------------
# CachyOS rebuilds every Arch package for newer CPUs (cachyos-v3 /
# cachyos-extra-v3 for x86-64-v3, the v4/znver4 tiers for v4 CPUs). When the
# optimized repos are enabled, a plain `pacman -S mpv` automatically picks the
# AVX2 build because pacman prefers the first repo that carries the package.
# Sections inserted here mirror the official CachyOS repo script
# (github.com/CachyOS/cachyos-repo-add-script, install-repo.awk): tiered repos
# go ahead of every existing repo section. Unlike that script we avoid pinned
# .zst package URLs and full `pacman -Syu` upgrades: the keyring/mirrorlist
# packages come from pacman itself and only the package DB is refreshed.

_CACHYOS_V3_REPOS = {
    "cachyos-v3",
    "cachyos-core-v3",
    "cachyos-extra-v3",
    "cachyos-testing-v3",
}
_CACHYOS_V4_REPOS = {
    "cachyos-v4",
    "cachyos-core-v4",
    "cachyos-extra-v4",
    "cachyos-testing-v4",
    "cachyos-znver4",
    "cachyos-core-znver4",
    "cachyos-extra-znver4",
}
_CACHYOS_MIRRORLIST_PACKAGES = (
    "cachyos-keyring",
    "cachyos-mirrorlist",
    "cachyos-v3-mirrorlist",
    "cachyos-v4-mirrorlist",
)


def _x86_64_isa_level(loader=None):
    """Return the machine's x86-64 microarchitecture level ("v3"/"v4"/"").

    Uses the dynamic loader's advertised ISA support — exactly what the
    official CachyOS repo script probes. Returns "" on non-x86_64 or
    non-Linux machines so callers skip cleanly.
    """
    loader = loader or "/lib64/ld-linux-x86-64.so.2"
    try:
        proc = subprocess.run(
            [loader, "--help"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""
    text = (proc.stdout or "") + (proc.stderr or "")
    # glibc prints lines like "  x86-64-v4 (supported, searched)".
    if "x86-64-v4 (supported, searched)" in text:
        return "v4"
    if "x86-64-v3 (supported, searched)" in text:
        return "v3"
    return ""


def _pacman_enabled_repos(conf_text):
    """Set of uncommented [repo] section names in a pacman.conf text."""
    enabled = set()
    for line in conf_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            enabled.add(stripped[1:-1].strip())
    return enabled


def _is_cachyos_host(os_release_text=None):
    """True when this machine is a CachyOS install (os-release mentions it)."""
    if os_release_text is None:
        try:
            with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as fh:
                os_release_text = fh.read()
        except OSError:
            return False
    return "cachyos" in os_release_text.lower()


def _cachyos_tier_block(tier):
    """pacman.conf lines for a tier's optimized repos (official layout)."""
    if tier == "v4":
        mirror = "/etc/pacman.d/cachyos-v4-mirrorlist"
        tier_repos = ["[cachyos-v4]", "[cachyos-core-v4]", "[cachyos-extra-v4]"]
    else:
        mirror = "/etc/pacman.d/cachyos-v3-mirrorlist"
        tier_repos = ["[cachyos-v3]", "[cachyos-core-v3]", "[cachyos-extra-v3]"]
    lines = ["", f"# x86-64-{tier} optimized CachyOS repos (added by mpv-config deployer)."]
    for repo in tier_repos:
        lines.append(repo)
        lines.append(f"Include = {mirror}")
        lines.append("")
    return lines


def _ensure_cachyos_optimized_repos(
    env,
    conf_path="/etc/pacman.conf",
    os_release_text=None,
    pacman_d_dir="/etc/pacman.d",
    tier=None,
):
    """Best effort: make pacman prefer x86-64-v3/v4 optimized CachyOS builds.

    Only acts on CachyOS machines reporting a supported ISA level. Inserts the
    tier repo sections ahead of everything else in pacman.conf (with a backup
    at <conf>.mpv-config.bak) and refreshes the package DB. Returns True when
    optimized repos are (or already were) enabled. Any failure is non-fatal:
    pacman keeps using the generic repos.
    """
    if env.os != "linux" or env.platform_key != "arch":
        return False
    if not _is_cachyos_host(os_release_text):
        return False
    tier = tier or _x86_64_isa_level()
    if not tier:
        return False

    tier_repos = _CACHYOS_V4_REPOS if tier == "v4" else _CACHYOS_V3_REPOS
    try:
        with open(conf_path, "r", encoding="utf-8", errors="replace") as fh:
            conf_text = fh.read()
    except OSError as exc:
        ui.warn(f"CachyOS repos: cannot read {conf_path}: {exc}")
        return False

    if _pacman_enabled_repos(conf_text) & tier_repos:
        return True  # already optimized

    ui.step(f"CachyOS: enabling x86-64-{tier} optimized repos before package installs...")
    ok = _run(
        ["sudo", "pacman", "-S", "--noconfirm", "--needed", *_CACHYOS_MIRRORLIST_PACKAGES],
        check=False,
        timeout=PKG_TIMEOUT,
    )
    if not ok:
        # One missing package name should not sink the whole transaction.
        for pkg in _CACHYOS_MIRRORLIST_PACKAGES:
            _run(
                ["sudo", "pacman", "-S", "--noconfirm", "--needed", pkg],
                check=False,
                timeout=PKG_TIMEOUT // 4,
            )
    include_name = f"cachyos-{tier}-mirrorlist"
    if not os.path.isfile(os.path.join(pacman_d_dir, include_name)):
        ui.warn(
            f"CachyOS repos: {include_name} still missing — keeping default package sources."
        )
        return False

    lines = conf_text.splitlines()
    insert_at = -1
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped[1:-1].strip() == "options":
                continue
            insert_at = idx
            break
    if insert_at < 0:
        ui.warn("CachyOS repos: no repo sections found in pacman.conf")
        return False

    new_lines = lines[:insert_at] + _cachyos_tier_block(tier) + lines[insert_at:]
    new_text = "\n".join(new_lines) + ("\n" if conf_text.endswith("\n") else "")

    fd, tmp_path = tempfile.mkstemp(prefix="pacman.conf.", suffix=".mpvconfig", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_text)
        if not _run(["sudo", "cp", conf_path, conf_path + ".mpv-config.bak"], timeout=60):
            return False
        if not _run(["sudo", "cp", tmp_path, conf_path], timeout=60):
            return False
        _run(["sudo", "chmod", "644", conf_path], check=False, timeout=60)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Refresh the package DB so the new repos resolve immediately. Avoids a
    # full system upgrade (-u) which a config deployer must never trigger.
    _run(["sudo", "pacman", "-Sy"], timeout=PKG_TIMEOUT)
    ui.success(
        f"CachyOS x86-64-{tier} optimized repos enabled — pacman installs now prefer optimized builds"
    )
    return True


def _install_aur_fallback(name, dep_info, env):
    """Install from a prebuilt source when the AUR path is unusable.

    The registry can carry a "fallback" install info dict (same shape as a
    platform entry, e.g. github_release_file for alass) either on the platform
    entry or at the top level. Used when the AUR helper is missing or the
    package failed to build.
    """
    platform = env.platform_key
    info = dep_info.get(platform) or {}
    fallback = info.get("fallback") or dep_info.get("fallback") or {}
    if not fallback.get("method"):
        return False
    ui.info(f"{name}: falling back to '{fallback['method']}' installer")
    synthetic = {k: v for k, v in dep_info.items() if k != "fallback"}
    if dep_info.get("fallback") is not None:
        synthetic.pop("fallback", None)
    synthetic[platform] = fallback
    return _install_one(name, synthetic, env)


def _install_one(name, dep_info, env, mpv_version=None):
    """Install a single dependency using the appropriate method."""
    platform = env.platform_key

    # Get platform-specific install info, fallback to 'all'
    info = dep_info.get(platform, dep_info.get("all"))
    if not info:
        ui.warn(f"No install method for {name} on {platform}")
        return False
    if name == "mpv" and mpv_version:
        info = {**info, "pin": mpv_version}

    method = info["method"]

    if method == "pacman":
        if info.get("prefer_optimized_repo"):
            _ensure_cachyos_optimized_repos(env)
        return _run(
            ["sudo", "pacman", "-S", "--noconfirm", "--needed", info["pkg"]],
            timeout=PKG_TIMEOUT,
        )

    elif method == "apt":
        return _run(
            ["sudo", "apt", "install", "-y", *_APT_OPTIONS, info["pkg"]],
            timeout=PKG_TIMEOUT,
        )

    elif method == "ppa":
        # Ubuntu/Mint apt repos ship ancient mpv (Noble: 0.37) that fails on
        # options this config requires — see _install_mpv_latest.
        return _install_mpv_latest(env)

    elif method == "dnf":
        return _run(["sudo", "dnf", "install", "-y", info["pkg"]], timeout=PKG_TIMEOUT)

    elif method == "brew":
        return _run(["brew", "install", info["pkg"]], timeout=PKG_TIMEOUT)

    elif method == "winget":
        return _run(
            [
                "winget",
                "install",
                "--id",
                info["id"],
                "-e",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            timeout=PKG_TIMEOUT,
        )

    elif method == "github_asset":
        return _install_github_asset(name, info, env)

    elif method == "github_release_zip":
        return _install_github_release_zip(name, info, env)

    elif method == "github_release_file":
        return _install_github_release_file(name, info, env)

    elif method == "direct_url":
        return _install_direct_url(name, info, env)

    elif method == "pipx":
        if not _ensure_pipx(env):
            return False
        return _run(["pipx", "install", info["pkg"]])

    elif method == "uv":
        return _install_uv(name, info, env)

    elif method == "uv_tool":
        return _install_uv_tool(info, env)

    elif method == "aur":
        ok = False
        if env.aur_helper:
            ok = _run(
                [env.aur_helper, "-S", "--noconfirm", info["pkg"]],
                check=False,
                timeout=PKG_TIMEOUT,
            )
            if not ok:
                fallback_pkg = info.get("fallback_pkg")
                if fallback_pkg:
                    ui.info(f"{info['pkg']} not found in AUR — trying fallback: {fallback_pkg}...")
                    ok = _run(
                        [env.aur_helper, "-S", "--noconfirm", fallback_pkg],
                        timeout=PKG_TIMEOUT,
                    )
        else:
            ui.warn(f"{name}: no AUR helper (paru/yay) found")
        if not ok:
            # AUR helper missing or the package failed to build — install a
            # prebuilt binary instead (registry "fallback" install info).
            ok = _install_aur_fallback(name, dep_info, env)
        return ok

    elif method == "manual":
        url = info.get("url", "")
        ui.warn(f"{name} must be installed manually: {url}")
        return False

    else:
        ui.warn(f"Unknown install method '{method}' for {name}")
        return False


def _uninstall_one(name, dep_info, env):
    """Uninstall a single dependency using the appropriate method."""
    platform = env.platform_key
    info = dep_info.get(platform, dep_info.get("all"))
    if not info:
        ui.warn(f"No uninstall method for {name} on {platform}")
        return False

    method = info["method"]

    if method == "pacman":
        return _run(["sudo", "pacman", "-Rns", "--noconfirm", info["pkg"]], check=False)
    elif method == "apt":
        return _run(["sudo", "apt", "remove", "-y", info["pkg"]], check=False)
    elif method == "brew":
        return _run(["brew", "uninstall", info["pkg"]], check=False)
    elif method == "winget":
        return _run(["winget", "uninstall", "--id", info["id"], "-e"], check=False)
    elif method == "dnf":
        return _run(["sudo", "dnf", "remove", "-y", info["pkg"]], check=False)
    elif method == "pipx":
        return _run(["pipx", "uninstall", info["pkg"]], check=False)
    elif method == "uv":
        return _uninstall_uv(info, env)
    elif method == "uv_tool":
        return _uninstall_uv_tool(info, env)
    elif method == "aur":
        if env.aur_helper:
            return _run([env.aur_helper, "-Rns", "--noconfirm", info["pkg"]], check=False)
        ui.warn(f"{name} was installed from AUR; no AUR helper found for auto-uninstall.")
        return False
    elif method == "github_release_zip":
        install_dir = info.get("install_dir")
        if install_dir and os.path.isdir(install_dir):
            shutil.rmtree(install_dir, ignore_errors=True)
            return True
        return False
    elif method == "github_release_file":
        install_dir = info.get("install_dir")
        dest_name = info.get("dest_name")
        if install_dir and dest_name:
            path = os.path.join(install_dir, dest_name)
            if os.path.isfile(path):
                os.remove(path)
                return True
        return False
    elif method == "direct_url":
        install_dir = info.get("install_dir")
        dest_name = info.get("dest_name") or os.path.basename(info.get("url", ""))
        if install_dir and dest_name:
            path = os.path.join(install_dir, dest_name)
            if os.path.isfile(path):
                os.remove(path)
                return True
        return False
    elif method == "manual":
        url = info.get("url", "")
        ui.warn(f"{name} is manual install; remove manually if needed: {url}")
        return False
    else:
        ui.warn(f"Unknown uninstall method '{method}' for {name}")
        return False


def uninstall_deps(env, remove_python=False, dry_run=False, pre_existing_pkgs=None, audit_log=None):
    """
    Uninstall dependencies managed by this installer.

    Parameters
    ----------
    pre_existing_pkgs:
        ``{package_name: was_pre_existing}`` from the audit log.  Packages
        where ``was_pre_existing`` is ``True`` (or that are absent from the
        dict) will be **skipped** so pre-existing software is never removed.
        When ``None`` (no log available) all packages are treated as
        pre-existing and none will be removed automatically.
    audit_log:
        Optional :class:`~deploy.audit_log.AuditLog` instance to record
        each uninstall outcome.

    Returns list of result dicts.
    """
    ui.header("Uninstalling System Dependencies")

    # When no log is available the safest default is to skip everything so
    # we never accidentally remove software we did not install.
    if pre_existing_pkgs is None:
        ui.warn("No audit log found — assuming all packages are pre-existing.")
        ui.warn("Only packages installed by this tool can be auto-removed.")
        pre_existing_pkgs = {}

    managed = ["mpv", "yt-dlp", "ffmpeg", "ffsubsync", "alass", "uv"]
    if remove_python:
        managed.append("python")

    results = []
    for name in managed:
        if not env.installed.get(name, False):
            ui.info(f"{name}: not installed (skipping)")
            results.append({"name": name, "status": "skipped", "detail": "not installed"})
            if audit_log:
                audit_log.record_package(name, True, "skip", "skipped", "not installed")
            continue

        # Safety check: never remove packages that pre-existed this tool
        was_pre_existing = pre_existing_pkgs.get(name, True)  # default: safe
        if was_pre_existing:
            ui.info(f"{name}: was installed before this tool — skipping (safe)")
            results.append(
                {"name": name, "status": "skipped", "detail": "pre-existing, not removed"}
            )
            if audit_log:
                audit_log.record_package(name, True, "skip", "skipped", "pre-existing")
            continue

        if dry_run:
            ui.info(f"[DRY RUN] Would uninstall: {name}")
            results.append({"name": name, "status": "skipped", "detail": "dry run"})
            if audit_log:
                audit_log.record_package(name, False, "uninstall", "skipped", "dry run")
            continue

        ui.step(f"Uninstalling {name}...")
        dep_info = SYSTEM_DEPS.get(name, {})
        ok = _uninstall_one(name, dep_info, env)
        if ok:
            ui.success(f"{name}: uninstalled")
            results.append({"name": name, "status": "ok", "detail": "uninstalled"})
            if audit_log:
                audit_log.record_package(name, False, "uninstall", "ok")
        else:
            ui.warn(f"{name}: could not uninstall automatically")
            results.append({"name": name, "status": "skipped", "detail": "manual/failed"})
            if audit_log:
                audit_log.record_package(
                    name, False, "uninstall", "failed", "auto-uninstall failed"
                )

    return results


def _dep_dest(info):
    """Absolute binary path that a file-based install method produces (or None)."""
    install_dir = info.get("install_dir")
    dest_name = info.get("dest_name")
    if install_dir and dest_name:
        return os.path.join(install_dir, dest_name)
    return None


def _write_refresh_stamp(info):
    """Record a file-method install as "fresh" (sidecar <binary>.stamp file)."""
    dest = _dep_dest(info)
    if not dest or not os.path.isfile(dest):
        return
    try:
        with open(dest + ".stamp", "w", encoding="utf-8") as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass


def _dep_is_fresh(info, refresh_days):
    """True when the file-method binary exists AND was installed < refresh_days.

    A binary without a stamp (e.g. apt's frozen /usr/bin/yt-dlp) counts as
    STALE so the file-based installer gets the chance to shadow it with a
    current build — YouTube extractor rules go stale weekly.
    """
    dest = _dep_dest(info)
    if not dest:
        return False
    try:
        stamp_mtime = os.stat(dest + ".stamp").st_mtime
    except OSError:
        return False
    return (time.time() - stamp_mtime) < refresh_days * 86400


def install_deps(env, dry_run=False, audit_log=None, mpv_version=None):
    """
    Install all missing system dependencies.

    Parameters
    ----------
    audit_log:
        Optional :class:`~deploy.audit_log.AuditLog` instance.  When
        supplied, the pre-existing state and install outcome for each package
        is recorded so future uninstall operations can be safe.

    Returns list of result dicts.
    """
    ui.header("Installing System Dependencies")

    # sudo credential warm-up: one password prompt UP-FRONT so none of the
    # package-manager steps below stop mid-flow waiting for a password.
    # (Runner:-loop heartbeats flooding right after a sudo prompt previously
    # made this moment indistinguishable from a hang and got the run
    # interrupted.) sudo caches credentials for ~15 minutes, covering the
    # volume of the whole install phase.
    if env.os == "linux" and not dry_run:
        ui.info("Preauthenticating sudo — type your password if prompted (once for all install steps)...")
        _run(["sudo", "-v"], check=False, timeout=120)

    # Determine what's needed
    # Core deps always, optional deps we just warn about
    core_deps = ["mpv", "yt-dlp", "ffmpeg", "python", "uv"]
    optional_deps = ["ffsubsync", "alass"]

    to_install = []
    already_ok = []
    optional_missing = []

    for name in core_deps:
        if env.installed.get(name, False):
            if (
                name == "mpv"
                and env.mpv_version is not None
                and env.mpv_version < MPV_MINIMUM_VERSION
            ):
                # "Installed" but below the config's minimum (e.g. a distro
                # build) — force an upgrade instead of skipping.
                version_str = ".".join(map(str, env.mpv_version))
                ui.warn(
                    f"mpv {version_str} is older than required "
                    f"{'.'.join(map(str, MPV_MINIMUM_VERSION))} — will upgrade"
                )
                to_install.append(name)
            else:
                # Time-boxed self-refresh: extractor-class tools that
                # upstream services (YouTube) break on a weekly cadence
                # must not skip installs forever just because a stale
                # binary happens to exist (entries carry "refresh_days").
                info = SYSTEM_DEPS.get(name, {}).get(env.platform_key) or {}
                refresh_days = info.get("refresh_days")
                if refresh_days and not _dep_is_fresh(info, refresh_days):
                    ui.info(
                        f"{name}: refreshing (older than {refresh_days} days — "
                        "goes stale too fast to trust)"
                    )
                    to_install.append(name)
                else:
                    already_ok.append(name)
        else:
            to_install.append(name)

    for name in optional_deps:
        if not env.installed.get(name, False):
            optional_missing.append(name)

    # Report what's already installed
    if already_ok:
        for name in already_ok:
            ui.success(f"{name}: already installed")
            if audit_log:
                audit_log.record_package(name, True, "none", "ok", "already installed")

    # Nothing to install?
    if not to_install and not optional_missing:
        ui.success("All dependencies are already installed!")
        # Record optional packages that are also present
        for name in optional_deps:
            if env.installed.get(name, False) and audit_log:
                audit_log.record_package(name, True, "none", "ok", "already installed")
        return [
            {"name": n, "status": "ok", "detail": "already installed"}
            for n in core_deps + optional_deps
            if env.installed.get(n)
        ]

    # Show install plan
    results = [{"name": n, "status": "ok", "detail": "already installed"} for n in already_ok]

    if to_install:
        ui.step(f"Need to install: {', '.join(to_install)}")

    if optional_missing:
        ui.info(f"Optional (will attempt): {', '.join(optional_missing)}")

    if dry_run:
        for name in to_install + optional_missing:
            results.append({"name": name, "status": "skipped", "detail": "dry run"})
            if audit_log:
                audit_log.record_package(name, False, "install", "skipped", "dry run")
        return results

    # Confirm — never prompt in non-interactive sessions (curl | bash):
    # prompts there crash with "EOF when reading a line". Non-interactive
    # installs auto-proceed, matching cmd_install's plan confirmation.
    if to_install:
        proceed = True
        if ui.is_interactive():
            proceed = ui.confirm(
                f"Install {len(to_install)} core + {len(optional_missing)} optional packages?"
            )
        if not proceed:
            ui.warn("Skipping dependency installation")
            for name in to_install:
                results.append({"name": name, "status": "skipped", "detail": "user skipped"})
                if audit_log:
                    audit_log.record_package(name, False, "install", "skipped", "user skipped")
            for name in optional_missing:
                results.append({"name": name, "status": "skipped", "detail": "user skipped"})
                if audit_log:
                    audit_log.record_package(name, False, "install", "skipped", "user skipped")
            return results

    # Install core
    for name in to_install:
        try:
            # Plain step + streamed command output (see _run): a rich spinner
            # here redraws over apt's own progress lines and reads as "frozen".
            ui.step(f"Installing {name}...")
            dep_info = SYSTEM_DEPS.get(name, {})
            ok = _install_one(name, dep_info, env, mpv_version=mpv_version)
            if ok:
                ui.success(f"{name}: installed successfully")
                results.append({"name": name, "status": "ok", "detail": "freshly installed"})
                if audit_log:
                    audit_log.record_package(name, False, "install", "ok", "freshly installed")
            else:
                ui.error(f"{name}: installation failed")
                results.append({"name": name, "status": "failed", "detail": "install failed"})
                if audit_log:
                    audit_log.record_package(name, False, "install", "failed", "install failed")
        except Exception as e:
            ui.error(f"{name}: unexpected error: {e}")
            results.append({"name": name, "status": "failed", "detail": str(e)})
            if audit_log:
                audit_log.record_package(
                    name,
                    False,
                    "install",
                    "failed",
                    str(e),
                    error_context={
                        "type": type(e).__name__,
                        "traceback": str(e),
                        "env": getattr(env, "platform_key", ""),
                    },
                )

    # Install optional (don't fail the whole process)
    for name in optional_missing:
        try:
            ui.step(f"Installing {name} (optional)...")
            dep_info = SYSTEM_DEPS.get(name, {})
            ok = _install_one(name, dep_info, env)
            if ok:
                ui.success(f"{name}: installed successfully")
                results.append({"name": name, "status": "ok", "detail": "freshly installed"})
                if audit_log:
                    audit_log.record_package(
                        name, False, "install", "ok", "freshly installed (optional)"
                    )
            else:
                ui.warn(f"{name}: skipped (optional)")
                results.append(
                    {"name": name, "status": "skipped", "detail": "optional, install failed"}
                )
                if audit_log:
                    audit_log.record_package(
                        name, False, "install", "skipped", "optional, install failed"
                    )
        except Exception as e:
            ui.warn(f"{name}: skipped (optional) due to error: {e}")
            results.append({"name": name, "status": "skipped", "detail": str(e)})
            if audit_log:
                audit_log.record_package(
                    name,
                    False,
                    "install",
                    "failed",
                    str(e),
                    error_context={
                        "type": type(e).__name__,
                        "traceback": str(e),
                        "env": getattr(env, "platform_key", ""),
                    },
                )

    return results


def _get_target_tools_dir(env=None):
    """
    Determine default install directory for binaries:
    C:\\Program Files\\mpv if running with elevation / writable,
    otherwise %APPDATA%\\mpv\\tools (or ~/.local/bin on Linux).
    """
    if env and env.os != "windows":
        return os.path.expanduser("~/.local/bin")

    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    mpv_dir = os.path.join(prog_files, "mpv")

    is_writable = False
    try:
        os.makedirs(mpv_dir, exist_ok=True)
        test_path = os.path.join(mpv_dir, ".perm_test")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        is_writable = True
    except Exception:
        is_writable = False

    if is_writable:
        return mpv_dir

    appdata = os.environ.get("APPDATA")
    if appdata:
        tools_dir = os.path.join(appdata, "mpv", "tools")
    else:
        tools_dir = os.path.expanduser("~/.mpv/tools")
    os.makedirs(tools_dir, exist_ok=True)
    return tools_dir


def _unblock_path(path):
    """Unblock downloaded files on Windows using PowerShell Unblock-File."""
    if sys.platform != "win32":
        return
    try:
        if os.path.isfile(path):
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Unblock-File -LiteralPath '{path}'"],
                capture_output=True,
                timeout=10,
            )
        elif os.path.isdir(path):
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-ChildItem -LiteralPath '{path}' -Recurse | Unblock-File",
                ],
                capture_output=True,
                timeout=15,
            )
    except Exception:
        pass


def sync_dependencies(env=None, target_dir=None, force=False, dry_run=False, audit_log=None):
    """
    Automated Dependency Suite Pipeline (Self-Healing Fetcher):
      - yt-dlp: latest 64-bit Windows binary from yt-dlp/yt-dlp
      - ffmpeg-full: latest release archive (ffmpeg.exe, ffprobe.exe, ffplay.exe)
      - alass: latest release (alass.exe) from kaegi/alass
      - ffsubsync: pip/uv installation/upgrade
      - Unblock files on Windows
      - Update ytdl_hook.conf with localized path
    """
    if env is None:
        from deploy import detector

        env = detector.detect()

    if dry_run:
        return [
            {"name": "yt-dlp", "status": "skipped", "detail": "dry-run"},
            {"name": "ffmpeg-full", "status": "skipped", "detail": "dry-run"},
            {"name": "alass", "status": "skipped", "detail": "dry-run"},
            {"name": "ffsubsync", "status": "skipped", "detail": "dry-run"},
        ]

    ui.header("Syncing MPV Dependencies Suite")
    target = target_dir or _get_target_tools_dir(env)
    ui.info(f"Target directory: {target}")

    os.makedirs(target, exist_ok=True)

    if env.os == "windows":
        _add_to_path(target)

    results = []

    # 1. yt-dlp
    ui.step("Checking yt-dlp...")
    ytdlp_exe = os.path.join(target, "yt-dlp.exe")
    if dry_run:
        results.append({"name": "yt-dlp", "status": "skipped", "detail": "dry-run"})
    else:
        try:
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
            ui.step("Downloading latest yt-dlp.exe...")
            _download_asset(url, ytdlp_exe)
            _unblock_path(ytdlp_exe)
            ui.success(f"yt-dlp: verified at {ytdlp_exe}")
            results.append({"name": "yt-dlp", "status": "ok", "path": ytdlp_exe})
            if audit_log:
                audit_log.record_file(ytdlp_exe, "download", "ok", "yt-dlp binary")
        except Exception as e:
            ui.error(f"yt-dlp download failed: {e}")
            results.append({"name": "yt-dlp", "status": "failed", "detail": str(e)})

    # 2. ffmpeg-full
    ui.step("Checking ffmpeg-full suite (ffmpeg, ffprobe, ffplay)...")
    if dry_run:
        results.append({"name": "ffmpeg-full", "status": "skipped", "detail": "dry-run"})
    else:
        try:
            ffmpeg_bins = (
                ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"]
                if env.os == "windows"
                else ["ffmpeg", "ffprobe", "ffplay"]
            )
            already_have_ffmpeg = not force and all(
                os.path.isfile(os.path.join(target, b)) for b in ffmpeg_bins
            )
            if already_have_ffmpeg:
                ui.success(f"ffmpeg-full: already present in {target}")
                results.append({"name": "ffmpeg-full", "status": "ok", "detail": "already present"})
            else:
                ui.step("Fetching latest ffmpeg-full release (BtbN/FFmpeg-Builds)...")
                release = _fetch_latest_release("BtbN/FFmpeg-Builds")
                patterns = [
                    r"^ffmpeg-master-latest-win64-gpl\.zip$",
                    r"^ffmpeg-master-latest-win64-gpl-shared\.zip$",
                    r"^ffmpeg-.*-win64-gpl\.zip$",
                ]
                asset = _select_release_asset(release, patterns)
                if not asset:
                    raise RuntimeError("No matching ffmpeg release asset found")

                with tempfile.TemporaryDirectory() as tmpdir:
                    archive_path = os.path.join(tmpdir, asset["name"])
                    ui.step(
                        f"Downloading {asset['name']} ({asset.get('size', 0) / (1024*1024):.1f} MB)..."
                    )
                    _download_asset(asset["browser_download_url"], archive_path)
                    extract_dir = os.path.join(tmpdir, "extracted")
                    _extract_zip(archive_path, extract_dir)

                    found_count = 0
                    for root, _, files in os.walk(extract_dir):
                        for f in files:
                            if f.lower() in (
                                "ffmpeg.exe",
                                "ffprobe.exe",
                                "ffplay.exe",
                                "ffmpeg",
                                "ffprobe",
                                "ffplay",
                            ):
                                src_f = os.path.join(root, f)
                                dst_f = os.path.join(target, f)
                                shutil.copy2(src_f, dst_f)
                                _unblock_path(dst_f)
                                found_count += 1

                    ui.success(f"ffmpeg-full: extracted {found_count} binaries to {target}")
                    results.append({"name": "ffmpeg-full", "status": "ok", "path": target})
                    if audit_log:
                        audit_log.record_package(
                            "ffmpeg-full", False, "install", "ok", f"extracted to {target}"
                        )
        except Exception as e:
            ui.warn(f"ffmpeg-full fetch notice: {e}")
            results.append({"name": "ffmpeg-full", "status": "failed", "detail": str(e)})

    # 3. alass
    ui.step("Checking alass (subtitle auto-synchronization)...")
    alass_exe = os.path.join(target, "alass.exe" if env.os == "windows" else "alass")
    if dry_run:
        results.append({"name": "alass", "status": "skipped", "detail": "dry-run"})
    else:
        try:
            if not force and os.path.isfile(alass_exe):
                ui.success(f"alass: already present at {alass_exe}")
                results.append({"name": "alass", "status": "ok", "path": alass_exe})
            else:
                ui.step("Fetching latest alass release (kaegi/alass)...")
                release = _fetch_latest_release("kaegi/alass")
                patterns = (
                    [
                        r"^alass-.*windows.*x64.*\.zip$",
                        r"^alass-.*win64.*\.zip$",
                        r"^alass-.*win.*\.zip$",
                    ]
                    if env.os == "windows"
                    else [r"^alass-.*linux.*\.tar\.gz$", r"^alass-.*linux.*\.zip$"]
                )
                asset = _select_release_asset(release, patterns)
                if asset:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        archive_path = os.path.join(tmpdir, asset["name"])
                        _download_asset(asset["browser_download_url"], archive_path)
                        extract_dir = os.path.join(tmpdir, "extracted")
                        _extract_zip(archive_path, extract_dir)
                        for root, _, files in os.walk(extract_dir):
                            for f in files:
                                if f.lower() in ("alass.exe", "alass-cli.exe", "alass"):
                                    src_f = os.path.join(root, f)
                                    dst_f = os.path.join(target, f)
                                    shutil.copy2(src_f, dst_f)
                                    _unblock_path(dst_f)
                        ui.success(f"alass: verified at {target}")
                        results.append({"name": "alass", "status": "ok", "path": target})
                else:
                    ui.warn("No matching alass asset found")
                    results.append({"name": "alass", "status": "skipped", "detail": "no asset"})
        except Exception as e:
            ui.warn(f"alass fetch notice: {e}")
            results.append({"name": "alass", "status": "failed", "detail": str(e)})

    # 4. ffsubsync
    ui.step("Checking ffsubsync (Python/pip/uv)...")
    if dry_run:
        results.append({"name": "ffsubsync", "status": "skipped", "detail": "dry-run"})
    else:
        try:
            installed_ffsubsync = False
            if shutil.which("uv"):
                ui.step("Installing/upgrading ffsubsync via uv tool...")
                installed_ffsubsync = _run(
                    ["uv", "tool", "install", "--upgrade", "ffsubsync"], check=False
                )
            if not installed_ffsubsync and shutil.which("python"):
                ui.step("Installing/upgrading ffsubsync via python -m pip...")
                installed_ffsubsync = _run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "ffsubsync"], check=False
                )
            if not installed_ffsubsync and shutil.which("pip"):
                ui.step("Installing/upgrading ffsubsync via pip...")
                installed_ffsubsync = _run(
                    ["pip", "install", "--upgrade", "ffsubsync"], check=False
                )

            if installed_ffsubsync or shutil.which("ffsubsync"):
                ui.success("ffsubsync: verified")
                results.append({"name": "ffsubsync", "status": "ok"})
            else:
                ui.warn("ffsubsync: could not automatically install via pip/uv")
                results.append(
                    {"name": "ffsubsync", "status": "skipped", "detail": "pip/uv failed"}
                )
        except Exception as e:
            ui.warn(f"ffsubsync install notice: {e}")
            results.append({"name": "ffsubsync", "status": "failed", "detail": str(e)})

    # 5. Local deployment artifact: update active ytdl_hook.conf
    try:
        from deploy.deployer import _resolve_ytdl_path

        resolved_ytdl = _resolve_ytdl_path(env)
        config_dir = getattr(env, "config_dir", None)
        if not config_dir:
            if env.os == "windows":
                config_dir = os.path.join(os.environ.get("APPDATA", ""), "mpv")
            else:
                config_dir = os.path.expanduser("~/.config/mpv")
        if config_dir and os.path.isdir(config_dir):
            opts_dir = os.path.join(config_dir, "script-opts")
            os.makedirs(opts_dir, exist_ok=True)
            hook_conf = os.path.join(opts_dir, "ytdl_hook.conf")
            with open(hook_conf, "w", encoding="utf-8") as f:
                f.write(f"ytdl_path={resolved_ytdl}\n")
            ui.success(f"Updated {hook_conf} (ytdl_path={resolved_ytdl})")
    except Exception as e:
        ui.warn(f"Could not update ytdl_hook.conf: {e}")

    ui.success("MPV dependencies suite synchronization finished.")
    return results
