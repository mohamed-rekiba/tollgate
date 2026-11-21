"""Tests for python3 -m action.manifest."""

import contextlib
import io
import unittest

from action import manifest as mf
from tests.helpers import Repo


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mf.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ManifestCliTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write("a.txt", "a\n")
        self.repo.commit()

    def test_prints_lines(self):
        m = {"ticket": "T-1", "commit": "abc123",
             "files": {"tests/test_b.py": "sha256:1", ".tollgate/tickets/T-1/ticket.md": "sha256:2"},
             "tests": ["tests.test_b::test_c1_x", "tests.test_b::test_c2_y"]}
        self.repo.tag("freeze-1", f"Freeze 1\n\n{mf.dumps(m)}\n")
        code, out, _ = run("--repo", str(self.repo.path), "--tag", "freeze-1")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "T-1", "abc123", ".tollgate/tickets/T-1/ticket.md", "tests/test_b.py",
            "tests.test_b::test_c1_x", "tests.test_b::test_c2_y"])

    def test_missing_tag(self):
        code, out, err = run("--repo", str(self.repo.path), "--tag", "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no tag", err)

    def test_tag_without_manifest(self):
        self.repo.tag("plain", "just words")
        code, _, err = run("--repo", str(self.repo.path), "--tag", "plain")
        self.assertEqual(code, 1)
        self.assertIn("no manifest", err)


if __name__ == "__main__":
    unittest.main()
