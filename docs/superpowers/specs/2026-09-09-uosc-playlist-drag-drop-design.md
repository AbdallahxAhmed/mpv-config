# Design Spec: uosc Playlist Drag-and-Drop Reordering

**Date**: 2026-09-09  
**Status**: Revised with IPC Decoupling & Edge Stabilization  
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

## 2. Technical Architecture & Core Principles

The implementation follows the established repository pattern (used by `tools/patch_uosc_button.py`):
- Upstream `uosc` is installed cleanly from releases.
- An idempotent patcher script (`tools/patch_uosc_playlist_drag.py`) injects our modifications into the deployed `uosc` scripts (`lib/menus.lua` and `elements/Menu.lua`).
- Updates to `uosc` can be downloaded at any time, and the patcher re-applies our modifications without code loss.

### Core Architectural Decisions:
1. **IPC Decoupling (Optimistic UI)**: Local array mutation during drag; zero MPV IPC commands in-flight during cursor sweeps. A single `playlist-move` command is dispatched upon mouse release (`primary_up`).
2. **Tick-Based Auto-Scroll**: Continuous scrolling driven by a periodic timer or render-loop accumulator, ensuring scrolling continues even when the mouse remains stationary at the boundary.
3. **Midpoint Hysteresis**: Item swapping triggers only when the cursor crosses past 50% of the adjacent item's height, preventing single-pixel edge jitter.
4. **Window Focus / Blur Guard**: Automatic abort if MPV loses window focus or cursor button release is missed by the OS.
5. **Search Invalidation Guard**: Drag handle is cleanly disabled during active query filtering.

```
[primary_down on drag_indicator]
   │
   ├──> Record start_index = current_index, target_index = current_index
   ├──> Set is_reordering = true
   │
[cursor moves (while is_reordering)]
   │
   ├──> Check midpoint threshold (50% hysteresis)
   ├──> Mutate local uosc items table (instant 60fps UI feedback)
   └──> If in edge zone: run continuous scroll tick accumulator
   │
[primary_up OR window-focus lost]
   │
   ├──> Set is_reordering = false
   ├──> Stop scroll tick
   └──> If start_index ~= target_index:
           Dispatch single: mp.commandv('playlist-move', start_index - 1, target_index - 1)
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
- `self.reorder_start_index: integer|nil` — original index where the drag started.
- `self.reorder_current_index: integer|nil` — current visual slot index of the dragged item.
- `self.reorder_scroll_timer: any|nil` — periodic timer for continuous edge scrolling.

#### B. Drag Initiation (`primary_down` on Drag Handle)
When rendering action buttons for the selected item:
- If search filtering is active (`menu.search` is non-empty):
  - Disable the action: render with `opacity = menu_opacity * 0.2` and tooltip `Reordering disabled while searching`.
  - Ignore `primary_down`.
- Otherwise:
  - Register `cursor:zone('primary_down', rect, ...)` handler.
  - When pressed:
    - Set `self.is_reordering = true`.
    - Set `self.reorder_start_index = index`.
    - Set `self.reorder_current_index = index`.
    - Suppress menu drag-scroll (`self.is_dragging = false`, `self.drag_last_y = nil`).
    - Request re-render.

#### C. Optimistic Local Reordering with 50% Midpoint Hysteresis
During mouse movement (`handle_cursor_move` or inside the render loop):
- If `self.is_reordering` is active:
  - Do NOT dispatch `playlist-move` IPC commands.
  - Compute cursor vertical position relative to neighboring item rectangles.
  - Apply **50% Midpoint Hysteresis**:
    - To move **down**: Cursor Y must cross past the midpoint of the item below (`item.ay + item.height * 0.5`).
    - To move **up**: Cursor Y must cross past the midpoint of the item above (`item.ay + item.height * 0.5`).
  - When threshold is crossed into target slot `new_index`:
    - Locally swap/shift `self.current.items` table elements:
      ```lua
      local item = table.remove(self.current.items, self.reorder_current_index)
      table.insert(self.current.items, new_index, item)
      self.reorder_current_index = new_index
      self.current.selected_index = new_index
      request_render()
      ```
    - The UI updates instantly at 60 FPS without touching MPV's event loop or property observers.

#### D. Continuous Edge Auto-Scrolling (Stationary Cursor Support)
- When `self.is_reordering` is active:
  - Check if cursor Y is within edge threshold (`edge_zone = self.item_height * 1.2` from top/bottom menu boundaries).
  - If inside edge zone:
    - Start (or keep active) a periodic timer (or tick callback every 16ms):
      - Calculate scroll speed proportional to distance into the threshold zone.
      - Accumulate `self.current.scroll = self.current.scroll + delta_scroll`.
      - Clamp scroll to valid bounds and update `self.mouse_hovered_index`.
      - Perform hysteresis check and mutate local items table accordingly.
      - Call `request_render()`.
  - If cursor leaves edge zone:
    - Stop and clear `self.reorder_scroll_timer`.

#### E. Drag Release & Single-Commit IPC Execution
In `Menu:handle_cursor_up()` and on `primary_up`:
- If `self.is_reordering`:
  - Set `self.is_reordering = false`.
  - Stop and clear `self.reorder_scroll_timer`.
  - Retrieve `from_idx = self.reorder_start_index` and `to_idx = self.reorder_current_index`.
  - Reset state variables.
  - If `from_idx ~= to_idx` and `from_idx` and `to_idx`:
    - Dispatch a single atomic MPV command:
      ```lua
      mp.commandv('playlist-move', tostring(from_idx - 1), tostring(to_idx - (to_idx > from_idx and 0 or 1)))
      ```
    - This eliminates all in-flight race conditions; MPV's property observer fires once, perfectly synchronizing with the user's final desired order.

#### F. Window Blur & Lost Focus Protection ("Sticky Drag" Fix)
- Register an observer on MPV's `window-focus` property:
  ```lua
  mp.observe_property('window-focus', 'bool', function(_, focused)
      if not focused and Menu.is_reordering then
          Menu:abort_reorder()
      end
  end)
  ```
- On cursor zone re-entry or `handle_cursor_move`:
  - Check if mouse button is actually pressed (`cursor.primary_down`).
  - If not pressed, immediately abort: `self.is_reordering = false`, kill scroll timer, and either commit current slot or revert local items table.

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
  2. `elements/Menu.lua`: Adds optimistic reordering, midpoint hysteresis, tick-based edge scroll, single-commit drop, and window focus guard.

---

## 4. Edge Cases & Mitigations Matrix

| Failure Mode | Cause | Mitigation |
|---|---|---|
| **Property Observer Race Condition** | Sweeping across items triggers rapid `playlist-move` calls; async MPV observer callbacks interleave and desync indices. | **Optimistic Local Mutation + Commit on Release**: Mutate local `self.current.items` during drag; dispatch single `playlist-move` on `primary_up`. |
| **Auto-Scroll Stalls on Stationary Mouse** | Edge scroll hooked only to mouse move events. | **Timer/Tick Accumulator**: Run continuous periodic timer while cursor is inside boundary zone, scrolling until cursor moves away or releases. |
| **Sticky Drag on Window Blur** | User releases mouse button outside window; OS drops `primary_up` event. | **Window Focus Observer & State Check**: Abort/commit drag when `window-focus == false` or on cursor re-entry without primary button pressed. |
| **Boundary Oscillation (Jitter)** | Item swap shifts boundary at the exact instant cursor enters edge. | **50% Midpoint Hysteresis**: Swap only when cursor passes the halfway point of the adjacent row. |
| **Active Filtering Desync** | Reordering filtered items produces undefined indices. | **Disabled Action**: Dim handle opacity to `0.2` with tooltip `Reordering disabled while searching`; ignore `primary_down`. |

---

## 5. Verification & Test Plan

1. **Automated Unit Tests** (`tests/test_patch_uosc_playlist_drag.py`):
   - Test patch application on clean uosc files.
   - Test idempotency (repeated application leaves files identical).
   - Test unpatch restores exact byte-for-byte original content.
   - Test presence of hysteresis calculation, optimistic table mutation, window-focus observer, and tick scroll timer.
   - Lua syntax compilation check (`luac` or syntax parser).
2. **Interactive mpv Verification**:
   - **Rapid Drag**: Sweep mouse rapidly across 10 items in <200ms; verify smooth 60 FPS reorder and single clean playlist update on drop with zero index corruption.
   - **Stationary Edge Hold**: Drag item to top edge and hold stationary; verify list continuously scrolls up.
   - **Window Exit Release**: Drag item, move cursor outside MPV window, release button, and return; verify drag state cancels cleanly without sticking.
   - **Search Query**: Type query in playlist; verify drag handle dims and does not trigger drag.
   - **Keyboard Reorder**: Verify `ctrl+up` and `ctrl+down` still work as expected.
