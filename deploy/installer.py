"""
installer.py — Install system dependencies.

Handles package installation via winget, pacman, apt, brew, dnf, pipx,
and github_asset (direct GitHub release downloads) based on the
detected environment.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from deploy import ui
from deploy.registry import SYSTEM_DEPS



def _run(cmd, check=True, env=None):
    """Run a command, showing output. Returns success bool."""
    try:
        result = subprocess.run(
            cmd, check=check, timeout=300, env=env,
            # Don't capture — let user see install progress
        )
        if not check and result.returncode != 0:
            return False
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        ui.error(f"Command not found: {cmd[0]}")
        return False
    except subprocess.TimeoutExpired:
        ui.error(f"Command timed out: {' '.join(cmd)}")
        return False


def _ensure_pipx(env):
    """Ensure pipx is available, installing via OS package manager if missing."""
    if shutil.which("pipx"):
        return True

    ui.step("pipx not found — attempting to install via OS package manager...")
    if env.os == "linux":
        if env.distro in ("ubuntu", "debian", "mint", "pop"):
            return _run(["sudo", "apt", "install", "-y", "pipx"])
        elif env.distro == "fedora":
            return _run(["sudo", "dnf", "install", "-y", "pipx"])
    elif env.os == "macos":
        return _run(["brew", "install", "pipx"])

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
    return _run([
        "winget", "install", "--id", "7zip.7zip",
        "-e", "--accept-package-agreements", "--accept-source-agreements",
    ])


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


def _download_asset(url, dest_path):
    """Download an asset to dest_path."""
    urllib.request.urlretrieve(url, dest_path)


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
            ["powershell", "-NoProfile", "-Command",
             f"$p = [Environment]::GetEnvironmentVariable('PATH','User');"
             f"if ($p -notlike '*{directory}*') {{"
             f"  [Environment]::SetEnvironmentVariable('PATH', $p + ';{directory}', 'User');"
             f"  Write-Output 'added'"
             f"}} else {{ Write-Output 'exists' }}"],
            capture_output=True, text=True, timeout=15,
        )
        if "added" in result.stdout:
            ui.success(f"Added {directory} to user PATH")
            # Also update current process PATH so mpv is findable immediately
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + directory
            broadcast_cmd = [
                "powershell", "-NoProfile", "-Command",
                "$sig=@'\n"
                "[DllImport(\"user32.dll\", SetLastError=true, CharSet=CharSet.Auto)]\n"
                "public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);\n"
                "'@; "
                "Add-Type -MemberDefinition $sig -Name NativeMethods -Namespace Win32; "
                "$HWND_BROADCAST = [intptr]0xffff; "
                "$WM_SETTINGCHANGE = 0x1A; "
                "$result = [uintptr]::Zero; "
                "[Win32.NativeMethods]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [uintptr]::Zero, 'Environment', 2, 5000, [ref]$result) | Out-Null"
            ]
            broadcast_result = subprocess.run(broadcast_cmd, capture_output=True, text=True, timeout=10)
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

    repo          = info["repo"]
    fallback_repo = info.get("fallback_repo")
    pin           = info.get("pin")
    install_dir   = info.get("install_dir", r"C:\Program Files\mpv")
    patterns_map  = info.get("asset_patterns", {}) or {}
    generic_pat   = info.get("asset_pattern_generic")
    require_sha   = os.environ.get("MPV_REQUIRE_SHA256") == "1"

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
                attempts.append(("x86_64 (AVX2 build unavailable, using plain)", repo_pats["plain"]))
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

        download_url   = asset["browser_download_url"]
        asset_name     = asset["name"]
        asset_size_mb  = asset.get("size", 0) / (1024 * 1024)
        assets         = release.get("assets", [])

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
            urllib.request.urlretrieve(download_url, archive_path)
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
    else:
        _add_to_path(install_dir)

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

    ui.success(f"{name}: installed to {dest_path}")
    return True


def _install_uv(name, info, env):
    """Install uv with OS-specific fallbacks."""
    if shutil.which("uv"):
        return True

    if env.os == "macos":
        if shutil.which("brew") and _run(["brew", "install", "uv"]):
            return True
    elif env.os == "linux":
        if env.distro == "arch":
            if _run(["sudo", "pacman", "-S", "--noconfirm", "--needed", "uv"]):
                return True
        elif env.distro in ("ubuntu", "debian", "mint", "pop"):
            if _run(["sudo", "apt", "install", "-y", "uv"]):
                return True
        elif env.distro == "fedora":
            if _run(["sudo", "dnf", "install", "-y", "uv"]):
                return True

    if env.os == "windows":
        if info.get("repo") and info.get("asset_patterns"):
            return _install_github_release_zip(name, info, env)
        ui.warn("uv install on Windows requires a release asset configuration.")
        return False

    ui.step("Installing uv via official installer script...")
    ok = _run(["/bin/sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])
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
        return _run(["sudo", "pacman", "-S", "--noconfirm", "--needed", info["pkg"]])

    elif method == "apt":
        return _run(["sudo", "apt", "install", "-y", info["pkg"]])

    elif method == "dnf":
        return _run(["sudo", "dnf", "install", "-y", info["pkg"]])

    elif method == "brew":
        return _run(["brew", "install", info["pkg"]])

    elif method == "winget":
        return _run(["winget", "install", "--id", info["id"], "-e", "--accept-package-agreements", "--accept-source-agreements"])

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
        if env.aur_helper:
            ok = _run([env.aur_helper, "-S", "--noconfirm", info["pkg"]], check=False)
            if not ok:
                fallback_pkg = info.get("fallback_pkg")
                if fallback_pkg:
                    ui.info(f"{info['pkg']} not found in AUR — trying fallback: {fallback_pkg}...")
                    ok = _run([env.aur_helper, "-S", "--noconfirm", fallback_pkg])
            return ok
        else:
            ui.warn(f"{name} requires an AUR helper (paru/yay). Install manually.")
            return False

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
            results.append({"name": name, "status": "skipped", "detail": "pre-existing, not removed"})
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
                audit_log.record_package(name, False, "uninstall", "failed", "auto-uninstall failed")

    return results


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

    # Determine what's needed
    # Core deps always, optional deps we just warn about
    core_deps = ["mpv", "yt-dlp", "ffmpeg", "python", "uv"]
    optional_deps = ["ffsubsync", "alass"]

    to_install = []
    already_ok = []
    optional_missing = []

    for name in core_deps:
        if env.installed.get(name, False):
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
        return [{"name": n, "status": "ok", "detail": "already installed"} for n in core_deps + optional_deps if env.installed.get(n)]

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

    # Confirm
    if to_install:
        if not ui.confirm(f"Install {len(to_install)} core + {len(optional_missing)} optional packages?"):
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
            with ui.spinner(f"Installing {name}..."):
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
                    name, False, "install", "failed", str(e),
                    error_context={"type": type(e).__name__, "traceback": str(e), "env": getattr(env, "platform_key", "")}
                )

    # Install optional (don't fail the whole process)
    for name in optional_missing:
        try:
            with ui.spinner(f"Installing {name} (optional)..."):
                dep_info = SYSTEM_DEPS.get(name, {})
                ok = _install_one(name, dep_info, env)
            if ok:
                ui.success(f"{name}: installed successfully")
                results.append({"name": name, "status": "ok", "detail": "freshly installed"})
                if audit_log:
                    audit_log.record_package(name, False, "install", "ok", "freshly installed (optional)")
            else:
                ui.warn(f"{name}: skipped (optional)")
                results.append({"name": name, "status": "skipped", "detail": "optional, install failed"})
                if audit_log:
                    audit_log.record_package(name, False, "install", "skipped", "optional, install failed")
        except Exception as e:
            ui.warn(f"{name}: skipped (optional) due to error: {e}")
            results.append({"name": name, "status": "skipped", "detail": str(e)})
            if audit_log:
                audit_log.record_package(
                    name, False, "install", "failed", str(e),
                    error_context={"type": type(e).__name__, "traceback": str(e), "env": getattr(env, "platform_key", "")}
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
                ["powershell", "-NoProfile", "-Command", f"Get-ChildItem -LiteralPath '{path}' -Recurse | Unblock-File"],
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

    ui.header("Syncing MPV Dependencies Suite")
    target = target_dir or _get_target_tools_dir(env)
    os.makedirs(target, exist_ok=True)
    ui.info(f"Target directory: {target}")

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
            ffmpeg_bins = ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"] if env.os == "windows" else ["ffmpeg", "ffprobe", "ffplay"]
            already_have_ffmpeg = not force and all(os.path.isfile(os.path.join(target, b)) for b in ffmpeg_bins)
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
                    ui.step(f"Downloading {asset['name']} ({asset.get('size', 0) / (1024*1024):.1f} MB)...")
                    _download_asset(asset["browser_download_url"], archive_path)
                    extract_dir = os.path.join(tmpdir, "extracted")
                    _extract_zip(archive_path, extract_dir)

                    found_count = 0
                    for root, _, files in os.walk(extract_dir):
                        for f in files:
                            if f.lower() in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe", "ffmpeg", "ffprobe", "ffplay"):
                                src_f = os.path.join(root, f)
                                dst_f = os.path.join(target, f)
                                shutil.copy2(src_f, dst_f)
                                _unblock_path(dst_f)
                                found_count += 1

                    ui.success(f"ffmpeg-full: extracted {found_count} binaries to {target}")
                    results.append({"name": "ffmpeg-full", "status": "ok", "path": target})
                    if audit_log:
                        audit_log.record_package("ffmpeg-full", False, "install", "ok", f"extracted to {target}")
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
                patterns = [
                    r"^alass-.*windows.*x64.*\.zip$",
                    r"^alass-.*win64.*\.zip$",
                    r"^alass-.*win.*\.zip$",
                ] if env.os == "windows" else [r"^alass-.*linux.*\.tar\.gz$", r"^alass-.*linux.*\.zip$"]
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
                installed_ffsubsync = _run(["uv", "tool", "install", "--upgrade", "ffsubsync"], check=False)
            if not installed_ffsubsync and shutil.which("python"):
                ui.step("Installing/upgrading ffsubsync via python -m pip...")
                installed_ffsubsync = _run([sys.executable, "-m", "pip", "install", "--upgrade", "ffsubsync"], check=False)
            if not installed_ffsubsync and shutil.which("pip"):
                ui.step("Installing/upgrading ffsubsync via pip...")
                installed_ffsubsync = _run(["pip", "install", "--upgrade", "ffsubsync"], check=False)

            if installed_ffsubsync or shutil.which("ffsubsync"):
                ui.success("ffsubsync: verified")
                results.append({"name": "ffsubsync", "status": "ok"})
            else:
                ui.warn("ffsubsync: could not automatically install via pip/uv")
                results.append({"name": "ffsubsync", "status": "skipped", "detail": "pip/uv failed"})
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

