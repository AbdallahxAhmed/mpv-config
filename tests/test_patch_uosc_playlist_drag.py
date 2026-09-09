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
\t\tfunction handle_event(event)
\t\t\tif event.type == 'activate' then
\t\t\t\topts.on_activate(event)
\t\t\telseif event.type == 'key' then
\t\t\t\topts.on_key(event)
\t\t\tend
\t\tend
"""

SAMPLE_MENU_LUA = """
function Menu:on_global_mouse_move()
\tself:update_content_dimensions()
end

function Menu:handle_cursor_up(shortcut)
\tself:update_dimensions()
end

function Menu:handle_shortcut(shortcut, info)
\tif shortcut.key == 'enter' then return end
end

function Menu:render()
\tlocal highlight_opacity = 0 + (item.active and 0.8 or 0) + (is_selected and 0.15 or 0)
\tcursor:zone('primary_click', rect, self:create_action(function(shortcut)
\t\tself:activate_selected_item(shortcut, true)
\tend))
end

return Menu
"""


class TestPatchUoscPlaylistDrag(unittest.TestCase):
    def test_menus_lua_patch_and_unpatch(self):
        patched = patcher.patch_menus_lua(SAMPLE_MENUS_LUA)
        self.assertIn("drag_reorder", patched)
        self.assertIn("drag_indicator", patched)
        self.assertNotIn("move_up", patched)
        self.assertNotIn("move_down", patched)
        self.assertIn("elseif event.type == 'move' and opts.on_move then", patched)
        self.assertIn("opts.on_move(event)", patched)

        # Idempotent
        patched_again = patcher.patch_menus_lua(patched)
        self.assertEqual(patched, patched_again)

        # Unpatch
        unpatched = patcher.unpatch_menus_lua(patched)
        self.assertIn("move_up", unpatched)
        self.assertIn("move_down", unpatched)
        self.assertNotIn("drag_reorder", unpatched)
        self.assertNotIn("elseif event.type == 'move' and opts.on_move then", unpatched)

    def test_menu_lua_patch_and_unpatch(self):
        patched = patcher.patch_menu_lua(SAMPLE_MENU_LUA)
        self.assertIn("function Menu:start_reorder", patched)
        self.assertIn("function Menu:update_reorder", patched)
        self.assertIn("function Menu:finish_reorder", patched)
        self.assertIn("function Menu:abort_reorder", patched)
        self.assertIn("reorder_items_snapshot", patched)
        self.assertIn("if self.is_reordering then", patched)
        self.assertIn("self:finish_reorder()", patched)
        self.assertIn("self:update_reorder(cursor.y)", patched)
        self.assertIn("self.drag_last_y = nil", patched)
        self.assertIn("shortcut.key == 'esc' or shortcut.id == 'esc'", patched)
        self.assertIn("self.reorder_current_index == index", patched)

        # Idempotent
        patched_again = patcher.patch_menu_lua(patched)
        self.assertEqual(patched, patched_again)

        # Unpatch
        unpatched = patcher.unpatch_menu_lua(patched)
        self.assertNotIn("function Menu:start_reorder", unpatched)
        self.assertNotIn("UOSC_PLAYLIST_DRAG_PATCH", unpatched)
        self.assertNotIn("self.drag_last_y = nil", unpatched)
        self.assertNotIn("self.reorder_current_index == index", unpatched)

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
            self.assertIn("opts.on_move(event)", menus_path.read_text(encoding="utf-8"))

            # Unpatch
            patcher.run_patcher(base, unpatch=True)
            self.assertIn("move_up", menus_path.read_text(encoding="utf-8"))
            self.assertNotIn("start_reorder", menu_path.read_text(encoding="utf-8"))
            self.assertNotIn("opts.on_move(event)", menus_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
