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


CODE = ("import os, tests; "
        "print(sorted(k for k in os.environ if k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE')))")


class HookEnvironmentTest(unittest.TestCase):
    """git sets GIT_DIR for a hook that runs from a linked worktree."""

    def test_the_tests_start_without_the_git_location_variables(self):
        import os
        import sys
        env = dict(os.environ, GIT_DIR="/nowhere", GIT_WORK_TREE="/nowhere",
                   GIT_INDEX_FILE="/nowhere/index")
        root = str(Path(__file__).resolve().parent.parent)
        done = subprocess.run(
            [sys.executable, "-c", CODE],
            cwd=root, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(done.stdout.strip(), "[]", done.stderr)

    def test_a_commit_in_a_temporary_repository_stays_in_it_when_git_dir_is_set(self):
        import os
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp, "outer")
            inner = Path(tmp, "inner")
            for d in (outer, inner):
                d.mkdir()
                subprocess.run(["git", "init", "-q", str(d)], check=True)
            env = dict(os.environ, GIT_DIR=str(outer / ".git"))
            code = ("import subprocess, tests; "
                    f"subprocess.run(['git', '-C', {str(inner)!r}, 'commit', '-q', '--allow-empty',"
                    " '-m', 'x', '--author=a <a@b.c>'], check=True, env={**__import__('os').environ,"
                    " 'GIT_COMMITTER_NAME': 'a', 'GIT_COMMITTER_EMAIL': 'a@b.c'})")
            root = str(Path(__file__).resolve().parent.parent)
            subprocess.run([sys.executable, "-c", code], cwd=root, env=env, check=True)
            count = {d.name: subprocess.run(["git", "-C", str(d), "rev-list", "--all", "--count"],
                                            capture_output=True, text=True, check=False).stdout.strip()
                     for d in (outer, inner)}
            self.assertEqual(count, {"outer": "0", "inner": "1"})
