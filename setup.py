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
    python setup.py --verify        # Verify current install
    python setup.py --status        # Show install status
    python setup.py --dry-run       # Preview without changes
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

# Ensure we can import the deploy package from this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from deploy import ui
from deploy.registry import SCRIPTS, SHADERS
from deploy.detector import detect
from deploy.installer import install_deps
from deploy.fetcher import fetch_all
from deploy.deployer import deploy, rollback_config
from deploy.verifier import verify


def cmd_install(args):
    """Full installation: detect → install deps → fetch → deploy → verify."""
    ui.banner()

    # 1. Detect environment
    env = detect()

    # 2. Check connectivity
    ui.header("Pre-flight Checks")
    try:
        import urllib.request
        urllib.request.urlopen("https://api.github.com", timeout=5)
        ui.success("Internet connectivity: OK")
    except Exception:
        ui.error("Cannot reach GitHub. Check your internet connection.")
        if not args.dry_run:
            sys.exit(1)

    # 3. Install system dependencies
    dep_results = install_deps(env, dry_run=args.dry_run)

    # 4. Fetch scripts & shaders into a staging directory
    staging_dir = os.path.join(SCRIPT_DIR, ".staging")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir)

    try:
        fetch_results, lockfile = fetch_all(SCRIPTS, SHADERS, staging_dir)

        # 5. Deploy to config dir
        deploy_results = deploy(staging_dir, env, SCRIPT_DIR, dry_run=args.dry_run)

        # 6. Save lockfile
        if not args.dry_run:
            lockfile_path = os.path.join(env.config_dir, ".deploy.lock.json")
            with open(lockfile_path, "w", encoding="utf-8") as f:
                json.dump(lockfile, f, indent=2)
            ui.success(f"Lockfile saved: {lockfile_path}")

        # 7. Verify
        if not args.dry_run:
            verify_results = verify(env.config_dir, env)
        else:
            verify_results = []

        # 8. Final summary
        all_results = dep_results + fetch_results + deploy_results + verify_results
        ui.summary(fetch_results)

        # Done!
        if not args.dry_run:
            failed = sum(1 for r in fetch_results if r["status"] == "failed")
            if failed == 0:
                print(f"\n  {ui.C.GREEN}{ui.C.BOLD}🎉 Deployment complete!{ui.C.RESET}")
                print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")
            else:
                print(f"\n  {ui.C.YELLOW}⚠ Deployment finished with {failed} issue(s).{ui.C.RESET}")
                print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")
    finally:
        # Clean up staging
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)


def cmd_update(args):
    """Update scripts only (re-fetch + deploy, no dep installation)."""
    ui.banner()

    env = detect()

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

        # Save lockfile
        lockfile_path = os.path.join(config_dir, ".deploy.lock.json")
        with open(lockfile_path, "w", encoding="utf-8") as f:
            json.dump(lockfile, f, indent=2)

        ui.summary(fetch_results)
        print(f"\n  {ui.C.GREEN}{ui.C.BOLD}✨ Update complete!{ui.C.RESET}\n")
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

    print(f"\n  {ui.C.DIM}Lockfile: {lockfile_path}{ui.C.RESET}")
    print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")


def cmd_rollback(args):
    """Rollback current config from backup."""
    ui.banner()
    env = detect()

    requested_backup = None if args.rollback == "__latest__" else args.rollback

    ui.header("Rollback Configuration")
    result = rollback_config(env.config_dir, backup_path=requested_backup, dry_run=args.dry_run)
    ui.summary([result])

    if result["status"] == "ok":
        print(f"\n  {ui.C.GREEN}{ui.C.BOLD}↩ Rollback complete!{ui.C.RESET}")
        print(f"  {ui.C.DIM}Config dir: {env.config_dir}{ui.C.RESET}\n")


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
        const="__latest__",
        metavar="BACKUP_DIR",
        help="Rollback to latest backup (or provide a specific backup directory)",
    )
    parser.add_argument("--verify", action="store_true", help="Verify current deployment")
    parser.add_argument("--status", action="store_true", help="Show installed versions")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")

    args = parser.parse_args()

    # Default to --install if no action specified
    if not any([args.install, args.update, args.verify, args.status, args.rollback is not None]):
        args.install = True

    try:
        if args.rollback is not None:
            cmd_rollback(args)
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
