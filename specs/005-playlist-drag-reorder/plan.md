# Implementation Plan: Playlist Drag-to-Reorder

**Branch**: `005-playlist-drag-reorder` (directory name only; the maintainer commits to `main`) | **Date**: 2026-11-20, revised 2026-11-22 after Stage 9 review rounds 1-4 | **Status**: Planned | **Spec**: [spec.md](spec.md)
**Input**: Feature specification `specs/005-playlist-drag-reorder/spec.md`, plus the maintainer's planning instructions of 2026-11-20 and review decisions of 2026-11-21 and 2026-11-22

**Artifacts**: [research.md](research.md) · [data-model.md](data-model.md) · [quickstart.md](quickstart.md) ·
contracts: [uosc-reorder-patch.md](contracts/uosc-reorder-patch.md), [uosc-release-check.md](contracts/uosc-release-check.md), [playlist-drag-ui.md](contracts/playlist-drag-ui.md)

## Scope

**This plan delivers User Story 1 (drag to reorder) only.** It does not cover User
Story 2 (playlist item thumbnails). Nothing here implements, stubs or prepares
thumbnails: no overlays, no cache, no image fetching, and no thumbnail-related
hunks in the uosc patch. The spec moved User Story 2 to
[spec 006](spec.md#deferred-to-spec-006-playlist-item-thumbnails). It gets its own
spec and its own plan **after User Story 1 ships**, starting from the open
questions and the security and privacy requirements recorded in
[spec.md](spec.md#security-and-privacy).

## Summary

The uosc playlist menu gets these drag features:

- a mouse-only drag handle on the hovered row;
- an outline on the held row;
- a drop line that moves in whole-row steps;
- auto-scroll at the menu edges;
- cancel on Esc (also while the button is held), menu close, playlist change, a
  new press after a release uosc missed, or a release outside the menu when focus
  is not reported;
- a drop line that freezes while the pointer is outside the mpv window;
- a single `playlist-move` one event-loop turn after the release (Esc, any other
  menu key, a close or a list update in that turn cancels it).

The move-up and move-down buttons and every keyboard path stay as upstream.

The change is a byte-reversible patch of one upstream uosc 5.13.0 file,
`elements/Menu.lua`: 8 literal hunks, made of one payload block and 7 one-line
hooks. `lib/menus.lua` is not touched. A throwaway 2026-11-22 prototype measured a
149-line payload and +159 lines in `Menu.lua` (payload + 2 marker lines + 1 empty
line + 7 hooks), 0 replaced. The C-002 budget is exactly that: payload ≤ 149,
`Menu.lua` +≤ 159 (raised on 2026-11-22; why is in the decisions table). A test will
enforce both limits.

The deployer checks the file's SHA-256 against the pinned release, then patches the
**prepared** copy before `replace_items`. The patched file is swapped in with the
rest of `scripts/` and is covered by the existing recovery. A skipped patch shows
up as a warning in the run's summary, and the run exits 0 (SC-008).

uosc is pinned to `5.13.0`. A weekly CI job checks the latest upstream release
against the patch anchors, under one 120 s download deadline.

The old patcher is removed after the new tests pass and SC-001 to SC-004 and SC-007
to SC-009 pass, including SC-003 on Windows (C-006).

## Planning instructions and review decisions

The review findings are in [round 1](../../.egm/implementation_readiness_report.md),
[round 2](../../.egm/implementation_readiness_report_round2.md),
[round 3](../../.egm/implementation_readiness_report_round3.md),
[round 4](../../.egm/implementation_readiness_report_round4.md) and
[round 5](../../.egm/implementation_readiness_report_round5.md). How each was
resolved is in [the resolution log](../../.egm/goldfish_review_report.md).

| Instruction or decision (date) | Where |
|---|---|
| Patch the staged uosc copy before `replace_items` (2026-11-20) | [R1](research.md#r1--where-the-patch-runs-in-the-prepared-tree-before-replace_items); [deployer integration](contracts/uosc-reorder-patch.md#deployer-integration) |
| Handle "already at the pin, nothing staged"; a second run changes nothing (2026-11-20) | [R2](research.md#r2--uosc-already-installed-at-the-pin-nothing-staged); patcher guarantee 2; quickstart §3 |
| Keep the move-up/down buttons; the playing item keeps its highlight (FR-008, FR-006) | [R4](research.md#r4--patch-shape-c-002-one-payload-block-and-7-one-line-hooks-all-in-menulua) |
| Byte-exact unpatch; real 5.13.0 fixtures reused for SC-009 | [R3](research.md#r3--byte-exact-patch-and-unpatch-one-atomic-write), [R9](research.md#r9--fixtures-real-uosc-5130-files) |
| CI download has a timeout and fails clearly; one 120 s deadline across all reads (2026-11-20, 2026-11-21) | [R8](research.md#r8--release-check-one-total-deadline-across-all-reads) |
| `pathlib` for new and changed code only; never `shell=True` (**decided 2026-11-21**) | Technical Context. Rewriting `transaction.py`'s existing `os.path` code is a separate follow-up, not part of this feature. `shell=True`: hygiene AST test |
| Mouse-only handle drawn by `Menu.lua`; `lib/menus.lua` not patched (approved 2026-11-21) | R4; spec FR-024 |
| The handle zone is registered after the click zones (2026-11-21) | [R5](research.md#r5--event-routing-in-uosc-why-the-handle-zone-is-registered-after-the-action-loop) |
| Exact hook lines and payload API; session on the instance (2026-11-21) | R4; [data-model](data-model.md) |
| Catch the drag's own release through uosc's `cursor:on('primary_up', …)`; no forced `mbtn_left` binding. A new press that uosc receives after the drag started (a release mpv saw but uosc dropped) cancels instead of committing; a release mpv never got is covered in the deferred-commit row (**decided 2026-11-22**, replaces the 2026-11-21 forced binding, which mpv cannot route the release to: round 3, R3-B1, measured) | R5 "Release"; quickstart §4 step 6 |
| While the pointer is outside the mpv window (hover lost, or coordinates outside it), the drop line freezes at its last in-window position and nothing auto-scrolls; a release there commits that position when `focused` is reported and cancels otherwise; Esc still cancels (**decided 2026-11-22**, R3-M1) | R4 `reorder_off_window`; R7; spec edge cases; quickstart §4 step 6 |
| C-002 budget raised from payload ≤ 129 / `Menu.lua` +≤ 140 (2026-11-21 prototype: 129 / 140) to payload ≤ 149 / +≤ 159, 0 replaced (**decided 2026-11-22**: R3-B1, R3-M1, R4-M1, R4-B1 and R5-M1 cannot be fixed within the old limit, and correctness comes first). The payload grows by 20, line for line against the old prototype: the off-window predicate `reorder_off_window`, a 3-line local function, plus a comment and an empty line (+5); the two `cursor:on` registrations and a comment in place of the 3-line forced binding (0); two disposer calls in place of one `remove_key_binding` (+1); the handle's hover condition on a second line (+1); restoring hover state in `reorder_end` (+1, R4-M1); the deferred commit (R4-B1): a 2-line comment, a 4-line `reorder_release` body plus its `end` line (5), an empty line and the `reorder_commit` header (+9), minus the `outside` line that moved into `reorder_release` (−1), so +8; the stale-playlist guard (R5-M1): the `file` field on a second line of the session table (+1), a comment (+1) and a 2-line check in `reorder_commit` (+2), so +4. The search guards, the stale scroll-drag and fling reset and the pending-commit checks share existing lines (0). Hooks drop from 8 to 7 (−1). File total +19 (140 → 159). If a payload that passes every Lua test exceeds the limit, remove comment lines first; if it still exceeds, stop and report; do not edit the limit without maintainer approval | R4 "Budget"; research intro |
| The release's commit waits one event-loop turn (`mp.add_timeout(0, …)`, one one-shot timer per release); Esc, any other menu key (the `menu-key` hook), a menu close or a list update in that turn cancel it. Focus loss while the button is held: mpv sends the button-up first, so the drag commits at the visible drop line, unless the `focused` change is processed before the deferred commit, which cancels it; both outcomes are accepted. A non-menu key pressed while the button is held lets the drag commit at the visible drop line, and `reorder_commit` refuses if the playlist changed under it (count, or the held item's filename). A release never reported to mpv leaves the drag visibly active, and the next click drops there (accepted) (**decided 2026-11-22**, rounds 4-5, R4-B1, R5-M1) | R4 `reorder_release`/`reorder_commit`; R5 "Early release"; spec edge cases; quickstart §4 steps 5-6 |
| Observe `focused` and cancel on true → false (while the button is held, see the deferred commit); without it, release outside the menu cancels (2026-11-21) | R4 `reorder_start`/`reorder_release` |
| Hash check first in deploy; anchor tests switch it off (2026-11-21) | [R12](research.md#r12--checking-the-release-before-patching-and-the-state-procedure) |
| A skipped patch is a warning, exit 0. On update it is shown through the summary's Warnings block only, never twice (2026-11-21) | [Summary warnings](#summary-warnings); patch contract "Update" |
| Remove the local `Path` import in `deploy()` (2026-11-21) | Design "Deploy flow"; patch contract "Install" |

**Spec alignment**: as of 2026-11-22 the following match this plan: FR-024, SC-008
(scoped to `elements/Menu.lua`, one warning in the Warnings block), the edge cases,
the Risks and Mitigations table and the Security and Privacy section.

## Technical Context

**Language/Version**: Python ≥ 3.10 (`pyproject.toml`; CI 3.10–3.12; local venv 3.14). Lua as embedded in mpv (a 2026-11-22 prototype of the patched file compiled under `luac -p` and `luajit -bl`)
**Primary Dependencies**: uosc 5.13.0 (pinned upstream), mpv ≥ 0.40. Python stdlib only for new code (`pathlib`, `http.client`, `threading`, `zipfile`, `hashlib`, `dataclasses`). No new packages
**Storage**: none new. The patched `Menu.lua` and, when staged, its hash in the existing `.deploy.lock.json`
**Testing**: `unittest` in the project venv; Lua suites in headless mpv (`tests/run_lua_tests.py`); `ruff check` and `ruff format --check`
**Target Platform**: Linux (KDE Plasma Wayland) and Windows 10/11. CI unit tests on `ubuntu`, `windows` and `macos` latest; the release check on `ubuntu-latest`
**Project Type**: deploy tool (Python) plus a reversible patch of a third-party mpv Lua script
**Performance Goals**: 0 delayed and 0 dropped frames during drags, `avsync` within ±5 ms (SC-003). Auto-scroll ≤ 12 rows/s, run from the render hook. One one-shot timer per release (the deferred commit); no other timers.
- Outside a drag, 6 of the 7 hooks are a single `self.reorder` check.
- `menu-handle` calls `reorder_handle` for the selected row. It checks `reorder_enabled` and draws the handle only when that row is the mouse-hovered one and the pointer is over the menu.
- The payload calls `request_render()` only during a drag.

**Constraints**:
- C-001: idempotent, marked, byte-exact unpatch, skip with a warning.
- C-002: payload ≤ 149 lines; `Menu.lua` +≤ 159 lines (payload + 10) and 0 replaced; `lib/menus.lua` unchanged; patcher ≤ 300 lines. Tests will enforce each limit.
- FR-024: one file, written by one atomic replace.
- Bytes-only I/O. `pathlib` for every new or changed path operation (the `prepared` value `update_assets` hands to the hook stays a `str`; the hook converts it). No `shell=True`.
- Release check: one 120 s monotonic deadline (per-read socket timeout plus a watchdog), step 5 min, job 10 min.

**Scale/Scope**: playlist menu only; 200-item playlists (SC-003). Repo files: 12 created, 11 modified, 2 deleted (Project Structure)

No NEEDS CLARIFICATION remains. The only open items are the manual platform checks
in quickstart §4.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1 design. Result: **PASS**,
with two documented exceptions (Complexity Tracking).*

| Principle | Status | Notes |
|---|---|---|
| I. Boundary Separation | ✅ PASS | The patch logic lives in `tools/`, next to the existing uosc patchers. The Lua payload `tools/uosc_patches/playlist_reorder.lua` is patch input read by the patcher; it is never deployed as config. Nothing is added to `config/` or the installers |
| II. Cross-Platform Parity | ✅ PASS (design) | Bytes-only I/O and `.gitattributes` keep LF on Windows. Platform gaps have defined fallbacks: a VO without `focused`, and a release outside the window. SC-003 and the off-window check (quickstart §4 step 6) have not been run on either OS yet. They run on KDE Wayland, then on Windows (Phase 2 step 7) |
| III. Dependency Classification | ✅ PASS | stdlib only |
| IV. Shell Compatibility | ✅ N/A | no Bash or PowerShell changes |
| V. Aesthetic CLI UX | ✅ PASS, 1 exception | Deployer output goes through `deploy/ui.py`, and `ui.summary` gains a Warnings list. The exception is the two maintainer/CI CLIs in `tools/` (Complexity Tracking) |
| VI. User Customization Sovereignty | ✅ PASS | uosc is a managed upstream asset. `snapshot_config()` still backs up before the swap. `--dry-run` stops before staging. User files in `scripts/` survive the overlay |
| VII. Idempotent & Safe Operations | ✅ PASS | `already-patched` writes nothing, and the deployed bytes are identical on a second run. A failure before `replace_items` leaves the live config untouched. A failure during it is undone by the `replace_items` recovery, which restores the previous `scripts/` |
| Workflow: branching | ⚠ exception | The maintainer commits to `main` (spec header) |
| Workflow: pre-merge | ✅ PASS | `setup.py` does not exist in this repo. Its checklist items map to `python -m deploy.deployer --update --dry-run` and `--verify` (quickstart §1). `ruff check`/`ruff format --check` run in CI and quickstart §1 |

**Post-design re-check**: unchanged. The new `deploy/` surface is
`update_assets(prepare_hook=None)`, one deployer function, the removal of one
redundant import, and the Warnings list in `ui.summary`.

## Project Structure

### Documentation (this feature)

```text
specs/005-playlist-drag-reorder/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
├── contracts/{uosc-reorder-patch,uosc-release-check,playlist-drag-ui}.md
├── checklists/requirements.md
└── tasks.md             # Phase 2, written by /speckit-tasks (not by this command)
```

### Source Code (write allowlist: C = create, M = modify, D = delete)

```text
C  .gitattributes                                  # fixtures -text, payload eol=lf
C  .github/workflows/uosc-release-check.yml        # weekly + manual; step 5 min, job 10 min
M  deploy/registry.py                              # uosc "pin": None → "5.13.0" (C-007)
M  deploy/transaction.py                           # update_assets(..., prepare_hook=None)
M  deploy/deployer.py                              # _patch_prepared_uosc(); deploy() + cmd_update() wiring;
                                                   #   delete the local `from pathlib import Path` at :1455
M  deploy/ui.py                                    # summary(): Warnings list for status "warn"
C  tools/patch_uosc_playlist_reorder.py            # patcher (bytes, 8 hunks, hash check, CLI)
C  tools/uosc_patches/playlist_reorder.lua         # payload inserted verbatim into Menu.lua
C  tools/check_uosc_release.py                     # release check (C-008)
D  tools/patch_uosc_playlist_drag.py               # last (C-006)
C  tests/fixtures/uosc-5.13.0/elements/Menu.lua    # upstream, unmodified (sha256 0cbc42af…0f2f49, 1831 lines)
C  tests/fixtures/uosc-5.13.0/LICENSE              # uosc LGPL-2.1, from tag 5.13.0
C  tests/fixtures/uosc-5.13.0/README.md            # provenance, hash, line count
C  tests/test_patch_uosc_playlist_reorder.py
C  tests/test_deploy_uosc_reorder_patch.py         # also holds the registry pin test
C  tests/test_uosc_release_check.py
C  tests/lua/test_playlist_reorder.lua             # auto-discovered by run_lua_tests.py
M  tests/test_update_regenerates_mpv_conf.py       # fake update_assets gains prepare_hook=None
M  tests/test_ui_summary.py                        # Warnings list tests
M  tests/test_ui_protocol.py                       # warn rows emitted as log warnings
M  tests/test_repo_hygiene.py                      # no shell=True (AST scan; reuses tracked + VENDORED_PREFIXES)
D  tests/test_patch_uosc_playlist_drag.py          # last (C-006)
M  CHANGELOG.md
M  docs/superpowers/specs/2026-09-09-uosc-playlist-drag-drop-design.md   # marked superseded (C-006)
M  docs/superpowers/plans/2026-09-09-uosc-playlist-drag-drop.md          # marked superseded (C-006)
```

Totals: 12 created, 11 modified, 2 deleted. Nothing else may change.

**Structure Decision**: single project. The patchers go in `tools/`, the deploy
flow in `deploy/`, unit tests in `tests/`, and Lua suites in `tests/lua/`. The new
directories are `tests/fixtures/uosc-5.13.0/` and `tools/uosc_patches/`.

## Design

### Deploy flow (R1, R2, R12)

```text
fetch_all → staging/ ──▶ prepare_assets(live ⊕ staged) → prepared/
                                 │
                                 ▼
                 _patch_prepared_uosc(prepared, staging, config_dir, lockfile)  ◀── NEW
                   (writes only inside prepared/; no network)
                   source = staged | live ;  version = lockfile, else config_dir/tx.MANIFEST
                   state (checked in this order): ABSENT, FOREIGN, UNEXPECTED_UPSTREAM,
                                                  PATCHED, BROKEN_ANCHOR, UPSTREAM
                   UPSTREAM            → patch Menu.lua (temp + atomic replace)        row ok
                   PATCHED             → no write                                     row ok
                   FOREIGN, UNEXPECTED_UPSTREAM, OSError on write → no write          row warn
                   BROKEN_ANCHOR       → unreachable here (verify_hash=True; the pinned bytes match every anchor)
                   ABSENT              → nothing                                      row skipped
                                 │
                                 ▼
                 asset_manifest(prepared)        # hashes the patched bytes when uosc is staged
                 snapshot_config(live)           # backup for `mpv-config rollback` (update path; install uses backup_existing, and builds the manifest only when lockfile is not None)
                 replace_items(scripts/, …)      # recovery restores the old scripts/ on failure
                                 │
                                 ▼
                 _migrate_deployed_configs(...)  # unchanged; Timeline/TopBar still post-commit
```

- Error handling:
  - A hash mismatch, a foreign marker, or an `OSError` during the write becomes one
    `warn` row, and the run exits 0.
  - Any other exception propagates. It aborts the run before `replace_items`, so
    the live config is untouched.
- **Install** (`deploy()`): the row is appended to `results`, and `ui.summary` lists
  it under Warnings. The same change deletes the function-local
  `from pathlib import Path` at `deployer.py:1455`, which would otherwise make the
  new `Path(...)` call raise `UnboundLocalError`. A test runs the real `deploy()`
  with a staged uosc.
- **Update** (`cmd_update()`): after `update_assets` returns, `ok` rows are
  printed with `ui.success` (renderers keep `ok` lines; the Go renderer shows
  `info` only while it is current) and `skipped` rows with `ui.info`. Then `ui.summary(patch_rows)` runs, and its
  Warnings block is the only place a skipped patch appears. There is no `ui.warn`
  for it (SC-008).
- Exact code: [patch contract](contracts/uosc-reorder-patch.md#deployer-integration).

### Patch (R3, R4, R5, R12)

- **Before writing**: the prepared copy (staged or live) is checked first. The
  SHA-256 of its unpatched form must equal `EXPECTED_UPSTREAM_SHA256` for the pin,
  and only then are the anchors checked. If a check fails, the file is left
  unchanged. `detect_state`'s structural round trip uses `verify_hash=False`, so
  only the hash step judges the hash.
- **Hunks**: 8 literal `(anchor, insertion, where)` hunks. Anchors include their
  trailing LF, and insertions are whole LF-terminated lines.
  - Every anchor is copied verbatim from upstream 5.13.0. Uniqueness was checked on
    2026-11-21 against the installed file, which has the same SHA-256 as the
    planned fixture, and the fixture test re-checks it.
  - `menu-core` inserts the payload between `begin`/`end` marker lines.
  - The other 7 are one-line hooks with a trailing ` -- mpv-config:playlist-reorder v1`.
  - The exact lines are in the R4 hook table.
- **Session**: `self.reorder` on the menu instance. Every exit goes through
  `reorder_end()`: close, Esc, `Menu:update`, focus true → false, a new press after
  the drag started, and the deferred `reorder_commit`. `reorder_end()` disposes the session's `cursor:on`
  handlers. So neither the session nor its handlers outlive the menu.
- **Handle**: drawn by `reorder_handle` after the action loop, left of the action
  buttons. Its `primary_down` zone is registered after every `primary_click` zone,
  which `cursor:find_zone` requires (R5). It is not an item action, so Tab, Enter,
  `action_index` and the selected-row indicator stay as upstream.
- **Release** (R5): mpv sends the button-up to the command that got the
  button-down (measured, round 3), and the drag's press goes to uosc. So the
  session registers `cursor:on('primary_up', …)` → `reorder_release()`, which
  uosc's `cursor:trigger` calls whether or not a zone is under the pointer, for
  every release the platform reports. There is no forced binding and no
  `menu-cursor-up` hook.
  - Deferred commit (R4-B1): mpv also sends the button-up early, before an Esc
    key-down or on focus-out (measured, round 4). `reorder_release` therefore only
    records `outside` and schedules `reorder_commit` with `mp.add_timeout(0, …)`;
    the session stays alive for that one event-loop turn, with the gap frozen.
    Esc, a close or a list update queued behind the early up end the session, and
    the timer then finds no session and does nothing (measured for Esc: 5 of 5).
    Focus loss while the button is held: mpv sends the button-up first, so the drag commits at the visible drop line, unless the `focused` change is processed before the deferred commit, which cancels it; both outcomes are accepted.
    Any menu key (the `menu-key` hook sits right after `handle_shortcut`'s
    `if info.event == 'up' then return end`) ends the session, so Ctrl+Up/Down,
    Del and the rest cannot run during it. A non-menu key commits at the drop
    line; `reorder_commit` refuses if the playlist count or the held item's
    filename changed (R5-M1).
  - Guard: `cursor:on('primary_down', …)` ends the session when `started` is true.
    It covers a release mpv saw but uosc dropped (`cursor.disabled`); that press
    acts as a normal click. The drag's own press cannot trip it, because `started`
    is set later, in `reorder_move`.
  - A release mpv never gets: mpv still holds the button, drops the next press and
    sends that click's release, so the drag stays visibly active and the next
    click drops at the drop line (accepted).
  - Whether KDE Wayland and Windows report the button-up outside the window is
    checked by hand (quickstart §4 step 6).
- **Off-window** (R7): `reorder_off_window()` is true when hover is lost
  (`cursor.y == math.huge`) or the held-button coordinates are outside the window.
  While it holds, the drop line stays at its last in-window position and nothing
  auto-scrolls; a release there commits that position (with `focused` reported).
  Above or below the list but inside the window, the gap clamps to the first or
  last one and the list auto-scrolls; beside the list, the gap follows the
  pointer's y.
- **Focus**: `focused` is read at the press and observed during the drag. Only a
  change from true to false cancels (while the button is held, see the deferred
  commit above). If the VO does not report it, a release
  outside the menu cancels instead. "Outside" means `reorder_off_window()` or
  `proximity_raw > 0`; `proximity_raw` is measured against the menu element box (title row excluded), so a
  release over the title row also counts as outside.
- **Exclusion**: `reorder_enabled` requires `self.type == 'playlist'`,
  `menu == self.current`, `on_move`, no search, and ≥ 2 items. A search started
  during a drag (it replaces `menu.items` without `Menu:update`) keeps the session
  but hides the outline and drop line and stops auto-scroll; the release moves
  nothing.
- **Hover state**: `reorder_start` also clears upstream's scroll-drag state
  (`drag_last_y = nil`, `is_dragging = false`), so upstream `handle_cursor_up`
  cannot activate or fling on the session's release. Every exit, in `reorder_end`,
  restores `mouse_nav = true` and clears `mouse_hovered_index`, so hover-select
  resumes on the next render and a still click acts on the row under the pointer,
  never on the previously held row unless the pointer is on it (round 4, R4-M1).
  `reorder_start` also stops a running fling (`self.current.fling = nil`).
- **Commit**: `selected_index = from`, then upstream `move_selected_item_to(to)`.
  That gives one event and one `playlist-move` (FR-005).

### Summary warnings

`deploy/ui.py: summary()` sorts rows into three groups: `ok`/`skipped` (counted as
before), `warn` (new Warnings list), and every other status (failed, as before).
Exact output:

- **Rich**: when there are warnings, print `[bold]Warnings[/bold]`, then one line
  per row: `[yellow]![/yellow] {name} -- {detail}` (no ` -- ` part when `detail` is
  empty), printed with `soft_wrap=True` so test capture at 80 columns does not
  wrap it. This comes before the existing failure table.
- **ANSI**: `\n{BOLD}Warnings:{RESET}`, then
  `  {YELLOW}{S.WARN}{RESET} {name}` per row, followed by ` {DIM}-- {detail}{RESET}`
  only when `detail` is not empty (as the `Failed:` block does, `ui.py:667`). This
  comes before the existing `Failed:` block.
- **Count line**: the order is succeeded, skipped, warnings, failed. The warning
  part is `("warn", f"{n} warning" + ("" if n == 1 else "s"))`, styled `yellow`.
- **Protocol mode** (Go renderer): before the `summary` event, emit
  `_proto.emit("log", level="warn", text=_proto.plain(name), detail=_proto.plain(detail) or None)`
  once per `warn` row, like every other emitter (`ui.py:221`, 647-648).
  The Go side already renders `log` warnings and `Detail` (`ui/model.go:480-486`).
  The `summary` event's `failed` list leaves them out. No Go change, so
  `ui/release.json` stays valid.

Exit codes do not change: `cmd_install` raises only on `failed` rows
(`deployer.py:3103`). The existing `warn` rows (the post-commit uosc patchers,
autosubsync, migrations) move from Failed to Warnings too. None of them fails the
run today.

### Release check (R8)

`run()` fetches `API_URL`, then the `browser_download_url` of `uosc.zip` (up to 5
redirects), and reads `MEMBER` in memory. Everything runs under one monotonic
deadline (default 120 s):

- the socket timeout is set to the remaining time before each `getresponse()` and
  each `read1()`;
- a watchdog timer shuts the socket down at the deadline, which bounds header reads
  too.

Then it runs `check_anchors`. Exit codes: 0 pass; 1 an anchor failed (the version
and hunk id are named); 2 the check could not run (the message names the seconds
and the URL). `check_dir()` is the offline mode the SC-009 tests use.

## Test Strategy

The baseline on 2026-11-20 is venv `unittest` 684 OK (skipped 10) and Lua 14/14.
Tests come first per area. The Python patch, deployer and release-check tests use
the fixture. The Lua tests use stubs (R10).

| Area | Key assertions |
|---|---|
| Fixture | SHA-256 and 1831 lines equal the upstream values; no `b"\r"`; `.gitattributes` marks it `-text` |
| Patch/unpatch | `unpatch(patch(f)) == f`; each anchor matches once (`verify_hash=False`); hunks do not overlap; the `highlight_opacity` and `font_color = item.active…` lines are unchanged (FR-006); the handle hook comes after the last `primary_click` (R5); budget (C-002); payload SHA-256 pinned to `PATCH_VERSION` |
| Idempotency | `apply()` twice: the second returns `already-patched`, with `st_mtime_ns` and `st_ino` unchanged |
| Release integrity (R12) | one byte changed outside every anchor → `skipped` with the hash-mismatch detail, file untouched; a patched copy of non-pinned bytes → `UNEXPECTED_UPSTREAM`, no exception; a patched pinned copy passes through its unpatched form |
| All-or-nothing (FR-024) | `patch_bytes(verify_hash=False)` with a broken anchor raises naming the hunk, input unchanged; `Path.replace` raising `OSError` in `apply()` → original untouched, temp removed, `skipped` |
| Deployer | the real `deploy()` runs with a staged uosc; staged → live patched; 2nd `update` → identical live bytes; nothing staged + live upstream → patched; nothing staged + live patched → no write; hash mismatch → `cmd_update` shows the patch once, in the summary's Warnings block, with no `ui.warn` for it, exits 0, and live `elements/Menu.lua` equals the fetched bytes (SC-008); install lists it under Warnings and exits 0; install `verify_callback` raising → live `scripts/uosc` as before; update with `os.replace` failing inside `replace_items` → live `scripts/uosc` as before; the patch runs before `replace_items` (call-order spy) |
| Registry | uosc `pin == "5.13.0"` (in `test_deploy_uosc_reorder_patch.py`) |
| Summary | the exact Rich, ANSI and count-line strings above; `warn` rows not counted as failed; protocol `log` warn per row |
| Release check | contract test table: SC-009, hang, trickled body, trickled headers, HTTP 500, invalid zip, missing asset or member, token scope, CLI smoke |
| Lua | threshold; pointer → gap table; 50 random drags vs. emulated `playlist-move` (SC-002), released through the `primary_up` handler and committed when the stubbed `mp.add_timeout(0)` runs; the commit is pending (no move) until then, and Esc, close or `Menu:update` before it → no move; one timer per release; the gap does not change while pending; `outside` is judged at the release, not at the commit; a playlist change (move or remove) in the pending turn → no move; a running fling stops at start; depth (including beyond the edge), `dt` cap, clamp; off-window (`math.huge` and finite coordinates on all four sides) keeps the gap, gives depth 0 and does not start a drag; off-window release commits the frozen gap with `focused`, cancels without; `cursor:on` handlers registered at start and disposed on every exit; a new press after the drag started cancels and its release moves nothing; the drag's own press does not cancel; cancel paths: Esc, close, `Menu:update`, focus true → false; no cancel when unfocused at the press; release outside the menu with and without `focused`; search during a drag → no move, no outline; start refused: search, < 2 items, non-playlist, existing session; no handle when the pointer is outside the menu; `mouse_nav` off during a drag; drawing never writes `item.active` |
| Hygiene | AST scan: no `shell=True` keyword in tracked `*.py` outside `VENDORED_PREFIXES` |
| Regression | every existing suite passes. Changes to existing tests are limited to: the `prepare_hook=None` fake in `test_update_regenerates_mpv_conf.py`; new tests added to `test_ui_summary.py`, `test_ui_protocol.py` and `test_repo_hygiene.py`; and any existing assertion that lists a `warn` row as failed, which moves to the Warnings list (none exists on 2026-11-22: no test builds a `warn` summary row). No other existing assertion is edited |

Manual checks are in quickstart §4: SC-001; SC-003 on both OSes; SC-004; the FR-006
visual check; the keyboard path; Esc, a menu key and focus loss with the button
held (quickstart §4 step 5); and the off-window check (quickstart §4 step 6)
on KDE Wayland and Windows.

## Phase 2 outline (input for `/speckit-tasks`)

1. **Foundations**: `.gitattributes`. The fixture plus README, LICENSE, and its
   hash and line-count test. The registry pin and its test.
2. **Patcher and payload, test-first, as one phase**:
   - Lua test → payload file.
   - Python tests → hunk table, pure functions, `apply()` and the CLI.
   - Budget, FR-006 and zone-order guards.
3. **Summary warnings**: `ui.summary` and its tests (Rich, ANSI and protocol).
4. **Deployer**: `update_assets(prepare_hook)` → `_patch_prepared_uosc` → remove the
   local `Path` import → wiring in `deploy()` and `cmd_update()` → the test-double
   update → integration tests.
5. **Release check**: script → offline tests (SC-009, hang, trickles, HTTP 500,
   invalid zip) → workflow.
6. **Hygiene**: the `shell=True` AST test.
7. **Verification**: quickstart §1–§5. SC-003 and the off-window
   check on KDE Wayland, then on Windows.
8. **Retire (C-006)**, only after step 7 passes on both OSes: delete the old patcher
   and its tests, mark the 2026-09-09 design and plan superseded, and update
   `CHANGELOG.md`.

## Follow-ups (not in this spec)

- Rewrite the existing `os.path` code in `deploy/transaction.py` to `pathlib`
  (decided 2026-11-21: a separate change, not part of this feature).
- Move the Timeline and TopBar patchers to the same pre-commit `prepare_hook` and to
  bytes I/O. Today they write live files after the commit, use `write_text` (CRLF
  on Windows), and leave the manifest hashes stale.
- Pin the SHA-256 of the whole `uosc.zip` in `deploy/registry.py` (R12). This needs
  a measured hash and a fetcher change that applies to all components.
- Optionally let `fetch_all` skip an unchanged pinned uosc. R2 already handles
  "nothing staged".

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Principle V: `tools/patch_uosc_playlist_reorder.py` and `tools/check_uosc_release.py` print plain lines rather than going through `deploy/ui.py` | Both are maintainer/CI tools. The release check must print GitHub `::error` annotations, and the existing `tools/patch_uosc_*.py` print plain lines too | Rich markup in CI logs, and `deploy.ui` as a CI dependency. The user-facing path (`mpv-config update`/install) does go through `ui` |
| Workflow: no feature branch | Maintainer's standing practice | Not a technical constraint |
