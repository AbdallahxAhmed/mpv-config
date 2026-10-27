"""
dep_actions.py — The single source of truth for what will happen to each
system dependency in this session.

One decision function consumed by BOTH sides:

- planner.display-plan: renders each action as an Installation Plan row
  (the plan can no longer contradict the installer).
- installer.install_deps: executes exactly what the plan announced.

Each action classifies as ``install`` (binary missing — or mpv below the
config's minimum), ``refresh`` (installed but stale past its registry
``refresh_days`` gate) or ``skip`` (installed and fresh — no change).
File-method deps also carry a write-probed landing directory, choosing the
registered ``fallback_install_dir`` (a user-writable dir, e.g.
%APPDATA%\\mpv\\tools) when the primary install dir is read-only in this
shell — so a non-elevated install lands somewhere real instead of dying
on ``C:\\Program Files`` ACLs after downloading megabytes.
"""

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from deploy.registry import MPV_MINIMUM_VERSION, SYSTEM_DEPS

CORE_DEPS = ["mpv", "yt-dlp", "ffmpeg", "python", "uv"]
OPTIONAL_DEPS = ["ffsubsync", "alass"]

_DIR_PROBE_PID = f"{os.getpid():d}"


@dataclass
class DepAction:
    """One planned dependency operation, shared by plan and installer."""

    name: str
    kind: str  # "install" | "refresh" | "skip"
    optional: bool
    landing_dir: Optional[str]  # dir the binary will land in; None = no download
    writable: Optional[bool]  # write-probe verdict for landing_dir; None = no download
    detail: str  # human wording shared by the plan row and install messages


def dir_is_writable(path):
    """True when this user can create a file in ``path`` (create-unlink probe).

    ``os.access(dir, W_OK)`` lies on Windows ACLs (C:\\Program Files reports
    writable for any user while os.open is denied). Probing the nearest
    EXISTING ancestor avoids creating directories at plan time while still
    establishing whether the target can be created.
    """
    probe_dir = path
    while not os.path.isdir(probe_dir):
        parent = os.path.dirname(probe_dir)
        if parent == probe_dir:
            return False
        probe_dir = parent
    probe = os.path.join(probe_dir, f".mpv-write-{_DIR_PROBE_PID}")
    try:
        fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return False
    os.close(fd)
    os.unlink(probe)
    return True


def dep_dest(info):
    """Absolute binary path that a file-based install method produces (or None)."""
    install_dir = info.get("install_dir")
    dest_name = info.get("dest_name")
    if install_dir and dest_name:
        return os.path.join(install_dir, dest_name)
    return None


def _dest_candidates(info):
    """All dirs a landing copy of this dep may exist in: primary, then fallback.

    A refresh previously landed in the fallback dir leaves its stamp there;
    the age check must look there too or every run would re-download.
    """
    candidates = []
    dest = dep_dest(info)
    if dest:
        candidates.append(dest)
    fallback = info.get("fallback_install_dir")
    primary = info.get("install_dir")
    if fallback and fallback != primary:
        alt = dep_dest({**info, "install_dir": fallback, "ensure_in_dir": fallback})
        if alt and alt not in candidates:
            candidates.append(alt)
    return candidates


def dep_is_fresh(info, refresh_days):
    """True when the file-method binary was installed < refresh_days.

    A binary without a stamp (e.g. apt's frozen /usr/bin/yt-dlp) counts as
    STALE so the file-based installer gets the chance to shadow it with a
    current build — YouTube extractor rules go stale weekly. Honors the
    fallback landing dir (see _dest_candidates).
    """
    for dest in _dest_candidates(info):
        try:
            stamp_mtime = os.stat(dest + ".stamp").st_mtime
        except OSError:
            continue
        return (time.time() - stamp_mtime) < refresh_days * 86400
    return False


def write_refresh_stamp(info):
    """Record a file-method install as "fresh" (sidecar <binary>.stamp file)."""
    dest = dep_dest(info)
    if not dest or not os.path.isfile(dest):
        return
    try:
        with open(dest + ".stamp", "w", encoding="utf-8") as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass


def _landing(info, is_writable):
    """(landing_dir, writable) for a file-method entry; (None, None) otherwise.

    Primary install dir probed first; a registered fallback_install_dir is
    probed second (both against the nearest existing ancestor, see
    dir_is_writable). Neither writable → the planned landing stays the
    primary dir with writable=False so the plan can say "will not land".
    """
    primary = info.get("install_dir")
    if not primary:
        return None, None
    if is_writable(primary):
        return primary, True
    fallback = info.get("fallback_install_dir")
    if fallback and is_writable(fallback):
        return fallback, True
    return primary, False


def _detail_suffix(landing_dir, writable, primary):
    """Human note added to install/refresh details about where bytes land."""
    if landing_dir is None:
        return ""
    if writable:
        if landing_dir != primary:
            return f" → lands in {landing_dir} (primary dir not writable in this shell)"
        return ""
    return f" — {landing_dir} is not writable in this shell (needs Administrator)"


def compute_dep_actions(env) -> List[DepAction]:
    """Classify every core/optional dep for THIS environment. Read-only apart
    from the filesystem write probe, so it is safe to call at plan time."""
    optional_names = list(OPTIONAL_DEPS)
    if env.os == "windows":
        optional_names.append("autohotkey")

    actions: List[DepAction] = []
    for name in CORE_DEPS + optional_names:
        optional = name not in CORE_DEPS
        installed = env.installed.get(name, False)
        info: Dict = SYSTEM_DEPS.get(name, {}).get(env.platform_key) or {}
        method = info.get("method", "unknown")
        pkg = info.get("pkg") or info.get("id") or name

        if (
            installed
            and name == "mpv"
            and env.mpv_version is not None
            and env.mpv_version < MPV_MINIMUM_VERSION
        ):
            # "Installed" but below the config's minimum (e.g. a distro
            # build) — force an upgrade instead of skipping.
            actions.append(
                DepAction(
                    name,
                    "install",
                    False,
                    None,
                    None,
                    f"installed {'.'.join(map(str, env.mpv_version))} < required "
                    f"{'.'.join(map(str, MPV_MINIMUM_VERSION))} — upgrade via "
                    "ppa:ubuntuhandbook1/mpv",
                )
            )
            continue

        if installed:
            refresh_days = info.get("refresh_days")
            if refresh_days and not dep_is_fresh(info, refresh_days):
                landing, writable = _landing(info, dir_is_writable)
                detail = (
                    f"refreshing (older than {refresh_days} days — goes stale too "
                    f"fast to trust){_detail_suffix(landing, writable, info.get('install_dir'))}"
                )
                actions.append(DepAction(name, "refresh", optional, landing, writable, detail))
            else:
                actions.append(DepAction(name, "skip", optional, None, None,
                                         "already installed — no change"))
            continue

        suffix = " (optional)" if optional else " (required)"
        base = f"install via {method}: {pkg}{suffix}"
        landing, writable = _landing(info, dir_is_writable)
        detail = f"{base}{_detail_suffix(landing, writable, info.get('install_dir'))}"
        actions.append(DepAction(name, "install", optional, landing, writable, detail))

    return actions


def installable(action: DepAction) -> bool:
    """True when the installer must run the install methods for this action.

    An action whose landing dir cannot be written is NOT installable: the
    caller must skip it (optional) or fail it (required) without a download.
    """
    return action.writable is not False and action.kind in ("install", "refresh")
