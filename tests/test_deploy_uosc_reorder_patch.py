"""Spec 005: the deployer applies the uosc playlist-reorder patch.

The uosc pin lives here too (plan Test Strategy "Registry").
"""

import unittest

from deploy import registry


class RegistryPinTests(unittest.TestCase):
    def test_uosc_is_pinned_to_the_patched_release(self):
        (uosc,) = [entry for entry in registry.SCRIPTS if entry["name"] == "uosc"]
        self.assertEqual("5.13.0", uosc["source"]["pin"])


if __name__ == "__main__":
    unittest.main()
