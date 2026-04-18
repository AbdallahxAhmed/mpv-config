"""
planner.py — Pre-flight action planner and user-approval prompt.

After environment detection this module builds a complete, human-readable
plan of every action the installer intends to take, displays it to the user
with colour-coded action types, and asks for explicit Yes/No approval before
a single file or package is touched.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List, Tuple

from deploy import ui
from deploy.registry import SCRIPTS, SHADERS, SYSTEM_DEPS

if TYPE_CHECKING:
    from deploy.detector import Environment


# ─── Plan entry ────────────────────────────────────────────────────────

class PlanEntry:
    """A single planned action."""

    def __init__(
        self,
        category: str,  # "package" | "fetch" | "backup" | "file"
        action: str,    # "install" | "skip" | "remove" | "backup" | "deploy" | "fetch" | "create"
        target: str,    # package name or file path
        detail: str = "",
    ):
        self.category = category
        self.action = action
        self.target = target
        self.detail = detail


# ─── Plan builders ─────────────────────────────────────────────────────

def build_install_plan(env: "Environment") -> List[PlanEntry]:
    """
    Inspect the environment and return a plan of all install actions.
    Read-only analysis — nothing is executed here.
    """
    plan: List[PlanEntry] = []

    # ── System packages ──────────────────────────────────────────────
    core_deps = ["mpv", "yt-dlp", "ffmpeg", "python"]
    optional_deps = ["ffsubsync", "alass"]

    for name in core_deps + optional_deps:
        is_optional = name in optional_deps
        if env.installed.get(name, False):
            plan.append(PlanEntry(
                "package", "skip", name,
                "already installed — no change",
            ))
        else:
            dep_info = SYSTEM_DEPS.get(name, {})
            pkg_info = (
                dep_info.get(env.platform_key)
                or dep_info.get("all")
                or {}
            )
            method = pkg_info.get("method", "unknown")
            pkg = pkg_info.get("pkg") or pkg_info.get("id") or name
            suffix = " (optional)" if is_optional else " (required)"
            plan.append(PlanEntry(
                "package", "install", name,
                f"install via {method}: {pkg}{suffix}",
            ))

    # ── Scripts & shaders to download ────────────────────────────────
    for script in SCRIPTS:
        repo = script["source"]["repo"]
        plan.append(PlanEntry(
            "fetch", "fetch", script["name"],
            f"download from github.com/{repo}",
        ))
    plan.append(PlanEntry(
        "fetch", "fetch", SHADERS["name"],
        f"download from github.com/{SHADERS['source']['repo']}",
    ))

    # ── Backup ───────────────────────────────────────────────────────
    if os.path.isdir(env.config_dir):
        plan.append(PlanEntry(
            "backup", "backup", env.config_dir,
            "existing config dir backed up with timestamp before overwrite",
        ))
    else:
        plan.append(PlanEntry(
            "backup", "create", env.config_dir,
            "config dir does not yet exist — will be created",
        ))

    # ── Config files to deploy ───────────────────────────────────────
    _deploy_targets: List[Tuple[str, str]] = [
        ("scripts/",                    "mpv scripts (Lua)"),
        ("shaders/",                    "Anime4K shader files (.glsl)"),
        ("fonts/",                      "uosc UI fonts"),
        ("script-opts/",                "per-script config files"),
        ("mpv.conf",                    "main config — patched from template for this platform"),
        ("input.conf",                  "keybinding config — patched from template"),
        ("script-opts/autosubsync.conf","subtitle-sync tool config — patched from template"),
        ("shader_cache/",               "shader cache directory — created if missing"),
        ("chapters/",                   "chapters directory — created if missing"),
        (".deploy.lock.json",           "script version lockfile"),
        (".audit-log.json",             "operation audit log (this run)"),
    ]
    for rel_path, detail in _deploy_targets:
        plan.append(PlanEntry(
            "file", "deploy",
            os.path.join(env.config_dir, rel_path),
            detail,
        ))

    return plan


def build_update_plan(env: "Environment") -> List[PlanEntry]:
    """Build a plan for the update-scripts-only operation."""
    plan: List[PlanEntry] = []

    for script in SCRIPTS:
        plan.append(PlanEntry(
            "fetch", "fetch", script["name"],
            f"re-download latest from github.com/{script['source']['repo']}",
        ))
    plan.append(PlanEntry(
        "fetch", "fetch", SHADERS["name"],
        f"re-download latest from github.com/{SHADERS['source']['repo']}",
    ))

    for rel_path, detail in [
        ("scripts/",          "replace all deployed scripts"),
        ("shaders/",          "replace all deployed shaders"),
        ("fonts/",            "replace fonts"),
        (".deploy.lock.json", "update version lockfile"),
        (".audit-log.json",   "append this update to audit log"),
    ]:
        plan.append(PlanEntry(
            "file", "deploy",
            os.path.join(env.config_dir, rel_path),
            detail,
        ))

    return plan


def build_uninstall_plan(
    env: "Environment",
    pre_existing_pkgs: Dict[str, bool],
    purge_config: bool = False,
    remove_backups: bool = False,
    remove_deps: bool = False,
    remove_python: bool = False,
) -> List[PlanEntry]:
    """
    Build an uninstall plan that honours the audit log: packages that were
    present *before* this tool was run will be skipped — never auto-removed.

    Parameters
    ----------
    env:
        Detected environment.
    pre_existing_pkgs:
        ``{package_name: was_pre_existing}`` from ``AuditLog.get_pre_existing_packages()``.
        If the log is unavailable this should be ``{}`` (all packages assumed
        pre-existing — the conservative safe default).
    purge_config:
        If ``True`` the whole config directory is removed instead of just the
        managed entries.
    remove_backups:
        Also list backup directories for removal.
    remove_deps:
        Include system-package uninstall entries.
    remove_python:
        (Only meaningful when *remove_deps* is True) include Python itself.
    """
    plan: List[PlanEntry] = []

    # ── Config files ─────────────────────────────────────────────────
    if purge_config:
        if os.path.isdir(env.config_dir):
            plan.append(PlanEntry(
                "file", "remove", env.config_dir,
                "entire mpv config directory — all contents deleted",
            ))
    else:
        managed = [
            "scripts", "shaders", "fonts", "script-opts",
            "shader_cache", "chapters",
            "mpv.conf", "input.conf",
            ".deploy.lock.json",
            # .audit-log.json is preserved during partial uninstall so future
            # operations can still consult the history.  It is removed only
            # when purge_config=True deletes the whole config directory.
        ]
        for name in managed:
            path = os.path.join(env.config_dir, name)
            if os.path.lexists(path):
                plan.append(PlanEntry(
                    "file", "remove", path,
                    "deployed by this installer",
                ))

    # ── Backups ──────────────────────────────────────────────────────
    if remove_backups:
        from deploy.deployer import list_backups
        for bp in list_backups(env.config_dir):
            plan.append(PlanEntry(
                "backup", "remove", bp,
                "rollback backup directory",
            ))

    # ── System packages ──────────────────────────────────────────────
    if remove_deps:
        managed_pkgs = ["mpv", "yt-dlp", "ffmpeg", "ffsubsync", "alass"]
        if remove_python:
            managed_pkgs.append("python")

        for name in managed_pkgs:
            # Conservative default: if not in log assume pre-existing
            was_pre_existing = pre_existing_pkgs.get(name, True)
            if not env.installed.get(name, False):
                plan.append(PlanEntry(
                    "package", "skip", name,
                    "not currently installed — nothing to do",
                ))
            elif was_pre_existing:
                plan.append(PlanEntry(
                    "package", "skip", name,
                    "was installed BEFORE this tool — will NOT be removed (safe)",
                ))
            else:
                plan.append(PlanEntry(
                    "package", "remove", name,
                    "was installed BY this tool — will be uninstalled",
                ))

    return plan


# ─── Display & confirmation ────────────────────────────────────────────

_CATEGORY_LABELS: Dict[str, str] = {
    "package": "System Packages",
    "fetch":   "Scripts & Shaders to Download",
    "backup":  "Backup",
    "file":    "Configuration Files",
}

# (ANSI color, icon char, fixed-width label)
_ACTION_STYLE: Dict[str, Tuple[str, str, str]] = {
    "install": (ui._C.YELLOW, "+", "INSTALL"),
    "remove":  (ui._C.RED,    "-", "REMOVE "),
    "fetch":   (ui._C.CYAN,   "↓", "FETCH  "),
    "deploy":  (ui._C.GREEN,  "→", "DEPLOY "),
    "backup":  (ui._C.BLUE,   "⊙", "BACKUP "),
    "create":  (ui._C.GREEN,  "+", "CREATE "),
    "skip":    (ui._C.DIM,    "=", "SKIP   "),
}


def _short_path(path: str) -> str:
    """Replace the home directory prefix with ``~`` for compact display."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def display_plan(plan: List[PlanEntry], title: str = "Planned Actions"):
    """
    Print the action plan grouped by category with colour-coded action types.
    Nothing is executed — this is purely informational output.
    """
    ui.header(title)
    print(f"  {ui._C.DIM}The following actions will be performed:{ui._C.RESET}\n")

    # Collect categories in the order they first appear
    seen_cats: List[str] = []
    categories: Dict[str, List[PlanEntry]] = {}
    for entry in plan:
        if entry.category not in categories:
            categories[entry.category] = []
            seen_cats.append(entry.category)
        categories[entry.category].append(entry)

    cat_order = ["package", "fetch", "backup", "file"]
    ordered = [c for c in cat_order if c in categories] + \
              [c for c in seen_cats if c not in cat_order]

    for cat in ordered:
        entries = categories[cat]
        label = _CATEGORY_LABELS.get(cat, cat.title())
        print(f"  {ui._C.BOLD}{label}:{ui._C.RESET}")
        for entry in entries:
            color, icon, action_label = _ACTION_STYLE.get(
                entry.action,
                (ui._C.WHITE, "?", entry.action.upper()[:7].ljust(7)),
            )
            target = _short_path(entry.target)
            detail_str = (
                f"  {ui._C.DIM}# {entry.detail}{ui._C.RESET}"
                if entry.detail else ""
            )
            print(
                f"    {color}[{icon}]{ui._C.RESET} "
                f"{ui._C.DIM}{action_label}{ui._C.RESET} "
                f"{target}{detail_str}"
            )
        print()


def confirm_plan(plan: List[PlanEntry], operation: str = "install") -> bool:
    """
    Print a one-line summary and ask the user for explicit Yes/No approval.

    Returns ``True`` if the user approves (or presses Enter), ``False``
    if they type ``n``/``no`` or press Ctrl+C.
    """
    active = [e for e in plan if e.action != "skip"]
    skipped = len(plan) - len(active)

    print(
        f"  {ui._C.BOLD}Summary:{ui._C.RESET} "
        f"{ui._C.GREEN}{len(active)}{ui._C.RESET} action(s) pending"
        + (f", {ui._C.DIM}{skipped} skipped{ui._C.RESET}" if skipped else "")
        + ".\n"
    )

    try:
        reply = input(
            f"  {ui._C.YELLOW}?{ui._C.RESET}  "
            f"Proceed with {operation}? "
            f"{ui._C.BOLD}[Y/n]{ui._C.RESET} "
        ).strip().lower()
        return reply in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
