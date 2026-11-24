"""The checks and the tests give the same result whatever the machine's git settings are."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_check_writing import Repo as WritingRepo
from tests.test_check_writing import sh


class MnemonicPrefixTest(unittest.TestCase):
    """diff.mnemonicPrefix prints i/ and w/, not b/, for a diff against the index."""

    def test_the_writing_check_still_finds_filler_in_the_staged_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = WritingRepo(Path(tmp))
            sh(repo.root, "git", "config", "diff.mnemonicPrefix", "true")
            repo.write("docs/guide.md", "We leverage the gate.\n")
            sh(repo.root, "git", "add", "-A")
            code, out = repo.check(staged=True)
            self.assertEqual(code, 1, out)
            self.assertIn("docs/guide.md:1", out)


class SigningTest(unittest.TestCase):
    def test_a_commit_in_a_test_repository_is_not_signed(self):
        # tests/__init__.py turns signing off, so a global commit.gpgsign=true cannot fail a test.
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            for key in ("commit.gpgsign", "tag.gpgsign"):
                got = subprocess.run(["git", "-C", tmp, "config", "--get", key],
                                     capture_output=True, text=True, check=False).stdout.strip()
                self.assertEqual(got, "false", key)


if __name__ == "__main__":
    unittest.main()
