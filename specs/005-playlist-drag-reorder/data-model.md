# Data Model: Playlist Drag-to-Reorder (spec 005)

**Plan**: [plan.md](plan.md) · **Research**: [research.md](research.md) · revised 2026-11-22

There are two runtime worlds. Lua runs inside uosc in mpv; Python runs in the
deployer, the patcher and the release check. Nothing new is stored on disk except
the patched `Menu.lua` and its hash in the existing manifest.

---

## Lua (inside patched uosc)

### Playlist item (existing, upstream)

A `MenuStackItem` built by the playlist serializer in uosc `main.lua:874-884`.

| Field | Type | Meaning |
|---|---|---|
| `value` | integer | 1-based playlist index at serialisation time |
| `title`, `hint` | string | display text; `hint` is the index |
| `active` | boolean | `playlist[i].current`, which is the **playing** marker |

Invariant (FR-006): the payload never writes `item.active`. Only the serializer
writes it, on a `playlist` property change.

### Drag session: `self.reorder` on the menu **instance**, `nil` when idle

The session is a field of the open `Menu` element, never of the `Menu` class. It is
removed by `reorder_end()`. Every way out of a drag calls `reorder_end()`:

- the `menu-close` hook, which runs on every close, including the replacement
  close in `Menu:open`;
- Esc, `Menu:update` (a list update, also via the `update-menu` message), focus
  true → false, a new press after the drag started, and the deferred commit
  after a release (`reorder_commit`).

A closed menu therefore never holds a session.

| Field | Type | Meaning |
|---|---|---|
| `menu_id` | string | `self.current.id` at start; a release in another (sub)menu does nothing |
| `from` | integer | 1-based index of the held item |
| `gap` | integer ∈ [0, n] | drop gap between items `gap` and `gap + 1` (n = `#items`); starts at `from` |
| `press_y` | number | `cursor.y` at the press |
| `started` | boolean | becomes true once `abs(cursor.y - press_y) >= 4 × state.scale` |
| `last_tick` | number or nil | `mp.get_time()` of the previous auto-scroll step; nil outside the edge zones |
| `focused` | boolean or nil | last known `focused` value, first read at the press; nil when the VO does not report it |
| `on_focus` | function or nil | the `focused` observer; cancels if and only if the new value is false and `focused` is true, otherwise stores the new value; nil when not reported |
| `off_up` | function | disposer returned by `cursor:on('primary_up', …)`; the handler calls `reorder_release()` for every release uosc receives, inside or outside the window |
| `outside` | boolean or nil | nil until a release; then whether that release was outside (`reorder_off_window()` or `proximity_raw > 0`). Non-nil means a commit is pending for one event-loop turn: the gap and auto-scroll are frozen and a second release is ignored |
| `off_down` | function | disposer returned by `cursor:on('primary_down', …)`; the handler calls `reorder_end()` when `started` is true (a new press reaching uosc means uosc dropped the drag's release) |

`reorder_end()` calls `off_up()` and `off_down()`, so no handler outlives the
session (research R5).

Derived values: `to = gap < from and gap + 1 or gap`, and `is_noop = not started or to == from`.

#### Pointer → gap

```text
p   = (cursor.y - menu.top + menu.scroll_y) / scroll_step   -- rows from the content top
gap = clamp(0, math.floor(p + 0.5), #items)                       -- upper half of row r → r-1, lower half → r
```

Worked example (`menu.top = 100`, `scroll_step = 40`, `scroll_y = 0`, 5 items):

| `cursor.y` | over | p | gap | from = 2 → `to` | result |
|---|---|---|---|---|---|
| 90 | above the list | -0.25 | 0 | 1 | item 2 becomes first |
| 115 | row 1, upper half | 0.375 | 0 | 1 | becomes first |
| 130 | row 1, lower half | 0.75 | 1 | 2 | no move (own gap) |
| 175 | row 2, lower half | 1.875 | 2 | 2 | no move (own gap) |
| 225 | row 4, upper half | 3.125 | 3 | 3 | goes after item 3 |
| 290 | row 5, lower half | 4.75 | 5 | 5 | becomes last |
| 400 | below the list | 7.5 → 5 | 5 | 5 | becomes last |

Rows y=90 and y=400 show the pointer above or below the list but inside the window:
the gap clamps to the first or last one, and auto-scroll runs at full depth
(research R7). Beside the list, the gap follows the pointer's y.

**Off-window** (`reorder_off_window()`: `cursor.y == math.huge`, or `cursor.x < 0`,
`cursor.y < 0`, `cursor.x >= display.width` or `cursor.y >= display.height`):
`gap` and `started` keep their values, so the drop line stays at its last in-window
position, and auto-scroll stops. A release there commits that gap when `focused` is
observed; otherwise it cancels.

#### Validation (in `reorder_start`; if it fails, no session is created)

- `self.type == 'playlist'`, `menu == self.current` and `menu.on_move ~= nil` (FR-021)
- `self.current.search == nil` (FR-009)
- `#self.current.items >= 2` (no handle on 0 or 1 items)
- no session already exists

#### State transitions

```text
                  primary_down on the handle (valid)
  Idle ────────────────────────────────────────▶ Pressed (started = false)
   ▲                                               │ |Δy| ≥ 4·scale
   │ release while Pressed: Releasing, then no move ▼
   ├───────────────────────────────────────── Dragging (started = true)
   │                                               │ move      → gap = pointer → gap
   │                                               │ edge zone → scroll (R7), gap recomputed
   │                                               │ off-window → gap frozen, no scroll
   │ release (`primary_up` handler, anywhere, also off-window, also an early up)
   │                                               ▼
   │                       Releasing (outside recorded; commit after one turn)
   │   reorder_commit:                             │
   │   to ≠ from → ONE move_selected_item_to(to) · to = from → no move
   │   outside the menu and `focused` not observed → cancel, no move
   │   a search is active → no move
   ├───────────────────────────────────────────────┤
   │ Esc or any menu key · close · Menu:update · focused true→false (while Dragging or Releasing)
   │ · a new press while Dragging
   └──────────────── cancel, no move ◀─────────────┘
```

Every exit clears `self.reorder` **before** any move is issued, so the `playlist`
change caused by the commit cannot cancel anything. While a session exists,
`self.mouse_nav` is false: upstream hover-select and action-hover are off, and the
selected row stays the held row (research R4, M8).

### Rendering contributions (additive only)

`t = round(2 × state.scale)` · `ax = self.ax + self.padding` ·
`bx = ax + menu.width` · `top = menu.top` · `bottom = menu.top + menu.height` ·
`clip = \clip(0, top, display.width, bottom)`, which clips everything to the
content area.

| Element | Drawn when | Geometry | Style |
|---|---|---|---|
| Handle `drag_handle` | `reorder_enabled(menu)` and either (no session, `self.mouse_nav`, the row is selected, `self.mouse_hovered_index == index` and `self.proximity_raw <= 0`) or (session and row = `from`) | square slot of `size = actions_rect.by - actions_rect.ay`, right edge at `actions_rect.ax - gap × 2`; icon at the slot centre, `size × 0.66` | `fg`, opacity `self.opacity`, row clip |
| Held-row outline | `started`, `self.current.id == menu_id` and no search active | row `ay = top - scroll_y + scroll_step × (from - 1)`, `by = ay + item_height`; 4 rects of thickness `t` on its edges, from `ax` to `bx` | `bg` if the held item is `active`, otherwise `fg`; opacity `self.opacity`; content clip |
| Drop line | same | `y = top - scroll_y + scroll_step × gap - (scroll_step - item_height) / 2`, clamped to `[top + t/2, bottom - t/2]`; rect `ax..bx`, `y ± t/2` | `fg`, opacity `self.opacity`; content clip |

Only the current menu is drawn: `reorder_handle` checks `menu == self.current`, and
`reorder_draw` uses `self.current`. Parent menus and submenus never show a handle,
an outline or a line. The upstream row background (`highlight_opacity`, including
`active and 0.8`) and `font_color` are drawn as before, underneath.

---

## Python (deployer / patcher / release check)

### Hunk

| Field | Type | Meaning |
|---|---|---|
| `id` | str | stable name used in messages, for example `menu-key` (8 hunks, research R4) |
| `anchor` | bytes | verbatim upstream bytes, tabs and LF; must occur exactly once |
| `insertion` | bytes | inserted bytes; each hook line ends with ` -- mpv-config:playlist-reorder v1` |
| `where` | `"before"` or `"after"` | side of the anchor |

The file is always `elements/Menu.lua`. Hunks never overlap. Unpatch removes each
`insertion`, and only when it occurs exactly once next to its anchor.

### Patch target state

Decided by the ordered procedure in research R12:

| Order | State | Condition |
|---|---|---|
| (in `apply`) | `ABSENT` | `scripts/uosc/elements/Menu.lua` is missing |
| 1 | `FOREIGN` | the marker is present, but `unpatch_bytes` fails or does not round-trip |
| 2 | `UNEXPECTED_UPSTREAM` | `verify_hash` is set and the SHA-256 of the unpatched form ≠ `EXPECTED_UPSTREAM_SHA256` |
| 3 | `PATCHED` | the marker is present and steps 1 and 2 passed |
| 4 | `BROKEN_ANCHOR` | some anchor matches ≠ 1 time; reachable only with `verify_hash=False` (CI and tests) |
| 5 | `UPSTREAM` | otherwise |

### Patch result (`apply()`) → deployer result row

| `status` | When | Row `status` | Row `detail` (exact format) |
|---|---|---|---|
| `patched` | `UPSTREAM`, written | `ok` | `patched ({source}, {version})` |
| `already-patched` | `PATCHED` | `ok` | `already patched ({source}, {version})` |
| `skipped` | `UNEXPECTED_UPSTREAM` | `warn` | `uosc-playlist-reorder skipped: elements/Menu.lua does not match uosc {pin} (sha256 of the unpatched form {first 12 hex}…); uosc left unchanged` |
| `skipped` | `FOREIGN` | `warn` | `uosc-playlist-reorder skipped: elements/Menu.lua carries an unknown or partial playlist-reorder patch; uosc left unchanged` |
| `skipped` | `BROKEN_ANCHOR` | `warn` | `uosc-playlist-reorder skipped: anchor {hunk_id} matched {n}× in elements/Menu.lua (expected 1); uosc left unchanged` |
| `skipped` | write raised `OSError` | `warn` | `uosc-playlist-reorder skipped: could not write elements/Menu.lua ({error}); uosc left unchanged` |
| `absent` | `ABSENT` | `skipped` | `uosc not present in this deployment; nothing to patch` |

`{source}` is `staged` or `live`, and `{version}` is the uosc tag or `unknown`. Row
`name` is always `uosc-playlist-reorder-patch`. With `unpatch=True`, `apply()`
returns `unpatched` or `already-unpatched`; the deployer never unpatches.

### Release check result

| Field | Type | Meaning |
|---|---|---|
| `version` | str | `tag_name` from the API, or `--version` |
| `failures` | list[`AnchorFailure(hunk_id, found)`] | empty means pass |
| exit code | int | 0 pass · 1 anchor failure · 2 could not run (deadline, HTTP error, asset or member missing, bad zip) |
