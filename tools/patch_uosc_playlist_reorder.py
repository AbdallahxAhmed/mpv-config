#!/usr/bin/env python3
"""Byte-exact, reversible patch of uosc's elements/Menu.lua: playlist drag-to-reorder.

Spec 005 (contracts/uosc-reorder-patch.md): the payload file plus seven one-line hooks,
as literal byte hunks (no regexes, no newline translation), so unpatch is exact.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

PATCH_NAME = "uosc-playlist-reorder"
PATCH_VERSION = 1
MARKER = b" -- mpv-config:playlist-reorder v1"
MARKER_TOKEN = b"mpv-config:playlist-reorder"
PAYLOAD_PATH = Path(__file__).parent / "uosc_patches" / "playlist_reorder.lua"
PAYLOAD = PAYLOAD_PATH.read_bytes()
PAYLOAD_SHA256 = "33460949faa6c39008ff0499de7da84e1aa12681d7592af5d0972957c5fc63bf"
TARGET = "elements/Menu.lua"
PIN = "5.13.0"
EXPECTED_UPSTREAM_SHA256 = {
    TARGET: "0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49",
}


class PatchState(Enum):
    ABSENT = "absent"
    FOREIGN = "foreign"
    UNEXPECTED_UPSTREAM = "unexpected-upstream"
    PATCHED = "patched"
    BROKEN_ANCHOR = "broken-anchor"
    UPSTREAM = "upstream"


@dataclass(frozen=True)
class Hunk:
    id: str
    anchor: bytes
    insertion: bytes
    where: str  # "before" | "after"


@dataclass(frozen=True)
class AnchorFailure:
    hunk_id: str
    found: int


@dataclass(frozen=True)
class PatchResult:
    status: str
    changed: bool
    detail: str


class PatchError(Exception):
    def __init__(self, state: PatchState, detail: str):
        super().__init__(detail)
        self.state = state
        self.detail = detail


def _hook(indent: bytes, code: bytes) -> bytes:
    return indent + code + MARKER + b"\n"


# Exact lines: research.md R4. Anchors include their trailing LF.
HUNKS: tuple[Hunk, ...] = (
    Hunk(
        "menu-core",
        b"function Menu:on_display() self:update_dimensions() end\n",
        b"-- mpv-config:playlist-reorder v1 begin\n"
        + PAYLOAD
        + b"-- mpv-config:playlist-reorder v1 end\n\n",
        "before",
    ),
    Hunk(
        "menu-close",
        b"\tlocal menu = self == Menu and Elements.menu or self\n",
        _hook(b"\t", b"if menu and menu.reorder then menu:reorder_end() end"),
        "after",
    ),
    Hunk(
        "menu-update",
        b"function Menu:update(data)\n",
        _hook(b"\t", b"if self.reorder then self:reorder_end() end"),
        "after",
    ),
    Hunk(
        "menu-mouse-move",
        b"function Menu:on_global_mouse_move()\n",
        _hook(b"\t", b"if self.reorder then return self:reorder_move() end"),
        "after",
    ),
    Hunk(
        "menu-key",
        b"\tif info.event == 'up' then return end\n",
        _hook(b"\t", b"if self.reorder then return self:reorder_end() end"),
        "after",
    ),
    Hunk(
        "menu-render-tick",
        b"\tcursor:zone('primary_down', display, self:create_action(function() "
        b"self:handle_cursor_down() end))\n",
        _hook(b"\t", b"if self.reorder then self:reorder_tick() end"),
        "before",
    ),
    Hunk(
        "menu-handle",
        b"\t\t\t\ttitle_clip_bx = actions_rect.ax - self.gap * 2\n",
        _hook(
            b"\t\t\t\t",
            b"actions_rect.ax = self:reorder_handle(ass, menu, index, actions_rect, item_clip)",
        ),
        "before",
    ),
    Hunk(
        "menu-draw",
        b"\treturn ass\nend\n\nreturn Menu\n",
        _hook(b"\t", b"if self.reorder then self:reorder_draw(ass) end"),
        "before",
    ),
)


def _patched_span(hunk: Hunk) -> bytes:
    return hunk.insertion + hunk.anchor if hunk.where == "before" else hunk.anchor + hunk.insertion


def _splice(data: bytes, edits: list[tuple[int, int, bytes]], kind: str) -> bytes:
    """Replace each (start, end) span with its bytes; spans must not overlap."""
    edits = sorted(edits)
    for (_, end, _), (start, _, _) in zip(edits, edits[1:]):
        if end > start:
            raise PatchError(PatchState.FOREIGN, f"{PATCH_NAME}: {kind} spans overlap")
    out, pos = [], 0
    for start, end, replacement in edits:
        out += [data[pos:start], replacement]
        pos = end
    out.append(data[pos:])
    return b"".join(out)


def check_anchors(data: bytes) -> list[AnchorFailure]:
    """Every anchor that does not occur exactly once (all of them, never raises)."""
    return [
        AnchorFailure(hunk.id, found) for hunk in HUNKS if (found := data.count(hunk.anchor)) != 1
    ]


def _unpatched_form(data: bytes) -> bytes:
    try:
        return unpatch_bytes(data) if MARKER_TOKEN in data else data
    except PatchError:
        return data


def _state_detail(state: PatchState, data: bytes) -> str:
    if state is PatchState.UNEXPECTED_UPSTREAM:
        digest = hashlib.sha256(_unpatched_form(data)).hexdigest()[:12]
        return (
            f"{PATCH_NAME} skipped: {TARGET} does not match uosc {PIN} "
            f"(sha256 of the unpatched form {digest}…); uosc left unchanged"
        )
    if state is PatchState.FOREIGN:
        return (
            f"{PATCH_NAME} skipped: {TARGET} carries an unknown or partial "
            "playlist-reorder patch; uosc left unchanged"
        )
    if state is PatchState.BROKEN_ANCHOR:
        failure = check_anchors(data)[0]
        return (
            f"{PATCH_NAME} skipped: anchor {failure.hunk_id} matched {failure.found}× in "
            f"{TARGET} (expected 1); uosc left unchanged"
        )
    return ""


def detect_state(data: bytes, *, verify_hash: bool = True) -> PatchState:
    """The ordered procedure of research R12 (never ABSENT, never raises)."""
    marked = MARKER_TOKEN in data
    unpatched = data
    if marked:
        try:
            unpatched = unpatch_bytes(data)
            if patch_bytes(unpatched, verify_hash=False) != data:
                return PatchState.FOREIGN
        except PatchError:
            return PatchState.FOREIGN
    if verify_hash and hashlib.sha256(unpatched).hexdigest() != EXPECTED_UPSTREAM_SHA256[TARGET]:
        return PatchState.UNEXPECTED_UPSTREAM
    if marked:
        return PatchState.PATCHED
    if check_anchors(data):
        return PatchState.BROKEN_ANCHOR
    return PatchState.UPSTREAM


def patch_bytes(data: bytes, *, verify_hash: bool = True) -> bytes:
    """Patched bytes; raises PatchError unless the input is UPSTREAM."""
    state = detect_state(data, verify_hash=verify_hash)
    if state is not PatchState.UPSTREAM:
        raise PatchError(state, _state_detail(state, data))
    edits = []
    for hunk in HUNKS:
        start = data.index(hunk.anchor)
        edits.append((start, start + len(hunk.anchor), _patched_span(hunk)))
    return _splice(data, edits, "anchor")


def unpatch_bytes(data: bytes) -> bytes:
    """The original bytes; raises PatchError if any insertion is not found exactly once."""
    edits = []
    for hunk in HUNKS:
        span = _patched_span(hunk)
        found = data.count(span)
        if found != 1:
            raise PatchError(PatchState.FOREIGN, f"insertion {hunk.id} found {found}× (expected 1)")
        start = data.index(span)
        edits.append((start, start + len(span), hunk.anchor))
    return _splice(data, edits, "insertion")


def _write_atomically(target: Path, data: bytes) -> str | None:
    """Temp file next to the target, original mode, then one replace. Error text or None."""
    tmp = target.with_name(target.name + ".mpvcfg-tmp")
    try:
        mode = target.stat().st_mode
        tmp.write_bytes(data)
        tmp.chmod(mode)
        tmp.replace(target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        return exc.strerror or str(exc)
    return None


def apply(uosc_dir: Path, *, unpatch: bool = False) -> PatchResult:
    """Patch (or unpatch) uosc_dir/elements/Menu.lua in place."""
    target = Path(uosc_dir) / TARGET
    if not target.is_file():
        return PatchResult("absent", False, "")
    data = target.read_bytes()
    state = detect_state(data)
    if state is PatchState.UPSTREAM and not unpatch:
        new, done = patch_bytes(data), "patched"
    elif state is PatchState.PATCHED and unpatch:
        new, done = unpatch_bytes(data), "unpatched"
    elif state is PatchState.PATCHED:
        return PatchResult("already-patched", False, "")
    elif state is PatchState.UPSTREAM:
        return PatchResult("already-unpatched", False, "")
    else:
        return PatchResult("skipped", False, _state_detail(state, data))
    error = _write_atomically(target, new)
    if error is not None:
        detail = f"{PATCH_NAME} skipped: could not write {TARGET} ({error}); uosc left unchanged"
        return PatchResult("skipped", False, detail)
    return PatchResult(done, True, "")


def main(argv: list[str] | None = None) -> int:
    from tools.patch_uosc_timeline_thumb import get_default_uosc_dir

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--uosc-dir", type=Path, default=None, help="uosc script directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--unpatch", action="store_true", help="restore the upstream file")
    mode.add_argument("--check", action="store_true", help="only check the anchors")
    args = parser.parse_args(argv)
    uosc_dir = args.uosc_dir or get_default_uosc_dir()

    if args.check:
        target = uosc_dir / TARGET
        if not target.is_file():
            print(f"{PATCH_NAME}: absent")
            return 2
        failures = check_anchors(target.read_bytes())
        for failure in failures:
            print(f"anchor {failure.hunk_id} matched {failure.found}x")
        if not failures:
            print(f"{PATCH_NAME}: all {len(HUNKS)} anchors match")
        return 1 if failures else 0

    result = apply(uosc_dir, unpatch=args.unpatch)
    print(f"{PATCH_NAME}: {result.status}" + (f" -- {result.detail}" if result.detail else ""))
    return {"skipped": 1, "absent": 2}.get(result.status, 0)


if __name__ == "__main__":
    sys.exit(main())
