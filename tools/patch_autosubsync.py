#!/usr/bin/env python3
"""
tools/patch_autosubsync.py

Idempotent patcher for vendored autosubsync.lua to enable stderr capture
and append engine diagnostic error lines to failure notifications.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

AUTOSUBSYNC_STDERR_MARKER = "-- AUTOSUBSYNC_STDERR_DIAGNOSTICS_PATCH"

SUBPROCESS_PATTERN = re.compile(
    r'(local\s+function\s+subprocess\s*\(\s*args\s*\)\s*\n'
    r'\s*return\s+mp\.command_native\s*\{\s*\n'
    r'\s*name\s*=\s*"subprocess",\s*\n'
    r'\s*playback_only\s*=\s*false,\s*\n'
    r'\s*capture_stdout\s*=\s*true,)(\s*\n\s*args\s*=\s*args)',
    re.MULTILINE,
)

FAILURE_NOTIFY_PATTERN = re.compile(
    r'(\n\s*else\s*\n\s*)notify\s*\(\s*"Subtitle synchronization failed\."\s*,\s*"error"\s*,\s*3\s*\)',
    re.MULTILINE,
)

PATCHED_FAILURE_BLOCK = (
    r'\1' + AUTOSUBSYNC_STDERR_MARKER + '\n'
    r'        local err_msg = "Subtitle synchronization failed."\n'
    r'        if ret and ret.stderr and ret.stderr ~= "" then\n'
    r'            local lines = {}\n'
    r'            for line in ret.stderr:gmatch("[^\\r\\n]+") do\n'
    r'                local trimmed = line:match("^%s*(.-)%s*$")\n'
    r'                if trimmed ~= "" then table.insert(lines, trimmed) end\n'
    r'            end\n'
    r'            if #lines > 0 then\n'
    r'                local _unpack = table.unpack or unpack\n'
    r'                local tail = table.concat({ _unpack(lines, math.max(1, #lines - 2)) }, "\\n")\n'
    r'                err_msg = err_msg .. ":\\n" .. tail\n'
    r'            end\n'
    r'        end\n'
    r'        notify(err_msg, "error", 5)'
)


def patch_autosubsync_lua(content: str) -> str:
    """Ensure subprocess captures stderr and sync failure surfaces engine errors."""
    patched = content

    # 1. Enable capture_stderr = true in subprocess()
    if "capture_stderr = true" not in patched:
        patched, _ = SUBPROCESS_PATTERN.subn(
            r'\1\n        capture_stderr = true,\2',
            patched,
            count=1,
        )

    # 2. Append error lines to notification on sync failure
    if AUTOSUBSYNC_STDERR_MARKER not in patched:
        patched, _ = FAILURE_NOTIFY_PATTERN.subn(
            PATCHED_FAILURE_BLOCK,
            patched,
            count=1,
        )

    return patched


def patch_autosubsync_file(file_path: str | Path) -> bool:
    """Patch autosubsync.lua in-place idempotently. Returns True if modified."""
    path = Path(file_path)
    if not path.is_file():
        return False

    original = path.read_text(encoding="utf-8")
    patched = patch_autosubsync_lua(original)
    if patched == original:
        return False

    path.write_text(patched, encoding="utf-8")
    return True


def find_and_patch_autosubsync(base_dir: str | Path) -> bool:
    """Locate autosubsync.lua within base_dir and patch it."""
    base = Path(base_dir)
    candidates = [
        base / "autosubsync.lua",
        base / "scripts" / "autosubsync" / "autosubsync.lua",
        base / "autosubsync" / "autosubsync.lua",
    ]
    for cand in candidates:
        if cand.is_file():
            return patch_autosubsync_file(cand)
    return False


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    target_path = Path(target)
    if target_path.is_file():
        success = patch_autosubsync_file(target_path)
    else:
        success = find_and_patch_autosubsync(target_path)
    sys.exit(0 if success else 1)
