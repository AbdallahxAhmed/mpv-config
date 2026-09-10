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
PATCH_READY_MARKER = "-- UOSC_TIMELINE_THUMB_READY_PATCH"

TARGET_LEAVE_PATTERN = r"(function\s+Timeline:on_global_mouse_leave\(\)\s*\n\s*self\.pressed\s*=\s*false)(\s*\n\s*end)"
TARGET_RECT_PATTERN = r"(\t+local bx, by = [^\n]+\n)(\t+)(ass:rect\(ax,\s*ay,\s*bx,\s*by,\s*\{.*?\n\2\}\))(\n\t+local thumb_seconds)"


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
    """Ensure Timeline:on_global_mouse_leave calls self:clear_thumbnail(),

    and guard thumbnail ass:rect so empty black placeholders are suppressed
    until thumbfast has produced a valid frame.
    """
    patched = content

    # 1. Mouse leave cleanup patch
    has_leave_patch = PATCH_MARKER in patched or (
        "function Timeline:on_global_mouse_leave" in patched
        and "self:clear_thumbnail()" in patched.split("function Timeline:on_global_mouse_leave")[1].split("end")[0]
    )
    if not has_leave_patch:
        leave_sub, count = re.subn(TARGET_LEAVE_PATTERN, r"\1\n\t" + PATCH_MARKER + r"\n\tself:clear_thumbnail()\2", patched, count=1)
        if count > 0:
            patched = leave_sub
        elif "function Timeline:on_global_mouse_leave" in patched:
            raise RuntimeError("Failed to anchor Timeline:on_global_mouse_leave in Timeline.lua")

    # 2. Thumbnail ready guard patch
    if PATCH_READY_MARKER not in patched and "if thumbnail.ready ~= false then" not in patched:
        def _wrap_rect(m: re.Match) -> str:
            bx_line, tabs, rect, thumb_sec = m.group(1), m.group(2), m.group(3), m.group(4)
            return (
                f"{bx_line}{tabs}{PATCH_READY_MARKER}\n"
                f"{tabs}if thumbnail.ready ~= false then\n"
                f"{tabs}\t{rect}\n"
                f"{tabs}end{thumb_sec}"
            )

        rect_sub, count = re.subn(TARGET_RECT_PATTERN, _wrap_rect, patched, count=1, flags=re.DOTALL)
        if count > 0:
            patched = rect_sub

    return patched


def unpatch_timeline_lua(content: str) -> str:
    """Revert Timeline:on_global_mouse_leave and thumbnail ready guard to original."""
    patched = content

    # 1. Unpatch mouse leave
    if "function Timeline:on_global_mouse_leave()" in patched:
        parts = patched.split("function Timeline:on_global_mouse_leave()")
        if len(parts) == 2:
            body, rest = parts[1].split("end", 1)
            pattern = (
                r"(\s*\t*" + re.escape(PATCH_MARKER) + r"\s*\n)?"
                r"\s*\t*self:clear_thumbnail\(\)\s*\n"
            )
            body = re.sub(pattern, "", body)
            if not body.endswith("\n"):
                body += "\n"
            patched = parts[0] + "function Timeline:on_global_mouse_leave()" + body + "end" + rest

    # 2. Unpatch ready guard
    if PATCH_READY_MARKER in patched or "if thumbnail.ready ~= false then" in patched:
        unpatch_rect_pattern = (
            r"(\t+local bx, by = [^\n]+\n)"
            r"\s*\t*" + re.escape(PATCH_READY_MARKER) + r"\s*\n"
            r"\s*\t*if\s+thumbnail\.ready\s*~=\s*false\s+then\s*\n"
            r"\s*\t*(ass:rect\(ax,\s*ay,\s*bx,\s*by,\s*\{.*?\n\s*\t*\}\))\s*\n"
            r"\s*\t*end"
            r"(\n\t+local thumb_seconds)"
        )
        patched = re.sub(unpatch_rect_pattern, r"\1\t\t\t\2\3", patched, count=1, flags=re.DOTALL)

    return patched


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
