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



def _run(cmd, check=True):
    """Run a command, showing output. Returns success bool."""
    try:
        result = subprocess.run(
            cmd, check=check, timeout=300,
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
            if regex.match(name) or regex.search(name):
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
        else:
            ui.info(f"{directory} already in PATH")
        return True
    except Exception as e:
        ui.warn(f"Could not update PATH: {e}")
        return False


def _install_github_asset(name, info, env):
    """Download a GitHub release asset (.7z), extract, and add to PATH."""
    repo = info["repo"]
    install_dir = info.get("install_dir", r"C:\Program Files\mpv")
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    # 1. Fetch latest release metadata
    ui.step(f"Fetching latest release from {repo}...")
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read())
    except Exception as e:
        ui.error(f"Failed to fetch release info: {e}")
        return False

    # 2. Select asset based on AVX2 support
    if env.has_avx2:
        pattern = re.compile(r"^mpv-x86_64-v3-\d{8}-git-[0-9a-f]+\.7z$")
        label = "v3 (AVX2)"
    else:
        pattern = re.compile(r"^mpv-x86_64-\d{8}-git-[0-9a-f]+\.7z$")
        label = "x86_64"

    asset = None
    for a in release.get("assets", []):
        if pattern.match(a["name"]):
            asset = a
            break

    if not asset:
        ui.error(f"No matching {label} asset found in {repo} release")
        return False

    download_url = asset["browser_download_url"]
    asset_name = asset["name"]
    asset_size_mb = asset.get("size", 0) / (1024 * 1024)

    # 3. Ensure 7-Zip is available for extraction
    if not _ensure_7zip():
        ui.error("Cannot extract .7z archive without 7-Zip.")
        return False

    sevenz = _find_7z()
    if not sevenz:
        ui.error("7z.exe not found even after installation.")
        return False

    # 4. Download asset
    os.makedirs(install_dir, exist_ok=True)
    archive_path = os.path.join(install_dir, asset_name)

    ui.step(f"Downloading {asset_name} ({label}, {asset_size_mb:.1f} MB)...")
    try:
        urllib.request.urlretrieve(download_url, archive_path)
    except Exception as e:
        ui.error(f"Download failed: {e}")
        return False

    # 5. Extract
    ui.step(f"Extracting to {install_dir}...")
    ok = _run([sevenz, "x", "-y", f"-o{install_dir}", archive_path])
    if not ok:
        ui.error("Extraction failed.")
        return False

    # Clean up archive
    try:
        os.remove(archive_path)
    except OSError:
        pass

    _flatten_single_dir(install_dir)

    # 6. Add to PATH
    _add_to_path(install_dir)

    ui.success(f"mpv {label} installed to {install_dir}")
    return True


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
    if bin_dir:
        cmd += ["--bin-dir", bin_dir]
    ok = _run(cmd)
    if not ok:
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

    ok = False
    if shutil.which("uv"):
        ok = _run(["uv", "tool", "uninstall", pkg], check=False)
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

def _install_one(name, dep_info, env):
    """Install a single dependency using the appropriate method."""
    platform = env.platform_key

    # Get platform-specific install info, fallback to 'all'
    info = dep_info.get(platform, dep_info.get("all"))
    if not info:
        ui.warn(f"No install method for {name} on {platform}")
        return False

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


def install_deps(env, dry_run=False, audit_log=None):
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
                ok = _install_one(name, dep_info, env)
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
