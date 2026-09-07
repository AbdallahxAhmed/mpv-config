import json
from pathlib import Path
import tempfile
import types
import unittest

from deploy.audit_log import AuditLog, LOG_SCHEMA_VERSION


class AuditLogIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name, '.audit-log.json')
        self.env = types.SimpleNamespace(os='linux', installed={})

    def test_corrupt_read_is_nonmutating_and_write_preserves_original(self):
        original = b'{broken json'
        self.path.write_bytes(original)
        log = AuditLog(str(self.path))
        self.assertEqual(log.get_packages_installed_by_us(), [])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        log.start_session('install', self.env)
        backups = list(self.path.parent.glob('.audit-log.json.corrupt.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertIsInstance(json.loads(self.path.read_text())['sessions'], list)

    def test_malformed_histories_are_conservative(self):
        for sessions in (None, {}, [None], [{'packages': []}], [{'packages': {'pkg': False}}], [{'files': [None]}]):
            with self.subTest(sessions=sessions):
                data = {'schema_version': LOG_SCHEMA_VERSION, 'sessions': sessions}
                original = json.dumps(data)
                self.path.write_text(original)
                log = AuditLog(str(self.path))
                self.assertEqual(log.get_packages_installed_by_us(), [])
                self.assertEqual(self.path.read_text(), original)

    def record(self, log, preexisting, action, status):
        log.start_session(action, self.env)
        log.record_package('pkg', preexisting, action, status)
        log.complete_session()

    def test_only_explicit_new_success_grants_ownership(self):
        for preexisting, action, status in ((False, 'install', 'failed'), (False, 'skip', 'skipped'), (True, 'install', 'ok'), ('false', 'install', 'ok'), (0, 'install', 'ok'), (None, 'install', 'ok')):
            with self.subTest(preexisting=preexisting, action=action, status=status):
                if self.path.exists():
                    self.path.unlink()
                log = AuditLog(str(self.path))
                self.record(log, preexisting, action, status)
                self.assertEqual(log.get_packages_installed_by_us(), [])

    def test_successful_uninstall_releases_and_reinstall_reacquires_ownership(self):
        log = AuditLog(str(self.path))
        self.record(log, False, 'install', 'ok')
        self.assertEqual(log.get_packages_installed_by_us(), ['pkg'])
        self.record(log, True, 'skip', 'skipped')
        self.assertEqual(log.get_packages_installed_by_us(), ['pkg'])
        self.record(log, False, 'uninstall', 'ok')
        self.assertEqual(log.get_packages_installed_by_us(), [])
        self.record(log, False, 'install', 'ok')
        self.assertEqual(log.get_packages_installed_by_us(), ['pkg'])
        self.assertEqual(AuditLog(str(self.path)).get_packages_installed_by_us(), ['pkg'])


if __name__ == '__main__':
    unittest.main()
