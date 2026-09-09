# Design Spec: uosc Playlist Drag-and-Drop Reordering

**Date**: 2026-09-09  
**Status**: Approved  
**Target**: `uosc` (MPV On-Screen Controller)  
**Implementation Tool**: `tools/patch_uosc_playlist_drag.py`

---

## 1. Problem Statement & Motivation

In the default `uosc` on-screen controller, moving items within the playlist menu is achieved by hovering over an item and clicking separate `arrow_upward` and `arrow_downward` action buttons, or using keyboard shortcuts (`ctrl+up`, `ctrl+down`).

This model has several usability limitations:
1. Moving an item several slots up or down requires repetitive clicking on tiny arrow icons.
2. Clicking and dragging anywhere on the menu currently performs kinetic list scrolling, leaving no mouse-first gesture for reordering.
3. The presence of two separate arrow buttons clutters the item action area.

The goal is to replace the arrow buttons with a single **drag handle** (`drag_indicator`) that supports intuitive click-and-drag reordering with live visual feedback, while preserving list scrolling and keyboard navigation.

---

## 2. Technical Architecture & Component Design

The implementation follows the established repository pattern (used by `tools/patch_uosc_button.py`):
- Upstream `uosc` is installed cleanly from releases.
- An idempotent patcher script (`tools/patch_uosc_playlist_drag.py`) injects our modifications into the deployed `uosc` scripts (`lib/menus.lua` and `elements/Menu.lua`).
- Updates to `uosc` can be downloaded at any time, and the patcher re-applies our modifications without code loss.

```
┌─────────────────────────────────────────────────────────────┐
│                    uosc Playlist Menu                       │
│                                                             │
│  [Track 01 - Intro.mp4]               [⋮⋮ Drag] [🗑 Delete] │ ◄── Replaces arrows
│  [Track 02 - Episode.mp4] ◄──(Swaps)                        │
│  [Track 03 - Ending.mp4]                                    │
└─────────────────────────────────────────────────────────────┘
                               ▲
                               │
               ┌───────────────┴───────────────┐
               │ tools/patch_uosc_playlist_drag│
               └───────────────────────────────┘
```

---

## 3. Detailed Component Specifications

### 3.1 `lib/menus.lua` Action Definition
In `lib/menus.lua`, `opts.on_move` controls whether movable action items are added to list items.

- **Current Behavior**:
  ```lua
  if opts.on_move then
      actions[#actions + 1] = {
          name = 'move_up',
          icon = 'arrow_upward',
          label = t('Move up') .. ' (ctrl+up/pgup/home)',
          filter_hidden = true,
      }
      actions[#actions + 1] = {
          name = 'move_down',
          icon = 'arrow_downward',
          label = t('Move down') .. ' (ctrl+down/pgdwn/end)',
          filter_hidden = true,
      }
  end
  ```
- **New Behavior**:
  Replace `move_up` and `move_down` with:
  ```lua
  if opts.on_move then
      actions[#actions + 1] = {
          name = 'drag_reorder',
          icon = 'drag_indicator',
          label = t('Drag to reorder') .. ' (ctrl+up/down)',
          filter_hidden = true,
      }
  end
  ```
- **Icon**: `drag_indicator` (6 dots `⋮⋮`) from Google Material Icons (included in uosc's font).

---

### 3.2 `elements/Menu.lua` Interaction & State Management

#### A. State Variables
The following properties are maintained on `Menu`:
- `self.is_reordering: boolean` — `true` when a drag operation is actively in progress.
- `self.reorder_source_index: integer|nil` — the playlist index currently being dragged.

#### B. Drag Initiation (`primary_down` on Drag Handle)
When rendering action buttons for the selected item:
- For `action.name == 'drag_reorder'`:
  - Register a `cursor:zone('primary_down', rect, ...)` handler.
  - When pressed:
    - Set `self.is_reordering = true`.
    - Set `self.reorder_source_index = index`.
    - Suppress menu drag-scroll (`self.is_dragging = false`, `self.drag_last_y = nil`).
    - Request re-render to reflect the active dragging state.

#### C. Live Swapping During Drag
During mouse movement (`handle_cursor_move` or inside the render loop while `self.is_reordering` is true):
- Detect the item under the cursor: `hovered = self.mouse_hovered_index`.
- If `hovered` is valid (`1 <= hovered <= #items`) and `hovered ~= self.reorder_source_index`:
  - Invoke `self:move_selected_item_to(hovered)`.
  - Update `self.reorder_source_index = hovered`.
  - `move_selected_item_to` calls mpv's `playlist-move` command, instantly updating mpv's playlist array and uosc's items.

#### D. Edge Auto-Scrolling
If the cursor Y position is within `self.item_height` of the top or bottom of the menu container during reordering:
- Automatically adjust `self.current.scroll` by `self.scroll_step * direction` to allow dragging items across multi-page playlists.

#### E. Drag Release & Termination
In `Menu:handle_cursor_up()` and on `primary_up`:
- If `self.is_reordering`:
  - Reset `self.is_reordering = false`.
  - Reset `self.reorder_source_index = nil`.
  - Normal menu mouse hover and touch/drag scrolling resume.

---

### 3.3 Keyboard Navigation Preservation
All existing keyboard reorder bindings in `elements/Menu.lua` remain active:
- `ctrl+up` / `ctrl+down`: move by 1 slot.
- `ctrl+pgup` / `ctrl+pgdwn`: move by page.
- `ctrl+home` / `ctrl+end`: move to top/bottom.

---

### 3.4 Patcher Tool (`tools/patch_uosc_playlist_drag.py`)

- **Safety & Idempotence**:
  - Uses patch markers (`-- UOSC_PLAYLIST_DRAG_PATCH`).
  - Checks if already patched; running repeatedly does not duplicate code.
- **CLI Interface**:
  - `--uosc-dir <path>`: Specifies target `uosc` directory (defaults to `%APPDATA%/mpv/scripts/uosc` on Windows).
  - `--unpatch`: Reverts both files to original state.
- **Target Files**:
  1. `lib/menus.lua`: Swaps arrow actions for `drag_reorder`.
  2. `elements/Menu.lua`: Adds `primary_down` drag initiation, live move, auto-scroll, and cleanup.

---

## 4. Edge Cases & Mitigations

| Edge Case | Mitigation |
|-----------|------------|
| Dragging during active search/filter | `drag_reorder` action has `filter_hidden = true`. Moving filtered items is already blocked by `move_selected_item_to`. |
| Conflict between drag-reorder and drag-scroll | Drag handle captures `primary_down`, which sets `self.is_reordering = true` and clears `drag_last_y`, preventing `is_dragging` (scroll) from triggering. |
| Mouse released outside mpv window | `cursor` global tracks button state. On next mouse entry or window blur, unsets `is_reordering`. |
| Long playlists requiring paging | Edge auto-scrolling smoothly scrolls the list when dragging near top/bottom menu boundaries. |

---

## 5. Verification & Test Plan

1. **Automated Unit Tests** (`tests/test_patch_uosc_playlist_drag.py`):
   - Test patch application on clean uosc files.
   - Test idempotency (repeated application leaves files identical).
   - Test unpatch restores exact byte-for-byte original content.
   - Lua syntax compilation check (`luac` or syntax parser).
2. **Interactive mpv Verification**:
   - Open playlist menu with multiple files.
   - Verify `arrow_upward` and `arrow_downward` icons are replaced with `drag_indicator`.
   - Click and drag the handle up and down; verify tracks live-swap into position and mpv's playlist updates.
   - Verify clicking anywhere else on the row plays the file.
   - Verify dragging non-handle areas scrolls the list normally.
   - Verify `ctrl+up` and `ctrl+down` still work.
