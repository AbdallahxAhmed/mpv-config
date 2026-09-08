import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('gui_upgrade', ROOT / 'tools/apply_youtube_gui.py')
gui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gui)

class GuiUpgrade(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'script-opts/uosc.conf'
        self.path.parent.mkdir()
        self.raw = ('# Personal note\ncontrols=' + gui.OLD_CONTROLS + '\ncontrols_size=32\n'
                    'controls_spacing=2\nlanguages=slang,en\nrefine=\n').encode()
        self.path.write_bytes(self.raw)
        for name in gui.REQUIRED_SCRIPTS:
            script = self.root / name
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text('-- Presence fixture; never executed by the updater.\n')

    def test_preview_has_no_writes(self):
        changes, backup = gui.upgrade(self.root)
        self.assertIn('controls', changes)
        self.assertIsNone(backup)
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_apply_backup_and_idempotence(self):
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertEqual(backup.read_bytes(), self.raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())
        self.assertIn(b'languages=slang,en\nrefine=\n', self.path.read_bytes())
        before = set(self.path.parent.iterdir())
        self.assertEqual(gui.upgrade(self.root, apply=True), ([], None))
        self.assertEqual(set(self.path.parent.iterdir()), before)

    def test_custom_toolbar_is_not_overwritten(self):
        custom = b'controls=menu,fullscreen\n'
        self.path.write_bytes(custom)
        with self.assertRaises(ValueError):
            gui.upgrade(self.root, apply=True)
        self.assertEqual(self.path.read_bytes(), custom)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_custom_size_and_missing_settings_are_preserved(self):
        raw = self.raw.replace(b'controls_size=32', b'controls_size=57')
        updated, changes = gui.plan(raw)
        self.assertIn(b'controls_size=57', updated)
        self.assertNotIn('controls_size', changes)
        self.assertNotIn(b'menu_padding=', updated)

    def test_duplicate_settings_are_rejected(self):
        for extra in ('controls=' + gui.OLD_CONTROLS, 'controls_size=32'):
            with self.assertRaises(ValueError):
                gui.plan(self.raw + extra.encode() + b'\n')

    def test_bom_crlf_and_notes_are_preserved(self):
        raw = b'\xef\xbb\xbf' + self.raw.replace(b'\n', b'\r\n')
        updated, changes = gui.plan(raw)
        self.assertTrue(updated.startswith(b'\xef\xbb\xbf# Personal note\r\n'))
        self.assertNotIn(b'\n', updated.replace(b'\r\n', b''))
        self.assertIn('controls', changes)

    def test_symlink_is_rejected(self):
        target = self.root / 'elsewhere.conf'
        target.write_bytes(self.raw)
        self.path.unlink()
        try:
            self.path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation is unavailable on this system')
        with self.assertRaises(ValueError):
            gui.upgrade(self.root, apply=True)
        self.assertEqual(target.read_bytes(), self.raw)

    def test_failed_replace_keeps_original_and_backup(self):
        with mock.patch.object(gui.os, 'replace', side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError):
                gui.upgrade(self.root, apply=True)
        self.assertEqual(self.path.read_bytes(), self.raw)
        backups = list(self.path.parent.glob('*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.raw)
        self.assertEqual(list(self.path.parent.glob('.uosc-youtube-*')), [])

    def test_repository_toolbar_matches_upgrade(self):
        text = (ROOT / 'config/script-opts/uosc.conf').read_text(encoding='utf-8')
        controls = [line.partition('=')[2] for line in text.splitlines() if line.startswith('controls=')]
        self.assertEqual(controls, [gui.NEW_CONTROLS])

    def test_previous_youtube_toolbar_is_upgraded(self):
        raw = self.raw.replace(gui.OLD_CONTROLS.encode(), gui.PREVIOUS_CONTROLS.encode())
        self.path.write_bytes(raw)
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertIn('controls', changes)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())

    def test_icon_first_v1_toolbar_is_upgraded(self):
        raw = self.raw.replace(gui.OLD_CONTROLS.encode(), gui.ICON_FIRST_V1_CONTROLS.encode())
        self.path.write_bytes(raw)
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertIn('controls', changes)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())

    def test_icon_first_v2_toolbar_is_upgraded(self):
        raw = self.raw.replace(gui.OLD_CONTROLS.encode(), gui.ICON_FIRST_V2_CONTROLS.encode())
        self.path.write_bytes(raw)
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertIn('controls', changes)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())

    def test_icon_first_v3_toolbar_is_upgraded(self):
        raw = self.raw.replace(gui.OLD_CONTROLS.encode(), gui.ICON_FIRST_V3_CONTROLS.encode())
        self.path.write_bytes(raw)
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertIn('controls', changes)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())

    def test_icon_first_v4_toolbar_is_upgraded(self):
        raw = self.raw.replace(gui.OLD_CONTROLS.encode(), gui.ICON_FIRST_V4_CONTROLS.encode())
        self.path.write_bytes(raw)
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertIn('controls', changes)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())

    def test_icon_first_v5_toolbar_is_upgraded(self):
        raw = self.raw.replace(gui.OLD_CONTROLS.encode(), gui.ICON_FIRST_V5_CONTROLS.encode())
        self.path.write_bytes(raw)
        changes, backup = gui.upgrade(self.root, apply=True)
        self.assertIn('controls', changes)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertIn(gui.NEW_CONTROLS.encode(), self.path.read_bytes())

    def test_missing_scripts_block_apply_without_writes(self):
        (self.root / 'scripts/player-toolbar.lua').unlink()
        before = set(self.path.parent.iterdir())
        self.assertIn('controls', gui.upgrade(self.root)[0])
        with self.assertRaisesRegex(ValueError, 'Update GUI scripts'):
            gui.upgrade(self.root, apply=True)
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(set(self.path.parent.iterdir()), before)

    def test_toolbar_is_mouse_first_and_fullscreen_is_rightmost(self):
        items = gui.NEW_CONTROLS.split(',')
        self.assertEqual(items[-2:], ['space', 'fullscreen'])
        self.assertEqual(items.count('space'), 1)
        self.assertEqual(items.count('fullscreen'), 1)
        self.assertIn('command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions', items)
        self.assertIn('button:audio-tracks', items)
        self.assertIn('button:stable-volume', items)
        self.assertIn('loop-file', items)
        self.assertIn('<stream>button:stream-quality', items)
        self.assertIn('<stream>button:download-video', items)
        self.assertNotIn('keypress', gui.NEW_CONTROLS)
        self.assertNotIn('#audio', gui.NEW_CONTROLS)

if __name__ == '__main__':
    unittest.main()
