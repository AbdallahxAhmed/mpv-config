# Research: Playlist Drag-to-Reorder (spec 005)

**Date**: 2026-11-20, revised 2026-11-22 after Stage 9 review rounds 1-4 | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

Every finding below was checked against this repo and the installed uosc 5.13.0
(`~/.config/mpv/scripts/uosc`). Its files match the SHA-256 values that
`.deploy.lock.json` recorded for the upstream 5.13.0 release:

| File | SHA-256 (upstream 5.13.0) | Lines (`wc -l`) | Patched? |
|------|---------------------------|-----------------|----------|
| `elements/Menu.lua` | `0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49` | 1831 | yes, the only patched file |
| `lib/menus.lua` | `08181fa05c2a0dd0c5146c0a0e02e44a690732f84a08e3c5bfdd06ff68e0f79e` | 1138 | no (since 2026-11-21) |

Both files are ASCII, LF line endings, tab-indented, and contain no `\r`.

No item in the Technical Context is left as NEEDS CLARIFICATION.

**Prototype measurements (2026-11-22, after review round 5)**: these come from a
throwaway prototype, not from shipped code. The payload file does not exist yet,
and implementation starts from this document.

The prototype applied the payload and the 7 hooks below to a scratch copy of the
5.13.0 `Menu.lua`:

- The patched copy compiled under `luac -p` and `luajit -bl`.
- The prototype payload was 149 lines. The patch added 159 lines in total
  (payload + 2 marker lines + 1 empty line + 7 hooks) and replaced none. The
  budget was raised to exactly these numbers (see "Budget" below and the plan's
  decisions table).
- A stub run of the prototype payload passed:
  - 50/50 random drags, each ending where the drop line showed after at most one
    simulated `playlist-move`, released through the `primary_up` handler;
  - the 3 px click;
  - the focus cancel on true → false, with no cancel when the window was
    unfocused at the press;
  - no drag start when the pointer leaves the window before the threshold;
  - off-window freeze: finite coordinates above, below, left and right of the
    window, and `math.huge`, keep the gap and give depth 0; a release there
    commits the frozen gap when `focused` is reported, and cancels when it is not;
  - the stale-press guard: a press after the drag started cancels, and its release
    moves nothing; the drag's own press does not cancel;
  - search started during a drag: no move;
  - no handle when the pointer is outside the menu;
  - refusal to start during search or with a single item;
  - no `cursor:on` handler left registered after any exit;
  - after any exit `mouse_nav` is true and `mouse_hovered_index` is nil; a search
    started mid-drag stops auto-scroll; `reorder_start` clears a stale
    `drag_last_y`/`is_dragging`;
  - the deferred commit: after the up, the commit is pending until the zero-delay
    timer runs; Esc, close or a list update in between → no move; one timer per
    release; the gap stays fixed while pending; `outside` is judged at the release;
  - the stale-playlist guard: a playlist change (move or remove) in the pending turn
    → no move; `reorder_start` stops a running fling.

---

## R1 — Where the patch runs: in the prepared tree, before `replace_items`

**Decision**: Apply the reorder patch to `<prepared>/scripts/uosc`, the offline copy
built by `tx.prepare_assets()`. It runs after `prepare_assets` and before
`tx.asset_manifest()` and `tx.replace_items()`, in both code paths:

- `deploy()` (`deploy/deployer.py`, install) calls
  `_patch_prepared_uosc(...)` right after
  `tx.prepare_assets(config_dir, staging_dir, repo_dir, prepared)` (`deployer.py:1313`).
- `cmd_update()` → `tx.update_assets()`: `update_assets` gets one new keyword
  argument, `prepare_hook=None`. It calls `prepare_hook(prepared)` once, after
  `prepare_assets` and before `asset_manifest` (`transaction.py:461-463`), and it
  ignores the return value. `cmd_update` passes a closure. See
  [the patch contract](contracts/uosc-reorder-patch.md#deployer-integration).

The patch is **not** added to `_migrate_deployed_configs()`, which writes to the
live config after the transaction has committed.

**Rationale**:

- The patched file rides inside the `scripts/` rename of `replace_items`. If a rename
  fails, or `verify_callback` fails (install only), the existing recovery restores the
  previous `scripts/` from its `old/` journal. The snapshot taken by `snapshot_config()`
  before the swap stays usable for `mpv-config rollback`.
- When uosc is staged, `asset_manifest()` hashes the patched bytes in `prepared`, so
  `.deploy.lock.json` matches the deployed file. When nothing is staged (R2), the
  uosc files are not in `managed_files` at all, because `asset_manifest` lists only
  staged paths (`transaction.py:431-444`). This is existing behaviour.
- Any failure before `replace_items` leaves the live config untouched, because only
  the temporary `prepared` directory was written.

**Alternatives considered**:

- *Patch `staging/` before `prepare_assets`*: this misses the nothing-staged case.
  Rejected.
- *Patch after the commit, as Timeline and TopBar do*: no rollback, and a stale
  manifest. Rejected.
- *Put uosc code into `deploy/transaction.py`*: that module is generic. It gets a
  hook instead. Rejected.

**Out of scope**: moving the Timeline and TopBar patchers (follow-up in the plan).

## R2 — uosc already installed at the pin, nothing staged

**Finding**: today `fetch_all()` always downloads every component, and
`_require_complete_fetch()` refuses to continue without them, so production runs
always stage uosc. `prepare_assets()` builds `prepared/scripts` as the live copy
with the staged copy on top. When `staging/scripts/uosc` is missing,
`prepared/scripts/uosc` is the live copy, which may already carry the patch.

**Decision**: the patch step works only on `prepared/scripts/uosc`, wherever that
copy came from. It records the source: `staged` when
`staging/scripts/uosc/elements/Menu.lua` exists, `live` otherwise. The outcome
depends only on the file's state, decided by the procedure in R12 and
[data-model.md](data-model.md#patch-target-state):

| Prepared `Menu.lua` is… | Result | Row status | Bytes written |
|---|---|---|---|
| pinned upstream, all anchors match | `patched` | `ok` | the file |
| already patched with this patch version | `already-patched` | `ok` | none (mtime and inode unchanged) |
| hash differs from the pinned 5.13.0 value | `skipped` | `warn` | none |
| marker present but not this exact patch | `skipped` | `warn` | none |
| the write itself fails (`OSError`) | `skipped` | `warn` | none (original untouched, R3) |
| `scripts/uosc/elements/Menu.lua` absent | `absent` | `skipped` | none |

Where the version comes from: when uosc is staged, from
`lockfile["scripts"]["uosc"]["version"]`. When nothing is staged, from the live
manifest `config_dir / tx.MANIFEST` (`scripts.uosc.version`). Otherwise it is
`"unknown"`. The version is
used in messages only.

A second run changes nothing:

- staged: run 2 stages the same upstream bytes and produces the same patched bytes;
- nothing staged: run 2 returns `already-patched` and writes nothing.

## R3 — Byte-exact patch and unpatch, one atomic write

**Findings**: the existing patchers use `read_text`/`write_text`. On Windows that
turns `\n` into `\r\n`. Their unpatch uses whitespace-tolerant regexes, which is how
the old drag patcher lost the original indentation. The repo has no
`.gitattributes`, and Git for Windows defaults to `core.autocrlf=true`.

**Decision**:

- Bytes only: `Path.read_bytes()`, and writes via a temporary file.
- Each hunk is `(anchor, insertion, where)`, where `where` is `before` or `after`.
  `anchor` is copied verbatim from upstream 5.13.0, tabs included. No regexes, no
  normalisation.
- Byte convention: an `anchor` includes the trailing LF of each of its lines. An
  `insertion` is one or more complete lines, each ending in LF. A `before`
  insertion is placed directly in front of the anchor's first byte, and an `after`
  insertion directly behind its last LF.
- Patch: every anchor must occur exactly once. Unpatch: every `anchor+insertion`
  (or `insertion+anchor`) must occur exactly once, and is replaced by the anchor.
  Hunks must not overlap.
- Round trip: `unpatch(patch(x)) == x`, byte for byte, checked on the fixture.
- **Single file, atomic write**: write `Menu.lua.mpvcfg-tmp` in the same directory,
  copy the original's mode onto it, then `Path.replace()` it over the target. If the
  write or the replace raises `OSError`, the temporary file is removed and the
  original is untouched, because `os.replace` is atomic on one filesystem. `apply()`
  then returns `skipped` with an I/O detail: one warning, and the update continues
  with the unpatched file. Any other exception propagates. It aborts the operation
  before `replace_items`, with the live config untouched.
- `.gitattributes`: `tests/fixtures/uosc-*/** -text` and
  `tools/uosc_patches/*.lua eol=lf`.

## R4 — Patch shape (C-002): one payload block and 7 one-line hooks, all in `Menu.lua`

**Decision (2026-11-21)**: `Menu.lua` draws the drag handle itself, next to the row's
action buttons. It is **not** an item action. This follows from the maintainer's
M9 decision (the handle is mouse-only, not a Tab stop, and does not change the
selected-row indicator):

- `Menu:navigate_action` cycles over every entry in `actions` and ignores
  `filter_hidden` (`Menu.lua:508-519`).
- Hovering an action sets `menu.action_index`, and a non-nil `selected_action`
  hides the selected-row indicator (`Menu.lua:1566-1569`, `1579`).

As an action, the handle would need more hunks to undo both effects. Drawn by
`Menu.lua`, it never enters `actions`, so Tab/Enter, `action_index` and the
indicator stay as upstream. `lib/menus.lua` needs no change.

Each hook below is the exact line inserted (`→` shows the tab depth). Every hook ends
with the trailing marker ` -- mpv-config:playlist-reorder v1`, written as `MARKER`
here. Uniqueness of every anchor was checked against the 5.13.0 file on 2026-11-21.

| Hunk id | Anchor (verbatim, upstream line) | Where | Inserted line(s) |
|---|---|---|---|
| `menu-core` | `function Menu:on_display() self:update_dimensions() end` (689) | before | `-- mpv-config:playlist-reorder v1 begin`, the payload file verbatim, `-- mpv-config:playlist-reorder v1 end`, then one empty line |
| `menu-close` | `→local menu = self == Menu and Elements.menu or self` (in `Menu:close`) | after | `→if menu and menu.reorder then menu:reorder_end() end MARKER` |
| `menu-update` | `function Menu:update(data)` (172; reached by `update_items` and by the `update-menu` script message) | after | `→if self.reorder then self:reorder_end() end MARKER` |
| `menu-mouse-move` | `function Menu:on_global_mouse_move()` (726) | after | `→if self.reorder then return self:reorder_move() end MARKER` |
| `menu-key` | `→if info.event == 'up' then return end` (1248, in `Menu:handle_shortcut`) | after | `→if self.reorder then return self:reorder_end() end MARKER`: Esc and every other menu key (arrows, Ctrl+moves, Del, Enter, Tab, `/`, `mbtn_back`, …) cancel a session and are consumed; key-ups and type-to-search input do not pass here (R5-M1) |
| `menu-render-tick` | `→cursor:zone('primary_down', display, self:create_action(function() self:handle_cursor_down() end))` (1374) | before | `→if self.reorder then self:reorder_tick() end MARKER` |
| `menu-handle` | `→→→→title_clip_bx = actions_rect.ax - self.gap * 2` (1575, right after the action loop) | before | `→→→→actions_rect.ax = self:reorder_handle(ass, menu, index, actions_rect, item_clip) MARKER` |
| `menu-draw` | `→return ass` + `end` + empty line + `return Menu` (end of `render`) | before | `→if self.reorder then self:reorder_draw(ass) end MARKER` |

**Budget, to be enforced by test** (raised 2026-11-22, see the plan's decisions
table for why): `Menu.lua` gains ≤ 159 lines and has **0** lines replaced. The file
grows by the payload + 10 lines (2 markers, 1 empty line, 7 hooks), so the payload is
≤ 149 lines. The prototype measured 149 and 159. `lib/menus.lua` is unchanged.
There is no `menu-cursor-up` hook: every release uosc receives reaches the session
through its `cursor:on('primary_up')` handler (R5), so upstream `handle_cursor_up`
runs unchanged.
`tools/patch_uosc_playlist_reorder.py` is ≤ 300 lines. For comparison, the old
patcher added 200 lines and replaced 8 in `Menu.lua`, added 6 to `menus.lua`, and
was 684 lines long. The patcher holds `PAYLOAD_SHA256`, the SHA-256 of the payload
file for the current `PATCH_VERSION`; a test checks the file against it, so any
payload change forces a version and marker bump.

**Payload API** (`tools/uosc_patches/playlist_reorder.lua`, methods on `Menu`):

| Method | Called by | Does | Returns |
|---|---|---|---|
| `reorder_enabled(menu?)` | `reorder_start`, `reorder_handle` | true only if all hold: `self.type == 'playlist'`, `menu == self.current`, `menu.on_move ~= nil`, no `menu.search`, and `#menu.items >= 2` | boolean |
| `reorder_gap(y)` | `reorder_move`, `reorder_tick` | `clamp(0, math.floor((y - menu.top + menu.scroll_y) / self.scroll_step + 0.5), #menu.items)` for `menu = self.current` | integer gap |
| `reorder_off_window()` (local function; the **first definition** in the payload file, so the later methods see it as an upvalue, not a nil global) | `reorder_move`, `reorder_depth`, `reorder_release` | true when the pointer is outside the mpv window: `cursor.y == math.huge` (hover lost, `cursor:leave()`) **or** held-button coordinates outside it, `cursor.x < 0 or cursor.y < 0 or cursor.x >= display.width or cursor.y >= display.height` (R7) | boolean |
| `reorder_start(index)` | the handle's `primary_down` zone | refuses if a session exists or `reorder_enabled()` is false. Creates `self.reorder`, sets `selected_index = index`, and on one line `self.mouse_nav, self.drag_last_y, self.is_dragging, self.current.fling = false, nil, false, nil` (no upstream scroll-drag or fling state survives into the session, so upstream `handle_cursor_up` cannot activate or fling on its release and the list does not keep scrolling). The session also records `file = mp.get_property('playlist/' .. (index - 1) .. '/filename')`. Registers two uosc cursor-bus handlers and stores their disposers in the session: `session.off_up = cursor:on('primary_up', function() self:reorder_release() end)` and `session.off_down = cursor:on('primary_down', function() if session.started then self:reorder_end() end end)` (R5). Records `focused = mp.get_property_native('focused')`. If that is not `nil`, it observes `focused`: the callback cancels if and only if the new value is `false` and the stored value is `true`; otherwise it stores the new value | — |
| `reorder_end()` | Esc, close, `Menu:update`, focus true → false, a press after the drag started, `reorder_commit` | clears `self.reorder`, calls `session.off_up()` and `session.off_down()`, sets `self.mouse_nav, self.mouse_hovered_index = true, nil` (hover-select resumes on the next render, and a still click can no longer match the held row; R4-M1), unobserves `focused`, requests a render | the ended session, or `nil` |
| `reorder_move()` | mouse-move hook | first, if `reorder_off_window()` or a release is pending (`session.outside ~= nil`), only requests a render: the gap and `started` stay as they are (the drop line freezes at its last in-window position). Otherwise it sets `started` once `abs(cursor.y - press_y) >= 4 × state.scale`, and while started sets `gap = reorder_gap(cursor.y)`. Requests a render | — |
| `reorder_release()` | the session's `primary_up` handler: every button release uosc receives, inside or outside the window, including the early ups mpv sends before an Esc key-down or on focus-out (R5) | does nothing if there is no session or a release is already pending. Otherwise records `session.outside = reorder_off_window() or self.proximity_raw > 0` (judged at the release; `proximity_raw` is measured against the menu element box, which excludes the title row, so a release over the title also counts as outside), then `mp.add_timeout(0, function() if self.reorder == session then self:reorder_commit() end end)`. The session stays alive for that one event-loop turn, so Esc, close or `Menu:update` queued behind the up cancel it | — |
| `reorder_commit()` | the zero-delay timer, only if the same session still exists | calls `reorder_end()` first. Issues no move when the drag never started, the menu changed (`self.current.id ~= menu_id`), a search is active, or `session.outside` and `focused` is not observed, or the playlist changed under the session (`playlist-count ~= #self.current.items`, or the filename at `from` differs from `session.file`: a key handled in the pending turn moved or removed an entry before `Menu:update` arrived; R5-M1). Otherwise commits the session's `gap`, which off-window is the frozen last in-window gap: `to = gap < from and gap + 1 or gap`, and if `to ~= from`: `selected_index = from`, then upstream `move_selected_item_to(to)` | — |
| `reorder_depth()` | `reorder_tick` | 0 when `reorder_off_window()`, so nothing scrolls while the pointer is outside the window. Top: for any `y < menu.top + zone`, `-clamp(0, (menu.top + zone - y) / zone, 1)`, so a pointer above the list counts as full depth. Bottom: the mirror image for `y > menu.top + menu.height - zone`. Otherwise 0. The zone is one `scroll_step` | number in [-1, 1] |
| `reorder_tick()` | render hook | does nothing unless started, no search is active (`self.current.search`) and no release is pending, so a search started mid-drag stops auto-scroll. At depth 0 it sets `last_tick = nil`. Otherwise, with `now = mp.get_time()`: `dt = last_tick and math.min(now - last_tick, 0.1) or 0`; then `last_tick = now`; then `set_scroll_by(depth × 12 × scroll_step × dt)`; then it recomputes `gap` and calls `request_render()` | — |
| `reorder_handle(ass, menu, index, actions_rect, clip)` | handle hook | draws the `drag_handle` icon in a button-sized slot (`size = actions_rect.by - actions_rect.ay`, `margin = self.gap × 2`) left of the actions. Only when `reorder_enabled(menu)` holds and either `index == reorder.from`, or there is no session, `self.mouse_nav` is on, `self.mouse_hovered_index == index` and `self.proximity_raw <= 0` (the pointer is over the menu; upstream clears neither `selected_index` nor `mouse_hovered_index` when it leaves). With no session, it registers `cursor:zone('primary_down', slot, self:create_action(function() self:reorder_start(index) end))` | new `actions_rect.ax` (unchanged when not drawn) |
| `reorder_draw(ass)` | draw hook | only when started, `self.current.id == menu_id` and no search is active. Draws the held-row outline and the drop line (geometry in [data-model.md](data-model.md#rendering-contributions-additive-only)) | — |

**Why no hunk changes the highlight code (FR-006)**: upstream computes
`highlight_opacity = 0 + (item.active and 0.8 or 0) + (is_selected and 0.15 or 0)`
(`Menu.lua:1499`) and `font_color = item.active and fgt or bgt` (1478). No hunk
touches those lines or the background `ass:rect`, and the payload never writes
`item.active`. `reorder_draw` runs at the end of `render()`, so the outline is drawn
on top of the playing highlight. On the playing row the outline uses the `bg` colour,
so it stays visible against the `fg` highlight.

**Hover selection during a drag (M8)**: `reorder_start` sets `self.mouse_nav = false`,
and the mouse-move hook returns before upstream's `self.mouse_nav = true`. So
upstream hover-select (`Menu.lua:1461-1471`) and the action-hover zones (1561) stay
off for the whole drag. The selected row stays the held row, with its upstream 0.15
selection background, its action buttons (drawn but not clickable), and its handle.
No other row is highlighted. `reorder_end` turns `mouse_nav` back on (R4-M1).

**Icon**: `drag_handle`. Present in `fonts/uosc_icons.otf` (fontTools, 2026-11-20).
That font's family is "Material Icons Round", which is the font `ass:icon` uses
(`lib/ass.lua:41`).

## R5 — Event routing in uosc: why the handle zone is registered after the action loop

- **Zone lookup** (`lib/cursor.lua:94-104`): `cursor:find_zone(event)` walks the
  zones from the **last** registered to the first. A zone counts if its event equals
  the requested one **or** equals `event_propagation_blockers[event]`, and its hitbox
  contains the cursor. For `primary_down` the blocker is `primary_click`
  (`cursor.lua:53-58`). If the first hit is a blocker, `find_zone` returns `nil`.
  `cursor.lua:113` says it directly: "Binding both makes only the last bound fire."
- **Consequence**: the handle's `primary_down` zone must be registered **after** every
  `primary_click` zone whose hitbox could contain the pointer. The upstream action
  buttons register `primary_click` inside the action loop (`Menu.lua:1561-1564`).
  `menu-handle` inserts the handle call just after that loop ends (before line 1575),
  so the handle zone is the last zone whose hitbox can contain the handle (the title
  zone at 1713 and parent-menu zones at 1416 come later but do not overlap it). Its slot also sits left of the leftmost action
  hitbox, so the two do not overlap. A Python test asserts the hook order in the
  patched file: the `reorder_handle` line comes after the last
  `cursor:zone('primary_click'` in the action block.
- **Press on the handle**: `find_zone('primary_down')` returns the handle zone,
  which was registered later than the display-wide `primary_down` zone (line 1374).
  `handle_cursor_down` is not called, so no scroll-drag starts (FR-002). A press
  anywhere else still reaches `handle_cursor_down`.
- **Release** (decided 2026-11-22 after round 3, finding R3-B1): the session catches
  the release through uosc's own cursor bus, not through an mpv key binding.
  - **How mpv routes the button.** Measured in headless mpv 0.42 with a script that
    binds `mbtn_left` as `lib/cursor.lua:459-471` does (`.egm/implementation_readiness_report_round3.md`):
    the key-up goes to the command that received the key-down, even when that
    command's section was disabled while the button was held (test T4). A binding
    added during the press never sees that press's release (T1), and a section
    re-enabled by `decide_keybinds` sits above forced bindings (T3). So a forced
    `mbtn_left` binding cannot catch the drag's own release; it is not used.
  - **What catches it.** The drag's press and release both reach uosc's
    `mbtn_left` handlers, which call `cursor:trigger('primary_up')`.
    `cursor:trigger` runs every global handler registered with `cursor:on`
    whether or not a zone is under the pointer (`lib/cursor.lua:166-175`).
    `reorder_start` registers `cursor:on('primary_up', …)`, which calls
    `reorder_release()`; `reorder_end` calls the disposer `cursor:on` returns
    (`cursor.lua:129-135`). This covers a release inside the menu, elsewhere in the
    window, and outside it, as long as the platform reports the button-up at all.
    The display-wide `primary_up` zone (line 1375) still runs upstream
    `handle_cursor_up` first; `reorder_start` cleared `drag_last_y` and
    `is_dragging`, so it does nothing.
  - **Early release** (decided 2026-11-22 after round 4, finding R4-B1; measured in
    the same harness, `.egm/implementation_readiness_report_round4.md`): when
    another key goes down while the button is held, mpv first sends the button-up
    (T5: `up` before `esc-down`); release-all, the focus-out path, sends it too
    (T7). uosc's plain `mbtn_left` functions cannot see mpv's `canceled` flag
    (T8). So `reorder_release` defers the commit with `mp.add_timeout(0, …)`.
    mpv's Lua event loop runs timers only when no events are queued, so an Esc
    queued behind the early up is dispatched first: the `menu-key` hook ends the
    session and the timer does nothing (T9: 5 of 5). The same hook ends it for any
    other menu key, so a Ctrl+move or Del cannot run inside the pending turn
    (R5-M1). A non-menu key lets the commit run; `reorder_commit` refuses if the
    playlist changed under it. Focus loss while the button is held: mpv sends the button-up first, so the drag commits at the visible drop line, unless the `focused` change is processed before the deferred commit, which cancels it; both outcomes are accepted. One one-shot timer per release; no other
    timers.
  - **A press after the drag started (guard).** `reorder_start` also registers
    `cursor:on('primary_down', …)`, which ends the session when `session.started`
    is true. The drag's own press can never trip it: `started` becomes true only in
    `reorder_move`, after the press. It covers a release that mpv received but uosc
    dropped (`cursor:create_handler` ignores events while `cursor.disabled`,
    `lib/cursor.lua:429`): the new press acts normally (its zone handlers run
    before global handlers), and its release finds no session.
  - **A release mpv never gets** (accepted 2026-11-22): mpv still holds the button,
    so it drops the next press (T6) and sends that click's up. The drag stays
    visibly active, the drop line follows the pointer back into the window, and the
    next click drops the item there.
  - Not covered by the measurement: whether KDE Wayland and Windows report the
    button-up when it happens outside the window. Quickstart §4 step 6 checks it by
    hand and records which of the two outcomes each platform shows.
- **Clicks and keys**: the handle is not an action and has no `primary_click` zone,
  so a mouse click on it triggers no `activate` event. It is never part of
  `actions`, so Tab and Enter cannot reach it.

## R6 — One move, playback untouched (FR-005, FR-006, SC-004)

- Commit sets `selected_index = from` and calls upstream
  `Menu:move_selected_item_to(to)`. That function refuses filtered menus, emits one
  `move` event, and selects and scrolls to `to` (`Menu.lua:666-676`). `lib/menus.lua`
  passes the event to `opts.on_move` (line 191). `main.lua:895-898` issues
  `playlist-move <from-1> <to - (to > from and 0 or 1)>`.
- The mpv manual describes `playlist-move` as moving an entry so that it takes the
  place of another. It is not a load command. The expected behaviour (no pause, no
  reload, `playlist-pos` follows the item) is measured in quickstart step 4 (SC-004),
  not assumed.
- The menu order does not change during a drag, so a cancel only forgets the session
  (FR-007).

**Gap → target index** (gap `g ∈ [0, n]` lies between items `g` and `g + 1`):
`to = g < from and g + 1 or g`. No move when `to == from`, that is, when
`g == from - 1` or `g == from`.

## R7 — Auto-scroll (FR-004)

- Zone: one `scroll_step` at the top and the bottom of the content area
  (`menu.top` to `menu.top + menu.height`).
- Speed: `depth × 12 rows/s × scroll_step` pixels per second.
- Frame-time step: `dt = now - last_tick` with `now = mp.get_time()`. It is capped at
  0.1 s, so a stalled frame cannot jump the list. It is 0 on the first tick in a zone,
  and `last_tick` resets when the pointer leaves the zones.
- `Menu:set_scroll_by()` clamps at the first and last item.
- During a drag, `request_render()` runs on each pointer move and, while the
  pointer is in an edge zone, on every frame. Outside a drag it runs only once, in
  `reorder_end`, and the render hook is a single `nil` check.
- Pointer outside the window (decided 2026-11-22, R3-M1): `cursor.y` is
  `math.huge` only after `cursor:leave()`, which runs when mpv reports
  `mouse-pos.hover == false` (`lib/cursor.lua:375`, 436-444). While the button is
  held, Wayland's implicit pointer grab and win32 mouse capture normally keep
  reporting coordinates outside the window with hover still true. So "outside the
  window" is `reorder_off_window()`: hover lost, or coordinates outside
  `display`. While it holds, `reorder_depth()` returns 0 and `reorder_move()` keeps
  the last gap: the drop line freezes at its last in-window position and nothing
  auto-scrolls. A release there commits that frozen gap when `focused` is reported
  (and cancels when it is not, per R4 `reorder_release`); Esc still cancels.
- Pointer outside the menu but inside the window: `reorder_gap` clamps to the
  first or last gap and `reorder_depth` gives full depth beyond the edge, so the
  drop line moves to that end and the list auto-scrolls.

## R8 — Release check: one total deadline across all reads

**Findings**: `deploy/fetcher._request()` uses `urlopen(timeout=30)`, a limit per
socket operation, plus 3 retries. A plain `resp.read(65536)` blocks until it has
64 KiB or reaches EOF, so a server that trickles one byte at a time defeats both a
per-operation timeout and a check made "after each chunk".

**Decision** (`tools/check_uosc_release.py`, stdlib only):

- **One deadline**: `deadline = time.monotonic() + download_timeout` (default
  120 s). It covers everything: the API request, any redirects, and the zip body.
- Requests go through `http.client.HTTPSConnection`. `HTTPConnection` is allowed
  only for loopback hosts, which the tests use. Before connecting, and before
  **every** read, the code sets the socket timeout to the remaining time,
  `conn.sock.settimeout(max(0.01, deadline - time.monotonic()))`. Bodies are read
  with `resp.read1(65536)`, which returns as soon as any bytes arrive, and the
  deadline is checked after each read.
  - A server that hangs is cut off when the remaining time runs out.
  - A server that trickles is cut off at the deadline.
- **Watchdog** (round 2, finding R2-M3): `getresponse()` reads the status line and
  headers itself, and every `recv` starts a fresh socket timeout, so trickled
  headers could outlast the deadline. Each connection therefore starts
  `threading.Timer(max(0.0, deadline - time.monotonic()), shutdown)` just before
  `getresponse()`. Here `shutdown` calls `conn.sock.shutdown(socket.SHUT_RDWR)`.
  The timer is cancelled in `finally`. A blocked header or body read then returns
  at the deadline, and the error is reported with the deadline message. This is
  not the rejected worker-thread download: the download stays on the main thread,
  and the timer only closes the socket.
- The asset is downloaded from `asset["browser_download_url"]`, the same field
  `deploy/fetcher.py:289` uses. Redirects (GitHub answers 302) are followed by
  hand, at most 5, under the same deadline. The timeout is also set before each
  `getresponse()`.
- On a socket timeout, or when the deadline passes, the message is:
  `uosc <tag or "latest">: download did not finish within <N> s (<url>); the release check could not run`,
  with `<N>` formatted as `f"{download_timeout:g}"` (120.0 prints `120`, 1 prints `1`).
  The exit code is **2**. Anchor failures exit **1**, success exits **0**.
- No retries. Job `timeout-minutes: 10` and step `timeout-minutes: 5` stay as a
  backstop.
- Token: `GITHUB_TOKEN`, or else `GH_TOKEN` (the same pair `fetcher._request`
  accepts). It is sent only when the request host is exactly `api.github.com`, and
  never to the redirect target or a test server.
- Test seam: module constant `API_URL`, and
  `run(api_url=API_URL, download_timeout=120.0) -> int`. The tests call `run()`
  in-process against a local `http.server` on `127.0.0.1`.
- The zip stays in memory. Only `scripts/uosc/elements/Menu.lua` is read from it.
  The `fetcher` limits apply (`MAX_DOWNLOAD_BYTES`, `MAX_ARCHIVE_MEMBERS`,
  `MAX_EXPANDED_BYTES`, `_safe_zip_name`). Nothing is written, imported or executed.
- No `subprocess` in the module. The single CLI test uses
  `subprocess.run([sys.executable, "-m", "tools.check_uosc_release", …])` with a
  list.

**Alternatives considered**:

- *`urlopen` plus the private `resp.fp.raw._sock`*: relies on private attributes.
  Rejected.
- *Download in a worker thread joined with a timeout*: the thread cannot be stopped
  and lingers in tests. Rejected.
- *`curl --max-time` in YAML*: the logic leaves tested Python. Rejected.

## R9 — Fixtures: real uosc 5.13.0 files

**Decision**: `tests/fixtures/uosc-5.13.0/elements/Menu.lua` holds the upstream
file unmodified (1831 lines, SHA-256 above). Next to it: uosc's `LICENSE`
(LGPL-2.1, from tag `5.13.0`) and a `README.md` stating the release URL, the tag,
the hash and the line count.

- To obtain it, download `uosc.zip` for tag `5.13.0`, extract the member, check its
  SHA-256 and `wc -l`, and copy it unchanged.
- A test fails if the fixture's SHA-256 changes.
- The same fixture feeds three suites: the patcher tests, the deployer tests (copied
  into a fake staging tree) and SC-009 (copied to a temp dir, with one anchor broken
  in the copy).
- `lib/menus.lua` is not a fixture, because the patch no longer touches it.

## R10 — Lua testing of the drag block

The payload is its own file, `tools/uosc_patches/playlist_reorder.lua`. The Python
patcher inserts it verbatim. `tests/lua/test_playlist_reorder.lua` loads it with
`dofile`, with stubs standing in for uosc:

- `Menu`, `state` (`scale`), `display` (`width`, `height`), `fg`/`bg`;
- `cursor`: `x`, `y`, `zone(event, rect, fn)` (recording), and a cursor bus with
  `on(event, fn)` returning a disposer, and `trigger(event, zone_fn)`, which
  mirrors `cursor:trigger` (`lib/cursor.lua:166-175`): it calls `zone_fn` first
  (for a press on the handle, that is `reorder_start`), then runs `ipairs` over the
  **live** handler table, so a handler registered inside `zone_fn` runs in the same
  press. Disposers remove from that same table with `table.remove`, as
  `cursor:off` does (139-147);
- `clamp`/`round` (same definitions as `lib/std.lua:6,11`);
- `request_render`;
- `mp` (`get_property_native`, `get_property` and `get_property_number` backed by the
  emulated playlist, `observe_property`, `unobserve_property`, `get_time`, and
  `add_timeout(delay, fn)`, which records `fn` in a pending list; the test runs the
  pending callbacks explicitly and counts them for "one timer per release");
- a recording `ass` (`icon`, `rect`);
- a menu with `create_action(fn)` (returns `fn`), `set_scroll_by`, `scroll_step`,
  `item_height`, `gap`, `padding`, `opacity`, `proximity_raw`,
  `mouse_hovered_index`, `mouse_nav`, and a `move_selected_item_to` that emulates
  `main.lua`'s `playlist-move`.

It runs in headless mpv through `tests/run_lua_tests.py`. A stub version of exactly
this harness passed in the 2026-11-22 prototype.

## R11 — Test environment baseline (2026-11-20)

- System Python 3.14 shows 7 import errors (`mpv_config` not installed, `rich`
  missing). This is the environment, not the code.
- The project venv `~/.local/share/mpv-config/venv/bin/python` gives **684 tests,
  OK (skipped=10)**. `python3 tests/run_lua_tests.py` gives **14/14 PASS**.
- `mpv_config` in that venv resolves to `~/.mpv-config-deploy`. Pull it before
  running tests (AGENTS.md).

## R12 — Checking the release before patching, and the state procedure

**Finding**: `fetch_release` validates the zip's structure but not its content. The
pin fixes the tag, but not the bytes.

**Decision**: the patcher stores
`EXPECTED_UPSTREAM_SHA256 = {"elements/Menu.lua": "0cbc42af…0f2f49"}` for the pin.
`detect_state(data, *, verify_hash=True)` runs this ordered procedure:

1. The marker is present, tested version-free as `b"mpv-config:playlist-reorder" in data`
   (so a partial patch or another patch version is `FOREIGN`): try `unpatch_bytes(data)`. If it fails, the state is
   `FOREIGN`. If it succeeds but `patch_bytes(unpatched, verify_hash=False) != data`
   (or raises), the state is also `FOREIGN`. This round trip only checks the
   structure; step 2 alone judges the hash. So a patched copy of bytes that are not
   the pinned release gives `UNEXPECTED_UPSTREAM`, without raising.
2. If `verify_hash` is set and the SHA-256 of the unpatched form (`data` when no
   marker is present) is not the expected value, the state is
   `UNEXPECTED_UPSTREAM`.
3. If the marker was present (and step 1 passed), the state is `PATCHED`.
4. If any anchor matches a number of times other than 1, the state is
   `BROKEN_ANCHOR`.
5. Otherwise the state is `UPSTREAM`.

`ABSENT` (the file is missing) is decided by `apply()` before it reads anything.

**Where each outcome applies (maintainer decision M3)**:

- **The deploy** uses `verify_hash=True`. The hash runs first, so for any file that
  is not the pinned upstream, the result is `UNEXPECTED_UPSTREAM`. `BROKEN_ANCHOR`
  cannot occur here, because the pinned bytes match every anchor, as the fixture
  test proves.
- **The CI release check** judges a new release whose hash is not known yet. It uses
  `check_anchors()`, which never checks hashes. `BROKEN_ANCHOR` is its outcome.
- **The anchor tests** (FR-024 all-or-nothing, the anchor-uniqueness test, SC-009)
  call `patch_bytes(data, verify_hash=False)`, `detect_state(data, verify_hash=False)`
  and `check_anchors`.

A pin bump (C-009) updates the hash, the fixture and the pin together, in one
commit.

**Alternatives considered**: pinning the SHA-256 of the whole `uosc.zip` in
`deploy/registry.py` would cover every uosc file. But that hash has not been
measured yet, and it changes the fetcher for all components. It is a follow-up.
Using anchors only was rejected, because an anchor can still match on changed code
nearby.
