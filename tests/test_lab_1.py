"""Locked tests for the lab ticket lab-1. The import sits inside each test, so a
missing module fails the test instead of breaking collection."""

import unittest


class LabOne(unittest.TestCase):
    def test_c1_shout(self):
        from lab.shout import shout
        self.assertEqual(shout("ann"), "ANN")

    def test_c2_matches_kept(self):
        from action.paths import matches
        self.assertTrue(matches("a/b.py", ["a/**"]))
