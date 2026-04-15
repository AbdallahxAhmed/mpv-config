"""
installer.py — Install system dependencies.

Handles package installation via winget, pacman, apt, brew, and pip
based on the detected environment.
"""

import subprocess
import sys

from deploy import ui
from deploy.registry import SYSTEM_DEPS


def _run(cmd, check=True):
    """Run a command, showing output. Returns success bool."""
    try:
        subprocess.run(
            cmd, check=check, timeout=300,
            # Don't capture — let user see install progress
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        ui.error(f"Command not found: {cmd[0]}")
        return False
    except subprocess.TimeoutExpired:
        ui.error(f"Command timed out: {' '.join(cmd)}")
        return False


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

    elif method == "brew":
        return _run(["brew", "install", info["pkg"]])

    elif method == "winget":
        return _run(["winget", "install", "--id", info["id"], "-e", "--accept-package-agreements", "--accept-source-agreements"])

    elif method == "pip":
        # Special handling for ffsubsync: pin setuptools first
        if name == "ffsubsync":
            _prepare_ffsubsync_build(env)
        cmd = [env.pip_cmd, "install", info["pkg"]]
        flags = info.get("flags", [])
        cmd.extend(flags)
        return _run(cmd)

    elif method == "aur":
        if env.aur_helper:
            return _run([env.aur_helper, "-S", "--noconfirm", info["pkg"]])
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


def _prepare_ffsubsync_build(env):
    """
    Prepare the build environment for ffsubsync.
    ffsubsync depends on webrtcvad which needs C compilation.
    Also, setuptools >= 74 breaks build — must pin to < 74.
    """
    ui.info("Preparing build environment for ffsubsync...")

    # 1. Pin setuptools to a compatible version
    ui.step("Pinning setuptools<74 (ffsubsync compatibility)...")
    _run([env.pip_cmd, "install", "--quiet", "pip>=23.0", "setuptools<74.0", "wheel"], check=False)

    # 2. Install build dependencies on Linux
    if env.os == "linux":
        if env.distro in ("arch",):
            ui.step("Installing build deps: base-devel python...")
            _run(["sudo", "pacman", "-S", "--noconfirm", "--needed", "base-devel", "python"], check=False)
        elif env.distro in ("ubuntu", "debian"):
            ui.step("Installing build deps: build-essential python3-dev...")
            _run(["sudo", "apt", "install", "-y", "-qq", "build-essential", "python3-dev"], check=False)
    elif env.os == "windows":
        # Check for Visual C++ Build Tools
        try:
            import subprocess as sp
            vswhere = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
            r = sp.run([vswhere, "-latest", "-products", "*",
                       "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                       "-property", "installationPath"],
                      capture_output=True, text=True, timeout=10)
            if r.returncode != 0 or not r.stdout.strip():
                ui.warn("Visual C++ Build Tools not detected!")
                ui.warn("ffsubsync may fail. Get them from:")
                ui.warn("  https://visualstudio.microsoft.com/visual-cpp-build-tools/")
        except Exception:
            ui.warn("Could not check for Visual C++ Build Tools")


def install_deps(env, dry_run=False):
    """
    Install all missing system dependencies.
    Returns list of result dicts.
    """
    ui.header("Installing System Dependencies")

    # Determine what's needed
    # Core deps always, optional deps we just warn about
    core_deps = ["mpv", "yt-dlp", "ffmpeg", "python"]
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

    # Nothing to install?
    if not to_install and not optional_missing:
        ui.success("All dependencies are already installed!")
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
        return results

    # Confirm
    if to_install:
        if not ui.confirm(f"Install {len(to_install)} core + {len(optional_missing)} optional packages?"):
            ui.warn("Skipping dependency installation")
            for name in to_install:
                results.append({"name": name, "status": "skipped", "detail": "user skipped"})
            for name in optional_missing:
                results.append({"name": name, "status": "skipped", "detail": "user skipped"})
            return results

    # Install core
    for name in to_install:
        ui.step(f"Installing {name}...")
        dep_info = SYSTEM_DEPS.get(name, {})
        ok = _install_one(name, dep_info, env)
        if ok:
            ui.success(f"{name}: installed successfully")
            results.append({"name": name, "status": "ok", "detail": "freshly installed"})
        else:
            ui.error(f"{name}: installation failed")
            results.append({"name": name, "status": "failed", "detail": "install failed"})

    # Install optional (don't fail the whole process)
    for name in optional_missing:
        ui.step(f"Installing {name} (optional)...")
        dep_info = SYSTEM_DEPS.get(name, {})
        ok = _install_one(name, dep_info, env)
        if ok:
            ui.success(f"{name}: installed successfully")
            results.append({"name": name, "status": "ok", "detail": "freshly installed"})
        else:
            ui.warn(f"{name}: skipped (optional)")
            results.append({"name": name, "status": "skipped", "detail": "optional, install failed"})

    return results
