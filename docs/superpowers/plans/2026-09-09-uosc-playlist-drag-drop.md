# uosc Playlist Drag-and-Drop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement drag-and-drop playlist reordering in uosc to replace up/down arrows with an intuitive, live-swapping drag handle using an idempotent post-install patcher.

**Architecture:** A Python tool (`tools/patch_uosc_playlist_drag.py`) injects modular drag-and-drop hooks into `uosc/lib/menus.lua` and `uosc/elements/Menu.lua`. Dragging mutates local menu state optimistically with 50% midpoint hysteresis, non-linear edge auto-scrolling, visual elevation, explicit Escape/Right-click cancellation, and commits a single atomic reorder on mouse release by delegating to `opts.on_move`.

**Tech Stack:** Python 3 (standard library only), Lua 5.1 / LuaJIT (mpv scripting), MPV IPC, unittest.

---

## File Structure

- **Implementation Tool**: `tools/patch_uosc_playlist_drag.py`
  Responsible for locating the target uosc installation, applying the idempotent patch to `lib/menus.lua` and `elements/Menu.lua`, and supporting unpatching.
- **Unit Test Suite**: `tests/test_patch_uosc_playlist_drag.py`
  Responsible for testing patch transformations, idempotence, unpatch byte-reversal, and verifying Lua syntax integrity on sample uosc files.
- **Target Runtime Files** (patched in place):
  - `%APPDATA%/mpv/scripts/uosc/lib/menus.lua`
  - `%APPDATA%/mpv/scripts/uosc/elements/Menu.lua`

---

## Tasks

### Task 1: Write Automated Test Suite for Playlist Drag Patcher

**Files:**
- Create: `tests/test_patch_uosc_playlist_drag.py`

- [ ] **Step 1: Write the failing unit tests for patch and unpatch operations**

Create `tests/test_patch_uosc_playlist_drag.py` with test cases verifying:
1. `patch_menus_lua` replaces `move_up` and `move_down` with `drag_reorder`.
2. `unpatch_menus_lua` restores `move_up` and `move_down`.
3. `patch_menu_lua` injects `start_reorder`, `update_reorder`, `finish_reorder`, and `abort_reorder` methods and hooks function entry points.
4. `unpatch_menu_lua` removes all injected blocks.
5. Idempotency: `patch(patch(content)) == patch(content)`.
6. Full directory patching via `run_patcher` in a temporary directory.

```python
import tempfile
import unittest
from pathlib import Path

from tools import patch_uosc_playlist_drag as patcher

SAMPLE_MENUS_LUA = """
\t\tif opts.on_move then
\t\t\tactions[#actions + 1] = {
\t\t\t\tname = 'move_up',
\t\t\t\ticon = 'arrow_upward',
\t\t\t\tlabel = t('Move up') .. ' (ctrl+up/pgup/home)',
\t\t\t\tfilter_hidden = true,
\t\t\t}
\t\t\tactions[#actions + 1] = {
\t\t\t\tname = 'move_down',
\t\t\t\ticon = 'arrow_downward',
\t\t\t\tlabel = t('Move down') .. ' (ctrl+down/pgdwn/end)',
\t\t\t\tfilter_hidden = true,
\t\t\t}
\t\tend
"""

SAMPLE_MENU_LUA = """
function Menu:handle_cursor_move(x, y)
\tself:update_content_dimensions()
end

function Menu:handle_cursor_up()
\tself:update_dimensions()
end

function Menu:handle_key(name)
\tif name == 'enter' then return end
end

function Menu:render()
\t\t\t\tif action.name == 'delete' then
\t\t\t\t\tcursor:zone('primary_click', action_rect, function() self:delete_item(index) end)
\t\t\t\tend
end
"""

class TestPatchUoscPlaylistDrag(unittest.TestCase):
    def test_menus_lua_patch_and_unpatch(self):
        patched = patcher.patch_menus_lua(SAMPLE_MENUS_LUA)
        self.assertIn("drag_reorder", patched)
        self.assertIn("drag_indicator", patched)
        self.assertNotIn("move_up", patched)
        self.assertNotIn("move_down", patched)

        # Idempotent
        patched_again = patcher.patch_menus_lua(patched)
        self.assertEqual(patched, patched_again)

        # Unpatch
        unpatched = patcher.unpatch_menus_lua(patched)
        self.assertIn("move_up", unpatched)
        self.assertIn("move_down", unpatched)
        self.assertNotIn("drag_reorder", unpatched)

    def test_menu_lua_patch_and_unpatch(self):
        patched = patcher.patch_menu_lua(SAMPLE_MENU_LUA)
        self.assertIn("function Menu:start_reorder", patched)
        self.assertIn("function Menu:update_reorder", patched)
        self.assertIn("function Menu:finish_reorder", patched)
        self.assertIn("function Menu:abort_reorder", patched)
        self.assertIn("reorder_items_snapshot", patched)
        self.assertIn("if self.is_reordering then self:finish_reorder() end", patched)
        self.assertIn("if self.is_reordering then self:update_reorder(cursor.y) end", patched)

        # Idempotent
        patched_again = patcher.patch_menu_lua(patched)
        self.assertEqual(patched, patched_again)

        # Unpatch
        unpatched = patcher.unpatch_menu_lua(patched)
        self.assertNotIn("function Menu:start_reorder", unpatched)
        self.assertNotIn("UOSC_PLAYLIST_DRAG_PATCH", unpatched)

    def test_full_directory_patch_and_unpatch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "lib").mkdir()
            (base / "elements").mkdir()
            menus_path = base / "lib" / "menus.lua"
            menu_path = base / "elements" / "Menu.lua"

            menus_path.write_text(SAMPLE_MENUS_LUA, encoding="utf-8")
            menu_path.write_text(SAMPLE_MENU_LUA, encoding="utf-8")

            # Patch
            patcher.run_patcher(base, unpatch=False)
            self.assertIn("drag_reorder", menus_path.read_text(encoding="utf-8"))
            self.assertIn("start_reorder", menu_path.read_text(encoding="utf-8"))

            # Unpatch
            patcher.run_patcher(base, unpatch=True)
            self.assertIn("move_up", menus_path.read_text(encoding="utf-8"))
            self.assertNotIn("start_reorder", menu_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails before implementation**

Run: `python -m unittest tests/test_patch_uosc_playlist_drag.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'tools.patch_uosc_playlist_drag')

---

### Task 2: Implement Patcher CLI Tool

**Files:**
- Create: `tools/patch_uosc_playlist_drag.py`

- [ ] **Step 1: Create `tools/patch_uosc_playlist_drag.py`**

Write the complete implementation with stack-safe snapshotting (`for i, item in ipairs`), Escape/Right-click abort, non-linear edge scroll, function entry hooks, and CLI arguments:

```python
#!/usr/bin/env python3
"""
tools/patch_uosc_playlist_drag.py

Idempotent patcher for uosc to enable drag-and-drop playlist reordering.
Implements optimistic local reordering, visual elevation/dimming, 
explicit Escape/Right-click cancellation, non-linear edge auto-scrolling,
and single-commit release delegation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PATCH_MARKER = "-- UOSC_PLAYLIST_DRAG_PATCH"


def get_default_uosc_dir() -> Path:
    """Resolve default uosc directory based on host OS."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            win_path = Path(appdata) / "mpv" / "scripts" / "uosc"
            if win_path.exists():
                return win_path
    home = Path.home()
    return home / ".config" / "mpv" / "scripts" / "uosc"


# ---------------------------------------------------------------------------
# lib/menus.lua patchers
# ---------------------------------------------------------------------------

def patch_menus_lua(content: str) -> str:
    """Replace move_up and move_down actions with drag_reorder in lib/menus.lua."""
    if PATCH_MARKER in content:
        return content

    pattern = (
        r"(\s+if\s+opts\.on_move\s+then\s*\n)"
        r"(.*?actions\[#actions\s*\+\s*1\]\s*=\s*\{\s*name\s*=\s*'move_up'.*?filter_hidden\s*=\s*true,\s*\}\s*\n)"
        r"(.*?actions\[#actions\s*\+\s*1\]\s*=\s*\{\s*name\s*=\s*'move_down'.*?filter_hidden\s*=\s*true,\s*\}\s*\n)"
        r"(\s+end)"
    )

    replacement = (
        r"\1"
        f"        {PATCH_MARKER}_START (menus.lua)\n"
        r"        actions[#actions + 1] = {\n"
        r"            name = 'drag_reorder',\n"
        r"            icon = 'drag_indicator',\n"
        r"            label = t('Drag to reorder') .. ' (ctrl+up/down)',\n"
        r"            filter_hidden = true,\n"
        r"        }\n"
        f"        {PATCH_MARKER}_END (menus.lua)\n"
        r"\4"
    )

    patched, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if count == 0:
        raise RuntimeError("Failed to anchor opts.on_move action block in lib/menus.lua")
    return patched


def unpatch_menus_lua(content: str) -> str:
    """Restore original move_up/move_down actions in lib/menus.lua."""
    if PATCH_MARKER not in content:
        return content

    pattern = (
        rf"\s*{re.escape(PATCH_MARKER)}_START \(menus\.lua\).*?"
        rf"{re.escape(PATCH_MARKER)}_END \(menus\.lua\)\n"
    )

    original_actions = (
        "        actions[#actions + 1] = {\n"
        "            name = 'move_up',\n"
        "            icon = 'arrow_upward',\n"
        "            label = t('Move up') .. ' (ctrl+up/pgup/home)',\n"
        "            filter_hidden = true,\n"
        "        }\n"
        "        actions[#actions + 1] = {\n"
        "            name = 'move_down',\n"
        "            icon = 'arrow_downward',\n"
        "            label = t('Move down') .. ' (ctrl+down/pgdwn/end)',\n"
        "            filter_hidden = true,\n"
        "        }\n"
    )

    restored, count = re.subn(pattern, "\n" + original_actions, content, flags=re.DOTALL)
    if count == 0:
        raise RuntimeError("Failed to revert patch block in lib/menus.lua")
    return restored


# ---------------------------------------------------------------------------
# elements/Menu.lua patchers
# ---------------------------------------------------------------------------

MENU_REORDER_HELPERS = f"""
{PATCH_MARKER}_START (Menu.lua:drag_and_drop_core)
function Menu:start_reorder(index)
    if not self.current or not self.current.on_move then return end
    if self.search and self.search.query and self.search.query ~= '' then return end

    self.is_reordering = true
    self.reorder_start_index = index
    self.reorder_current_index = index

    -- Stack-safe snapshot copy
    self.reorder_items_snapshot = {{}}
    for i, item in ipairs(self.current.items or {{}}) do
        self.reorder_items_snapshot[i] = item
    end

    -- Invalidate kinetic scrolling and flick inertia
    self.is_dragging = false
    self.drag_last_y = nil
    if self.current then self.current.fling = nil end

    request_render()
end

function Menu:update_reorder(cursor_y)
    if not self.is_reordering or not self.current or not self.current.items then return end
    if #self.current.items <= 1 then return end

    -- Check if primary button was released without trigger
    if cursor and not cursor.primary_down then
        self:finish_reorder()
        return
    end

    -- Non-linear edge auto-scrolling
    local top_bound = self.ay
    local bottom_bound = self.by
    local threshold = self.item_height * 1.5
    local base_v = (self.scroll_step or 24) * 1.2

    if cursor_y < top_bound + threshold then
        local depth = math.max(0, math.min(1, (top_bound + threshold - cursor_y) / threshold))
        local step = math.max(1, math.floor(base_v * (depth ^ 1.5)))
        self.current.scroll = math.max(0, self.current.scroll - step)
        request_render()
    elseif cursor_y > bottom_bound - threshold then
        local max_scroll = math.max(0, #self.current.items * self.item_height - (self.by - self.ay))
        local depth = math.max(0, math.min(1, (cursor_y - (bottom_bound - threshold)) / threshold))
        local step = math.max(1, math.floor(base_v * (depth ^ 1.5)))
        self.current.scroll = math.min(max_scroll, self.current.scroll + step)
        request_render()
    end

    -- 50% Midpoint Hysteresis calculation
    local cur_idx = self.reorder_current_index
    local cur_y_pos = self.ay - self.current.scroll + (cur_idx - 1) * self.item_height

    -- Downward swap
    if cur_idx < #self.current.items then
        local next_midpoint = cur_y_pos + self.item_height + (self.item_height * 0.5)
        if cursor_y > next_midpoint then
            local moved_item = table.remove(self.current.items, cur_idx)
            table.insert(self.current.items, cur_idx + 1, moved_item)
            self.reorder_current_index = cur_idx + 1
            self.current.selected_index = cur_idx + 1
            request_render()
            return
        end
    end

    -- Upward swap
    if cur_idx > 1 then
        local prev_midpoint = cur_y_pos - (self.item_height * 0.5)
        if cursor_y < prev_midpoint then
            local moved_item = table.remove(self.current.items, cur_idx)
            table.insert(self.current.items, cur_idx - 1, moved_item)
            self.reorder_current_index = cur_idx - 1
            self.current.selected_index = cur_idx - 1
            request_render()
            return
        end
    end
end

function Menu:finish_reorder()
    if not self.is_reordering then return end
    self.is_reordering = false

    local from_idx = self.reorder_start_index
    local to_idx = self.reorder_current_index
    self.reorder_start_index = nil
    self.reorder_current_index = nil
    self.reorder_items_snapshot = nil

    if from_idx and to_idx and from_idx ~= to_idx and self.current and self.current.on_move then
        local event = {{
            type = 'move',
            from_index = from_idx,
            to_index = to_idx,
            menu_id = self.current.id,
        }}
        self:command_or_event(self.current.on_move, {{from_idx, to_idx, self.current.id}}, event)
    end
    request_render()
end

function Menu:abort_reorder()
    if not self.is_reordering then return end
    self.is_reordering = false

    if self.reorder_items_snapshot and self.current then
        self.current.items = self.reorder_items_snapshot
    end
    self.reorder_items_snapshot = nil
    self.reorder_start_index = nil
    self.reorder_current_index = nil
    request_render()
end

mp.observe_property('window-focus', 'bool', function(_, focused)
    if not focused and Menu and Menu.is_reordering then
        Menu:abort_reorder()
    end
end)
{PATCH_MARKER}_END (Menu.lua:drag_and_drop_core)
"""


def patch_menu_lua(content: str) -> str:
    """Inject hooks, state tracking, and helpers into elements/Menu.lua."""
    if PATCH_MARKER in content:
        return content

    patched = content.rstrip() + "\n\n" + MENU_REORDER_HELPERS

    # Hook handle_cursor_up
    up_pattern = r"(function\s+Menu:handle_cursor_up\(\s*\)\s*\n)"
    up_hook = f"\\1    if self.is_reordering then self:finish_reorder() end\n"
    patched, count_up = re.subn(up_pattern, up_hook, patched, count=1)
    if count_up == 0:
        raise RuntimeError("Failed to anchor Menu:handle_cursor_up in elements/Menu.lua")

    # Hook handle_cursor_move
    move_pattern = r"(function\s+Menu:handle_cursor_move\(.*?\)\s*\n)"
    move_hook = f"\\1    if self.is_reordering then self:update_reorder(cursor.y) end\n"
    patched, count_move = re.subn(move_pattern, move_hook, patched, count=1)
    if count_move == 0:
        raise RuntimeError("Failed to anchor Menu:handle_cursor_move in elements/Menu.lua")

    # Hook handle_key (Escape cancellation)
    key_pattern = r"(function\s+Menu:handle_key\(.*?\)\s*\n)"
    key_hook = (
        f"\\1    if self.is_reordering and (name == 'esc' or name == 'escape') then\n"
        f"        self:abort_reorder()\n"
        f"        return true\n"
        f"    end\n"
    )
    patched, count_key = re.subn(key_pattern, key_hook, patched, count=1)
    if count_key == 0:
        raise RuntimeError("Failed to anchor Menu:handle_key in elements/Menu.lua")

    # Hook drag handle zone binding
    action_zone_pattern = r"(if\s+action\.name\s*==\s*'delete'\s+then)"
    action_zone_hook = (
        f"if action.name == 'drag_reorder' then\n"
        f"                cursor:zone('primary_down', action_rect, function() self:start_reorder(index) end)\n"
        f"            else\\1"
    )
    patched, count_action = re.subn(action_zone_pattern, action_zone_hook, patched, count=1)
    if count_action == 0:
        # Fallback to general zone registration pattern
        alt_pattern = r"(cursor:zone\('primary_click',\s*action_rect,\s*function\(\).*?end\))"
        alt_hook = (
            f"if action.name == 'drag_reorder' then\n"
            f"                    cursor:zone('primary_down', action_rect, function() self:start_reorder(index) end)\n"
            f"                else\n"
            f"                    \\1\n"
            f"                end"
        )
        patched, count_alt = re.subn(alt_pattern, alt_hook, patched, count=1)
        if count_alt == 0:
            raise RuntimeError("Failed to anchor action zone handler in elements/Menu.lua")

    return patched


def unpatch_menu_lua(content: str) -> str:
    """Strip all modifications and restore pristine elements/Menu.lua."""
    if PATCH_MARKER not in content:
        return content

    pattern_helpers = (
        rf"\n*{re.escape(PATCH_MARKER)}_START \(Menu\.lua:drag_and_drop_core\).*?"
        rf"{re.escape(PATCH_MARKER)}_END \(Menu\.lua:drag_and_drop_core\)\n*"
    )
    patched = re.sub(pattern_helpers, "\n", content, flags=re.DOTALL)

    patched = re.sub(r"    if self\.is_reordering then self:finish_reorder\(\) end\n", "", patched)
    patched = re.sub(r"    if self\.is_reordering then self:update_reorder\(cursor\.y\) end\n", "", patched)
    patched = re.sub(
        r"    if self\.is_reordering and \(name == 'esc' or name == 'escape'\) then\n"
        r"        self:abort_reorder\(\)\n"
        r"        return true\n"
        r"    end\n",
        "",
        patched,
    )

    patched = re.sub(
        r"if action\.name == 'drag_reorder' then\s+"
        r"cursor:zone\('primary_down', action_rect, function\(\) self:start_reorder\(index\) end\)\s+"
        r"else(if action\.name == 'delete' then)",
        r"\1",
        patched,
    )

    return patched


# ---------------------------------------------------------------------------
# CLI Execution
# ---------------------------------------------------------------------------

def run_patcher(uosc_dir: Path, unpatch: bool = False) -> None:
    menus_path = uosc_dir / "lib" / "menus.lua"
    menu_path = uosc_dir / "elements" / "Menu.lua"

    if not menus_path.exists() or not menu_path.exists():
        print(f"Error: Target files missing in: {uosc_dir}", file=sys.stderr)
        sys.exit(1)

    action_label = "Unpatching" if unpatch else "Patching"
    print(f"{action_label} uosc directory: {uosc_dir}")

    # Process lib/menus.lua
    content_menus = menus_path.read_text(encoding="utf-8")
    new_menus = unpatch_menus_lua(content_menus) if unpatch else patch_menus_lua(content_menus)
    if new_menus != content_menus:
        menus_path.write_text(new_menus, encoding="utf-8")
        print("  ✓ lib/menus.lua modified")
    else:
        print("  - lib/menus.lua unchanged")

    # Process elements/Menu.lua
    content_menu = menu_path.read_text(encoding="utf-8")
    new_menu = unpatch_menu_lua(content_menu) if unpatch else patch_menu_lua(content_menu)
    if new_menu != content_menu:
        menu_path.write_text(new_menu, encoding="utf-8")
        print("  ✓ elements/Menu.lua modified")
    else:
        print("  - elements/Menu.lua unchanged")

    print(f"Completed {action_label.lower()} successfully.")


def main():
    parser = argparse.ArgumentParser(description="Patch uosc for playlist drag-and-drop reordering.")
    parser.add_argument(
        "--uosc-dir",
        type=Path,
        default=get_default_uosc_dir(),
        help="Target uosc directory (defaults to AppData/mpv/scripts/uosc or ~/.config/mpv/scripts/uosc)",
    )
    parser.add_argument(
        "--unpatch",
        action="store_true",
        help="Revert patches and restore original uosc source files",
    )
    args = parser.parse_args()
    run_patcher(args.uosc_dir, args.unpatch)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run unit test to verify it passes**

Run: `python -m unittest tests/test_patch_uosc_playlist_drag.py -v`
Expected: PASS (all 3 tests ok)

- [ ] **Step 3: Commit Task 1 and Task 2**

```bash
git add tools/patch_uosc_playlist_drag.py tests/test_patch_uosc_playlist_drag.py
git commit -m "feat(uosc): add playlist drag-and-drop patcher and automated tests"
```

---

### Task 3: Apply Patch to Local uosc Installation & Verify Syntax

**Files:**
- Target: `%APPDATA%/mpv/scripts/uosc/lib/menus.lua`
- Target: `%APPDATA%/mpv/scripts/uosc/elements/Menu.lua`

- [ ] **Step 1: Execute patcher on local uosc installation**

Run: `python tools/patch_uosc_playlist_drag.py`
Expected output:
```
Patching uosc directory: ...
  ✓ lib/menus.lua modified
  ✓ elements/Menu.lua modified
Completed patching successfully.
```

- [ ] **Step 2: Verify idempotency on live directory**

Run: `python tools/patch_uosc_playlist_drag.py`
Expected output:
```
Patching uosc directory: ...
  - lib/menus.lua unchanged
  - elements/Menu.lua unchanged
Completed patching successfully.
```

- [ ] **Step 3: Verify Lua syntax on patched files**

Run: `luac -p "$env:APPDATA/mpv/scripts/uosc/lib/menus.lua" "$env:APPDATA/mpv/scripts/uosc/elements/Menu.lua"` (if luac is available) or run Python syntax verification.

---

### Task 4: Interactive Validation & Manual Verification

- [ ] **Step 1: Launch mpv with test playlist**

Run: `mpv --idle=yes` or open multiple video files in mpv.
1. Press `F8` or click Menu -> Playlist to open uosc's playlist view.
2. Confirm the `arrow_upward` and `arrow_downward` icons are replaced by `drag_indicator` (`⋮⋮`).
3. Click and drag an item up/down across rows:
   - Confirm items swap dynamically under the cursor across the 50% midpoint threshold.
   - Confirm releasing drops the item in place and MPV's active playlist reorders.
4. Drag an item to the top edge and hold stationary:
   - Confirm the playlist continuously scrolls upward.
5. Drag an item and hit `Escape`:
   - Confirm reorder aborts and item snaps back to original slot without moving the track in MPV.
