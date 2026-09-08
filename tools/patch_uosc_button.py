#!/usr/bin/env python3
"""
Idempotent patcher for UOSC Button & ManagedButton elements.
Enables Design A micro bottom progress bar rendering on managed toolbar buttons.

Usage:
    python tools/patch_uosc_button.py [--uosc-dir <path>] [--unpatch]
"""

import argparse
import os
import pathlib
import sys

PATCH_MARKER = "-- UOSC_MICRO_PROGRESS_BAR_PATCH"

MANAGED_TARGET = "for _, prop in ipairs({'icon', 'active', 'badge', 'command', 'tooltip', 'hide'}) do"
MANAGED_REPLACEMENT = "for _, prop in ipairs({'icon', 'active', 'badge', 'command', 'tooltip', 'hide', 'progress'}) do"

BUTTON_PROGRESS_SNIPPET = f"""\t{PATCH_MARKER}
\tif type(self.progress) == 'number' and self.progress > 0 then
\t\tlocal pad = 3 * state.scale
\t\tlocal bar_h = math.max(2, round(2.5 * state.scale))
\t\tlocal bar_y2 = self.by - pad
\t\tlocal bar_y1 = bar_y2 - bar_h
\t\tlocal total_w = (self.bx - self.ax) - pad * 2
\t\tif total_w > 0 then
\t\t\tass:rect(self.ax + pad, bar_y1, self.bx - pad, bar_y2, {{
\t\t\t\tcolor = background,
\t\t\t\topacity = visibility * 0.45,
\t\t\t\tradius = 1,
\t\t\t}})
\t\t\tlocal fill_w = math.min(total_w, math.max(1, total_w * math.min(1, math.max(0, self.progress))))
\t\t\tass:rect(self.ax + pad, bar_y1, self.ax + pad + fill_w, bar_y2, {{
\t\t\t\tcolor = foreground,
\t\t\t\topacity = visibility * 0.95,
\t\t\t\tradius = 1,
\t\t\t}})
\t\tend
\tend
"""


def find_default_uosc_dir() -> pathlib.Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        p = pathlib.Path(appdata) / "mpv" / "scripts" / "uosc"
        if p.exists():
            return p
    # Fallback to local config repo if present
    repo_uosc = pathlib.Path(__file__).resolve().parent.parent / "config" / "scripts" / "uosc"
    if repo_uosc.exists():
        return repo_uosc
    return pathlib.Path("scripts/uosc")


def patch_managed_button(managed_path: pathlib.Path, unpatch: bool = False) -> bool:
    if not managed_path.exists():
        print(f"[SKIP] {managed_path} not found")
        return False

    content = managed_path.read_text(encoding="utf-8")
    backup_path = managed_path.with_suffix(".lua.orig")

    if unpatch:
        if MANAGED_REPLACEMENT in content:
            content = content.replace(MANAGED_REPLACEMENT, MANAGED_TARGET)
            managed_path.write_text(content, encoding="utf-8")
            print(f"[UNPATCH] Restored {managed_path.name}")
            return True
        print(f"[NOOP] {managed_path.name} not patched")
        return False

    if MANAGED_REPLACEMENT in content:
        print(f"[ALREADY PATCHED] {managed_path.name}")
        return True

    if MANAGED_TARGET not in content:
        print(f"[WARN] Target loop not found in {managed_path.name}")
        return False

    if not backup_path.exists():
        backup_path.write_text(content, encoding="utf-8")

    content = content.replace(MANAGED_TARGET, MANAGED_REPLACEMENT)
    managed_path.write_text(content, encoding="utf-8")
    print(f"[PATCHED] {managed_path.name}")
    return True


def patch_button(button_path: pathlib.Path, unpatch: bool = False) -> bool:
    if not button_path.exists():
        print(f"[SKIP] {button_path} not found")
        return False

    content = button_path.read_text(encoding="utf-8")
    backup_path = button_path.with_suffix(".lua.orig")

    if unpatch:
        if PATCH_MARKER in content:
            # Remove snippet
            lines = content.splitlines(keepends=True)
            new_lines = []
            skip = False
            for line in lines:
                if PATCH_MARKER in line:
                    skip = True
                    continue
                if skip:
                    if line.strip() == "end" and line.startswith("\tend"):
                        skip = False
                        continue
                    continue
                new_lines.append(line)
            button_path.write_text("".join(new_lines), encoding="utf-8")
            print(f"[UNPATCH] Restored {button_path.name}")
            return True
        print(f"[NOOP] {button_path.name} not patched")
        return False

    if PATCH_MARKER in content:
        print(f"[ALREADY PATCHED] {button_path.name}")
        return True

    # Find where to insert before "return ass"
    target = "\treturn ass\nend"
    if target not in content:
        target = "return ass\nend"
    if target not in content:
        print(f"[WARN] Insertion anchor 'return ass' not found in {button_path.name}")
        return False

    if not backup_path.exists():
        backup_path.write_text(content, encoding="utf-8")

    insertion = BUTTON_PROGRESS_SNIPPET + "\n\treturn ass\nend"
    content = content.replace(target, insertion, 1)
    button_path.write_text(content, encoding="utf-8")
    print(f"[PATCHED] {button_path.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Patch UOSC Button elements for micro progress bar support")
    parser.add_argument("--uosc-dir", default=None, help="Path to uosc scripts directory")
    parser.add_argument("--unpatch", action="store_true", help="Revert patches")
    args = parser.parse_args()

    uosc_dir = pathlib.Path(args.uosc_dir) if args.uosc_dir else find_default_uosc_dir()
    if not uosc_dir.exists():
        print(f"Error: UOSC directory not found at {uosc_dir}", file=sys.stderr)
        return 1

    managed_path = uosc_dir / "elements" / "ManagedButton.lua"
    button_path = uosc_dir / "elements" / "Button.lua"

    ok_m = patch_managed_button(managed_path, args.unpatch)
    ok_b = patch_button(button_path, args.unpatch)

    if ok_m and ok_b:
        action = "unpatched" if args.unpatch else "patched"
        print(f"Successfully {action} UOSC button elements.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
