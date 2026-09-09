#!/usr/bin/env python3
"""
tools/patch_uosc_timeline_thumb.py

Idempotent patcher for uosc Timeline.lua to ensure thumbnail overlay
is properly cleared when the mouse leaves the mpv window.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PATCH_MARKER = "-- UOSC_TIMELINE_THUMB_CLEANUP_PATCH"

TARGET_LEAVE_PATTERN = r"(function\s+Timeline:on_global_mouse_leave\(\)\s*\n\s*self\.pressed\s*=\s*false)(\s*\n\s*end)"


def get_default_uosc_dir() -> Path:
    """Resolve default uosc directory based on host OS."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            win_path = Path(appdata) / "mpv" / "scripts" / "uosc"
            if win_path.exists():
                return win_path
    home = Path.home()
    return home / ".config" / "mpv" / "scripts" / "uosc"


def patch_timeline_lua(content: str) -> str:
    """Ensure Timeline:on_global_mouse_leave calls self:clear_thumbnail()."""
    if PATCH_MARKER in content or "self:clear_thumbnail()" in content.split("function Timeline:on_global_mouse_leave")[1].split("end")[0]:
        return content

    replacement = r"\1\n\t" + PATCH_MARKER + r"\n\tself:clear_thumbnail()\2"
    patched, count = re.subn(TARGET_LEAVE_PATTERN, replacement, content, count=1)
    if count == 0:
        raise RuntimeError("Failed to anchor Timeline:on_global_mouse_leave in Timeline.lua")
    return patched


def unpatch_timeline_lua(content: str) -> str:
    """Revert Timeline:on_global_mouse_leave to original."""
    if PATCH_MARKER not in content and "self:clear_thumbnail()" not in content.split("function Timeline:on_global_mouse_leave")[1].split("end")[0]:
        return content

    pattern = (
        r"(\s*\t*" + re.escape(PATCH_MARKER) + r"\s*\n)?"
        r"\s*\t*self:clear_thumbnail\(\)\s*\n"
    )
    # Only replace inside on_global_mouse_leave
    parts = content.split("function Timeline:on_global_mouse_leave()")
    if len(parts) != 2:
        return content

    body, rest = parts[1].split("end", 1)
    body = re.sub(pattern, "", body)
    if not body.endswith("\n"):
        body += "\n"
    return parts[0] + "function Timeline:on_global_mouse_leave()" + body + "end" + rest


def run_patcher(uosc_dir: Path, unpatch: bool = False) -> None:
    timeline_path = uosc_dir / "elements" / "Timeline.lua"
    if not timeline_path.exists():
        print(f"Error: Target file missing: {timeline_path}", file=sys.stderr)
        sys.exit(1)

    content = timeline_path.read_text(encoding="utf-8")
    new_content = unpatch_timeline_lua(content) if unpatch else patch_timeline_lua(content)

    action_label = "Unpatching" if unpatch else "Patching"
    if new_content != content:
        timeline_path.write_text(new_content, encoding="utf-8")
        print(f"[OK] {action_label} completed: {timeline_path}")
    else:
        print(f"[-] {timeline_path} already {'unpatched' if unpatch else 'patched'}")


def main():
    parser = argparse.ArgumentParser(description="Patch uosc Timeline.lua for thumbnail cleanup on window exit.")
    parser.add_argument(
        "--uosc-dir",
        type=Path,
        default=get_default_uosc_dir(),
        help="Target uosc directory",
    )
    parser.add_argument(
        "--unpatch",
        action="store_true",
        help="Revert patch and restore original uosc source",
    )
    args = parser.parse_args()
    run_patcher(args.uosc_dir, args.unpatch)


if __name__ == "__main__":
    main()
