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

if __name__ == '__main__':
    unittest.main()
