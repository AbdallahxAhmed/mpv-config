import os
import tempfile
import unittest

from deploy.audit_log import AuditLog
from deploy.detector import Environment


class TestAuditLogOwnership(unittest.TestCase):
    def test_failed_install_does_not_claim_ownership(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(os.path.join(tmpdir, ".audit-log.json"))
            env = Environment(os="linux", platform_key="ubuntu")
            log.start_session("install", env)
            log.record_package("ffsubsync", False, "install", "failed", "network")
            log.complete_session("failed")
            self.assertEqual(log.get_pre_existing_packages().get("ffsubsync"), True)

    def test_successful_uninstall_relinquishes_ownership(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(os.path.join(tmpdir, ".audit-log.json"))
            env = Environment(os="linux", platform_key="ubuntu")
            log.start_session("install", env)
            log.record_package("ffsubsync", False, "install", "ok", "installed")
            log.complete_session("completed")
            self.assertIn("ffsubsync", log.get_packages_installed_by_us())

            log.start_session("uninstall", env)
            log.record_package("ffsubsync", False, "uninstall", "ok", "removed")
            log.complete_session("completed")
            self.assertNotIn("ffsubsync", log.get_packages_installed_by_us())


if __name__ == "__main__":
    unittest.main()
