# Quickstart: verify spec 005 (playlist drag-to-reorder)

**Plan**: [plan.md](plan.md) · revised 2026-11-22

All commands run from the repo root. `PY` is the project venv. The system Python
lacks `rich` and `mpv_config`, so it reports 7 import errors that are not
regressions (research R11).

```bash
PY=~/.local/share/mpv-config/venv/bin/python
git -C ~/.mpv-config-deploy pull --ff-only   # the venv's mpv_config points there
```

## 1. Automated suites and pre-merge checks (all must pass)

```bash
$PY -m unittest discover -s tests            # baseline 684 OK (skipped=10), plus the new tests
python3 tests/run_lua_tests.py               # baseline 14 suites, plus test_playlist_reorder.lua
ruff check . && ruff format --check .
$PY -m deploy.deployer --update --dry-run    # constitution pre-merge 1 (setup.py does not exist;
$PY -m deploy.deployer --verify              #   these are the deployer equivalents) and pre-merge 2
```

The new and changed tests:

| Test file | Covers |
|---|---|
| `tests/test_patch_uosc_playlist_reorder.py` | fixture SHA-256 and line count; every anchor matches once (`verify_hash=False`); patch, then unpatch byte for byte; idempotency (no write on the 2nd run); all-or-nothing with a broken anchor (`verify_hash=False`); hash mismatch → `skipped`; a patched copy of non-pinned bytes → `UNEXPECTED_UPSTREAM` without raising; `OSError` on replace → original untouched, `skipped`; handle hook after the last `primary_click` zone (R5); C-002 budget; payload hash pinned to `PATCH_VERSION`; FR-006 highlight lines untouched; no `\r` |
| `tests/test_deploy_uosc_reorder_patch.py` | patch in `prepared` before `replace_items` (call-order spy, install and update); the real `deploy()` runs with a staged uosc (guards the removed local `Path` import); staged and nothing-staged; 2nd update leaves the live bytes unchanged; hash mismatch → update shows the patch once in the summary's Warnings block and calls no `ui.warn` for it, exits 0, and live `elements/Menu.lua` equals the fetched bytes (SC-008); install lists it under Warnings and exits 0; install `verify_callback` failure and update `os.replace` failure both restore the old `scripts/`; uosc pin is `"5.13.0"` |
| `tests/test_uosc_release_check.py` | SC-009 on the fixture; hung server, trickled body and trickled headers → exit 2 within 5 s; HTTP 500; invalid zip; missing asset or member; no token sent to non-GitHub hosts; CLI smoke test with a list argv |
| `tests/lua/test_playlist_reorder.lua` | 4 px threshold; the pointer→gap table and 50 random drags against an emulated `playlist-move` (SC-002); auto-scroll depth (including a pointer above or below the list), `dt` cap and clamping; off-window (`math.huge`, and finite coordinates above, below, left and right of the window) keeps the gap, gives depth 0 and does not start a drag; a release off-window commits the frozen gap with `focused` and cancels without it; the `cursor:on` `primary_up`/`primary_down` handlers are registered at start and disposed on every exit; a release through the `primary_up` handler commits; a new press after the drag started cancels and its release moves nothing; the drag's own press does not cancel; the commit is pending until the stubbed zero-delay timer runs, and Esc, close or `Menu:update` before it → no move; one timer per release; gap frozen while pending; `outside` judged at the release; a playlist change in the pending turn → no move; cancel paths (Esc, close, `Menu:update`, focus true → false); no cancel when unfocused at the press; release outside the menu with and without `focused`; search started during a drag → no move and no outline; start refused (search, < 2 items, non-playlist, existing session); no handle when the pointer is outside the menu; `mouse_nav` off during a drag; drawing never writes `item.active` |
| `tests/test_ui_summary.py`, `tests/test_ui_protocol.py` | exact Warnings output in Rich and ANSI, with the count order succeeded, skipped, warnings, failed; `warn` rows not counted as failed; protocol mode emits `log` with `level="warn", text=_proto.plain(name), detail=_proto.plain(detail) or None` |
| `tests/test_update_regenerates_mpv_conf.py` | unchanged behaviour; its fake `update_assets` accepts `prepare_hook=None` |
| `tests/test_repo_hygiene.py` | no `shell=True` keyword in tracked `*.py` outside `VENDORED_PREFIXES` (AST scan over the existing `tracked` listing) |

## 2. Patcher by hand on a throwaway copy

```bash
T=$(mktemp -d); mkdir -p "$T/uosc/elements"
cp tests/fixtures/uosc-5.13.0/elements/Menu.lua "$T/uosc/elements/"
$PY -m tools.patch_uosc_playlist_reorder --uosc-dir "$T/uosc"            # patched
$PY -m tools.patch_uosc_playlist_reorder --uosc-dir "$T/uosc"            # already-patched, no write
$PY -m tools.patch_uosc_playlist_reorder --uosc-dir "$T/uosc" --unpatch
cmp "$T/uosc/elements/Menu.lua" tests/fixtures/uosc-5.13.0/elements/Menu.lua && echo byte-identical
```

## 3. Deploy twice; the second run changes nothing (FR-023)

```bash
mpv-config update
sha256sum ~/.config/mpv/scripts/uosc/elements/Menu.lua > /tmp/run1
mpv-config update
sha256sum ~/.config/mpv/scripts/uosc/elements/Menu.lua | diff /tmp/run1 - && echo unchanged
```

Expect `uosc-playlist-reorder-patch: patched (staged, 5.13.0)` both times, and no
warning.

## 4. Manual UI and playback checks (SC-001, SC-003, SC-004, SC-007)

Run these on the real player, by the maintainer. An agent may only take screenshots
inside a nested KWin session (`kwin_wayland --virtual`) with throwaway `XDG_*`
directories, never on the live desktop.

1. Build a 30-item local playlist, play item 5, and open the playlist menu.
2. Hover rows: the handle appears only on the hovered row, left of the move buttons,
   and disappears when the pointer leaves the menu.
   Press Tab and Enter: the handle is skipped, and move up/down work as before.
3. Drag item 20 to position 2 in under 5 s (SC-001). Item 5 keeps playing and keeps
   its highlight.
4. Drag item 5 itself: its highlight stays on throughout (FR-006). `time-pos` keeps
   rising, and `--msg-level=cplayer=v` shows no `end-file` or `start-file` (SC-004).
5. Esc mid-drag, with the button still held: no change, and the menu stays open
   (the early release's commit is cancelled). Alt+Tab away mid-drag, button held:
   the item drops at the visible drop line, or the drag is cancelled if the focus
   change is processed first (both pass). Ctrl+Down with the button held: the drag
   is cancelled and nothing moves. Space with the button held: playback pauses and
   the item drops at the drop line. Filter with `/`: no handle. Ctrl+Up/Down and the move buttons behave
   as before (SC-007).
6. **Pointer and release outside the window, on KDE Wayland and again on Windows**
   (research R5 and R7, findings R3-B1 and R3-M1). Start a drag and place the drop
   line on a middle row:
   - Still holding, move the pointer above, below, then beside the mpv window: the
     drop line stays where it was and the list does not scroll.
   - Esc while the pointer is outside the window (button still held) cancels.
   - Start again and release outside the window. Then record which outcome the
     platform shows; both pass:
     - **(a) Button-up reported.** With `focused` reported (check with
       `mpv --msg-level=all=v` or `print-text ${focused}`), the item moves to the
       frozen drop-line position; without it, nothing moves. Moving the pointer
       back shows no drop line, and a still click on a row acts on the row under
       the pointer (never on the previously held row unless the pointer is on it).
     - **(b) Button-up not reported.** Moving the pointer back, the drop line
       follows it again (the drag is still active). The next click drops the item
       at the drop line, with one move.
   - Still inside the window, drag above or below the list: the drop line goes to
     the first or last gap and the list auto-scrolls.
7. SC-003: a 200-item playlist, a 23.976 fps file, the 143.98 Hz panel, 60 s and 20
   drags, including edge auto-scroll from one end to the other. Measure with the
   spec 004 method. Pass: delayed 0, dropped 0, `avsync` within ±5 ms. Then repeat
   on Windows.

## 5. Release check

```bash
$PY -m tools.check_uosc_release --uosc-dir tests/fixtures/uosc-5.13.0 --version 5.13.0   # exit 0
$PY -m tools.check_uosc_release --latest                                                  # network; exit 0 while 5.13.0 is latest
```

To bump the pin (C-009), run the workflow by hand (`workflow_dispatch`). Only after
it passes for the new tag, update three things in one commit: `"pin"` in
`deploy/registry.py`, `EXPECTED_UPSTREAM_SHA256` and `PIN` in the patcher, and the
fixture directory. Then re-run section 1.
