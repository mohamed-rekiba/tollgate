"""Locked tests for the gate proof of /tollgate:init. Each import sits inside its test."""

import unittest


class Proof(unittest.TestCase):
    def test_c1_returns_ok(self):
        from lab.proof import tollgate_proof
        self.assertEqual(tollgate_proof(), "ok")

    def test_c2_takes_no_arguments(self):
        from lab.proof import tollgate_proof
        self.assertEqual(tollgate_proof.__code__.co_argcount, 0)
