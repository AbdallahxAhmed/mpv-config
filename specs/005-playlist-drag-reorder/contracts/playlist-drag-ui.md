# Contract: playlist menu drag behaviour (user-facing)

Applies only to the uosc menu with `type == 'playlist'` (FR-021). Every other menu,
and every parent menu or submenu, renders and behaves exactly as with upstream uosc
5.13.0.

## Controls

| Input | Where | Result | Req |
|---|---|---|---|
| Hover a row with the mouse | playlist, ≥ 2 items, no search, pointer over the menu | that row shows the handle `drag_handle` **left of** its unchanged action buttons (move up, move down, remove) | FR-001, FR-008 |
| Keyboard navigation (arrows, Tab, Enter) | — | exactly as upstream. The handle is mouse-only: it is never drawn while navigating by keyboard, it is not a Tab stop, and it never changes the selected-row indicator | FR-008 |
| Press the handle, move < 4 px, release | handle | nothing; the item is not activated, and the handle stays on the hovered row | edge case |
| Press the handle, move ≥ 4 px | handle | drag starts: the held row gets an outline, the drop line appears, and hover selection is off until the drag ends | FR-002, FR-003 |
| Move while dragging | over the menu's list | the drop line jumps in whole-row steps to the gap under the pointer (half-row split, data-model "Pointer → gap") | FR-003 |
| Hold in the top or bottom row-high zone | menu edges | scrolls toward that edge at up to 12 rows/s, faster the deeper the pointer, stopping at the ends | FR-004 |
| Move outside the menu but inside the window | above or below the list (beside it, the gap follows the pointer's y) | the drop line goes to the first or last gap and the list auto-scrolls toward that end | FR-003, FR-004, edge case |
| Move outside the mpv window | off-window (hover lost, or coordinates outside the window while the button is held) | the drop line freezes at its last in-window position; no auto-scroll | edge case |
| Release inside the menu | — | one `playlist-move` to the indicated gap, or none for the item's own gap | FR-005 |
| Release outside the menu or the window | — | when the platform reports the button-up, the session's `cursor:on('primary_up')` handler gets it. `focused` reported by the VO: commits to the drop line's position (off-window: the frozen one). Not reported: cancel, no move. If mpv never gets the button-up, the drag stays active with its drop line visible and the next click drops there | FR-007, edge case |
| Esc or any other menu key (also while the button is held) · menu closes · playlist changes · window loses focus (`focused` true → false, when reported, if processed before the release's commit) · a new press after the drag started, when uosc missed the release | — | drag cancelled, no move. Hover selection resumes, so a new press acts as a normal click on the row under the pointer | FR-007 |
| Window loses focus while the button is held | — | mpv sends the button-up first, so the drag commits at the visible drop line, unless the `focused` change is processed before the deferred commit, which cancels it; both accepted | edge case |
| A non-menu key (e.g. Space) while the button is held | — | mpv sends the button-up first, so the drag commits at the visible drop line; if the playlist changed meanwhile, no move | edge case |
| Search started during a drag | — | outline and drop line hidden, no auto-scroll; the release moves nothing | FR-009 |
| Press a row outside the handle and drag | row | scrolls the menu, as upstream | FR-002 |
| Ctrl+Up/Down/Home/End/PgUp/PgDn, move buttons | — | unchanged | FR-008 |
| Search or filter active | — | no handle, no drag | FR-009 |

## Visual invariants

- The playing row keeps its upstream highlight (background opacity 0.8, `fgt`
  text) at all times, including while it is the held row. The outline (in `bg` on
  the playing row, `fg` otherwise) and the drop line are drawn on top and replace
  nothing (FR-006).
- During a drag, only the held row is selected (its 0.15 selection background and
  action buttons stay as upstream). No other row lights up under the pointer.
- The menu order on screen does not change until release, and then only by the one
  move the drop line showed (SC-002).
- No change to row height, padding or the scrollbar. On the hovered row, the title
  is clipped one button-width earlier to make room for the handle.

## Playback invariants

- A move never pauses, seeks, reloads or restarts the playing item (FR-006, SC-004).
- During drags, `vo-delayed-frame-count` and `frame-drop-count` stay 0, and `avsync`
  stays within ±5 ms (spec 004 method; FR-020, SC-003).
