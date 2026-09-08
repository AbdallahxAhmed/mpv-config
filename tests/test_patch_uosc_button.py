import os
import pathlib
import shutil
import tempfile
import unittest

from tools.patch_uosc_button import (
    MANAGED_TARGET,
    MANAGED_REPLACEMENT,
    PATCH_MARKER,
    patch_managed_button,
    patch_button,
)

SAMPLE_MANAGED_BUTTON = """
local Button = require('elements/Button')
local ManagedButton = class(Button)

function ManagedButton:update(data)
	local hide_before = self.hide
	for _, prop in ipairs({'icon', 'active', 'badge', 'command', 'tooltip', 'hide'}) do
		self[prop] = data[prop]
	end
	self.is_clickable = self.command ~= nil
end

return ManagedButton
"""

SAMPLE_BUTTON = """
local Button = class(Element)

function Button:render()
	local ass = assdraw.ass_new()
	ass:icon(x, y, self.font_size, self.icon, {
		color = foreground,
	})

	return ass
end

return Button
"""


class TestPatchUoscButton(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.elements_dir = pathlib.Path(self.temp_dir) / "elements"
        self.elements_dir.mkdir(parents=True, exist_ok=True)
        self.managed_file = self.elements_dir / "ManagedButton.lua"
        self.button_file = self.elements_dir / "Button.lua"
        self.managed_file.write_text(SAMPLE_MANAGED_BUTTON, encoding="utf-8")
        self.button_file.write_text(SAMPLE_BUTTON, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_patch_and_idempotency_managed_button(self):
        # Initial patch
        self.assertTrue(patch_managed_button(self.managed_file))
        content = self.managed_file.read_text(encoding="utf-8")
        self.assertIn(MANAGED_REPLACEMENT, content)

        # Idempotent re-run
        self.assertTrue(patch_managed_button(self.managed_file))
        content_again = self.managed_file.read_text(encoding="utf-8")
        self.assertEqual(content, content_again)

    def test_patch_and_idempotency_button(self):
        # Initial patch
        self.assertTrue(patch_button(self.button_file))
        content = self.button_file.read_text(encoding="utf-8")
        self.assertIn(PATCH_MARKER, content)
        self.assertIn("self.progress", content)
        self.assertIn("return ass", content)

        # Idempotent re-run
        self.assertTrue(patch_button(self.button_file))
        content_again = self.button_file.read_text(encoding="utf-8")
        self.assertEqual(content, content_again)

    def test_unpatch(self):
        patch_managed_button(self.managed_file)
        patch_button(self.button_file)

        # Unpatch
        self.assertTrue(patch_managed_button(self.managed_file, unpatch=True))
        self.assertTrue(patch_button(self.button_file, unpatch=True))

        content_m = self.managed_file.read_text(encoding="utf-8")
        content_b = self.button_file.read_text(encoding="utf-8")

        self.assertIn(MANAGED_TARGET, content_m)
        self.assertNotIn(MANAGED_REPLACEMENT, content_m)
        self.assertNotIn(PATCH_MARKER, content_b)


if __name__ == "__main__":
    unittest.main()
