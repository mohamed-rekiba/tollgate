"""Tests for retro --print."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from driver import retro


class RetroPrintTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.p = tmp.name
        logs = Path(self.p, ".tollgate/logs")
        logs.mkdir(parents=True)
        events = [{"event": "attempt_passed", "ticket": "t-a", "task": "demo", "attempt": 1}]
        (logs / "t-a.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    def run_main(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = retro.main(["--project", self.p, "--task", "demo", *extra])
        return code, out.getvalue()

    def lesson(self):
        return Path(self.p, ".tollgate/lessons/demo.md")

    def test_without_print_only_the_path(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), str(self.lesson()))
        self.assertTrue(self.lesson().exists())

    def test_print_shows_the_numbers_table_and_still_writes_the_file(self):
        code, out = self.run_main("--print")
        self.assertEqual(code, 0)
        self.assertIn("| Number | Value |", out)
        self.assertIn("| tickets | 1 |", out)
        self.assertIn("| first attempt pass pct | 100 |", out)
        self.assertNotIn("Candidates", out)
        self.assertIn(str(self.lesson()), out)
        self.assertIn("| tickets | 1 |", self.lesson().read_text())

    def test_printed_table_matches_the_file(self):
        _, out = self.run_main("--print")
        table = [ln for ln in out.splitlines() if ln.startswith("|")]
        self.assertTrue(all(ln in self.lesson().read_text() for ln in table))


if __name__ == "__main__":
    unittest.main()
