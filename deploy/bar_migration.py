"""Pure text operations and inspection for spec 006 control bar cleanup."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

THEME_LINE_VALUES = frozenset(
    {
        "uosc-border_radius=10",
        "uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80",
    }
)


# Files spec 006 P1-P5 shipped that the revert (66e11bc) removed from the repo.
# Updates keep unknown files in scripts/ (transaction.prepare_assets), so these
# survive an update and the leftover script re-applies the dropped theme unless
# removed here. A script counts as ours only if it starts with the header every
# P1-P5 version had; ui_appearance.conf is removed by name.
LEFTOVER_THEME_FILES = (
    ("scripts/ui_appearance.lua", "-- scripts/ui_appearance.lua:"),
    ("scripts/modules/looks.lua", "-- scripts/modules/looks.lua:"),
    ("script-opts/ui_appearance.conf", None),
)


def _first_line(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        return stream.readline().lstrip("\ufeff")


def leftover_theme_files(config_dir: str | Path) -> Tuple[List[Path], List[Path]]:
    """(removable, kept) leftover theme files: regular files only, never links or dirs."""
    removable: List[Path] = []
    kept: List[Path] = []
    for relative, header in LEFTOVER_THEME_FILES:
        path = Path(config_dir, *relative.split("/"))
        if path.is_symlink() or not path.is_file():
            continue
        if header is None or _first_line(path).startswith(header):
            removable.append(path)
        else:
            kept.append(path)
    return removable, kept


def controls_line(repo_config_dir: str | Path) -> str:
    """Read the shipped controls= line from config/script-opts/uosc.conf."""
    conf_path = Path(repo_config_dir) / "script-opts" / "uosc.conf"
    if not conf_path.is_file():
        raise FileNotFoundError(f"Shipped uosc.conf not found at: {conf_path}")
    text = conf_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        body = line.lstrip("\ufeff \t")
        if body.startswith("#") or "=" not in body:
            continue
        key, val = body.split("=", 1)
        if key.strip() == "controls":
            return val.strip()
    raise ValueError(f"controls= setting not found in {conf_path}")


def update_controls(text: str, shipped: str) -> Tuple[str, bool]:
    """Replace the value of every non-comment line whose key is controls.

    Preserves custom other keys, comments, CRLF line endings, and UTF-8 BOM.
    Already-current returns (text, False).
    """
    lines = text.splitlines(keepends=True)
    changed = False
    new_lines = []
    for line in lines:
        stripped = line.lstrip("\ufeff \t")
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        has_bom = line.startswith("\ufeff")
        line_no_bom = line[1:] if has_bom else line
        leading = line_no_bom[: len(line_no_bom) - len(line_no_bom.lstrip(" \t"))]
        body = line_no_bom.lstrip(" \t")
        key_part, sep, val_part = body.partition("=")
        if key_part.strip() == "controls":
            ending = "\r\n" if val_part.endswith("\r\n") else "\n" if val_part.endswith("\n") else ""
            current_val = val_part[: len(val_part) - len(ending)] if ending else val_part
            if current_val == shipped and key_part == "controls":
                new_lines.append(line)
            else:
                changed = True
                bom_prefix = "\ufeff" if has_bom else ""
                new_lines.append(f"{bom_prefix}{leading}controls={shipped}{ending}")
        else:
            new_lines.append(line)
    if not changed:
        return text, False
    return "".join(new_lines), True


def drop_theme_lines(text: str) -> Tuple[str, int]:
    """Remove only the two FR-004 theme lines from mpv.conf text."""
    lines = text.splitlines(keepends=True)
    kept = []
    removed = 0
    for line in lines:
        stripped = line.lstrip("\ufeff \t").rstrip("\r\n \t")
        if stripped.startswith("#") or "=" not in stripped:
            kept.append(line)
            continue
        key, sep, val = stripped.partition("=")
        if key.strip() == "script-opts-append" and val.strip() in THEME_LINE_VALUES:
            removed += 1
        else:
            kept.append(line)
    if removed == 0:
        return text, 0
    return "".join(kept), removed


def pending_changes(
    config_dir: str | Path,
    repo_config_dir: str | Path,
    include_mpv_conf: bool = False,
) -> List[Tuple[str, str, str]]:
    """Return (action, path, detail) for each change a deploy/update would make. Read-only."""
    cfg = Path(config_dir)
    if not cfg.is_dir():
        return []

    changes: List[Tuple[str, str, str]] = []

    uosc_conf = cfg / "script-opts" / "uosc.conf"
    if uosc_conf.is_file() and not uosc_conf.is_symlink():
        try:
            text = uosc_conf.read_text(encoding="utf-8")
            _, changed = update_controls(text, controls_line(repo_config_dir))
        except (OSError, ValueError) as exc:
            changes.append(("modify", str(uosc_conf), f"cannot inspect controls line: {exc}"))
        else:
            if changed:
                changes.append(
                    ("modify", str(uosc_conf), "replace the controls= line with the shipped one")
                )

    if include_mpv_conf:
        mpv_conf = cfg / "mpv.conf"
        if mpv_conf.is_file() and not mpv_conf.is_symlink():
            try:
                _, count = drop_theme_lines(mpv_conf.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                changes.append(("modify", str(mpv_conf), f"cannot inspect theme lines: {exc}"))
            else:
                if count:
                    changes.append(
                        ("modify", str(mpv_conf), f"drop {count} spec 006 theme line(s)")
                    )

    try:
        removable, kept = leftover_theme_files(cfg)
    except OSError as exc:
        changes.append(("remove", str(cfg), f"cannot inspect leftover theme files: {exc}"))
    else:
        for path in removable:
            changes.append(("remove", str(path), "remove leftover spec 006 theme file"))
        for path in kept:
            changes.append(("skip", str(path), "kept: not the file spec 006 shipped"))

    return changes
