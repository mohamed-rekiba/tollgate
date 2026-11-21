"""Tests for the manifest command line: print what a freeze tag locked."""

import contextlib
import io
import unittest

from action import junit, manifest, tickets
from tests.helpers import TICKET, Repo

FILES = {"tests/b.py": "fp-b", "a/ticket.md": "fp-a", "tests/a.py": "fp-a2"}
TESTS = ["t.b::test_c2_x", "t.a::test_c1_y", "t.a::test_c3_z"]
MANIFEST = {"ticket": "T-9", "commit": "abc123", "files": FILES, "tests": TESTS}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = manifest.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ManifestCliTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write("x.txt", "x")
        self.repo.commit()
        self.r = str(self.repo.path)

    def tag_manifest(self):
        self.repo.tag("freeze-1", "Freeze of T-9\n\n" + manifest.dumps(MANIFEST))

    def test_c1_prints_ticket_then_commit(self):
        self.tag_manifest()
        code, out, _ = run("--repo", self.r, "--tag", "freeze-1")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "ticket: T-9")
        self.assertEqual(lines[1], "commit: abc123")

    def test_c2_prints_files_sorted_then_tests(self):
        self.tag_manifest()
        _, out, _ = run("--repo", self.r, "--tag", "freeze-1")
        self.assertEqual(out.splitlines()[2:], [
            "file: a/ticket.md", "file: tests/a.py", "file: tests/b.py",
            "test: t.b::test_c2_x", "test: t.a::test_c1_y", "test: t.a::test_c3_z"])

    def test_c3_missing_tag_fails_on_stderr(self):
        self.repo.tag("other", "no manifest here")
        code, out, err = run("--repo", self.r, "--tag", "nope")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_c4_tag_without_manifest_fails_on_stderr(self):
        self.repo.tag("plain", "just words")
        code, out, err = run("--repo", self.r, "--tag", "plain")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_c5_keeps_build_changed_dumps_loads(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(manifest.ticket_path("T-1"), TICKET)
        repo.write("tests/test_t1.py", "# tests\n")
        commit = repo.commit()
        results = {
            f"tests.test_t1::{n}": junit.TestResult(f"tests.test_t1::{n}", s, "")
            for n, s in [("test_c1_retries", "failed"), ("test_c2_sent_once", "passed"),
                         ("test_c3_wait_logged", "failed")]}
        m = manifest.build(str(repo.path), commit, tickets.parse(TICKET), results)
        self.assertEqual(m["commit"], commit)
        self.assertEqual(manifest.loads("Freeze\n\n" + manifest.dumps(m)), m)
        self.assertEqual(manifest.changed(m, str(repo.path), commit), [])
        repo.write("tests/test_t1.py", "# edited\n")
        edited = repo.commit()
        self.assertEqual(manifest.changed(m, str(repo.path), edited), ["tests/test_t1.py"])


if __name__ == "__main__":
    unittest.main()
