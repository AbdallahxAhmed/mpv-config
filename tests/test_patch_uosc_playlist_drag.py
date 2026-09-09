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
        self.assertIn("name == 'esc' or name == 'escape'", patched)

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
