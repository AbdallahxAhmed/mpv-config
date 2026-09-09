# Design Spec: uosc Playlist Drag-and-Drop Reordering

**Date**: 2026-09-09  
**Status**: Revised with Visual Affordance, Explicit Cancellation & Resilient Hook Architecture  
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
1. **IPC Decoupling (Optimistic UI)**: Local array mutation during drag; zero MPV IPC commands in-flight during cursor sweeps. The final reorder is committed on mouse release (`primary_up`) via `self:command_or_event(self.current.on_move, ...)`.
2. **Visual "Held" Elevation & List Dimming**: While dragging, the held item is elevated with an accent outline / increased opacity, and non-dragged items are subtly dimmed (`opacity * 0.75`) to provide immediate, clear affordance.
3. **Explicit Cancellation (Escape & Right-Click)**: At drag start, a shallow snapshot of `self.current.items` is saved. Pressing `Escape` or right-clicking (`secondary_down`) triggers `Menu:abort_reorder()`, rolling back the table without firing `on_move`.
4. **Non-Linear Edge Auto-Scroll**: Continuous scrolling driven by a periodic tick loop where scroll velocity scales non-linearly ($v \propto \text{depth}^{1.5}$) based on cursor penetration into the edge boundary.
5. **Kinetic Scroll Isolation**: Initiating a drag handle grab immediately zeroes `drag_last_y` and `current.fling`, preventing kinetic inertia or list scrolling from fighting the drag.
6. **50% Midpoint Hysteresis**: Item swapping triggers only when the cursor crosses past 50% of the adjacent item's height, preventing single-pixel edge jitter.
7. **Patcher Resilience via Function Wrapping**: The Python patcher avoids brittle multiline regex matches across internal loops. Instead, it anchors to stable function signatures (e.g., `Menu:handle_cursor_move`, `Menu:handle_cursor_up`, `Menu:handle_key`) and injects clean wrapper/hook calls.

```
[primary_down on drag_indicator]
   │
   ├──> Save snapshot: reorder_items_snapshot = shallow_copy(self.current.items)
   ├──> Record start_index = current_index, current_index = current_index
   ├──> Set is_reordering = true
   ├──> Clear drag_last_y & fling (kill kinetic scroll)
   │
[cursor moves (while is_reordering)]
   │
   ├──> Check midpoint threshold (50% hysteresis)
   ├──> Mutate local uosc items table (instant 60fps UI feedback)
   └──> If in edge zone: run continuous scroll tick with non-linear acceleration (depth^1.5)
   │
[Escape OR secondary_down (Right-click)]
   │
   ├──> Abort: restore self.current.items = reorder_items_snapshot
   ├──> Set is_reordering = false, kill scroll timer
   └──> Do NOT call on_move
   │
[primary_up OR window-focus lost]
   │
   ├──> Set is_reordering = false, kill scroll timer
   └──> If start_index ~= target_index:
           Delegate to: self:command_or_event(self.current.on_move, ...)
           (Playlist opener in main.lua executes: mp.commandv('playlist-move', ...))
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
- `self.reorder_items_snapshot: table|nil` — shallow copy of `self.current.items` before drag began.
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
    - Take snapshot: `self.reorder_items_snapshot = {unpack(self.current.items)}`.
    - Suppress menu drag-scroll: `self.is_dragging = false`, `self.drag_last_y = nil`, `self.current.fling = nil`.
    - Request re-render.

#### C. Visual Drag Affordance (Held State & List Dimming)
Inside `Menu:render()`:
- When `self.is_reordering == true`:
  - The dragged item (`index == self.reorder_current_index`) is styled prominently:
    - Render with solid/elevated background (`opacity = menu_opacity * 1.0`).
    - Render an accent outline border (`border = 1.5`, `border_color = fg`).
  - Other items (`index ~= self.reorder_current_index`):
    - Render with softened text and icon opacity (`opacity = menu_opacity * 0.75`).
- This provides instant visual clarity: the user always sees which item is under their control and where it is slotted.

#### D. Optimistic Local Reordering with 50% Midpoint Hysteresis
During cursor movement:
- If `self.is_reordering` is active:
  - Do NOT dispatch `playlist-move` IPC commands.
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

#### E. Non-Linear Edge Auto-Scrolling (Accelerated Depth)
- When `self.is_reordering` is active:
  - Check distance to top and bottom edge boundaries of the menu viewport.
  - Define `edge_threshold = self.item_height * 1.5`.
  - Calculate normalized penetration depth:
    $$\text{depth} = \text{clamp}\left(\frac{\text{edge\_threshold} - \text{distance\_to\_edge}}{\text{edge\_threshold}}, 0, 1\right)$$
  - Calculate non-linear scroll velocity:
    $$v = v_{\text{base}} \times (\text{depth})^{1.5}$$
    where $v_{\text{base}} = \text{self.scroll\_step} \times 1.2$.
  - Run continuous periodic timer accumulator while $\text{depth} > 0$:
    - Smoothly increments/decrements `self.current.scroll`.
    - Updates `self.mouse_hovered_index` and recalculates slot reordering.
    - Continues scrolling smoothly even if the mouse is held completely stationary at the window edge.

#### F. Explicit Cancellation via Escape & Right-Click
- Define `Menu:abort_reorder()`:
  ```lua
  function Menu:abort_reorder()
      if not self.is_reordering then return end
      self.is_reordering = false
      if self.reorder_scroll_timer then
          self.reorder_scroll_timer:kill()
          self.reorder_scroll_timer = nil
      end
      if self.reorder_items_snapshot then
          self.current.items = self.reorder_items_snapshot
          self.reorder_items_snapshot = nil
      end
      self.reorder_start_index = nil
      self.reorder_current_index = nil
      request_render()
  end
  ```
- **Escape Key Binding**: Hook into `Menu:handle_key()`. If key is `esc` and `self.is_reordering` is true, call `self:abort_reorder()` and consume key (do not close menu).
- **Right-Click (Secondary Click)**: Register `secondary_down` zone over the menu while `self.is_reordering == true` to invoke `self:abort_reorder()`.
- **Window Blur**: Observe `window-focus` property; if `window-focus == false`, invoke `self:abort_reorder()`.

#### G. Drag Release & Single-Commit via `opts.on_move`
In `Menu:handle_cursor_up()` and on `primary_up`:
- If `self.is_reordering`:
  - Set `self.is_reordering = false`.
  - Kill and clear `self.reorder_scroll_timer`.
  - Retrieve `from_idx = self.reorder_start_index` and `to_idx = self.reorder_current_index`.
  - Clean snapshot and index references.
  - If `from_idx ~= to_idx` and `from_idx` and `to_idx`:
    - Dispatch a single event via uosc's standard `self:command_or_event` dispatcher:
      ```lua
      local callback = self.current.on_move
      if callback then
          local event = {
              type = 'move',
              from_index = from_idx,
              to_index = to_idx,
              menu_id = self.current.id,
          }
          self:command_or_event(callback, {from_idx, to_idx, self.current.id}, event)
      end
      ```
    - The playlist menu opener in `main.lua` receives `event`, executes `playlist-move` with proper 0-based offset math, and synchronizes MPV state without intermediate IPC flooding.

---

### 3.3 Keyboard Navigation Preservation
All existing keyboard reorder bindings in `elements/Menu.lua` remain active:
- `ctrl+up` / `ctrl+down`: move by 1 slot.
- `ctrl+pgup` / `ctrl+pgdwn`: move by page.
- `ctrl+home` / `ctrl+end`: move to top/bottom.

---

### 3.4 Patcher Tool Architecture (`tools/patch_uosc_playlist_drag.py`)

#### Regex Resilience & Function Wrapping
To avoid upstream breakage from whitespace, comment, or formatting changes, the patcher uses **strict token anchoring** and **clean method wrapping**:
1. **`lib/menus.lua`**:
   - Searches for the distinct block `if opts.on_move then ... end` and swaps the arrow definitions for `drag_reorder`.
2. **`elements/Menu.lua`**:
   - Appends modular helper methods (`Menu:start_reorder()`, `Menu:update_reorder()`, `Menu:finish_reorder()`, `Menu:abort_reorder()`) at the end of the file or at clean section markers.
   - Anchors into stable method headers:
     - `function Menu:handle_cursor_move` → injects reorder update check.
     - `function Menu:handle_cursor_up` → injects reorder finish check.
     - `function Menu:handle_key` → injects Escape cancel check.
- **Safety & Idempotence**:
  - Uses patch markers (`-- UOSC_PLAYLIST_DRAG_PATCH`).
  - Checks if already patched; running repeatedly does not duplicate code.
  - Supports `--uosc-dir <path>` and `--unpatch`.

---

## 4. Edge Cases & Mitigations Matrix

| Failure Mode | Cause | Mitigation |
|---|---|---|
| **Property Observer Race Condition** | Sweeping across items triggers rapid `playlist-move` calls; async MPV observer callbacks interleave and desync indices. | **Optimistic Local Mutation + Commit on Release**: Mutate local `self.current.items` during drag; dispatch single `on_move` on `primary_up`. |
| **Auto-Scroll Stalls on Stationary Mouse** | Edge scroll hooked only to mouse move events. | **Timer/Tick Accumulator**: Run continuous periodic timer while cursor is inside boundary zone, scrolling until cursor moves away or releases. |
| **Sluggish or Jarring Edge Scroll** | Fixed linear scroll step across different playlist lengths. | **Non-Linear Depth Acceleration ($v \propto \text{depth}^{1.5}$)**: Scroll velocity accelerates smoothly as mouse penetrates deeper toward the window edge. |
| **Sticky Drag on Window Blur** | User releases mouse button outside window; OS drops `primary_up` event. | **Window Focus Observer & State Check**: Abort/commit drag when `window-focus == false` or on cursor re-entry without primary button pressed. |
| **Accidental Drag Reorder (No Undo)** | User drags an item by mistake and has no way to cancel. | **Explicit Cancellation (Escape & Right-Click)**: `esc` and `secondary_down` trigger `Menu:abort_reorder()`, restoring original `reorder_items_snapshot`. |
| **Visual Disorientation During Drag** | Unchanged row styles make it hard to tell which item is anchored to cursor. | **Visible Held State**: Elevated outline/opacity on held item; other items dimmed to 75% opacity. |
| **Kinetic Inertia Fling Fighting Drag** | Mouse movement triggers list inertia simultaneously with drag. | **Kinetic Scroll Interception**: Zero out `drag_last_y` and `fling` on `primary_down` on handle. |
| **Boundary Oscillation (Jitter)** | Item swap shifts boundary at the exact instant cursor enters edge. | **50% Midpoint Hysteresis**: Swap only when cursor passes the halfway point of the adjacent row. |
| **Active Filtering Desync** | Reordering filtered items produces undefined indices. | **Disabled Action**: Dim handle opacity to `0.2` with tooltip `Reordering disabled while searching`; ignore `primary_down`. |
| **Upstream Code Churn Breaking Patch** | Multiline regex fails when upstream alters whitespace or internal loops. | **Method Wrapping / Strict Token Anchors**: Wrap stable function entry points instead of rewriting internal loops inline. |

---

## 5. Verification & Test Plan

1. **Automated Unit Tests** (`tests/test_patch_uosc_playlist_drag.py`):
   - **Patch Verification**: Applying patch to clean uosc copies succeeds.
   - **Idempotence**: Applying patch twice produces identical files with zero duplicate code.
   - **Unpatch Restoration**: Running `--unpatch` restores files byte-for-byte to their original pre-patch state.
   - **Logic Verification**: Test presence of snapshot cloning, Escape/Right-click abort, non-linear depth acceleration, and hysteresis formulas.
   - **Lua Syntax Check**: Validate patched Lua scripts compile cleanly with zero syntax errors.
2. **Interactive mpv Verification**:
   - **Visual Held State**: Click and hold drag handle; verify held row gains accent outline and list subtly dims.
   - **Midpoint Hysteresis**: Move cursor slightly across boundary; verify item only swaps past 50% midpoint.
   - **Stationary Edge Scroll**: Hold cursor stationary at top/bottom border; verify smooth, accelerated scrolling.
   - **Escape Cancellation**: Drag item to new position, press `Esc`; verify item snaps back to original position and no `playlist-move` is fired.
   - **Right-Click Cancellation**: Drag item to new position, right-click; verify immediate rollback.
   - **Window Blur Protection**: Drag item, Alt-Tab or click outside window; verify drag state cancels cleanly without sticking.
   - **Search Query**: Type in search box; verify drag handle dims to 0.2 and dragging is disabled.
   - **Keyboard Navigation**: Verify `ctrl+up`/`ctrl+down` still work.
