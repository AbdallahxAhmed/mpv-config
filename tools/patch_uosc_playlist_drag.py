#!/usr/bin/env python3
"""
tools/patch_uosc_playlist_drag.py

Idempotent patcher for uosc to enable drag-and-drop playlist reordering.
Implements YouTube Music-style free drag-and-drop, optimistic local reordering,
selection lock & hover isolation (preventing text/handle disappearance),
elevated card styling with 2px accent border, explicit Escape/Right-click cancellation,
continuous 60 FPS non-linear edge auto-scrolling, and single-commit release delegation.
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
    """Replace move_up and move_down actions with drag_reorder and hook move callback in lib/menus.lua."""
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
        f"        {PATCH_MARKER}_START (menus.lua:actions)\n"
        r"        actions[#actions + 1] = {\n"
        r"            name = 'drag_reorder',\n"
        r"            icon = 'drag_indicator',\n"
        r"            label = t('Drag to reorder') .. ' (ctrl+up/down)',\n"
        r"            filter_hidden = true,\n"
        r"        }\n"
        f"        {PATCH_MARKER}_END (menus.lua:actions)\n"
        r"\4"
    )

    patched, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if count == 0:
        raise RuntimeError("Failed to anchor opts.on_move action block in lib/menus.lua")

    # Hook event.type == 'move' callback delegation if present
    move_cb_pattern = r"(\s+)(elseif\s+event\.type\s*==\s*'key'\s+then)"
    if re.search(move_cb_pattern, patched):
        move_cb_hook = (
            r"\1" f"{PATCH_MARKER}_START (menus.lua:on_move)\n"
            r"\1elseif event.type == 'move' and opts.on_move then\n"
            r"\1\topts.on_move(event)\n"
            r"\1\tmenu:select_index(event.to_index)\n"
            r"\1" f"{PATCH_MARKER}_END (menus.lua:on_move)\n"
            r"\1\2"
        )
        patched = re.sub(move_cb_pattern, move_cb_hook, patched, count=1)

    return patched


def unpatch_menus_lua(content: str) -> str:
    """Restore original move_up/move_down actions and remove callback hook in lib/menus.lua."""
    if PATCH_MARKER not in content:
        return content

    # 1. Remove move callback hook if present
    pattern_cb = (
        rf"\s*{re.escape(PATCH_MARKER)}_START \(menus\.lua:on_move\).*?"
        rf"{re.escape(PATCH_MARKER)}_END \(menus\.lua:on_move\)\n"
    )
    patched = re.sub(pattern_cb, "\n", content, flags=re.DOTALL)

    # 2. Restore actions
    pattern = (
        rf"\s*{re.escape(PATCH_MARKER)}_START \(menus\.lua:actions\).*?"
        rf"{re.escape(PATCH_MARKER)}_END \(menus\.lua:actions\)\n"
    )
    # Support backward compatibility with older patch marker format
    if not re.search(pattern, patched, flags=re.DOTALL):
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

    restored, count = re.subn(pattern, "\n" + original_actions, patched, flags=re.DOTALL)
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
    if not self.current.items or #self.current.items <= 1 then return end
    if not index or index < 1 or index > #self.current.items then return end
    if self.search and self.search.query and self.search.query ~= '' then return end

    self.is_reordering = true
    self.reorder_start_index = index
    self.reorder_current_index = index

    -- Stack-safe snapshot copy (avoid unpack C-stack overflow in LuaJIT)
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
    local menu = self.current
    if #menu.items <= 1 then return end

    local scroll_step = self.scroll_step or self.item_height or 24
    local top_bound = menu.top
    local bottom_bound = menu.top + menu.height
    local threshold = scroll_step * 1.5
    local base_v = scroll_step * 1.2

    -- Continuous non-linear edge auto-scrolling
    local is_edge_scrolling = false
    if cursor_y < top_bound + threshold and menu.scroll_y > 0 then
        local depth = math.max(0, math.min(1, (top_bound + threshold - cursor_y) / threshold))
        local step = math.max(1, math.floor(base_v * (depth ^ 1.5)))
        self:set_scroll_by(-step, menu.id)
        is_edge_scrolling = true
    elseif cursor_y > bottom_bound - threshold and menu.scroll_y < menu.scroll_height then
        local depth = math.max(0, math.min(1, (cursor_y - (bottom_bound - threshold)) / threshold))
        local step = math.max(1, math.floor(base_v * (depth ^ 1.5)))
        self:set_scroll_by(step, menu.id)
        is_edge_scrolling = true
    end

    if is_edge_scrolling then
        request_render()
    end

    -- Downward swap loop (50% midpoint hysteresis)
    while self.reorder_current_index < #menu.items do
        local cur_idx = self.reorder_current_index
        local cur_y_pos = menu.top - menu.scroll_y + scroll_step * (cur_idx - 1)
        local next_midpoint = cur_y_pos + scroll_step + (scroll_step * 0.5)
        if cursor_y > next_midpoint then
            local moved_item = table.remove(menu.items, cur_idx)
            table.insert(menu.items, cur_idx + 1, moved_item)
            self.reorder_current_index = cur_idx + 1
            menu.selected_index = cur_idx + 1
            request_render()
        else
            break
        end
    end

    -- Upward swap loop (50% midpoint hysteresis)
    while self.reorder_current_index > 1 do
        local cur_idx = self.reorder_current_index
        local cur_y_pos = menu.top - menu.scroll_y + scroll_step * (cur_idx - 1)
        local prev_midpoint = cur_y_pos - (scroll_step * 0.5)
        if cursor_y < prev_midpoint then
            local moved_item = table.remove(menu.items, cur_idx)
            table.insert(menu.items, cur_idx - 1, moved_item)
            self.reorder_current_index = cur_idx - 1
            menu.selected_index = cur_idx - 1
            request_render()
        else
            break
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
        self:select_index(to_idx, self.current.id)
        self:scroll_to_index(to_idx, self.current.id, true)
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
    local orig_idx = self.reorder_start_index
    self.reorder_start_index = nil
    self.reorder_current_index = nil
    if orig_idx and self.current then
        self:select_index(orig_idx, self.current.id)
    end
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

    if "return Menu" in content:
        patched = re.sub(r"(\nreturn\s+Menu[^\n]*\s*)$", "\n\n" + MENU_REORDER_HELPERS + r"\1", content.rstrip())
        if PATCH_MARKER not in patched:
            patched = re.sub(r"(\nreturn\s+Menu)", "\n\n" + MENU_REORDER_HELPERS + r"\1", content, count=1)
    else:
        patched = content.rstrip() + "\n\n" + MENU_REORDER_HELPERS

    # Hook Menu:handle_cursor_down (record drag start coordinates and initial index)
    down_pattern = r"(function\s+Menu:handle_cursor_down\s*\([^\)]*\)\s*\n)"
    down_hook = (
        r"\1    self.drag_start_y = cursor.y\n"
        r"    self.drag_start_index = self.mouse_hovered_index or (self.current and self.current.selected_index)\n"
    )
    patched, count_down = re.subn(down_pattern, down_hook, patched, count=1)
    if count_down == 0:
        raise RuntimeError("Failed to anchor Menu:handle_cursor_down in elements/Menu.lua")

    # Hook Menu:handle_cursor_up (finish reorder or clean up drag coordinates)
    up_pattern = r"(function\s+Menu:handle_cursor_up\s*\([^\)]*\)\s*\n)"
    up_hook = (
        r"\1    if self.is_reordering then\n"
        r"        self:finish_reorder()\n"
        r"        self.drag_last_y = nil\n"
        r"        self.drag_start_y = nil\n"
        r"        self.drag_start_index = nil\n"
        r"        self.is_dragging = false\n"
        r"        return\n"
        r"    end\n"
        r"    self.drag_start_y = nil\n"
        r"    self.drag_start_index = nil\n"
    )
    patched, count_up = re.subn(up_pattern, up_hook, patched, count=1)
    if count_up == 0:
        raise RuntimeError("Failed to anchor Menu:handle_cursor_up in elements/Menu.lua")

    # Hook Menu:on_global_mouse_move (free drag initiation >= 6px and active reorder updates)
    move_pattern = r"(function\s+Menu:on_global_mouse_move\s*\([^\)]*\)\s*\n)"
    move_hook = (
        r"\1    if self.is_reordering then\n"
        r"        self.drag_last_y = nil\n"
        r"        self.is_dragging = false\n"
        r"        self:update_reorder(cursor.y)\n"
        r"        return\n"
        r"    end\n"
        r"    if self.current and self.current.on_move and not (self.current.action_index) and self.drag_start_y and self.drag_start_index then\n"
        r"        if math.abs(cursor.y - self.drag_start_y) >= 6 then\n"
        r"            self:start_reorder(self.drag_start_index)\n"
        r"            self.drag_last_y = nil\n"
        r"            self.is_dragging = false\n"
        r"            self:update_reorder(cursor.y)\n"
        r"            return\n"
        r"        end\n"
        r"    end\n"
    )
    patched, count_move = re.subn(move_pattern, move_hook, patched, count=1)
    if count_move == 0:
        raise RuntimeError("Failed to anchor mouse move handler in elements/Menu.lua")

    # Hook Menu:handle_shortcut (Escape & Right-click cancellation)
    key_pattern = r"(function\s+Menu:handle_shortcut\s*\([^\)]*\)\s*\n)"
    key_hook = (
        r"\1    if self.is_reordering and (shortcut and (shortcut.key == 'esc' or shortcut.id == 'esc' or shortcut.id == 'mbtn_right')) then\n"
        r"        self:abort_reorder()\n"
        r"        return\n"
        r"    end\n"
    )
    patched, count_key = re.subn(key_pattern, key_hook, patched, count=1)
    if count_key == 0:
        raise RuntimeError("Failed to anchor key/shortcut handler in elements/Menu.lua")

    # Hook Menu:render (continuous edge auto-scroll tick)
    render_pattern = r"(function\s+Menu:render\s*\([^\)]*\)\s*\n)"
    render_hook = r"\1    if self.is_reordering then self:update_reorder(cursor.y) end\n"
    patched, count_render = re.subn(render_pattern, render_hook, patched, count=1)
    if count_render == 0:
        raise RuntimeError("Failed to anchor Menu:render in elements/Menu.lua")

    # Hook selection lock before item loop in draw_menu (locks selected_index to dragged item)
    for_loop_pattern = r"(\n\s*)(for\s+index\s*=\s*start_index,\s*end_index,\s*1\s+do)"
    for_loop_hook = (
        r"\1if self.is_reordering and is_current then\n"
        r"\1\tmenu.selected_index = self.reorder_current_index\n"
        r"\1\tself.mouse_hovered_index = self.reorder_current_index\n"
        r"\1\tmenu.action_index = nil\n"
        r"\1end"
        r"\1\2"
    )
    patched, count_for = re.subn(for_loop_pattern, for_loop_hook, patched, count=1)
    if count_for == 0:
        raise RuntimeError("Failed to anchor item for loop in elements/Menu.lua")

    # Hook hover item selection guard (prevent hover selection stealing during reorder)
    hover_item_pattern = r"(if\s+)(is_current\s+and\s+self\.mouse_nav\s*\n\s*and\s*\(submenu_is_hovered\s+or\s+get_point_to_rectangle_proximity)"
    patched, count_hover_item = re.subn(hover_item_pattern, r"\1not self.is_reordering and \2", patched, count=1)
    if count_hover_item == 0:
        raise RuntimeError("Failed to anchor hover item selection guard in elements/Menu.lua")

    # Hook hover action selection guard (prevent action selection stealing during reorder)
    hover_action_pattern = r"(if\s+)(self\.mouse_nav\s+and\s+get_point_to_rectangle_proximity\(cursor,\s*rect\)\s*<=\s*0\s+then)"
    patched, count_hover_act = re.subn(hover_action_pattern, r"\1not self.is_reordering and \2", patched, count=1)
    if count_hover_act == 0:
        raise RuntimeError("Failed to anchor hover action selection guard in elements/Menu.lua")

    # Hook drag handle direct grab zone binding
    action_zone_pattern = r"(cursor:zone\('primary_click',\s*rect,\s*self:create_action\(function\(shortcut\)\s*\n\s*self:activate_selected_item\(shortcut,\s*true\)\s*\n\s*end\)\))"
    action_zone_hook = (
        r"if action.name == 'drag_reorder' then\n"
        r"                            cursor:zone('primary_down', rect, function() self:start_reorder(index) end)\n"
        r"                        else\n"
        r"                            \1\n"
        r"                        end"
    )
    patched, count_action = re.subn(action_zone_pattern, action_zone_hook, patched, count=1)
    if count_action == 0:
        raise RuntimeError("Failed to anchor action zone handler in elements/Menu.lua")

    # Hook card elevation border
    ass_rect_pattern = r"(\s+ass:rect\(content_rect\.ax,\s*item_ay,\s*content_rect\.bx,\s*item_by,\s*\{\s*\n\s*radius\s*=\s*state\.radius,\s*\n\s*color\s*=\s*fg,)"
    ass_rect_hook = (
        r"\1\n"
        r"\t\t\t\t\tborder = (self.is_reordering and self.reorder_current_index == index) and math.max(1, round(2 * state.scale)) or nil,\n"
        r"\t\t\t\t\tborder_color = fg,"
    )
    patched, count_border = re.subn(ass_rect_pattern, ass_rect_hook, patched, count=1)
    if count_border == 0:
        raise RuntimeError("Failed to anchor ass:rect border in elements/Menu.lua")

    # Hook visual highlight opacity (moderate fill opacity to keep text contrast crisp)
    highlight_pattern = r"(local\s+highlight_opacity\s*=\s*0\s*\+\s*\(item\.active\s+and\s+0\.8\s+or\s+0\)\s*\+\s*\(is_selected\s+and\s+0\.15\s+or\s+0\))"
    if re.search(highlight_pattern, patched):
        highlight_hook = r"\1 + ((self.is_reordering and self.reorder_current_index == index) and 0.20 or 0)"
        patched = re.sub(highlight_pattern, highlight_hook, patched, count=1)

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

    # Revert Menu:handle_cursor_down
    patched = re.sub(
        r"    self\.drag_start_y = cursor\.y\n"
        r"    self\.drag_start_index = self\.mouse_hovered_index or \(self\.current and self\.current\.selected_index\)\n",
        "",
        patched,
    )

    # Revert Menu:handle_cursor_up
    patched = re.sub(
        r"    if self\.is_reordering then\n\s+self:finish_reorder\(\)\n\s+self\.drag_last_y = nil\n\s+self\.drag_start_y = nil\n\s+self\.drag_start_index = nil\n\s+self\.is_dragging = false\n\s+return\n\s+end\n\s+self\.drag_start_y = nil\n\s+self\.drag_start_index = nil\n",
        "",
        patched,
    )

    # Revert Menu:on_global_mouse_move
    patched = re.sub(
        r"    if self\.is_reordering then\n\s+self\.drag_last_y = nil\n\s+self\.is_dragging = false\n\s+self:update_reorder\(cursor\.y\)\n\s+return\n\s+end\n\s+if self\.current and self\.current\.on_move and not \(self\.current\.action_index\) and self\.drag_start_y and self\.drag_start_index then\n\s+if math\.abs\(cursor\.y - self\.drag_start_y\) >= 6 then\n\s+self:start_reorder\(self\.drag_start_index\)\n\s+self\.drag_last_y = nil\n\s+self\.is_dragging = false\n\s+self:update_reorder\(cursor\.y\)\n\s+return\n\s+end\n\s+end\n",
        "",
        patched,
    )

    # Revert Menu:handle_shortcut
    patched = re.sub(
        r"    if self\.is_reordering and \(shortcut and \(shortcut\.key == 'esc' or shortcut\.id == 'esc'(?: or shortcut\.id == 'mbtn_right')?\)\) then\n\s+self:abort_reorder\(\)\n\s+return\n\s+end\n",
        "",
        patched,
    )

    # Revert Menu:render
    patched = re.sub(r"    if self\.is_reordering then self:update_reorder\(cursor\.y\) end\n", "", patched)

    # Revert selection lock
    patched = re.sub(
        r"if self\.is_reordering and is_current then\n\s*menu\.selected_index = self\.reorder_current_index\n\s*self\.mouse_hovered_index = self\.reorder_current_index\n\s*menu\.action_index = nil\n\s*end\n\t*",
        "",
        patched,
    )

    # Revert hover guards
    patched = re.sub(
        r"if not self\.is_reordering and (is_current\s+and\s+self\.mouse_nav\s*\n\s*and\s*\(submenu_is_hovered\s+or\s+get_point_to_rectangle_proximity)",
        r"if \1",
        patched,
    )
    patched = re.sub(
        r"if not self\.is_reordering and (self\.mouse_nav\s+and\s+get_point_to_rectangle_proximity\(cursor,\s*rect\)\s*<=\s*0\s+then)",
        r"if \1",
        patched,
    )

    # Revert card elevation border
    patched = re.sub(
        r"\n\t+border = \(self\.is_reordering and self\.reorder_current_index == index\) and math\.max\(1, round\(2 \* state\.scale\)\) or nil,\n\t+border_color = fg,",
        "",
        patched,
    )

    # Revert highlight opacity
    patched = re.sub(
        r" \+ \(\(self\.is_reordering and self\.reorder_current_index == index\) and 0\.20 or 0\)",
        "",
        patched,
    )

    # Restore action zone
    patched = re.sub(
        r"if action\.name == 'drag_reorder' then\s+"
        r"cursor:zone\('primary_down', rect, function\(\) self:start_reorder\(index\) end\)\s+"
        r"else\s+"
        r"(cursor:zone\('primary_click', rect, self:create_action\(function\(shortcut\)\s+"
        r"self:activate_selected_item\(shortcut, true\)\s+"
        r"end\)\))\s+"
        r"end",
        r"\1",
        patched,
        flags=re.DOTALL,
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
        print("  [OK] lib/menus.lua modified")
    else:
        print("  [-] lib/menus.lua unchanged")

    # Process elements/Menu.lua
    content_menu = menu_path.read_text(encoding="utf-8")
    new_menu = unpatch_menu_lua(content_menu) if unpatch else patch_menu_lua(content_menu)
    if new_menu != content_menu:
        menu_path.write_text(new_menu, encoding="utf-8")
        print("  [OK] elements/Menu.lua modified")
    else:
        print("  [-] elements/Menu.lua unchanged")

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
