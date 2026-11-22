"""Tests for the state folder and for signing records."""

import os
import tempfile
import unittest
from pathlib import Path

from gate import sign, state


class SignTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["TOLLGATE_STATE"] = str(Path(self.tmp.name, "state"))
        os.environ["TOLLGATE_KEYS"] = str(Path(self.tmp.name, "keys"))
        self.pub = sign.ensure_key()

    def tearDown(self):
        os.environ.pop("TOLLGATE_STATE")
        os.environ.pop("TOLLGATE_KEYS")
        self.tmp.cleanup()

    def test_a_signed_record_reads_back(self):
        p = state.path("/some/project", "passes", "abc.json")
        sign.write(p, {"commit": "abc", "score": 80}, "tollgate-pass")
        self.assertEqual(sign.read(p, "tollgate-pass", [self.pub])["score"], 80)

    def test_a_changed_record_does_not_verify(self):
        p = state.path("/some/project", "passes", "abc.json")
        sign.write(p, {"commit": "abc", "score": 60}, "tollgate-pass")
        p.write_bytes(p.read_bytes().replace(b"60", b"90"))
        with self.assertRaises(sign.SignError):
            sign.read(p, "tollgate-pass", [self.pub])

    def test_a_signature_does_not_cross_namespaces(self):
        p = state.path("/some/project", "passes", "abc.json")
        sign.write(p, {"commit": "abc"}, "tollgate-pass")
        with self.assertRaises(sign.SignError):
            sign.read(p, "tollgate-approval", [self.pub])

    def test_a_key_outside_signers_does_not_verify(self):
        p = state.path("/some/project", "locks", "T1.json")
        sign.write(p, {"ticket": "T1"}, "tollgate-lock")
        with self.assertRaises(sign.SignError):
            sign.read(p, "tollgate-lock", [])

    def test_two_projects_get_two_folders(self):
        self.assertNotEqual(state.state_dir("/a/app"), state.state_dir("/b/app"))


if __name__ == "__main__":
    unittest.main()
