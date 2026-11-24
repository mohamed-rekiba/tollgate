"""Tests for the records and the machine secret in gate/state.py."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import state


class RecordTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_a_record_reads_back_and_is_plain_json(self):
        path = self.tmp / "r.json"
        state.write_record(path, {"b": 1, "a": 2})
        self.assertEqual(state.read_record(path), {"a": 2, "b": 1})
        self.assertEqual(path.read_bytes(), state.dumps({"a": 2, "b": 1}))
        self.assertFalse((self.tmp / "r.json.sig").exists())

    def test_a_missing_record_says_so(self):
        with self.assertRaisesRegex(state.RecordError, "is missing"):
            state.read_record(self.tmp / "none.json")

    def test_text_that_is_not_a_record_says_so(self):
        path = self.tmp / "r.json"
        for bad in (b"not json", b"[1]", b'"text"'):
            path.write_bytes(bad)
            with self.subTest(bad=bad), self.assertRaisesRegex(state.RecordError,
                                                               "is not a record"):
                state.read_record(path)


class MachineSecretTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(os.environ, {"TOLLGATE_KEYS": f"{tmp.name}/keys"})
        env.start()
        self.addCleanup(env.stop)

    def test_the_secret_is_made_once_and_kept(self):
        first = state.machine_secret()
        self.assertEqual(len(first), 32)
        self.assertEqual(state.machine_secret(), first)

    def test_only_you_can_read_the_secret(self):
        state.machine_secret()
        folder = state.key_dir()
        self.assertEqual(stat.S_IMODE((folder / "secret").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
