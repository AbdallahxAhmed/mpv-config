"""
installer.py — Install system dependencies.

Handles package installation via winget, pacman, apt, brew, and pip
based on the detected environment.
"""

import shutil
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

    elif method == "pipx":
        if not _ensure_pipx(env):
            return False
        return _run(["pipx", "install", info["pkg"]])

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
    elif method == "aur":
        if env.aur_helper:
            return _run([env.aur_helper, "-Rns", "--noconfirm", info["pkg"]], check=False)
        ui.warn(f"{name} was installed from AUR; no AUR helper found for auto-uninstall.")
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

    managed = ["mpv", "yt-dlp", "ffmpeg", "ffsubsync", "alass"]
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
