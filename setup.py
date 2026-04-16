#!/usr/bin/env python3
"""
setup.py — MPV Auto-Deploy System

One command to rule them all. Detects your OS, installs dependencies,
fetches scripts from their upstream sources, and deploys everything
to the right place.

Usage:
    python setup.py                 # Full install (interactive)
    python setup.py --install       # Full install
    python setup.py --update        # Update scripts only
    python setup.py --rollback      # Restore latest backup
    python setup.py --rollback <backup_dir>  # Restore specific backup
    python setup.py --uninstall     # Remove deployed files
    python setup.py --verify        # Verify current install
    python setup.py --status        # Show install status
    python setup.py --dry-run       # Preview without changes
"""

import argparse
import json
import os
import shutil
import sys

# Ensure we can import the deploy package from this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from deploy import ui
from deploy.registry import SCRIPTS, SHADERS
from deploy.detector import detect
from deploy.installer import install_deps, uninstall_deps
from deploy.fetcher import fetch_all
from deploy.deployer import deploy, rollback_config, list_backups, _remove_path as remove_path_safe
from deploy.verifier import verify
from deploy.audit_log import AuditLog
from deploy.planner import (
    build_install_plan, build_update_plan, build_uninstall_plan,
    display_plan, confirm_plan,
)

LATEST_BACKUP_SENTINEL = "__latest__"
DEFAULT_INSTALL_DIR = os.path.expanduser("~/.mpv-deploy")
DEFAULT_LAUNCHER = os.path.expanduser("~/.local/bin/mpv-config")
MENU_MAX_OPTION = 8


def _audit_log_for(env):
    """Return an AuditLog instance pointing at the config dir's log file."""
    log_path = os.path.join(env.config_dir, ".audit-log.json")
    return AuditLog(log_path)


def cmd_install(args):
    """Full installation: detect → plan → confirm → install deps → fetch → deploy → verify."""
    ui.banner()

    # 1. Detect environment
    env = detect()

    # 2. Build and display the pre-flight action plan so the user knows
    #    exactly what will happen before anything is changed.
    plan = build_install_plan(env)
    display_plan(plan, "Installation Plan")

    # 3. Ask for explicit approval — skip only for dry-runs or non-interactive
    #    sessions (e.g. piped into bash).
    if not args.dry_run and _is_interactive_session():
        if not confirm_plan(plan, "installation"):
            ui.warn("Installation cancelled by user.")
            return

    # 4. Initialise audit log (creates the config dir early so the log can
    #    be written even before deploy() runs).
    os.makedirs(env.config_dir, exist_ok=True)
    audit_log = _audit_log_for(env)
    audit_log.start_session("install", env)

    try:
        # 5. Check connectivity
        ui.header("Pre-flight Checks")
        try:
            import urllib.request
            urllib.request.urlopen("https://api.github.com", timeout=5)
            ui.success("Internet connectivity: OK")
        except Exception:
            ui.error("Cannot reach GitHub. Check your internet connection.")
            if not args.dry_run:
                audit_log.complete_session("failed")
                sys.exit(1)

        # 6. Install system dependencies
        dep_results = install_deps(env, dry_run=args.dry_run, audit_log=audit_log)

        # 7. Fetch scripts & shaders into a staging directory
        staging_dir = os.path.join(SCRIPT_DIR, ".staging")
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir)

        try:
            fetch_results, lockfile = fetch_all(SCRIPTS, SHADERS, staging_dir)

            # 8. Deploy to config dir
            deploy_results = deploy(staging_dir, env, SCRIPT_DIR, dry_run=args.dry_run, audit_log=audit_log)

            # 9. Save lockfile
            if not args.dry_run:
                lockfile_path = os.path.join(env.config_dir, ".deploy.lock.json")
                with open(lockfile_path, "w", encoding="utf-8") as f:
                    json.dump(lockfile, f, indent=2)
                ui.success(f"Lockfile saved: {lockfile_path}")
                audit_log.record_file(lockfile_path, "create", "ok", "script version lockfile")

            # 10. Verify
            if not args.dry_run:
                verify_results = verify(env.config_dir, env)
            else:
                verify_results = []

            # 11. Final summary
            all_results = dep_results + fetch_results + deploy_results + verify_results
            ui.summary(fetch_results)

            # Done!
            if not args.dry_run:
                failed = sum(1 for r in fetch_results if r["status"] == "failed")
                if failed == 0:
                    print(f"\n  {ui.C.GREEN}{ui.C.BOLD}🎉 Deployment complete!{ui.C.RESET}")
                    print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")
                    audit_log.complete_session("completed")
                else:
                    print(f"\n  {ui.C.YELLOW}⚠ Deployment finished with {failed} issue(s).{ui.C.RESET}")
                    print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")
                    audit_log.complete_session("completed_with_errors")
        finally:
            # Clean up staging
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)

    except Exception:
        try:
            audit_log.complete_session("failed")
        except Exception:
            pass
        raise


def cmd_update(args):
    """Update scripts only (re-fetch + deploy, no dep installation)."""
    ui.banner()

    env = detect()

    # Show what will be updated
    plan = build_update_plan(env)
    display_plan(plan, "Update Plan")

    if not args.dry_run and _is_interactive_session():
        if not confirm_plan(plan, "update"):
            ui.warn("Update cancelled by user.")
            return

    audit_log = _audit_log_for(env)
    audit_log.start_session("update", env)

    staging_dir = os.path.join(SCRIPT_DIR, ".staging")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir)

    try:
        fetch_results, lockfile = fetch_all(SCRIPTS, SHADERS, staging_dir)

        # Deploy only scripts, shaders, fonts (not configs)
        config_dir = env.config_dir
        for item in ("scripts", "shaders", "fonts"):
            src = os.path.join(staging_dir, item)
            dst = os.path.join(config_dir, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                count = sum(len(f) for _, _, f in os.walk(dst))
                ui.success(f"{item}/: {count} file(s) updated")
                audit_log.record_file(dst, "copy", "ok", f"{count} file(s) updated")

        # Save lockfile
        lockfile_path = os.path.join(config_dir, ".deploy.lock.json")
        with open(lockfile_path, "w", encoding="utf-8") as f:
            json.dump(lockfile, f, indent=2)
        audit_log.record_file(lockfile_path, "modify", "ok", "version lockfile updated")

        ui.summary(fetch_results)
        print(f"\n  {ui.C.GREEN}{ui.C.BOLD}✨ Update complete!{ui.C.RESET}\n")
        audit_log.complete_session("completed")
    except Exception:
        try:
            audit_log.complete_session("failed")
        except Exception:
            pass
        raise
    finally:
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)


def cmd_verify(args):
    """Verify the current installation."""
    ui.banner()
    env = detect()
    results = verify(env.config_dir, env)
    ui.summary(results)


def cmd_status(args):
    """Show current install status vs available versions."""
    ui.banner()
    env = detect()

    lockfile_path = os.path.join(env.config_dir, ".deploy.lock.json")
    if not os.path.isfile(lockfile_path):
        ui.warn("No deployment lockfile found. Run 'setup.py --install' first.")
        return

    with open(lockfile_path, "r", encoding="utf-8") as f:
        lockfile = json.load(f)

    ui.header("Installed Scripts")

    scripts_data = lockfile.get("scripts", {})
    for name, info in scripts_data.items():
        version = info.get("version", info.get("source", "unknown"))
        date = info.get("fetched_at", "")[:10]
        ui.success(f"{name}: {version} (fetched {date})")

    # Also show audit log summary if available
    audit_log = _audit_log_for(env)
    sessions = audit_log.sessions()
    if sessions:
        last = sessions[-1]
        ui.header("Last Installer Session")
        ui.info(f"Operation : {last.get('operation', '?')}")
        ui.info(f"Status    : {last.get('status', '?')}")
        ui.info(f"Started   : {last.get('started_at', '?')}")
        ui.info(f"Completed : {last.get('completed_at', '?') or '(in progress)'}")
        pkg_safe = audit_log.get_packages_installed_by_us()
        if pkg_safe:
            ui.info(f"Installed by this tool (safe to remove): {', '.join(pkg_safe)}")

    print(f"\n  {ui.C.DIM}Lockfile: {lockfile_path}{ui.C.RESET}")
    print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")


def cmd_rollback(args):
    """Rollback current config from backup."""
    ui.banner()
    env = detect()

    requested_backup = None if args.rollback == LATEST_BACKUP_SENTINEL else args.rollback

    ui.header("Rollback Configuration")

    # Explain what will happen
    backups = list_backups(env.config_dir)
    if not backups and not requested_backup:
        ui.error("No backups found. Cannot rollback.")
        sys.exit(1)

    target_backup = requested_backup or (backups[0] if backups else None)
    if target_backup:
        ui.info(f"Will restore config from: {target_backup}")
        ui.info(f"Current config will be saved as a pre-rollback snapshot.")

    if not args.dry_run and _is_interactive_session():
        if not ui.confirm("Proceed with rollback?"):
            ui.warn("Rollback cancelled by user.")
            return

    audit_log = _audit_log_for(env)
    audit_log.start_session("rollback", env)

    try:
        result = rollback_config(env.config_dir, backup_path=requested_backup, dry_run=args.dry_run, audit_log=audit_log)
        ui.summary([result])

        if result["status"] == "ok":
            print(f"\n  {ui.C.GREEN}{ui.C.BOLD}↩ Rollback complete!{ui.C.RESET}")
            print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")
            audit_log.complete_session("completed")
        else:
            audit_log.complete_session("completed")
    except Exception:
        try:
            audit_log.complete_session("failed")
        except Exception:
            pass
        raise


def _remove_deployed_files(env, purge_config=False, remove_backups=False, dry_run=False, audit_log=None):
    results = []
    config_dir = env.config_dir

    managed_entries = [
        "scripts",
        "shaders",
        "fonts",
        "script-opts",
        "shader_cache",
        "chapters",
        "mpv.conf",
        "input.conf",
        ".deploy.lock.json",
        ".audit-log.json",
    ]

    if purge_config:
        if os.path.exists(config_dir):
            if dry_run:
                ui.info(f"[DRY RUN] Would remove config dir: {config_dir}")
                results.append({"name": "config_dir", "status": "skipped", "detail": "dry run"})
            else:
                remove_path_safe(config_dir)
                ui.success(f"Removed config dir: {config_dir}")
                results.append({"name": "config_dir", "status": "ok", "detail": "removed"})
                if audit_log:
                    audit_log.record_file(config_dir, "delete", "ok", "full config dir removed")
        else:
            results.append({"name": "config_dir", "status": "skipped", "detail": "not found"})
    else:
        for name in managed_entries:
            path = os.path.join(config_dir, name)
            if not os.path.lexists(path):
                continue
            if dry_run:
                ui.info(f"[DRY RUN] Would remove: {path}")
                results.append({"name": name, "status": "skipped", "detail": "dry run"})
            else:
                remove_path_safe(path)
                ui.success(f"Removed: {path}")
                results.append({"name": name, "status": "ok", "detail": "removed"})
                if audit_log:
                    audit_log.record_file(path, "delete", "ok", "removed by uninstall")

    if remove_backups:
        backups = list_backups(config_dir)
        if not backups:
            results.append({"name": "backups", "status": "skipped", "detail": "none found"})
        for backup in backups:
            if dry_run:
                ui.info(f"[DRY RUN] Would remove backup: {backup}")
                results.append({"name": "backup", "status": "skipped", "detail": backup})
            else:
                shutil.rmtree(backup)
                ui.success(f"Removed backup: {backup}")
                results.append({"name": "backup", "status": "ok", "detail": backup})
                if audit_log:
                    audit_log.record_file(backup, "delete", "ok", "backup removed by uninstall")

    return results


def _remove_launcher_and_install_dir(remove_install_dir=False, dry_run=False, audit_log=None):
    results = []
    if os.path.lexists(DEFAULT_LAUNCHER):
        if dry_run:
            ui.info(f"[DRY RUN] Would remove launcher: {DEFAULT_LAUNCHER}")
            results.append({"name": "launcher", "status": "skipped", "detail": "dry run"})
        else:
            remove_path_safe(DEFAULT_LAUNCHER)
            ui.success(f"Removed launcher: {DEFAULT_LAUNCHER}")
            results.append({"name": "launcher", "status": "ok", "detail": "removed"})
            if audit_log:
                audit_log.record_file(DEFAULT_LAUNCHER, "delete", "ok", "launcher removed")

    if remove_install_dir and os.path.isdir(DEFAULT_INSTALL_DIR):
        if dry_run:
            ui.info(f"[DRY RUN] Would remove install dir: {DEFAULT_INSTALL_DIR}")
            results.append({"name": "install_dir", "status": "skipped", "detail": "dry run"})
        else:
            shutil.rmtree(DEFAULT_INSTALL_DIR, ignore_errors=True)
            ui.success(f"Removed install dir: {DEFAULT_INSTALL_DIR}")
            results.append({"name": "install_dir", "status": "ok", "detail": "removed"})

    return results


def cmd_uninstall(args):
    """Remove deployed files and optionally dependencies."""
    ui.banner()
    env = detect()

    ui.header("Uninstall MPV Auto-Deploy")

    # Load the audit log to find out which packages were pre-existing.
    # If no log exists we fall back to the safe default (assume everything
    # is pre-existing so nothing is auto-removed).
    audit_log = _audit_log_for(env)
    pre_existing_pkgs = audit_log.get_pre_existing_packages()

    if not pre_existing_pkgs:
        ui.warn("No audit log found — all packages assumed pre-existing.")
        ui.warn("System packages will NOT be auto-removed even if --remove-deps is set.")

    # Build and show the full uninstall plan so the user can review what
    # will actually happen before anything is deleted.
    plan = build_uninstall_plan(
        env,
        pre_existing_pkgs=pre_existing_pkgs,
        purge_config=args.purge_config,
        remove_backups=args.remove_backups,
        remove_deps=args.remove_deps,
        remove_python=getattr(args, "remove_python", False),
    )
    display_plan(plan, "Uninstall Plan")

    # Ask for a single confirmation that covers everything.
    if not args.dry_run:
        if not confirm_plan(plan, "uninstall"):
            ui.warn("Uninstall cancelled by user.")
            return

    # Start an audit session to record the uninstall
    audit_log.start_session("uninstall", env)

    remove_results = _remove_deployed_files(
        env,
        purge_config=args.purge_config,
        remove_backups=args.remove_backups,
        dry_run=args.dry_run,
        audit_log=audit_log,
    )

    dep_results = []
    if args.remove_deps:
        dep_results = uninstall_deps(
            env,
            remove_python=getattr(args, "remove_python", False),
            dry_run=args.dry_run,
            pre_existing_pkgs=pre_existing_pkgs,
            audit_log=audit_log,
        )
    else:
        dep_results.append({"name": "dependencies", "status": "skipped", "detail": "not requested"})

    cleanup_results = _remove_launcher_and_install_dir(
        remove_install_dir=args.remove_install_dir,
        dry_run=args.dry_run,
        audit_log=audit_log,
    )

    all_results = remove_results + dep_results + cleanup_results
    ui.summary(all_results)
    if not args.dry_run:
        print(f"\n  {ui.C.GREEN}{ui.C.BOLD}🧹 Uninstall completed.{ui.C.RESET}\n")
        try:
            audit_log.complete_session("completed")
        except Exception:
            pass


def _is_interactive_session():
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _has_explicit_action(args):
    return any([
        args.install,
        args.update,
        args.verify,
        args.status,
        args.rollback is not None,
        args.uninstall,
    ])


def _interactive_menu(args):
    ui.banner()
    ui.header("Choose Action")
    print("  1) Full install")
    print("  2) Update scripts/shaders")
    print("  3) Rollback (latest backup)")
    print("  4) Rollback (specific backup path)")
    print("  5) Verify installation")
    print("  6) Show status")
    print("  7) Uninstall deployed files")
    print(f"  {MENU_MAX_OPTION}) Full remove (files + backups + deps + install dir)")
    print("  0) Exit")

    choice = input(f"\n  Select option [0-{MENU_MAX_OPTION}]: ").strip()
    if choice == "1":
        args.install = True
    elif choice == "2":
        args.update = True
    elif choice == "3":
        args.rollback = LATEST_BACKUP_SENTINEL
    elif choice == "4":
        path = input("  Backup path: ").strip()
        if not path:
            raise ValueError("Backup path cannot be empty. Please enter a valid path.")
        args.rollback = path
    elif choice == "5":
        args.verify = True
    elif choice == "6":
        args.status = True
    elif choice == "7":
        args.uninstall = True
        args.purge_config = ui.confirm("  Remove whole mpv config directory?")
        args.remove_backups = ui.confirm("  Remove rollback backups too?")
    elif choice == str(MENU_MAX_OPTION):
        args.uninstall = True
        args.purge_config = True
        args.remove_backups = True
        args.remove_deps = True
        args.remove_install_dir = True
        # Inform the user why removing Python is risky before asking
        print(
            f"\n  {ui.C.YELLOW}!{ui.C.RESET}  Removing Python packages is potentially risky: other"
            f" tools on your system may depend on the same packages."
        )
        print(
            f"  {ui.C.DIM}The audit log will be consulted — only packages installed"
            f" by this tool will be removed.{ui.C.RESET}"
        )
        args.remove_python = ui.confirm("  Also remove Python packages installed by this tool?")
    elif choice == "0":
        raise KeyboardInterrupt
    else:
        raise ValueError(f"Invalid selection. Please choose a number between 0 and {MENU_MAX_OPTION}.")


def main():
    parser = argparse.ArgumentParser(
        description="MPV Auto-Deploy System — one command, full setup.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--install", action="store_true", help="Full install (detect → deps → fetch → deploy → verify)")
    parser.add_argument("--update", action="store_true", help="Update scripts/shaders only")
    parser.add_argument(
        "--rollback",
        nargs="?",
        const=LATEST_BACKUP_SENTINEL,
        metavar="BACKUP_DIR",
        help="Rollback to latest backup (or provide a specific backup directory)",
    )
    parser.add_argument("--uninstall", action="store_true", help="Remove deployed files/config by this installer")
    parser.add_argument("--verify", action="store_true", help="Verify current deployment")
    parser.add_argument("--status", action="store_true", help="Show installed versions")
    parser.add_argument("--interactive", action="store_true", help="Show interactive menu")
    parser.add_argument("--purge-config", action="store_true", help="With --uninstall: remove full mpv config directory")
    parser.add_argument("--remove-backups", action="store_true", help="With --uninstall: remove backup directories")
    parser.add_argument("--remove-deps", action="store_true", help="With --uninstall: uninstall managed dependencies")
    parser.add_argument("--remove-python", action="store_true", help="With --remove-deps: also try uninstalling python package")
    parser.add_argument("--remove-install-dir", action="store_true", help="With --uninstall: remove ~/.mpv-deploy and launcher")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")

    args = parser.parse_args()

    try:
        if args.interactive or (not _has_explicit_action(args) and _is_interactive_session()):
            _interactive_menu(args)

        # Default to --install if no action specified and not interactive
        if not _has_explicit_action(args):
            args.install = True

        if args.rollback is not None:
            cmd_rollback(args)
        elif args.uninstall:
            cmd_uninstall(args)
        elif args.verify:
            cmd_verify(args)
        elif args.status:
            cmd_status(args)
        elif args.update:
            cmd_update(args)
        else:
            cmd_install(args)
    except KeyboardInterrupt:
        print(f"\n\n  {ui.C.YELLOW}Interrupted by user.{ui.C.RESET}\n")
        sys.exit(130)
    except Exception as e:
        ui.error(f"Fatal error: {e}")
        if os.getenv("DEBUG"):
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
