import unittest

from deploy.deployer import _process_conditionals


class TestConditionals(unittest.TestCase):
    def test_blocks_are_processed_independently(self):
        content = """start
{{#if FIRST}}
first
{{/if}}
middle
{{#if SECOND}}
second
{{/if}}
{{#if THIRD}}
third
{{/if}}
end
"""
        result = _process_conditionals(content, {
            "FIRST": True,
            "SECOND": False,
            "THIRD": True,
        })
        self.assertIn("first", result)
        self.assertIn("third", result)
        self.assertNotIn("second", result)
        self.assertNotIn("{{#if", result)
        self.assertNotIn("{{/if}}", result)


if __name__ == "__main__":
    unittest.main()
