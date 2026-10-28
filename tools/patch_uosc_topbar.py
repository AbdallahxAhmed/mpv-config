#!/usr/bin/env python3
"""tools/patch_uosc_topbar.py.

Idempotent patcher for uosc TopBar.lua to ensure the close button minimizes
the window immediately before calling mpv quit, eliminating visible Wayland /
libplacebo teardown freezes.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PATCH_MARKER = "-- UOSC_TOPBAR_FAST_CLOSE_PATCH"

TARGET_CLOSE_PATTERN = (
    r"(\t*local close = \{icon = 'close', hover_bg = '2311e8', hover_fg = 'ffffff', command = function\(\))\s*"
    r"mp\.command\('quit'\)\s*end\}"
)


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


def patch_topbar_lua(content: str) -> str:
    """Ensure TopBar close button minimizes window before invoking quit."""
    if PATCH_MARKER in content or "pcall(mp.set_property, 'window-minimized'" in content:
        return content

    replacement = (
        r"\1\n"
        f"\t\t{PATCH_MARKER}\n"
        r"\t\tpcall(mp.set_property, 'window-minimized', 'yes')\n"
        r"\t\tmp.command('quit')\n"
        r"\tend}"
    )

    patched, count = re.subn(TARGET_CLOSE_PATTERN, replacement, content, count=1)
    if count == 0 and "local close = {icon = 'close'" in content:
        raise RuntimeError("Failed to anchor close button definition in TopBar.lua")
    return patched


def unpatch_topbar_lua(content: str) -> str:
    """Revert TopBar close button definition to original."""
    if PATCH_MARKER not in content and "pcall(mp.set_property, 'window-minimized'" not in content:
        return content

    unpatch_pattern = (
        r"\t*local close = \{icon = 'close', hover_bg = '2311e8', hover_fg = 'ffffff', command = function\(\)\n"
        rf"\s*\t*{re.escape(PATCH_MARKER)}\n"
        r"\s*\t*pcall\(mp\.set_property,\s*['\"]window-minimized['\"],\s*['\"]yes['\"]\)\n"
        r"\s*\t*mp\.command\(['\"]quit['\"]\)\n"
        r"\s*\tend\}"
    )
    original_line = "\tlocal close = {icon = 'close', hover_bg = '2311e8', hover_fg = 'ffffff', command = function() mp.command('quit') end}"
    unpatched, count = re.subn(unpatch_pattern, original_line, content, count=1)
    return unpatched


def run_patcher(uosc_dir: Path, unpatch: bool = False) -> None:
    topbar_path = uosc_dir / "elements" / "TopBar.lua"
    if not topbar_path.exists():
        print(f"Error: Target file missing: {topbar_path}", file=sys.stderr)
        sys.exit(1)

    content = topbar_path.read_text(encoding="utf-8")
    new_content = unpatch_topbar_lua(content) if unpatch else patch_topbar_lua(content)

    action_label = "Unpatching" if unpatch else "Patching"
    if new_content != content:
        topbar_path.write_text(new_content, encoding="utf-8")
        print(f"[OK] {action_label} completed: {topbar_path}")
    else:
        print(f"[-] {topbar_path} already {'unpatched' if unpatch else 'patched'}")


def main():
    parser = argparse.ArgumentParser(
        description="Patch uosc TopBar.lua for instant window close on exit."
    )
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
