"""
detector.py — OS, environment, and capability detection.

Detects everything about the current machine needed for deployment:
OS, distro, display server, GPU, package manager, installed tools.
"""

import os
import sys
import platform
import subprocess
import shutil
from dataclasses import dataclass, field
from typing import Optional, Dict

from deploy import ui


@dataclass
class Environment:
    """Detected environment properties."""
    os: str = ""                   # "windows" | "linux" | "macos"
    distro: str = ""               # "arch" | "ubuntu" | "fedora" | ""
    platform_key: str = ""         # resolved key for PLATFORM_DEFAULTS
    display: str = ""              # "wayland" | "x11" | ""
    gpu_vendor: str = ""           # "nvidia" | "amd" | "intel" | ""
    pkg_manager: str = ""          # "pacman" | "apt" | "brew" | "winget" | ""
    aur_helper: str = ""           # "paru" | "yay" | ""
    config_dir: str = ""           # resolved mpv config path
    python_cmd: str = "python"     # "python" | "python3"
    pip_cmd: str = "pip"           # "pip" | "pip3"
    has_git: bool = False
    installed: Dict[str, bool] = field(default_factory=dict)


def _run_silent(cmd):
    """Run a command silently, return (success, stdout)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return r.returncode == 0, r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, ""


def _which(name):
    """Check if a binary exists in PATH."""
    return shutil.which(name) is not None


def _detect_os():
    """Detect the operating system."""
    s = sys.platform
    if s == "win32":
        return "windows"
    elif s == "darwin":
        return "macos"
    elif s.startswith("linux"):
        return "linux"
    return "linux"  # fallback


def _detect_distro():
    """Detect the Linux distribution."""
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
        if "arch" in content or "cachyos" in content or "endeavouros" in content or "manjaro" in content:
            return "arch"
        elif "ubuntu" in content or "debian" in content or "mint" in content or "pop" in content:
            return "ubuntu"
        elif "fedora" in content or "rhel" in content or "centos" in content:
            return "fedora"
    except FileNotFoundError:
        pass
    # Fallback: check for package managers
    if _which("pacman"):
        return "arch"
    elif _which("apt"):
        return "ubuntu"
    elif _which("dnf"):
        return "fedora"
    return ""


def _detect_display():
    """Detect the display server (Linux only)."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland":
        return "wayland"
    elif session == "x11":
        return "x11"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return ""


def _detect_gpu():
    """Detect the GPU vendor."""
    if sys.platform == "win32":
        ok, out = _run_silent(["wmic", "path", "win32_VideoController", "get", "name"])
        if ok:
            out_lower = out.lower()
            if "nvidia" in out_lower:
                return "nvidia"
            elif "amd" in out_lower or "radeon" in out_lower:
                return "amd"
            elif "intel" in out_lower:
                return "intel"
    else:
        ok, out = _run_silent(["lspci"])
        if ok:
            out_lower = out.lower()
            if "nvidia" in out_lower:
                return "nvidia"
            elif "amd" in out_lower or "radeon" in out_lower:
                return "amd"
            elif "intel" in out_lower:
                return "intel"
    return ""


def _detect_pkg_manager(os_name, distro):
    """Detect the primary package manager."""
    if os_name == "windows":
        if _which("winget"):
            return "winget"
        if _which("choco"):
            return "choco"
        if _which("scoop"):
            return "scoop"
        return "winget"  # assume available
    elif os_name == "macos":
        return "brew" if _which("brew") else ""
    elif distro == "arch":
        return "pacman"
    elif distro in ("ubuntu", "debian"):
        return "apt"
    elif distro == "fedora":
        return "dnf"
    return ""


def _detect_aur_helper():
    """Detect available AUR helper."""
    for helper in ("paru", "yay"):
        if _which(helper):
            return helper
    return ""


def _detect_python():
    """Detect the python/pip commands."""
    # We're already running Python, so sys.executable works
    python_cmd = "python" if sys.platform == "win32" else "python3"
    pip_cmd = "pip" if sys.platform == "win32" else "pip3"

    # Verify python command
    if not _which(python_cmd):
        if _which("python3"):
            python_cmd = "python3"
        elif _which("python"):
            python_cmd = "python"

    # Verify pip command: try pip3, pip, then python -m pip
    if not _which(pip_cmd):
        found = False
        for alt in ["pip3", "pip"]:
            if _which(alt):
                pip_cmd = alt
                found = True
                break
        if not found:
            # Check whether python -m pip works as a last resort
            ok, _ = _run_silent([python_cmd, "-m", "pip", "--version"])
            if ok:
                pip_cmd = f"{python_cmd} -m pip"

    return python_cmd, pip_cmd


def _resolve_config_dir(os_name):
    """Resolve the mpv configuration directory."""
    if os_name == "windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return os.path.join(appdata, "mpv")
        return os.path.expanduser("~/AppData/Roaming/mpv")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            return os.path.join(xdg, "mpv")
        return os.path.expanduser("~/.config/mpv")


def _check_installed(dep_name, dep_info):
    """Check if a system dependency is already installed."""
    verify = dep_info.get("verify", [])
    if verify:
        ok, _ = _run_silent(verify)
        if ok:
            return True
    verify_alt = dep_info.get("verify_alt", [])
    if verify_alt:
        ok, _ = _run_silent(verify_alt)
        if ok:
            return True
    return False


def detect():
    """Run full environment detection. Returns an Environment object."""
    ui.header("Detecting Environment")

    env = Environment()

    # OS
    env.os = _detect_os()
    ui.success(f"OS: {env.os} ({platform.platform()})")

    # Distro (Linux only)
    if env.os == "linux":
        env.distro = _detect_distro()
        ui.success(f"Distro: {env.distro or 'unknown'}")

    # Platform key for registry lookup
    if env.os == "windows":
        env.platform_key = "windows"
    elif env.os == "macos":
        env.platform_key = "macos"
    elif env.distro in ("arch",):
        env.platform_key = "arch"
    elif env.distro in ("ubuntu", "debian"):
        env.platform_key = "ubuntu"
    else:
        env.platform_key = "ubuntu"  # fallback to ubuntu-like
        ui.warn(f"Unknown distro '{env.distro}', using ubuntu-like defaults")

    # Display server
    if env.os == "linux":
        env.display = _detect_display()
        ui.success(f"Display: {env.display or 'unknown'}")

    # GPU
    env.gpu_vendor = _detect_gpu()
    if env.gpu_vendor:
        ui.success(f"GPU: {env.gpu_vendor}")

    # Package manager
    env.pkg_manager = _detect_pkg_manager(env.os, env.distro)
    ui.success(f"Package manager: {env.pkg_manager or 'none detected'}")

    # AUR helper
    if env.distro == "arch":
        env.aur_helper = _detect_aur_helper()
        if env.aur_helper:
            ui.success(f"AUR helper: {env.aur_helper}")

    # Python/pip
    env.python_cmd, env.pip_cmd = _detect_python()

    # Git
    env.has_git = _which("git")

    # Config dir
    env.config_dir = _resolve_config_dir(env.os)
    ui.success(f"mpv config dir: {env.config_dir}")

    # Check installed deps
    from deploy.registry import SYSTEM_DEPS
    ui.step("Checking installed dependencies...")
    for name, info in SYSTEM_DEPS.items():
        env.installed[name] = _check_installed(name, info)
        status = "installed" if env.installed[name] else "missing"
        if env.installed[name]:
            ui.success(f"{name}: {status}")
        else:
            ui.warn(f"{name}: {status}")

    return env
